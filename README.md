# Symbio

**AI-powered circular-economy waste matchmaking.**

Symbio takes a waste stream from any source, works out what the material actually is, finds who could use it —
cement plants, brick works, recyclers, farms, packaging SMEs, neighbourhood programmes — ranks those opportunities
with an explainable score, and shows the resulting circular flow with its economic and environmental upside.

```
WASTE SOURCE → AI IDENTIFICATION → MATERIAL KNOWLEDGE BASE → POTENTIAL USERS
             → MATCHING ENGINE → RANKED OPPORTUNITIES → ECONOMIC + ENVIRONMENTAL IMPACT
```

> **A working product with a fictional world inside it.** Accounts, organisation profiles, published listings and
> saved analyses are real and persistent. Every company, price and emission factor in the *seeded network* is demo
> data, and is labelled as such in the UI. There is no payment integration and no regulatory compliance engine; the
> environmental figures are not independently verified; an organisation's status says `verified` only when the
> platform team has set it, which nothing in the product can do for itself. It is not described as production-ready —
> see [what is not production-grade](#what-is-not-production-grade).

---

## The one rule this codebase is built around

**The language model never determines a match score.**

| Stage | Who does it | What they are allowed to do |
|---|---|---|
| Identification | LLM (`qwen2.5:3b` via Ollama) | Read a messy description, name the material, give a confidence, suggest candidate reuse categories |
| Facts | Knowledge base | Properties, reuse routes, compatible sectors, safety level, price, emission factor |
| Safety | Rule engine | Refuse hazardous / unidentified streams for household, farm and artisan use |
| Scoring | Deterministic engine | Compute all six components and the weighted total |
| Pathways | Deterministic engine | Group its own ranked matches into routes — it may collapse them, never invent one |
| Correction | The user, checked against the KB | Pick a known material for one analysis; the knowledge base is not written to |
| What-if | Deterministic engine, again | Re-run the same weights and safety rules on a temporary record that is never stored |
| Provenance | The code that produced the number | Tag each value shown as a reason: user, knowledge base, recipient, calculated, demo estimate, AI reading, or external service (a geocoded place, a routed distance — passed through with the time it was fetched, not verified) |

The model's output is validated against the knowledge base before it is used: `material_id` must resolve to a real
record, `category` / `properties` / `safety_level` / `requires_processing` are read **from the KB**, and suggested
reuse categories are **intersected** with the KB set — so the model can only narrow the options, never invent one.
It cannot produce companies, prices, emissions or safety verdicts, because nothing downstream reads those from it.

The same boundary applies to knowledge itself: a material the knowledge base does not carry stays *unidentified*, so
the matcher offers only licensed assessment routes instead of guessing. Extending the product means adding a record to
`backend/knowledge_base/materials.py` — raw `rice_husk` sits beside `rice_husk_ash` precisely because their uses
differ, and the app must not borrow the ash's cement route for the husk.

---

## Quick start (5 minutes)

You need **Python 3.11+** (3.12+ recommended) and **Node 18+**. No API keys, and no database server to install
either: sign-in, organisation profiles, facilities, published listings and saved analyses are stored in a local
file, which the first boot creates and migrates on its own. Set `DATABASE_URL` to a PostgreSQL (Supabase included)
connection string and the same code runs against that instead — with `psycopg` installed, which is why it is an
optional dependency: `pip install "psycopg[binary]"`.

### 1. Backend

```bash
cd symbio

python -m venv venv
source venv/bin/activate          # macOS / Linux
venv\Scripts\activate             # Windows (cmd and PowerShell)

pip install -r requirements.txt

# From the PROJECT ROOT:
uvicorn backend.main:app --reload
```

Both of these work — pick whichever suits you:

| Command | Run from |
|---|---|
| `uvicorn backend.main:app --reload` | project root (`symbio/`) |
| `uvicorn main:app --host 0.0.0.0 --port 8000 --reload` | inside `backend/` |

`backend/__init__.py` puts `backend/` on `sys.path` so the package-style command resolves the
same internal imports as the in-directory one.

Check it: <http://localhost:8000/api/health> — you should see `"status": "ok"` and `"ollama": {"available": false}`
if you have not installed Ollama yet. That is fine; see [Demo mode](#demo-mode-without-ollama).

Interactive API docs: <http://localhost:8000/docs>

### 2. Frontend

In a **second terminal**:

```bash
cd symbio/frontend
npm install
npm run dev
```

Open **<http://localhost:3000>**.

The Next.js server proxies `/api/*` to FastAPI (configured in `next.config.mjs`), so there is no CORS setup and no
backend URL baked into client-side code.

### 3. Ollama (optional, but recommended)

Without Ollama Symbio still works — it falls back to a deterministic keyword + composition classifier and says so in
the UI. With Ollama, identification handles free-form descriptions much better.

```bash
# macOS / Linux — see https://ollama.com/download for the Windows installer
curl -fsSL https://ollama.com/install.sh | sh

ollama serve              # if it is not already running as a service
ollama pull qwen2.5:3b    # ~1.9 GB download — optional, see below
```

**That is the whole setup. There is nothing to configure and no restart to do.** Symbio asks Ollama what is
available on every request, so the badge in the top-right turns green the moment the server answers, and the next
analysis uses the LLM. Stop Ollama and it drops back to demo mode just as fast.

`qwen2.5:3b` is the model this project is built and tuned around, so it is what `ollama pull qwen2.5:3b` gets you
and it always wins when present. It is **not** a hard requirement: if it is absent, Symbio drives whatever chat model
you already have pulled (`qwen2.5`, `llama3.1`, `llama3.2`, `llama3`, `mistral`, `gemma2`, `phi3`), and the UI tells
you which one it picked. A model that ignores the "reply with JSON only" instruction simply degrades to the
deterministic classifier — the answer is validated and re-grounded against the knowledge base either way, so a
substituted model can never invent a material.

To force one exact model and disable the substitution:

```bash
OLLAMA_MODEL=qwen2.5:3b  # honoured exactly: used if present, otherwise fallback with a clear message
```

Symbio talks to Ollama over its local HTTP API only — no OpenAI, Gemini, Claude or other cloud model is used
anywhere in the codebase.

---

## Demo flow (3–5 minutes)

The backend seeds three analyses on startup — run through the real pipeline, not hand-written — so the dashboard is
never empty. Signed out, that is what an analysis is: a run in this process. Signed in — administrator, operator
or viewer — the same run is stored against the organisation and appears in **History** (`/history`) with a `SYM-`
reference that still opens after a restart.

1. **Landing page** (`/`) — the problem, the pipeline, and the six scoring weights.
2. **Dashboard** (`/dashboard`) — seeded analyses, top matches, category chart, the five-stage **material flow**
   (Source → Material → Processing → Reuse sector → Product, drawn from the allocated tonnage of real matches), and
   the impact summary.
3. **Analyze Waste** (`/analyze`) — click the **"Fly ash · 5 t/month · Chennai"** example chip, then
   **Analyze with Symbio**.

   You should see:

   | | |
   |---|---|
   | Identified as | **Fly Ash**, ~80% confidence, `coal_combustion_residue` |
   | Composition parsed | SiO₂ 55%, Al₂O₃ 25%, CaO 8%, Fe₂O₃ 6% |
   | Top match | **Coromandel Cement Materials** — Cement Manufacturing |
   | Distance | ~10 km |
   | Est. value | ~₹9,750 / month *(demo)* |
   | Est. CO₂e avoided | 1.8 t / month *(demo)* |
   | Pathway | Industrial Waste → Fly Ash → Processing → Cement Manufacturing → Blended Cement / Concrete |
   | Ranked behind it | brick works, ready-mix concrete, adsorbent maker, recycler |

4. **Click "View"** on the top match — score breakdown for all six components, the reasons list, cautions from the
   safety layer, the reuse pathway, and the **Assistant** panel. Ask *"Why was this company recommended?"*
4a. **Review what was read.** On `/analyze`, either drop a `.txt`/`.pdf`/`.docx` report or paste one sentence —
   *"We produce around 5 tonnes of fly ash every month in Chennai"* — and press **Extract fields**. A review panel
   shows each value next to the text it came from, marks what was *not* found instead of filling it in silently, and
   offers **Revert form**. Analysis only runs after you look at it.
5. **Matches** (`/matches`) — pick an **optimisation mode** (*Best overall · Highest value · Best environmental ·
   Closest · Least processing*): each mode re-orders the same result set by a measured field, so the partner on top
   really does change. When a mode cannot change anything the page says why instead of looking broken. Narrow by
   recipient type or safety category, scope the list to one analysis, and tick **cmp** on two or three cards to compare
   them row by row — the strongest cell in each row is highlighted from the same numbers the list shows. Every card
   also shows the six factor percentages and a sentence explaining the ranking.
5a. **Pathways, correction and what-if** (`/analyze`, under the result) — the analysis page now carries four panels:
   **Material intelligence** (what the knowledge base actually holds, the five evidence checks that were run, and
   *Is this wrong? Correct it*, which re-runs the same analysis against a knowledge-base material you pick);
   **Reuse pathways** (primary route plus the genuine alternatives, grouped by processing / sector / product, with the
   partners that share a route named inside the row); the ranked matches; and the **What-if simulator** (change
   quantity, cadence or location and see which partners move, by how much, and what the scenario claims versus the
   stored analysis — *Reset to original* discards it, because nothing was ever saved).
6. **Map** (`/map`) — pick the fly-ash analysis; the filter row is the same query the list uses, including the
   optimisation mode. Click a partner node: the popup carries the material it accepts, its quantity range, distance,
   processing capability, match score, safety category and the explanation line. Switch the toggle to **NETWORK** for
   the same result set drawn as source → material → recipient links (line width = tonnes, colour = reuse type) when
   you want to show connections rather than geography — no tile provider involved.
7. **Impact** (`/impact`) — diversion by sector, reuse partners and routes, processing pathways, the circularity
   composite with its bands, the actual formulas, and the demo factors they use.
8. **Show the safety layer.** Back on `/analyze`, click the **"Spent catalyst · hazardous"** chip. Symbio identifies
   a hazardous stream and returns **only** licensed industrial recyclers — every household, farm and artisan
   recipient is refused, and the page lists who was excluded and why.

---

## Configuration

Nothing has to be configured to run the demo: every value below already has a working default. The backend reads
real environment variables and deliberately does **not** load a `.env` file, so `.env.example` is documentation —
copy out only the lines you want to change, e.g. `OLLAMA_TIMEOUT_SECONDS=90 uvicorn backend.main:app --reload`.

| Variable | Where | Default | Meaning |
|---|---|---|---|
| `OLLAMA_URL` | backend env | `http://localhost:11434` | Local Ollama server |
| `OLLAMA_MODEL` | backend env | `qwen2.5:3b` | Preferred model. Setting it explicitly *pins* it and turns auto-selection off |
| `OLLAMA_TIMEOUT_SECONDS` | backend env | `60` | Wait for inference before falling back to the deterministic classifier |
| `OLLAMA_PROBE_TIMEOUT_SECONDS` | backend env | `2` | Wait for the "is Ollama alive, and what does it have" check |
| `BACKEND_URL` | `frontend/.env.local` | `http://localhost:8000` | Where Next.js proxies `/api/*` |
| `PROXY_TIMEOUT_MS` | `frontend/.env.local` | `120000` | How long Next.js waits for the backend. Must exceed `OLLAMA_TIMEOUT_SECONDS` |
| `DATABASE_URL` | backend env | unset | Postgres (Supabase included). Unset means the local file below |
| `SYMBIO_DB_MODE` | backend env | `auto` | `postgres` requires the URL, `sqlite` forces the file, `off` disables persistence |
| `SYMBIO_SQLITE_PATH` | backend env | `~/.local/share/symbio/symbio.db` | The development database file |
| `SYMBIO_MIGRATE_ON_START` | backend env | `1` | Apply pending migrations at boot; `0` makes a screen ask for `python -m db.migrate apply` |
| `GEOCODING_PROVIDER` / `ROUTING_PROVIDER` | backend env | `nominatim` / `osrm` | The one external geography pair; `off` turns each one off |
| `GEO_CONTACT` | backend env | unset | A page or address Nominatim can attribute requests to |
| `SYMBIO_RATE_LIMIT` | backend env | `on` | Per-client request budget. `off` exists for the test suite |
| `TRUST_PROXY` | backend env | `0` | Read `X-Forwarded-For` only when a proxy in front really sets it |
| `CORS_ALLOW_ORIGINS` | backend env | unset | Origins allowed to call the API with credentials. Unset means none, which is right while Next.js proxies `/api` |
| `APP_URL` | backend env | unset | Decides whether session cookies carry `Secure`, and the CSRF origin check |

`BACKEND_URL` is read server-side only, so it never reaches the browser. Nothing secret is stored in the repository
and nothing secret leaves the API: the password in a connection string never leaves the settings object, the public
`/api/status` and `/api/health` answers describe storage as `PostgreSQL` or `local file (symbio.db)` and name no host
or port, and a log line carries the masked form only. There is no `.env` file to commit, because the backend does not
read one.

---

## Project structure

```
symbio/
├── backend/
│   ├── main.py                     FastAPI app, public routes, error handling, startup seeding
│   ├── api/                        the tenant-facing routes: auth.py, organization.py, marketplace.py,
│   │                               deps.py (actor + permission + database guards), security.py
│   │                               (headers, rate limits, the error translators)
│   ├── models/schemas.py           Pydantic models shared by API, engine and AI layer
│   ├── db/                         config.py (where the data goes), engine.py (hand-written SQL layer, no ORM),
│   │                               migrate.py (the ledger and the CLI), repositories.py (tenant-scoped reads/writes)
│   ├── knowledge_base/
│   │   ├── materials.py            29 materials: properties, reuse routes, sectors, safety, reference factors
│   │   └── loader.py               reads data/*.json — the seeded network, never written at runtime
│   ├── matching/                   engine.py (deterministic scoring, safety layer, allocation), logistics.py
│   ├── ai/
│   │   ├── prompts.py              identification prompt (JSON-only, no facts allowed)
│   │   ├── fallback.py             deterministic keyword + composition classifier
│   │   └── identification.py       Ollama client + grounding against the KB
│   ├── services/
│   │   ├── analysis.py             the end-to-end pipeline, and the geography resolution it runs
│   │   ├── geo.py                  the one external geography module: Nominatim, OSRM, throttle, cache, circuit
│   │   ├── storage.py              the in-process store for a visitor's session analyses (most recent 200)
│   │   ├── persistence.py          the organisation's own records: listings, profile, facilities, analyses, history
│   │   ├── identity.py             Argon2id passwords, server-side sessions, the actor
│   │   ├── rbac.py                 three roles, one permission table
│   │   ├── request_scope.py        which tenant this request belongs to
│   │   ├── listings.py             the seeded marketplace rows and the merged view
│   │   ├── profiles.py, dashboard.py, demand_forecast.py, material_flow.py, scenarios.py,
│   │   │   completeness.py, explain.py          aggregation and explanation behind the pages
│   │   ├── chat.py                 grounded assistant
│   │   ├── extract.py              deterministic field extraction (no model)
│   │   └── files.py                PDF / TXT / DOCX text extraction
│   ├── data/                       recipients.json (40), sources.json (15), listings.json (19),
│   │                               sector_profiles.json (22) — DEMO DATA, plus the two generators
│   └── tests/                      23 test files + conftest.py, 413 tests
├── database/
│   ├── migrations/                 0001–0006: the tenant schema, portable SQLite ↔ PostgreSQL
│   └── schema.sql                  the SQL shape of the seeded tables, mirrored by the models
├── frontend/
│   ├── app/                        /, /analyze, /matches, /matches/[matchId], /marketplace, /map, /dashboard,
│   │                               /impact, /knowledge-base, /organization, /history, /login, /signup
│   ├── components/                 Nav, Listings, TransportPanel, ui, and the rest of the page furniture
│   ├── lib/                        api.ts, types.ts, session.tsx, format.ts, palette.ts
│   └── scripts/check-palette.mjs   the colour-token lint
├── scripts/                        verify.sh (all four gates), check_location.py (geography end to end)
├── requirements.txt
├── .env.example
├── .gitignore
├── docker-compose.yml              optional convenience wrapper
└── README.md
```

**Frontend note:** you do not need `frontend/.env.local` at all — `next.config.mjs` already defaults `BACKEND_URL`
to `http://localhost:8000`. Create it only if your backend runs somewhere else.

---

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/analyze` | Run the full pipeline on a waste description. `material_override_id` re-uses the request with a user-selected knowledge-base material for that analysis only (the knowledge base is never written to) |
| `POST` | `/api/matches` | Ranked matches, with filters (`sector`, `max_distance_km`, `min_match_score`, `min_quantity`, `reuse_type`, `processing`, `min_estimated_value`, `safety_level`, `partner_type`) and `sort=score\|distance\|value\|environmental\|least_processing`. Carries `sort_note` when a mode cannot change the order, and says why |
| `GET` | `/api/matches/{analysis_id}/{recipient_id}` | One match: breakdown, reasons, cautions, pathway, the weights used, and `provenance` — every value tagged user / knowledge_base / recipient / calculated / estimate / ai |
| `GET` | `/api/pathways` | The same filtered, sorted matches collapsed into distinct routes (processing + sector + product). `primary` + `alternatives`, never padded |
| `GET` | `/api/intelligence?analysis_id=` | Material card for one analysis: the knowledge-base record, the gate rules that apply, and the five evidence checks recomputed from that analysis (also returned inline by `/api/analyze`) |
| `POST` | `/api/scenario` | What-if: re-runs the same engine and safety layer for a temporary quantity / unit / frequency / location. Nothing is stored; the analysis is not modified |
| `GET` | `/api/analyses` | This process' session analyses, newest first (`?limit=` up to 100) |
| `GET` | `/api/analyses/{id}` | One run, by id or by its `SYM-…` reference: this process' copy first, then the caller's stored record. An anonymous caller reads only what this process still holds, so a saved analysis cannot be reached by guessing ids |
| `GET` | `/api/analyses/{id}/completeness` | §3 — how complete that analysis' input is: percentage, per-field weights, what each gap would change. Recomputed from the stored record; it describes the input and never the ranking |
| `GET` | `/api/materials/{id}/similar` | §12 — the knowledge base's nearest neighbours (deterministic property / reuse-route / sector overlap), with `safety_delta` and `acceptance_note`. Cannot override a safety decision |
| `GET` | `/api/profiles`, `/api/profiles/{recipient_id}` | §5 / §7 — the 22 sector templates, and one receiver's structured profile (supply → material demand → production capability → potential reuse product), from that partner's own record first |
| `GET` | `/api/logistics` | §8 — the eight freight constants every transport figure is built from, the viability bands, and `?distance_km=&quantity_t_per_month=&value_inr_per_tonne=` to run the same calculation a card uses |
| `GET` | `/api/sources` | The seeded source records — the only parties a supply listing may name |
| `GET` | `/api/listings`, `POST /api/listings`, `GET /api/listings/{id}`, `POST /api/listings/match` | §6 — demand and supply listings generated from the partner records, a validated publish (unknown material, zero quantity, price above the recorded ceiling or an unknown party is refused), and a match that runs the listing-to-listing fit and the deterministic engine side by side. A publish by a signed-in organisation is stored against that tenant and survives a restart; the same form with no account produces a session listing, labelled as one |
| `GET` | `/api/material-flow` | §9 — the six-stage funnel (generated → reusable → viable → matched → processed → reused) plus the Source → Processor → Recipient → Product routes, each stage capped at the one above, reconciled against `/api/impact` |
| `GET` | `/api/demand` | §10 — regional demand potential by area: unfilled intake capacity, partner breadth, open listings and unserved nearby supply. Labelled potential, never a purchase forecast |
| `POST` | `/api/scenarios/compare` | §11 — 2–4 configurations of one analysis in one table: best match, totals, transport burden, net potential, the tonnage at which the haul starts paying, and the delta against the first column |
| `GET` | `/api/materials` | Knowledge-base materials, with aliases, identification hints and the safety-gate rules that apply to each record |
| `GET` | `/api/recipients` | Demo recipients (optional `?sector=`) |
| `GET` | `/api/dashboard` | Metrics, recent analyses, top matches, categories, sector flow |
| `GET` | `/api/impact` | Totals (including reuse partners, routes and direct-reuse share), per-sector and per-source breakdown, processing pathways, the circularity composite, formulas, factors used |
| `GET` | `/api/map` | Nodes + links; accepts the **same filter and sort parameters as `/api/matches`**, so the map is a view of that query rather than a second implementation |
| `POST` | `/api/chat` | Grounded assistant |
| `POST` | `/api/upload` | PDF / TXT / DOCX text extraction, plus candidate fields for review before analysis |
| `POST` | `/api/extract` | Read quantity / material / location / frequency / source out of free text — no analysis, nothing stored |
| `GET` | `/api/health` | Status, dataset sizes, Ollama availability |
| `GET` | `/api/status` | What is real in this deployment: storage, authentication mode, provider states, the size of each of the three kinds of data |
| `POST` | `/api/auth/signup`, `/api/auth/login`, `/api/auth/logout` | Account creation (person + organisation + session in one call), sign-in, sign-out. Failed credentials are 401 with one sentence; the rate limiter answers 429 with `Retry-After` |
| `GET` | `/api/auth/me` | Who is looking. A signed-out visitor gets `200 {signed_in: false}` — being anonymous is an answer, not an error |
| `GET` | `/api/auth/organizations`, `POST /api/auth/organizations/select` | The tenants this person belongs to, and pointing the session at another one. The membership table decides; a non-member's id is ignored in one sentence |
| `GET`/`PATCH` | `/api/org` | The tenant bundle: organisation, profile, facilities, members, counts, verification, persistence. `PATCH` is name / sector / description / website / contact only |
| `PUT` | `/api/org/profile` | Save the declared profile. Only the fields that arrived are written, so saving one section cannot empty another; a material the knowledge base does not have is refused |
| `GET`/`POST`/`PATCH`/`DELETE` | `/api/org/facilities` | Sites, placed if and only if something can place them |
| `GET`/`POST`/`DELETE` | `/api/org/members` | Roster, invite-by-email, removal. The last administrator cannot be removed |
| `GET` | `/api/org/history` | §6 — Analysis History: reference, material, quantity, location, date, match count and best match for each stored run |
| `GET` | `/api/org/listings/mine` | This organisation's listings, whatever their status — the only view that shows paused and closed rows |
| `PATCH` | `/api/org/listings/{id}` | Change what was stated (quantity, price, distance, location, cadence, use, notes, materials). `kind` and ownership are not changeable; another tenant's id is a 404 |
| `POST` | `/api/org/listings/{id}/status` | `active` / `paused` / `closed`. Deactivating is a status change, never a delete |

---

## How scoring works

Every component returns a value in `[0, 1]`; the total is a weighted sum rounded to one decimal.

```
match_score = compatibility × 0.30
            + quantity      × 0.20
            + location      × 0.15
            + sector        × 0.15
            + value         × 0.10
            + environmental × 0.10
```

| Component | How it is computed |
|---|---|
| **Compatibility** | 1.0 base if the recipient explicitly accepts the material, 0.65 if it accepts the material's family, 0 otherwise — scaled by identification confidence. Unidentified material gets a flat 0.45 and only for a licensed waste processor. |
| **Quantity** | Peaks when the offered tonnage sits inside the recipient's min–max range; falls off below the minimum and above the maximum. |
| **Location** | Haversine distance, decaying to 0 at 300 km. |
| **Sector** | Source-sector → recipient-sector affinity from a lookup table, **set to 1.0 when the recipient's preferred route is the material's primary route in the KB** (this is why fly ash ranks cement above a slightly closer brick works). |
| **Value** | Price ÷ the 90th percentile of KB prices. |
| **Environmental** | Avoidance factor ÷ the 90th percentile of KB factors. |

Both normalisation ceilings are **derived from the knowledge base**, not hardcoded, so adding a material cannot
silently distort every other score.

The same input always produces the same score — `tests/test_matching.py::test_matching_is_deterministic` asserts it.

### Impact calculation

```
waste diverted        = Σ allocated tonnes, where allocation is greedy in score order
estimated value       = allocated tonnes × max(recipient price, material reference price)
estimated CO₂e        = allocated tonnes × material.co2e_avoided_t_per_tonne
```

Allocation matters: without it, ten matches would each claim the same 5 tonnes and the dashboard would report 50
tonnes diverted from a 5-tonne source. Per-route figures on each match card still show what that route would deliver
on its own; only the totals use the shared budget.

**These are demo calculations, not certified figures.** Replace `typical_price_inr_per_tonne` and
`co2e_avoided_t_per_tonne` in `backend/knowledge_base/materials.py` with validated LCA factors and every number in
the product updates. Nothing else needs to change.

---

### Circularity score (optional, and deliberately simple)

One number, `0–100`, computed in `backend/services/dashboard.py` from three things the pipeline already measures:

```
100 × (0.60 × diversion_rate + 0.25 × direct_reuse_share + 0.15 × mean_identification_confidence)
```

Bands ("First Diversion" → "Close the Loop") are thresholds on that same number, and each band states the
measurement that earns it. Identification confidence is part of the formula on purpose: a diversion nobody could
identify confidently should not read as a strong circular result. The score is labelled a demo composite on the page —
it is a way of reading Symbio's own data, not a certified or standardised metric.

### Field extraction before analysis

`POST /api/extract` and the `fields` block on `POST /api/upload` are served by `backend/services/extract.py`, which is
deterministic — no model. Every field comes back as `{value, evidence, found, note}`, quantities are normalised to
tonnes, locations are only accepted if the demo gazetteer can geocode them, and anything not found is listed in
`missing` rather than defaulted. The UI shows this *before* `POST /api/analyze` runs, so an extracted 5 tonnes never
silently becomes the score's input; the analysis itself still reads the full report text through the normal pipeline.

## Safety classification

Every route carries one of `DIRECT_REUSE`, `REQUIRES_PROCESSING`, `INDUSTRIAL_ONLY`, `RESTRICTED`, `UNKNOWN`.

The rule-based layer (`matching/engine.py::safety_gate`) enforces:

1. **Hazardous** streams only go to recipients with `licensed_handling` capability.
2. **High-risk or hazardous** material is refused outright for community, farm and artisan recipients.
3. **Unidentified** material is offered *only* to a licensed waste processor, for assessment — never as a reuse route.
4. **Low identification confidence** (< 0.5) blocks casual-sector routes entirely.
5. The model **cannot downgrade** a KB hazard rating, and cannot mark a stream safe.

This is a rule-based safety demonstrator, **not** a regulatory compliance engine and not a claim of certification.
Real deployment needs jurisdiction-specific rules, lab verification and chain-of-custody paperwork.

---

## Demo mode (without Ollama)

If Ollama is not running, `ai/fallback.py` classifies the material from knowledge-base keywords plus composition
markers (`SiO2: 55%` → fly ash, and so on). The result is clearly labelled `fallback_keyword` in the UI and its
confidence is capped at 0.78 to stay honest about being less flexible than the LLM. Everything downstream —
safety layer, scoring, impact — behaves identically.

---

## Data: four kinds, kept apart

Symbio holds four kinds of data. They behave differently, and the difference is visible wherever a number is read:

| Kind | Where it lives | Survives a restart | Written by |
|---|---|---|---|
| **Seeded network** — 40 recipients, 15 sources, 19 listings, the material knowledge base. Geographically it is a Chennai-region network today: every seeded partner sits in and around Chennai, so a stream typed elsewhere is measured against partners whose own records say Chennai | `backend/data/*.json`, `backend/knowledge_base/` | Yes; it ships with the code | Nobody at runtime. No route writes to it |
| **Platform reference** — the 22 sector templates, freight constants, safety rules | same, plus `matching/` | Yes | Nobody at runtime |
| **Organisation data** — accounts, profiles, facilities, published listings, saved analyses | the database (Postgres, or a local file in development) | Yes | A signed-in person, through a tenant-scoped route |
| **Session data** — an analysis or a listing from somebody with no account | process memory: the most recent 200 analyses (`services/storage.py`) and the listings published this session (`services/listings.py`) | No | Anyone. Where a run or a listing did not reach a database, the UI says *Session listing* / *Kept for this session only* |

User data is never written into `backend/data/` or any seed file. That is what keeps the demo reproducible: a
published listing on Tuesday does not become somebody else's fixture on Wednesday.

### The tenant schema

`database/migrations/` holds the six SQL files — `0001_identity`, `0002_facilities`, `0003_organization_profile`,
`0004_marketplace`, `0005_analyses`, `0006_geography` — portable between SQLite and PostgreSQL, tracked in a
`schema_migrations` ledger so a second `apply` is a no-op and a drifted database refuses rather than half-migrates:

`organizations`, `users`, `organization_members`, `auth_sessions`, `organization_profile`, `facilities`,
`organization_listings`, `organization_listing_materials`, `organization_analyses`,
`organization_analysis_matches`, `geo_cache`, `reference_counters`.

The seeded knowledge base is **not** in these tables. `database/schema.sql` mirrors its columns for anyone who wants
it in SQL one day; today the network is read from `backend/data/*.json` and written by nobody at runtime.

```bash
cd backend
PYTHONPATH=. python -m db.migrate status   # what is applied, what is pending
PYTHONPATH=. python -m db.migrate apply    # apply the pending ones
```

`SYMBIO_MIGRATE_ON_START=1` (the default) runs the same ledger at boot. `/api/status` reports `storage`: configured,
reachable, migrations applied — and when the database is configured but unreachable, every screen keeps working, the
write routes answer 503 in one sentence, and nothing is quietly kept in memory and presented as saved.

### Accounts, roles, and what each one may do

Sign-up creates a person, the organisation they administer, and a live session in one step. The session is an
`HttpOnly; SameSite=lax` cookie backed by a row in `auth_sessions`; there is no token in a response body, no token in
local storage, and no way to present one from a script. Passwords are Argon2id, with a ten-character minimum
refused before anything is written.

| Role | Reads | Writes |
|---|---|---|
| `organization_admin` | everything in the tenant | the organisation record: name, sector, profile, facilities, members — and everything an operator may do |
| `operator` | everything in the tenant | facilities, and the listings: publish, edit, pause, close |
| `viewer` | everything in the tenant | nothing. A viewer cannot touch the organisation's records at all |

Reading is scoped by organisation first and by role second, which is why a viewer is a real role and not a
placeholder: they see the profile, the facilities, the members, the listings and the history of their own
organisation, and no write route accepts anything from them. Two actions in the permission table —
`run_analysis` and `save_analysis` — are declared but enforced by no route, because analysing is open to anybody
and a signed-in member's run is stored whatever their role; that is the behaviour, not an oversight to read past.

**Tenant isolation is enforced on the server, twice.** A route resolves the actor from the cookie and passes
`actor.organization_id` down; every repository statement repeats that id in its `where` clause, and reads that can
also be public (`GET /api/listings`) go through a different function than reads that are private
(`GET /api/org/listings/{id}` → 405, `PATCH` on another tenant's listing → 404). `test_tenant_isolation.py` asserts
the second organisation in the same process sees none of the first: not its listings, not its analyses, not its
profile, not its internal material lines.

Verification is **not** self-serve: no route in Symbio accepts `verification_status` from a request body. An
organisation that could mark itself verified has a field, not a credential.

### Geography, and the one external provider

Place names and road distances come from OpenStreetMap services behind `backend/services/geo.py` — Nominatim for
geocoding, the public OSRM demo for routing (OpenRouteService is the alternative if `ROUTING_PROVIDER=ors` and a key
is set). That module is the only place in the codebase that makes a geography HTTP call, it throttles itself to the
usage policy (≥1.1 s between Nominatim requests, a real `User-Agent` from `GEO_CONTACT`), caches answers for
`GEO_CACHE_HOURS`, and opens a circuit after three consecutive failures so a provider outage degrades instead of
multiplying.

When it fails, the location the person typed survives: coordinates, distance and freight go null, the analysis still
runs, and the UI says the route could not be calculated rather than borrowing a nearby city's coordinates. A routing
answer replaces only the distance *displayed* next to the freight estimate — it never re-prices a recommendation,
because the engine scored a straight line and the estimate was built on that.

> **Attribution.** Geocoding and routing data are © OpenStreetMap contributors, made available under the
> [ODbL](https://opendatacommons.org/licenses/odbl/) by the [OpenStreetMap Foundation](https://osmfoundation.org/)
> (Nominatim) and the [OSRM demo server](http://project-osrm.org/) (routing). Both are usage-policy-limited public
> services, not production infrastructure: a deployment that matters runs its own geocoder and router, which is what
> `NOMINATIM_URL`, `OSRM_BASE_URL` and `GEO_CONTACT` are for.

## File processing

Uploads accept **PDF, DOCX and TXT**. Text is extracted server-side (`backend/services/files.py`) and passed to the
identification stage; nothing is stored and there is no OCR.

PDF extraction prefers **PyMuPDF** and falls back to **pypdf**:

```bash
pip install PyMuPDF    # optional, ~25 MB binary wheel, better on real-world reports
```

pypdf is pure Python and already required, so the default install stays small. The upload response reports which
engine ran (`"engine": "pymupdf" | "pypdf"`). If extraction fails — a scanned PDF, for example — the API returns
`ok: false` with a message and the UI asks you to type the description instead.

---

## Deployment

**Local development is the primary target** and is fully supported. The architecture also fits the usual hosting
split, though this has not been exercised:

| Layer | Target | What to change |
|---|---|---|
| Frontend | Vercel | Standard Next.js deploy. Set `BACKEND_URL` to the public backend URL — it is read server-side only, so it is never exposed to the browser. |
| Backend | Render / Fly / any Python host | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`. Set `OLLAMA_URL` to a reachable Ollama host, or leave it unset and run in demo mode. |
| Database | Supabase / PostgreSQL | `pip install "psycopg[binary]"`, set `DATABASE_URL`, start the app. The migration ledger applies `database/migrations/` at boot; with `SYMBIO_MIGRATE_ON_START=0` run `python -m db.migrate apply` yourself. The seeded knowledge base stays in JSON either way — it is not read from the database, and no route writes to it. |

Four caveats worth knowing before you deploy:

- **Ollama is local by design.** A hosted backend cannot reach `localhost:11434` on your laptop. Point `OLLAMA_URL`
  at a hosted Ollama instance, or accept the deterministic classifier.
- **CORS is closed by default, and that is the intended posture.** `backend/main.py` adds `CORSMiddleware` only when
  `CORS_ALLOW_ORIGINS` names origins, and never with a wildcard alongside credentials; the Next.js server proxies
  `/api/*`, so a normal deployment needs no cross-origin permission at all. Set it only if you split the origins.
- **Cookies need the real scheme.** `APP_URL` decides whether the session cookie carries `Secure` (on when it starts
  with `https://`), and the same value is what the cross-site origin check compares against; behind a proxy that
  rewrites addresses, set `TRUST_PROXY=1` so the rate limiter sees clients honestly rather than the proxy.
- **A container filesystem is not a database.** `docker-compose.yml` mounts source only, so organisation records
  written to the default local file die with the container. Mount a volume at `SYMBIO_SQLITE_PATH`, or set
  `DATABASE_URL`.

### What is not production-grade

The persistence, the accounts and the degradation paths are real and tested. The operations around them are not:

- **One process holds the session store's short-lived data.** A visitor's analyses live in `services/storage.py`,
  capped at the most recent 200, and disappear with the process. Two workers behind a load balancer would each hold
  a different half of a visitor's session, so scale by replicating a shared store, not by adding workers.
- **No TLS, no backups, no key rotation.** Terminate TLS in front of the app, back the database up, and treat
  `auth_sessions` as revocable: removing a member revokes their sessions, and there is nothing else that does.
- **No self-service password reset, and no email at all.** There is no mail transport in this codebase: an invitation
  takes effect when that person next signs in, and a forgotten password is a platform-team action.
- **`verification_status` is a platform field, not a credential.** No route accepts it from a request body, so
  nothing in the product can mark an organisation verified. Unless the state says `verified`, it says `unverified`.
- **The external geography is a public demo service.** Nominatim and the OSRM demo server have usage policies, no
  SLA and no invoice; `GEO_*` variables exist so you can point at your own. Figures taken from them are labelled
  external and passed through unverified.
- **Prices and emission factors are recorded reference values, not live market data or certified LCAs.** The impact
  and circularity numbers are arithmetic over those values: internally consistent, reproducible, and not
  independently verified by anybody.
- **Known dependency advisories.** `npm audit` reports advisories in the `postcss` copy vendored inside
  `next@14.2.35`; the only fix npm offers is a breaking major upgrade of Next, which this project has not taken.

---

## Tests

```bash
cd /path/to/symbio
bash scripts/verify.sh        # pytest, then tsc, next build and the palette lint, in one command
bash scripts/verify.sh --postgres   # the same, plus the persistence tests against $SYMBIO_TEST_DATABASE_URL

cd backend
python -m pytest -q                                        # 405 passed, 8 skipped
python -m pytest -q --symbio-postgres-url="postgresql://…/symbio"   # the same suite against real Postgres
python3 ../scripts/check_location.py                       # geography end to end; needs the API on :8000
```

The 8 skips are the Postgres-only checks (schema drift, real-tenant SQL, the DB-backed part of the walkthrough) with
no database URL present; pointing the flag at a live server runs them too. The last such run, against PostgreSQL 17,
was 411 passed and 1 skipped; expect a number or two more, since the suite has grown since.

`tests/test_acceptance_walkthrough.py` is the production-readiness pass read as a script: sign up, sign in, save a
profile, re-read it from disk, add a facility, publish a supply and a demand listing, see them as a visitor, edit and
pause them, run an analysis in Coimbatore, compare it against the Chennai baseline, read the provenance rows and the
transport estimate, reopen the stored run from history, check that a second organisation sees none of it, sign out and
watch the private routes close. One test, twenty numbered steps, because a claim that is spread over five files is a
claim nobody has actually checked.

They cover the scoring arithmetic and determinism, the haversine and component functions, all five safety rules,
knowledge-base integrity (every sector, reuse route and material reference resolves), unit conversion, the primary
demo scenario, and every HTTP endpoint including filters, uploads and the assistant's "I don't know" path.

Added while upgrading the roadmap: field extraction from messy sentences and reports (`test_extract.py`), the
sort/filter contract shared by the list and the map, including map↔list parity and the sort orders
(`test_matches_query.py`), and the assistant's intent routing — including that "Why was this recipient ranked first?"
is answered and that a hazardous stream is never called safe (`test_chat_assistant.py`).

The depth pass added three files of its own, because each of those claims is easy to fake and worth pinning down:
`test_pathways_and_modes.py` (all five modes reorder the same set without touching the canonical score; pathways group
the engine's own matches, lose no partner, follow the selected mode, and never borrow a product the recipient's sector
does not make), `test_correction_and_scenario.py` (a correction re-runs the real engine, cannot open a refused route
and leaves the knowledge base byte-identical; a scenario mutates nothing, rescales by cadence, and re-applies the
safety layer at the new quantity), and `test_provenance_and_intelligence.py` (every value carries an origin, demo
estimates are labelled as estimates, and the material card is the knowledge-base record verbatim).

Sprint 3 added five files, one per claim that could otherwise drift into decoration:
`test_completeness.py` (the nine weighted fields, the four groups, and that a missing field can never block an
analysis or move a score), `test_material_similarity.py` (similarity is arithmetic over the knowledge base, and the
safety layer stays authoritative), `test_industry_profiles.py` (every partner resolves to a profile, the four steps
are always present, and a byproduct the knowledge base does not know is labelled as unmodelled instead of being given
a product), `test_listings_and_transport.py` (every listing is checked back against the party record it claims to
come from, the publish rules refuse anything that could not be true, and each transport figure is recomputed from the
published constants), and `test_flow_demand_scenarios.py` (the funnel is a subset chain and reconciles with the
impact dashboard, demand headroom is recomputed from the records, and a scenario rule can only remove routes - never
re-score or rescue one the safety layer refused).

Sprint 4's files pin the parts that are easy to claim and hard to fake: `test_identity_and_rbac.py` (password
hashing, the cookie's attributes, session expiry and revocation, and what each of the three roles may and may not
do), `test_tenant_isolation.py` (a second organisation in the same process sees none of the first: listings,
analyses, profile, internal material lines), `test_persistent_organisation_data.py` (profile, facilities, listings
and history round-trip through the database, and a partial save cannot empty a section), `test_persistence_layer.py`
(the SQL layer itself: transactions, the ledger, drift), `test_external_dependencies.py` (every provider failure
degrades to a stated absence rather than a number, including the breaker and the unreachable database) and
`test_security_baseline.py` (headers, rate limits with `Retry-After`, upload limits, validation before the engine,
safe error bodies with a correlation id, and no credential in any response).

```bash
cd frontend
npx tsc --noEmit             # typecheck (or: node node_modules/typescript/bin/tsc --noEmit)
npm run build                # production build, which also runs `next lint`
npm run lint:palette         # every colour resolves to a token in globals.css
```

---

## Troubleshooting

**"Cannot reach the Symbio API" / red badge**
The backend is not running on port 8000. Start it, then reload. `curl http://localhost:8000/api/health` should
return JSON.

**Badge reads "Demo mode · no Ollama"**
Expected without Ollama — Symbio is using the deterministic classifier. To enable the LLM: `ollama serve`, then
`ollama pull qwen2.5:3b`. No restart is needed; the status is re-checked on every request and the badge turns green
by itself. If it stays amber, check that `OLLAMA_URL` matches where Ollama is actually listening
(`curl http://localhost:11434/api/tags` should return JSON).

**Badge reads "Ollama · no model"**
Ollama is answering but has nothing pulled, so there is no model to drive. `ollama list` will come back empty.
Run `ollama pull qwen2.5:3b`, or any model from `OLLAMA_MODEL_PREFERENCE` — this state is amber, not red, because
the demo still works through the deterministic classifier.

**Identification is slow**
`qwen2.5:3b` on CPU takes roughly 10–30 s per call. Raise `OLLAMA_TIMEOUT_SECONDS` if you see fallback warnings on
a slow machine, or use a smaller model.

**Analyze fails with a 500 after about 30 s** / `Failed to proxy ... socket hang up` / `ECONNRESET` in the Next terminal
This is a timeout mismatch, not a bug in the request. Next.js limits proxied requests to **30 s in development**
(`next/dist/server/lib/router-utils/proxy-request.js` → `proxyTimeout || 30000`), so if the backend is still waiting on
Ollama at 30 s, the proxy tears down the connection and the browser gets an opaque 500 — the backend itself logs
nothing wrong. `next.config.mjs` raises this with `experimental.proxyTimeout` (default 120000 ms). Keep it above
`OLLAMA_TIMEOUT_SECONDS`, or the failure comes back:

```js
experimental: { proxyTimeout: Number(process.env.PROXY_TIMEOUT_MS || 120000) }
```

Note this applies to `npm run dev`. A production `next start` does not proxy with that 30 s cap, but set the value
anyway so dev and prod behave the same. `tests/test_analyze_latency.py` fails if the two settings drift apart again.

**"Unidentified Material" for a description that looks obvious**
The fallback classifier needs a keyword or composition marker from the knowledge base. Add the phrase to that
material's `keywords` list in `backend/knowledge_base/materials.py`. With Ollama enabled this is far less common.

**Port 8000 or 3000 already in use**
Backend: `uvicorn main:app --port 8001`. Frontend: `npm run dev -- --port 3001`, and set
`BACKEND_URL` in `frontend/.env.local` if you also moved the backend.

**Map has no streets underneath it**
`tile.openstreetmap.org` is run by volunteers and answers **HTTP 403** to requests it cannot attribute to an
application — most cloud and preview egress IPs, and some campus networks. The map probes one tile before drawing;
if that tile is refused (or the provider returns images the browser cannot load), the panel drops to a plain canvas
with its own coordinate grid and says why, instead of leaving grey squares or a vendor's watermark. The control
labelled **Basemap: streets / off** in the legend does the same thing by hand. To use a provider you can reach, put
it in `frontend/.env.local`:

```
NEXT_PUBLIC_TILE_URL=https://your-tile-host/{z}/{x}/{y}.png
NEXT_PUBLIC_TILE_ATTRIBUTION=&copy; Your tile provider
```

Nothing but tile coordinates leaves the browser. Markers, routes, distances and scores never depend on the tile
provider — they come from `/api/map`, so a refused basemap costs you the streets, not the data. A public
OSM-based mirror used to be offered here as the fallback; CARTO's free style now requires an API key and paints
"API KEY REQUIRED" over the tiles, which is why it is gone and the canvas is not.

**An analysis vanished after a restart**
Only if it was never stored. An anonymous run lives in process memory (`backend/services/storage.py`) and ends with
the process — the three seeded demo scenarios are recomputed on startup, so the dashboard is never empty — while a
run by a signed-in operator is a row in `organization_analyses` and reopens from `/history`. If an organisation's
listing or analysis is gone after a restart, the write never happened: check `storage.reachable` and
`migrations_applied` in <http://localhost:8000/api/status>, and `SYMBIO_DB_MODE` / `DATABASE_URL` in the
environment the process actually started with.

**A chip says "Session listing" / the page says "Kept for this session only"**
Not an error, and not a bug: it is the honest label for data that had no database to go to. It appears when nobody
is signed in, when `SYMBIO_DB_MODE=off`, or when a configured database is not answering.

**Sign-in answers "Symbio's database is not answering"**
That is the 503 saying what happened, in place of a stack trace: the account could not be read or written, and no
session was handed out. Analysis, the seeded network and the marketplace keep working meanwhile. Nothing is queued
or retried behind the scenes — a write that could not be saved is not saved.

**Upload says "No selectable text found"**
The PDF is a scan. OCR is deliberately out of scope — type the description instead. An unsupported or oversized file
is refused in one sentence that names the limit, and nothing is stored from an upload either way.

---

## What is deliberately *not* here

- Enterprise identity — no SSO, no SCIM, no per-record ACLs. Three roles and a membership table are the whole
  permission system, deliberately: a larger one would be infrastructure nobody has asked for yet.
- Real company data, live market prices, certified emission factors — the seeded network carries recorded demo
  values and says so; an organisation's own listings are what that organisation stated, nothing more.
- A regulatory compliance engine — the safety layer is a rule-based demonstrator.
- Payments, invoicing or escrow — a match is a ranked introduction.
- An admin console. There is no screen that verifies an organisation: `db.repositories.set_verification` is the only
  write that changes that state and no route in the application calls it, so an organisation is `unverified` until
  the platform team updates the row. Anything that reads as a verification badge is reading that column.
- OCR for scanned reports.
- A Sankey *layout* dependency — the material-flow view uses the Recharts `Sankey` already in the stack, so no extra
  package is pulled in for it.
- A queue, a cache tier or workers. Long requests wait in-process, and `POST /api/analyze` holds a request while
  Ollama thinks; nothing runs in the background, so a result either exists in the database or does not exist yet.
