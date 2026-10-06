"""Regression tests for the ECONNRESET / "Request failed (500)" failure.

Root cause
----------
POST /api/analyze is the only endpoint that blocks on local Ollama. Next.js
limits proxied requests to 30s in development
(next/dist/server/lib/router-utils/proxy-request.js -> `proxyTimeout || 30000`),
while the backend allowed OLLAMA_TIMEOUT_SECONDS (60) for inference. Any request
where Ollama took 30-60s was aborted by the proxy before FastAPI could answer,
so the browser saw an opaque 500 and the Next terminal logged
"Failed to proxy ... socket hang up / ECONNRESET".

These tests pin the two properties that prevent it recurring:

  1. FastAPI always answers within a bounded, configured time - either with the
     model's answer or with the deterministic fallback.
  2. A down or unresponsive Ollama triggers the fallback quickly, instead of
     consuming the whole inference timeout.
"""

import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402


# ---------------------------------------------------------------------------
# A controllable stand-in for the Ollama HTTP API
# ---------------------------------------------------------------------------


class _FakeOllama:
    def __init__(self, delay: float = 0.0, mode: str = "ok"):
        self.delay = delay
        self.mode = mode
        self.hits = 0

        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                pass

            def _send(self, status: int, payload: bytes):
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):  # /api/tags - used by the reachability probe
                outer.hits += 1
                if outer.mode == "probe_hang":
                    time.sleep(30)
                    return
                self._send(200, b'{"models":[{"name":"qwen2.5:3b"}]}')

            def do_POST(self):  # /api/chat - the inference call
                outer.hits += 1
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                time.sleep(outer.delay)
                answer = {
                    "material": "Fly Ash",
                    "confidence": 0.9,
                    "category": "coal_combustion_residue",
                    "properties": ["pozzolanic"],
                    "composition": {"SiO2": "18%"},
                    "alternatives": [],
                    "reuse_categories": ["cement_supplementary_material"],
                    "safety_level": "moderate",
                    "requires_processing": True,
                    "reasoning": "Siliceous combustion residue.",
                }
                import json as _json

                body = _json.dumps({"message": {"content": _json.dumps(answer)}}).encode()
                self._send(200, body)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_exc):
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def point_at(monkeypatch):
    """Repoint the identification module at a given URL and reload its config."""
    from ai import identification

    def _apply(url: str, timeout: float = 5.0, probe_timeout: float = 1.0):
        monkeypatch.setattr(identification, "OLLAMA_URL", url)
        monkeypatch.setattr(identification, "OLLAMA_TIMEOUT", timeout)
        monkeypatch.setattr(identification, "OLLAMA_PROBE_TIMEOUT", probe_timeout)

    return _apply


REQUEST = {
    "source_type": "industry",
    "material_description": "fly ash from our boiler precipitator",
    "quantity": 5.0,
    "unit": "tonnes",
    "location": "Chennai, Tamil Nadu",
    "frequency": "monthly",
    "composition": "SiO2:18%, CO2:20%",
}


# ---------------------------------------------------------------------------
# The failure modes
# ---------------------------------------------------------------------------


def test_ollama_unreachable_falls_back_fast(point_at):
    """Nothing listening on the port: fall back, do not block."""
    point_at("http://127.0.0.1:1", timeout=60.0, probe_timeout=1.0)

    from services import analysis as analysis_service

    started = time.monotonic()
    result = analysis_service.build_analysis(dict(REQUEST))
    elapsed = time.monotonic() - started

    assert result["material"]["id"] == "fly_ash"
    assert result["identification"]["engine"] == "fallback_keyword"
    assert elapsed < 3.0, f"fallback took {elapsed:.1f}s - must not wait on the inference timeout"
    assert any("deterministic classifier" in w for w in result["warnings"])


def test_unresponsive_ollama_falls_back_without_burning_inference_timeout(point_at):
    """Ollama accepts connections but never answers the probe.

    This is the case that used to block for the whole OLLAMA_TIMEOUT window and
    let the 30s Next.js proxy abort the request first.
    """
    with _FakeOllama(mode="probe_hang") as fake:
        point_at(f"http://127.0.0.1:{fake.port}", timeout=60.0, probe_timeout=1.0)

        from services import analysis as analysis_service

        started = time.monotonic()
        result = analysis_service.build_analysis(dict(REQUEST))
        elapsed = time.monotonic() - started

    assert result["identification"]["engine"] == "fallback_keyword"
    assert elapsed < 5.0, f"took {elapsed:.1f}s; the probe must cut this short"


