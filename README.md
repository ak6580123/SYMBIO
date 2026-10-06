# Symbio

**AI-powered circular-economy waste matchmaking.**

Symbio takes a waste stream from any source, works out what the material actually is, finds who could use it —
cement plants, brick works, recyclers, farms, packaging SMEs, neighbourhood programmes — ranks those opportunities
with an explainable score, and shows the resulting circular flow with its economic and environmental upside.

```
WASTE SOURCE → AI IDENTIFICATION → MATERIAL KNOWLEDGE BASE → POTENTIAL USERS
             → MATCHING ENGINE → RANKED OPPORTUNITIES → ECONOMIC + ENVIRONMENTAL IMPACT
```

> **This is a hackathon MVP.** Every company, price and emission factor is fictional demo data and is labelled as
> such in the UI. There is no authentication, no payment integration and no regulatory compliance engine.

---

## The one rule this codebase is built around

**The language model never determines a match score.**

| Stage | Who does it | What they are allowed to do |
|---|---|---|
| Identification | LLM (`qwen2.5:3b` via Ollama) | Read a messy description, name the material, give a confidence, suggest candidate reuse categories |
| Facts | Knowledge base | Properties, reuse routes, compatible sectors, safety level, price, emission factor |
| Safety | Rule engine | Refuse hazardous / unidentified streams for household, farm and artisan use |
| Scoring | Deterministic engine | Compute all six components and the weighted total |

The model's output is validated against the knowledge base before it is used: `material_id` must resolve to a real
record, `category` / `properties` / `safety_level` / `requires_processing` are read **from the KB**, and suggested
reuse categories are **intersected** with the KB set — so the model can only narrow the options, never invent one.
It cannot produce companies, prices, emissions or safety verdicts, because nothing downstream reads those from it.

---

## Quick start (5 minutes)

You need **Python 3.11+** (3.12+ recommended) and **Node 18+**. No database, no API keys.

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

The backend seeds three analyses on startup, so the dashboard is never empty.

1. **Landing page** (`/`) — the problem, the pipeline, and the six scoring weights.
2. **Dashboard** (`/dashboard`) — seeded analyses, top matches, category chart, circular-flow ribbons, impact summary.
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
5. **Matches** (`/matches`) — drag the distance and score sliders; filters apply immediately.
6. **Map** (`/map`) — pick the fly-ash analysis from the dropdown. Click a node, then click a connection line.
7. **Impact** (`/impact`) — diversion by sector, the actual formulas, and the demo factors they use.
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

No secrets are used anywhere, and `BACKEND_URL` is read server-side only, so it never reaches the browser.

---

## Project structure

