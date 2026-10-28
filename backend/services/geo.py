"""The one external integration: real geography, real routes (§8).

Two calls, both to free OpenStreetMap-based services, and neither is load-bearing:

    geocode(text)      → coordinates for a place, or an honest "not found"
    route(from, to)    → road distance and drive time, or "unavailable"

Everything else in Symbio behaves the same with them switched off, which is the point of
putting them behind one module: the deterministic engine keeps scoring on the values it
already has, the safety layer keeps refusing what it refuses, and the number this module
supplements is *displayed alongside* the one the engine measured - never quietly swapped
into it.

The rules this file exists to keep:

* **No invented geography.** A place the provider cannot find stays unplaced. There is no
  centroid, no capital city, no "closest match" - a fabricated coordinate would flow
  straight into a distance and then into a recommendation.
* **A failure is a result.** Timeouts, 429s, malformed bodies and an unreachable
  provider each come back as a `GeoResult` with a reader-facing state, and the caller
  decides what to say. Nothing raises into a request path.
* **Be a good guest.** One request at a time per provider with a courtesy gap (Nominatim's
  usage policy asks for 1/s), answers cached in `geo_cache` for `GEO_CACHE_HOURS`, and a
  circuit breaker: after a few consecutive failures the provider is set aside for a
  minute rather than retried on every page view.
* **Stay out of the response.** Provider names appear in provenance; URLs, keys, status
  codes and raw payloads do not leave this module.

Configuration (all optional, no key required for either default):

    GEOCODING_PROVIDER = nominatim | off      NOMINATIM_URL, GEO_CONTACT
    ROUTING_PROVIDER   = osrm | ors | off     OSRM_BASE_URL, ORS_API_KEY
    GEO_TIMEOUT_SECONDS = 4                   GEO_CACHE_HOURS = 720
    GEO_MIN_INTERVAL_MS = 1100                GEO_FAILURE_COOLDOWN_SECONDS = 60
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

GEOCODE_LABEL = "External geocoding (OpenStreetMap)"
ROUTE_LABEL = "External routing (OpenStreetMap)"

DEFAULTS = {
    "GEOCODING_PROVIDER": "nominatim",
    "ROUTING_PROVIDER": "osrm",
    "NOMINATIM_URL": "https://nominatim.openstreetmap.org",
    "OSRM_BASE_URL": "https://router.project-osrm.org",
    "ORS_BASE_URL": "https://api.openrouteservice.org",
    "GEO_TIMEOUT_SECONDS": "4",
    "GEO_CACHE_HOURS": "720",
    "GEO_MIN_INTERVAL_MS": "1100",
    "ROUTE_MIN_INTERVAL_MS": "250",
    "GEO_FAILURE_COOLDOWN_SECONDS": "60",
}

_states: dict[str, "ProviderState"] = {}
_MEMO: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

# Tests replace this with an httpx.MockTransport. Nothing else in the codebase
# constructs a client, so there is exactly one place a network call happens.
HTTP_TRANSPORT: Any = None


def _setting(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return DEFAULTS[name]
    return value.strip()


def _number(name: str, cast: Callable[[str], Any]) -> Any:
    try:
        return cast(_setting(name))
    except ValueError:
        return cast(DEFAULTS[name])


@dataclass
class ProviderState:
    """Throttle + circuit breaker, per provider name."""

    name: str
    min_interval: float
    cooldown: float
    last_call: float = 0.0
    failures: int = 0
    until: float = 0.0
    calls: int = 0
    hits: int = 0

    def ready(self) -> bool:
        return time.monotonic() >= self.until

    def wait_turn(self) -> None:
        gap = self.min_interval - (time.monotonic() - self.last_call)
        if gap > 0:
            time.sleep(min(gap, self.min_interval))
        self.last_call = time.monotonic()

    def succeeded(self) -> None:
        self.failures = 0
        self.until = 0.0

    def failed(self) -> None:
        self.failures += 1
        self.calls += 1
        if self.failures >= 3:
            self.until = time.monotonic() + self.cooldown
            self.failures = 0


def _state(name: str) -> ProviderState:
    with _lock:
        state = _states.get(name)
        if state is None:
            state = ProviderState(
                name=name,
                min_interval=(
        _number("ROUTE_MIN_INTERVAL_MS", float) if name.startswith("route:") else _number("GEO_MIN_INTERVAL_MS", float)
    ) / 1000.0,
                cooldown=_number("GEO_FAILURE_COOLDOWN_SECONDS", float),
            )
            _states[name] = state
        return state


@dataclass(frozen=True)
class GeoResult:
    """The one type every geography call returns.

    `ok` is the only boolean a caller should branch on. `payload` carries the numbers
    when there are any; `reason` says which kind of unavailability this is, for the log
    and for `/api/status`, and is never shown raw to a user.
    """

    ok: bool
    payload: dict[str, Any]
    reason: str = ""
    provider: str = ""
    source: str = ""

    def __bool__(self) -> bool:
        return self.ok

    def public(self) -> dict[str, Any]:
        """What may go into an API response. The provider's name and when it was asked;
        never the reason string, the status code or the URL (§9)."""
        out = {key: value for key, value in self.payload.items() if key != "provider_distance_metres"}
        out["source"] = self.source or ("external" if self.ok else "unavailable")
        return out


_UNAVAILABLE = GeoResult(False, {}, reason="unavailable")


def geocoding_provider() -> str:
    return _setting("GEOCODING_PROVIDER").lower()


def routing_provider() -> str:
    if _setting("ROUTING_PROVIDER").lower() == "ors" and not os.environ.get("ORS_API_KEY"):
        # Configured for a paid provider without a key is a misconfiguration, and
        # silently driving to the demo server instead would be a surprise on the bill
        # of whoever set the variable. Say so and do nothing.
        return "unconfigured"
    return _setting("ROUTING_PROVIDER").lower()


def external_geocoding_used() -> bool:
    """Asked by the profile path so a resolved place can say who resolved it."""
    return geocoding_provider() != "off"


def enabled() -> bool:
    return geocoding_provider() != "off" or routing_provider() != "off"


def status() -> dict[str, Any]:
    """Reported by `/api/status`. Names and counts, never URLs or keys."""
    routing = routing_provider()
    return {
        "geocoding": {
            "provider": "off" if geocoding_provider() == "off" else "nominatim",
            "label": GEOCODE_LABEL,
            "state": _provider_state("geocode"),
        },
        "routing": {
            "provider": routing,
            "label": ROUTE_LABEL if routing == "osrm" else ("OpenRouteService" if routing == "ors" else "off"),
            "state": _provider_state("route"),
        },
        "cache_hours": _number("GEO_CACHE_HOURS", float),
        "note": (
            "Distances and durations from an external provider are shown as external data with the time they "
            "were fetched. Where a provider is switched off, unreachable or has nothing to say, Symbio keeps "
            "the location text and reports the measurement as unavailable."
        ),
    }


def _provider_state(kind: str) -> str:
    provider = geocoding_provider() if kind == "geocode" else routing_provider()
    if provider in ("off", "unconfigured"):
        return "off"
    state = _states.get(f"{kind}:{provider}")
    if state is None:
        return "ready"
    return "cooling down" if not state.ready() else "ready"


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _get(url: str, params: dict[str, Any], *, headers: dict[str, str] | None = None) -> tuple[int | None, Any, str]:
    """Return `(status_code, parsed_json_or_None, error)`. Never raises."""
    import httpx  # noqa: PLC0415 - the one network import in the backend

    timeout = _number("GEO_TIMEOUT_SECONDS", float)
    try:
        client = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=min(timeout, 3.0)),
            headers={"User-Agent": _user_agent(), **({"Accept": "application/json"} if headers is None else headers)},
            transport=HTTP_TRANSPORT,
            follow_redirects=True,
        )
    except Exception as exc:
        return None, None, exc.__class__.__name__
    try:
        with client:
            response = client.get(url, params=params)
    except httpx.TimeoutException:
        return None, None, "timeout"
    except httpx.HTTPError as exc:
        return None, None, exc.__class__.__name__
    except Exception:
        return None, None, "unreachable"
    if response.status_code == 429:
        return 429, None, "rate limited"
    if response.status_code >= 400:
        return response.status_code, None, f"http {response.status_code}"
    try:
        return response.status_code, response.json(), ""
    except (ValueError, json.JSONDecodeError):
        return response.status_code, None, "invalid response"


def _user_agent() -> str:
    contact = (os.environ.get("GEO_CONTACT") or "").strip()
    # Nominatim's usage policy asks for a reachable contact. Development runs without
    # one are allowed, and the note in /api/status explains why a deployment must set it.
    return f"symbio/1.0 (+{contact})" if contact else "symbio/1.0 (local development; set GEO_CONTACT)"


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------


def _memo() -> dict[str, dict[str, Any]]:
    """The process tier of the cache.

    Two tiers on purpose: an analysis page asks the same handful of geography questions
    repeatedly, and none of them should cost a database round trip each time; the
    database tier is what makes the answers - and the "we asked, there was nothing"
    answers - survive a restart.
    """
    return _MEMO


def _cache_get(kind: str, query: str) -> dict[str, Any] | None:
    key = f"{kind}:{query.strip().lower()}"
    memo = _memo()
    entry = memo.get(key)
    if entry and entry["expires"] > time.monotonic():
        return entry["value"]
    db = _database()
    if db is not None:
        try:
            row = _repo().cache_lookup(db, kind, query)
        except Exception:
            row = None
        if row and not row.get("expired"):
            memo[key] = {"value": row, "expires": time.monotonic() + 60.0}
            return row
    return entry["value"] if entry else None


def _cache_put(kind: str, query: str, provider: str, payload: dict[str, Any], resolved: bool) -> None:
    key = f"{kind}:{query.strip().lower()}"
    _memo()[key] = {"value": {"payload": payload, "resolved": resolved, "provider": provider}, "expires": time.monotonic() + 60.0}
    db = _database()
    if db is None:
        return
    try:
        _repo().cache_store(
            db,
            kind=kind,
            query_text=query,
            provider=provider,
            payload=payload,
            resolved=resolved,
            ttl_hours=_number("GEO_CACHE_HOURS", float),
        )
    except Exception:
        # A cache write is never worth failing a request over.
        pass


def _database():
    from db import get as get_db  # noqa: PLC0415

    try:
        database = get_db()
    except Exception:
        return None
    return database if database.settings.configured else None


def _repo():
    from db import repositories  # noqa: PLC0415

    return repositories


# ---------------------------------------------------------------------------
# geocoding
# ---------------------------------------------------------------------------


def geocode(place: str) -> GeoResult:
    """Coordinates for a place name, or a refusal to guess one."""
    text = (place or "").strip()
    if not text or geocoding_provider() == "off":
        return _UNAVAILABLE
    provider = geocoding_provider()
    cached = _cache_get("geocode", text)
    if cached is not None:
        state = _state(f"geocode:{provider}")
        state.hits += 1
        payload = cached.get("payload") if isinstance(cached, dict) else {}
        resolved = bool(cached.get("resolved")) if isinstance(cached, dict) else False
        return GeoResult(resolved, dict(payload or {}), reason="" if resolved else "not found", provider=provider, source="external geocoding (cached)")

    state = _state(f"geocode:{provider}")
    if not state.ready():
        return GeoResult(False, {}, reason="cooling down", provider=provider, source="external geocoding")

    code, body, error = _call_geocode(provider, text)
    if code == 429 or error in ("rate limited",):
        state.failed()
        return GeoResult(False, {}, reason="rate limited", provider=provider, source="external geocoding")
    if error or not isinstance(body, list) or not body:
        state.failed() if error else state.succeeded()
        reason = error or "not found"
        if not error:
            # Remember the negative answer too, so an unplaceable town is not asked
            # about on every page view - and stays unplaceable either way.
            _cache_put("geocode", text, provider, {}, resolved=False)
        return GeoResult(False, {}, reason=reason, provider=provider, source="external geocoding")

    hit = body[0] if isinstance(body[0], dict) else {}
    try:
        latitude, longitude = float(hit["lat"]), float(hit["lon"])
    except (KeyError, TypeError, ValueError):
        state.failed()
        return GeoResult(False, {}, reason="invalid response", provider=provider, source="external geocoding")
    state.succeeded()
    payload = {
        "latitude": round(latitude, 6),
        "longitude": round(longitude, 6),
        "display_name": str(hit.get("display_name") or text)[:300],
        "place_type": str(hit.get("addresstype") or hit.get("type") or "")[:40],
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _cache_put("geocode", text, provider, payload, resolved=True)
    return GeoResult(True, payload, provider=provider, source="external geocoding")


def _geocode_params(text: str) -> dict[str, Any]:
    """Worldwide by default. `GEO_COUNTRY_CODES=in,sg` narrows it, because restricting
    the search to India would be its own quiet assumption about where a user is."""
    params: dict[str, Any] = {"q": text, "format": "jsonv2", "limit": 1, "addressdetails": 0}
    codes = (os.environ.get("GEO_COUNTRY_CODES") or "").strip()
    if codes:
        params["countrycodes"] = codes
    return params


def _call_geocode(provider: str, text: str) -> tuple[int | None, Any, str]:
    state = _state(f"geocode:{provider}")
    state.wait_turn()
    state.calls += 1
    if provider == "nominatim":
        base = _setting("NOMINATIM_URL").rstrip("/")
        return _get(
            f"{base}/search",
            _geocode_params(text),
        )
    return None, None, "unsupported provider"


# ---------------------------------------------------------------------------
# routing
# ---------------------------------------------------------------------------


def route(
    origin: tuple[float, float] | None,
    destination: tuple[float, float] | None,
    *,
    live: bool = True,
) -> GeoResult:
    """Road distance and drive time between two placed points.

    Takes coordinates, not place names: the caller already resolved them, and asking a
    router to geocode as a side effect is how a silent fallback gets smuggled back in.

    `live=False` answers from the cache and otherwise says nothing. A results list of
    fourteen cards must not become fourteen calls to a shared public router; the detail
    page for the route someone is actually reading is where the live call belongs.
    """
    provider = routing_provider()
    if provider in ("off", "unconfigured") or not origin or not destination:
        return GeoResult(False, {}, reason="unavailable" if provider == "off" else provider, provider=provider, source="external routing")

    origin_lat, origin_lng = origin
    dest_lat, dest_lng = destination
    cache_key = f"route|{round(origin_lat, 4)},{round(origin_lng, 4)}|{round(dest_lat, 4)},{round(dest_lng, 4)}"
    cached = _cache_get("route", cache_key)
    if cached is None and not live:
        return GeoResult(False, {}, reason="not fetched", provider=provider, source="external routing")
    if cached is not None:
        payload = dict(cached.get("payload") or {}) if isinstance(cached, dict) else {}
        return GeoResult(bool(payload), payload, provider=provider, source="external routing (cached)")

    state = _state(f"route:{provider}")
    if not state.ready():
        return GeoResult(False, {}, reason="cooling down", provider=provider, source="external routing")

    code, body, error = _call_route(provider, (origin_lat, origin_lng), (dest_lat, dest_lng))
    if code == 429 or error == "rate limited":
        state.failed()
        return GeoResult(False, {}, reason="rate limited", provider=provider, source="external routing")
    if error:
        state.failed()
        return GeoResult(False, {}, reason=error, provider=provider, source="external routing")
    payload = _parse_route(provider, body)
    if payload is None:
        state.failed()
        return GeoResult(False, {}, reason="invalid response", provider=provider, source="external routing")
    state.succeeded()
    payload["fetched_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _cache_put("route", cache_key, provider, payload, resolved=True)
    return GeoResult(True, payload, provider=provider, source="external routing")


def _call_route(provider: str, origin: tuple[float, float], destination: tuple[float, float]) -> tuple[int | None, Any, str]:
    state = _state(f"route:{provider}")
    state.wait_turn()
    state.calls += 1
    olat, olng = origin
    dlat, dlng = destination
    if provider == "osrm":
        base = _setting("OSRM_BASE_URL").rstrip("/")
        return _get(
            f"{base}/route/v1/driving/{olng:.6f},{olat:.6f};{dlng:.6f},{dlat:.6f}",
            {"overview": "false", "alternatives": "false", "steps": "false"},
        )
    if provider == "ors":
        base = _setting("ORS_BASE_URL").rstrip("/")
        import httpx  # noqa: PLC0415

        timeout = _number("GEO_TIMEOUT_SECONDS", float)
        try:
            with httpx.Client(timeout=timeout, transport=HTTP_TRANSPORT) as client:
                response = client.get(
                    f"{base}/v2/directions/driving-car",
                    params={
                        "start": f"{olng:.6f},{olat:.6f}",
                        "end": f"{dlng:.6f},{dlat:.6f}",
                    },
                    headers={"Authorization": os.environ.get("ORS_API_KEY", "")},
                )
        except httpx.TimeoutException:
            return None, None, "timeout"
        except httpx.HTTPError:
            return None, None, "unreachable"
        if response.status_code == 429:
            return 429, None, "rate limited"
        if response.status_code >= 400:
            return response.status_code, None, f"http {response.status_code}"
        try:
            return response.status_code, response.json(), ""
        except ValueError:
            return response.status_code, None, "invalid response"
    return None, None, "unsupported provider"


def _parse_route(provider: str, body: Any) -> dict[str, Any] | None:
    if not isinstance(body, dict):
        return None
    if provider == "osrm":
        if body.get("code") != "Ok":
            return None
        routes = body.get("routes") or []
        if not routes:
            return None
        first = routes[0]
        metres, seconds = float(first.get("distance") or 0), float(first.get("duration") or 0)
    else:
        routes = (body.get("routes") or [])
        if not routes:
            return None
        first = routes[0]
        metres, seconds = float(first.get("distance") or 0), float(first.get("duration") or 0)
    if metres <= 0:
        return None
    return {
        "route_distance_km": round(metres / 1000.0, 1),
        "route_duration_minutes": round(seconds / 60.0),
        "provider_distance_metres": int(metres),
    }


def reset_for_tests() -> None:
    """Drops the memo, the throttles and the breaker between tests."""
    global _MEMO
    with _lock:
        _states.clear()
        _MEMO = {}
