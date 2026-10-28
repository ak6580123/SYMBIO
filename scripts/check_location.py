"""Location correctness battery - run against a live API + app.

Answers the one question this pass is about: does Symbio use the location the user
gave it, or does it quietly fall back to Chennai? Each check prints what it found and
the script exits non-zero if any invariant is broken, so it can sit next to the test
suite and be re-run after any restart.

    python3 scripts/check_location.py [--api http://127.0.0.1:8000] [--app http://127.0.0.1:3000]
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.parse
import urllib.request

BASE = {
    "source_type": "industry",
    "material_description": (
        "Pulverised coal fly ash from the electrostatic precipitator, dry fine grey powder."
    ),
    "quantity": 5,
    "unit": "tonnes",
    "frequency": "monthly",
    "composition": "SiO2: 55%",
}
CENTROID = (13.0827, 80.2707)
failures: list[str] = []


def call(base: str, path: str, payload=None, params=None):
    url = base + path + (("?" + urllib.parse.urlencode(params)) if params else "")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {"raw": e.read().decode()[:200]}


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        failures.append(label)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--app", default="http://127.0.0.1:3000")
    args = ap.parse_args()

    print("1. Chennai (the seeded workflow must be untouched)")
    code, a = call(args.app, "/api/analyze", {**BASE, "location": "Manali, Chennai"})
    src, top = a["analysis"]["source"], a["matches"][0]
    check("analysis accepted", code == 200, f"HTTP {code}")
    check("location is the typed text", src["location"] == "Manali, Chennai", src["location"])
    check(
        "resolved to the seeded point",
        (src["latitude"], src["longitude"]) == (13.1667, 80.2667),
        f"{src['latitude']}, {src['longitude']}",
    )
    check("real distance computed", isinstance(top["distance_km"], float), f"{top['distance_km']} km")
    check("top match unchanged", top["overall_score"] == 77.5, f"{top['overall_score']}")

    print("2. Coimbatore (must stay Coimbatore)")
    code, b = call(args.app, "/api/analyze", {**BASE, "location": "Coimbatore, Tamil Nadu"})
    bsrc, btop = b["analysis"]["source"], b["matches"][0]
    check("analysis accepted", code == 200, f"HTTP {code}")
    check("text preserved", bsrc["location"] == "Coimbatore, Tamil Nadu", bsrc["location"])
    check("no coordinates invented", bsrc["latitude"] is None and bsrc["longitude"] is None)
    check("no distance fabricated", btop["distance_km"] is None, f"{btop['distance_km']}")
    check("geography scored neutrally", btop["breakdown"]["location"] == 0.5)
    check("not the Chennai centroid", (bsrc["latitude"], bsrc["longitude"]) != CENTROID)

    print("3. Bengaluru (must stay Bengaluru, no haulage claim)")
    code, c = call(args.app, "/api/analyze", {**BASE, "location": "Bengaluru, Karnataka"})
    cid = c["analysis"]["id"]
    csrc = c["analysis"]["source"]
    check("text preserved", csrc["location"] == "Bengaluru, Karnataka", csrc["location"])
    code, det = call(args.api, f"/api/matches/{cid}/{c['matches'][0]['recipient']['id']}")
    check("no freight estimate", det["transport"] is None, f"{det['transport']}")
    code, mp = call(args.api, "/api/map", params={"analysis_id": cid})
    sources = [n for n in mp["nodes"] if n["kind"] == "source"]
    check("map plots no source pin", len(sources) == 0, f"{len(sources)} source nodes")
    check("map links nothing", len(mp["links"]) == 0, f"{len(mp['links'])} links")
    check("partners still shown", len(mp["nodes"]) > 0, f"{len(mp['nodes'])} partner nodes")

    print("4. Empty location (refuse, never substitute)")
    for label, payload in (
        ("empty string", {**BASE, "location": ""}),
        ("whitespace", {**BASE, "location": "   "}),
        ("absent", {k: v for k, v in BASE.items() if k != "location"}),
    ):
        code, err = call(args.app, "/api/analyze", payload)
        blob = json.dumps(err)
        check(f"{label} -> 422", code == 422, f"HTTP {code}")
        check(f"{label} -> no Chennai in the answer", "Chennai" not in blob)
        check(f"{label} -> names the location field", "location" in blob.lower())

    print("5. Unknown location (text kept, nothing approximated)")
    code, k = call(args.app, "/api/analyze", {**BASE, "location": "Kodaikanal, Tamil Nadu"})
    ksrc = k["analysis"]["source"]
    check("analysis still runs", code == 200, f"HTTP {code}")
    check("text preserved", ksrc["location"] == "Kodaikanal, Tamil Nadu", ksrc["location"])
    check("coords stay unavailable", ksrc["latitude"] is None and ksrc["longitude"] is None)
    check("not the Chennai centroid", (ksrc["latitude"], ksrc["longitude"]) != CENTROID)

    print("6. Explicit coordinates (still honoured end to end)")
    code, e = call(
        args.app,
        "/api/analyze",
        {**BASE, "location": "Plot 14, SIDCO industrial estate", "latitude": 11.0168, "longitude": 76.9558},
    )
    esrc = e["analysis"]["source"]
    check("coordinates preserved exactly", (esrc["latitude"], esrc["longitude"]) == (11.0168, 76.9558))
    check("stated place kept", esrc["location"] == "Plot 14, SIDCO industrial estate", esrc["location"])
    check("distance now measurable", isinstance(e["matches"][0]["distance_km"], float), f"{e['matches'][0]['distance_km']} km")

    print("7. No placeholder geography anywhere in the visible UI")
    routes = ["/", "/analyze", "/dashboard", "/impact", "/knowledge-base", "/marketplace", "/matches", "/map"]
    code, listing = call(args.api, "/api/analyses")
    if listing.get("analyses"):
        aid = listing["analyses"][0]["id"]
        code, cards = call(args.api, "/api/matches", params={"analysis_id": aid})
        if cards.get("matches"):
            routes.append(f"/matches/{aid}:{cards['matches'][0]['recipient']['id']}")
    for route in routes:
        req = urllib.request.Request(args.app + route)
        with urllib.request.urlopen(req, timeout=60) as r:
            html, status = r.read().decode(), r.status
        # Script and style blocks are stripped first: Next.js carries its own
        # "$undefined" sentinels in the flight payload, and that is not our text.
        visible = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
        visible = re.sub(r"<[^>]+>", " ", visible)
        flags = [bad for bad in ("null km", "NaN", "[object Object]", "undefined", "Not found") if bad in visible]
        check(f"{route} renders clean", status == 200 and not flags, f"HTTP {status}{' ' + ','.join(flags) if flags else ''}")

    print()
    if failures:
        print(f"  {len(failures)} check(s) failed: " + "; ".join(failures))
        return 1
    print("  all location checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