```
symbio/
├── backend/
│   ├── main.py                     FastAPI app, routes, error handling, startup seeding
│   ├── api/                        (reserved for route splitting)
│   ├── models/schemas.py           Pydantic models shared by API, engine and AI layer
│   ├── knowledge_base/
│   │   ├── materials.py            28 materials: properties, reuse routes, sectors, safety, DEMO factors
│   │   └── loader.py               loads data/*.json  ← swap for Supabase here
│   ├── matching/engine.py          deterministic scoring, safety layer, impact allocation
│   ├── ai/
│   │   ├── prompts.py              identification prompt (JSON-only, no facts allowed)
│   │   ├── fallback.py             deterministic keyword + composition classifier
│   │   └── identification.py       Ollama client + grounding against the KB
│   ├── services/
│   │   ├── analysis.py             the end-to-end pipeline
│   │   ├── storage.py              in-memory analysis store  ← swap for Supabase here
│   │   ├── chat.py                 grounded assistant
│   │   ├── dashboard.py            dashboard + impact aggregation
│   │   └── files.py                PDF / TXT / DOCX text extraction
│   ├── data/
│   │   ├── recipients.json         40 fictional recipients (DEMO DATA)
│   │   ├── sources.json            15 fictional sources (DEMO DATA)
│   │   └── generate_seed_data.py   regenerates the two JSON files
│   └── tests/                      47 tests: engine, safety layer, pipeline, HTTP API
├── frontend/
│   ├── app/                        /, /dashboard, /analyze, /matches, /matches/[id], /map, /impact, /knowledge-base
│   ├── components/                 Nav, MapView, Charts, FlowDiagram, Assistant, FileDrop, ui
│   └── lib/                        api.ts, types.ts, format.ts
├── database/schema.sql             PostgreSQL/Supabase schema for the 7 conceptual tables
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
| `POST` | `/api/analyze` | Run the full pipeline on a waste description |
| `POST` | `/api/matches` | Ranked matches, with filters (`sector`, `max_distance_km`, `min_match_score`, `min_quantity`, `reuse_type`, `processing`, `min_estimated_value`) |
| `GET` | `/api/matches/{analysis_id}/{recipient_id}` | One match: breakdown, reasons, cautions, pathway, weights used |
| `GET` | `/api/analyses`, `/api/analyses/{id}` | Stored analyses |
| `GET` | `/api/materials` | Knowledge-base materials |
| `GET` | `/api/recipients` | Demo recipients (optional `?sector=`) |
| `GET` | `/api/dashboard` | Metrics, recent analyses, top matches, categories, sector flow |
| `GET` | `/api/impact` | Totals, per-sector and per-source breakdown, formulas, factors used |
| `GET` | `/api/map` | Nodes + links; `?analysis_id=` for one analysis, otherwise the whole network |
| `POST` | `/api/chat` | Grounded assistant |
| `POST` | `/api/upload` | PDF / TXT / DOCX text extraction |
| `GET` | `/api/health` | Status, dataset sizes, Ollama availability |

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

## Safety classification

Every route carries one of `DIRECT_REUSE`, `REQUIRES_PROCESSING`, `INDUSTRIAL_ONLY`, `RESTRICTED`, `UNKNOWN`.

The rule-based layer (`matching/engine.py::safety_gate`) enforces:

1. **Hazardous** streams only go to recipients with `licensed_handling` capability.
2. **High-risk or hazardous** material is refused outright for community, farm and artisan recipients.
3. **Unidentified** material is offered *only* to a licensed waste processor, for assessment — never as a reuse route.
4. **Low identification confidence** (< 0.5) blocks casual-sector routes entirely.
5. The model **cannot downgrade** a KB hazard rating, and cannot mark a stream safe.

This is a demonstrable MVP safety layer, **not** a regulatory compliance engine. Real deployment needs jurisdiction-
specific rules, lab verification and chain-of-custody paperwork.

---

## Demo mode (without Ollama)

If Ollama is not running, `ai/fallback.py` classifies the material from knowledge-base keywords plus composition
markers (`SiO2: 55%` → fly ash, and so on). The result is clearly labelled `fallback_keyword` in the UI and its
confidence is capped at 0.78 to stay honest about being less flexible than the LLM. Everything downstream —
safety layer, scoring, impact — behaves identically.

---

## Database

The MVP needs no database. It runs on seeded JSON plus an in-memory store, so `pip install` + `npm install` is the
whole setup. The schema is nonetheless written out in **`database/schema.sql`**, covering the seven conceptual tables:

| Table | Holds | MVP equivalent |
|---|---|---|
| `materials` | material facts: properties, reuse routes, compatible sectors, safety | `knowledge_base/materials.py` |
| `impact_factors` | demo price + CO₂e factors, versioned and flagged `is_certified` | fields on the same records |
| `recipients` | potential users, coordinates, accepted materials, capability | `data/recipients.json` |
| `waste_sources` | where a stream comes from | `data/sources.json` |
| `reuse_pathways` | the 5-step route drawn on the match page | computed by the engine |
| `analyses` | one pipeline run: source, identification, warnings, totals | `services/storage.py` |
| `matches` | every ranked opportunity, **with all six score components stored** | `services/storage.py` |

Every column maps 1:1 onto the Pydantic model of the same name in `backend/models/schemas.py`, so moving to Postgres
or Supabase means re-implementing **two modules** and nothing else:

- `backend/knowledge_base/loader.py` → `SELECT` from the knowledge-base tables
- `backend/services/storage.py` → `INSERT`/`SELECT` on `analyses` and `matches`

No other module reads those files' internals, and no Supabase auth is required. Load the schema with:

```bash
psql "$DATABASE_URL" -f database/schema.sql
```

> The schema parses as valid PostgreSQL and its columns are checked against the Pydantic models, but it has **not**
> been executed against a live Postgres instance — no server was available in the build environment.

---

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
| Database | Supabase / PostgreSQL | Load `database/schema.sql`, then re-implement `loader.py` and `storage.py`. |

Two caveats worth knowing before you deploy:

- **Ollama is local by design.** A hosted backend cannot reach `localhost:11434` on your laptop. Point `OLLAMA_URL`
  at a hosted Ollama instance, or accept demo mode.
- **CORS is currently `allow_origins=["*"]`** in `backend/main.py`. That is fine locally; narrow it to your frontend
  origin before any public deployment.

---

## Tests

```bash
cd backend
python -m pytest -q          # 47 tests
```

They cover the scoring arithmetic and determinism, the haversine and component functions, all five safety rules,
knowledge-base integrity (every sector, reuse route and material reference resolves), unit conversion, the primary
demo scenario, and every HTTP endpoint including filters, uploads and the assistant's "I don't know" path.

```bash
cd frontend
npx tsc --noEmit             # typecheck
npm run build                # production build
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

**Map tiles are blank**
OpenStreetMap tiles need outbound internet access. On a restricted network the markers and connection lines still
render over an empty background.

**Analyses disappeared after a restart**
Expected. Analyses live in process memory (`backend/services/storage.py`) and the three demo scenarios are re-seeded
on startup. Implement that module against Postgres/Supabase for persistence.

**Upload says "No selectable text found"**
The PDF is a scan. OCR is deliberately out of scope for the MVP — type the description instead.

---

## What is deliberately *not* here

- Authentication and multi-tenancy — out of scope for the MVP.
- Real company data, live market prices, certified emission factors — all demo values, clearly labelled.
- A regulatory compliance engine — the safety layer is a rule-based demonstrator.
- OCR for scanned reports.
- A true Sankey layout library — the circular-flow view draws proportional ribbons with plain CSS instead, which
  keeps the dependency count down.
- Database persistence — see `backend/services/storage.py` for the single place to change.