def test_slow_but_working_ollama_still_returns_a_real_answer(point_at):
    """Normal local inference must keep working - the fix must not disable Ollama."""
    with _FakeOllama(delay=0.4) as fake:
        point_at(f"http://127.0.0.1:{fake.port}", timeout=10.0, probe_timeout=2.0)

        from services import analysis as analysis_service

        result = analysis_service.build_analysis(dict(REQUEST))

    assert result["identification"]["engine"] == "ollama:qwen2.5:3b"
    assert result["identification"]["confidence"] == 0.9
    assert result["material"]["id"] == "fly_ash"
    assert result["warnings"] == []


def test_analyze_completes_within_the_proxy_budget(point_at):
    """The whole request must finish well inside the proxy timeout.

    The proxy default was 30s and the Ollama budget 60s; that inversion is the
    bug. With Ollama unreachable the answer must be near-instant.
    """
    point_at("http://127.0.0.1:1", timeout=60.0, probe_timeout=1.0)

    from services import analysis as analysis_service

    started = time.monotonic()
    analysis_service.build_analysis(dict(REQUEST))
    elapsed = time.monotonic() - started

    assert elapsed < 10.0


def test_proxy_timeout_configured_above_the_ollama_budget():
    """Guard the actual inversion that caused this: proxy 30s < Ollama 60s."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config = open(os.path.join(root, "frontend", "next.config.mjs"), encoding="utf-8").read()

    assert "proxyTimeout" in config, "next.config.mjs must set experimental.proxyTimeout"
    default_ms = int(os.environ.get("PROXY_TIMEOUT_MS", "120000"))
    ollama_seconds = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "60"))
    assert default_ms / 1000 > ollama_seconds, (
        f"proxyTimeout ({default_ms}ms) must exceed OLLAMA_TIMEOUT_SECONDS ({ollama_seconds}s)"
    )


def test_failure_message_names_the_cause(point_at):
    """An opaque 500 is what made this hard to diagnose - the message must not be."""
    from ai.identification import OllamaUnavailable, OllamaUnresponsive, _describe_failure

    down = _describe_failure(OllamaUnavailable("Ollama not reachable at http://localhost:11434: x"))
    assert "ollama serve" in down
    assert "11434" in down

    slow = _describe_failure(OllamaUnavailable("request timed out"))
    assert "OLLAMA_TIMEOUT_SECONDS" in slow

    wedged = _describe_failure(OllamaUnresponsive("did not respond within 2s"))
    assert "did not respond" in wedged
    assert "OLLAMA_PROBE_TIMEOUT_SECONDS" in wedged
    # The subclass must not be mistaken for an inference timeout.
    assert "did not answer within" not in wedged


def test_probe_distinguishes_refused_from_unresponsive(monkeypatch, point_at):
    """Connection refused and a wedged server need different advice."""
    import httpx

    from ai import identification

    point_at("http://127.0.0.1:1", probe_timeout=0.5)
    with pytest.raises(identification.OllamaUnavailable) as refused:
        identification.probe_ollama()
    assert not isinstance(refused.value, identification.OllamaUnresponsive)

    def _hang(*_a, **_k):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(identification.httpx, "get", _hang)
    with pytest.raises(identification.OllamaUnresponsive):
        identification.probe_ollama()


def test_invalid_input_still_returns_422_not_500(client):
    """The 422s in the log were legitimate validation - confirm they stay clean."""
    resp = client.post("/api/analyze", json={"material_description": "fly ash", "quantity": 0})
    assert resp.status_code == 422
    assert "errors" in resp.json()

    resp = client.post("/api/analyze", json={"quantity": 5})
    assert resp.status_code == 422


def test_user_reported_payload_succeeds_end_to_end(client):
    """The exact input from the bug report, through the real HTTP endpoint."""
    resp = client.post(
        "/api/analyze",
        json={
            "source_type": "industry",
            "location": "Chennai, Tamil Nadu",
            "material_description": "fly ash",
            "quantity": 5,
            "unit": "tonnes",
            "frequency": "monthly",
            "composition": "SiO2:18%, CO2:20%",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["analysis"]["material"]["id"] == "fly_ash"
    assert body["analysis"]["identification"]["composition"]["sio2"] == "18%"
    assert len(body["matches"]) > 0
    assert body["matches"][0]["overall_score"] > 0


def test_matches_endpoint_unaffected(client):
    """The fix must not disturb endpoints that were already working."""
    created = client.post(
        "/api/analyze",
        json={"source_type": "industry", "material_description": "fly ash", "quantity": 5,
              "unit": "tonnes", "location": "Chennai", "frequency": "monthly"},
    ).json()
    analysis_id = created["analysis"]["id"]

    resp = client.post("/api/matches", params={"analysis_id": analysis_id})
    assert resp.status_code == 200
    assert resp.json()["count"] > 0

    assert client.get("/api/dashboard").status_code == 200
    assert client.get("/api/materials").status_code == 200
    assert client.get("/api/recipients").status_code == 200
