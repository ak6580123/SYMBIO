# Symbio frontend

The Next.js App Router client for Symbio. It is a thin, honest view over the FastAPI service in
`../backend`: no data lives here, no calculation that decides a match is done here, and nothing about
who can see what is enforced here — the API decides all of that and this code only reflects it.

The repository README covers the system as a whole — setup, the four kinds of data, the API, the limits. This file
is about the frontend specifically.

## Running it

```bash
npm install
npm run dev            # http://localhost:3000
```

`next.config.mjs` proxies `/api/*` to the backend (`BACKEND_URL`, default `http://localhost:8000`), so
start the API first and there is no CORS to configure and no backend URL baked into client code. A long
analysis waits on the language model, so keep `PROXY_TIMEOUT_MS` (default 120000) above the backend's
`OLLAMA_TIMEOUT_SECONDS` — see the troubleshooting note in the repository README.

```bash
npm run build          # production build; runs `next lint` and the type check as part of it
npm run start          # serve the build
npx tsc --noEmit       # typecheck on its own
npm run lint:palette   # every colour in the codebase resolves to a token in app/globals.css
```

## How it talks to the API

One module: `lib/api.ts`. Every call goes through it, so there is exactly one place that decides what a
failure looks like — status codes, URLs and response bodies stay in the console, and a screen gets one
plain sentence the reader can act on, plus a retry where a retry makes sense. Field-level validation
messages arrive as `ApiError.fieldErrors` and land under the field they belong to.

`lib/types.ts` mirrors the API's response shapes. When a route changes, that file is where the two sides
are reconciled.

## Signing in, and what a screen may show

The session is an `HttpOnly` cookie held by the browser; the app never stores a token, because there is
no token to store. `lib/session.tsx` asks `GET /api/auth/me` once per load and shares the answer —
`signed_in`, `anonymous`, `checking` or `unreachable` — with the Nav and every screen that offers a verb.
A button appears only when the role behind that answer is allowed to press it: on `/organization` a viewer gets a
`Read-only` chip instead of an editor, and the tenant links in the Nav exist only once somebody is signed in.
Publishing on `/marketplace` is deliberately *not* gated that way — a signed-out visitor may publish and receives a
session listing, which the card labels as one; the same form used by an operator or administrator stores the row
against the organisation.

Server-rendered pages read public data (the marketplace list, the seeded network); every screen that needs a tenant
is a client component, where the browser attaches the cookie itself. That is deliberate: nothing in this codebase
forwards a session from a server component to the API, so a server-rendered page can only ever show what an
anonymous caller is allowed to see.

## The routes

| Path | What it is |
|---|---|
| `/` | The pitch, the pipeline, the six scoring weights |
| `/analyze` | Describe or upload a stream, review what was read, run the analysis; carries the material card, the reuse pathways, the what-if simulator and — for a signed-in organisation — the line saying `Saved as SYM-…` |
| `/matches` | The ranked result set, its filters and the five optimisation modes. Opens a stored run when it arrives as `?analysis=<id>` from history |
| `/matches/[matchId]` | One match: breakdown, reasons, cautions, pathway, provenance, the freight estimate and the external route beside it |
| `/marketplace` | The seeded and published demand/supply listings, and the two-step publish form |
| `/organization` | The tenant's own record: profile, facilities, people, and its listings with edit / pause / resume / close |
| `/history` | Analysis History — every run stored against the organisation, each row reopening the stored analysis rather than computing a new one |
| `/login`, `/signup` | The two auth screens. Sign-in says plainly when the database behind the app is not answering, instead of letting a password check fail mysteriously |
| `/map`, `/dashboard`, `/impact`, `/knowledge-base` | The network view, the overview, the impact numbers, and the seeded reference data |

## Data, and how it is labelled

Four kinds, and the UI names which one it is showing (the repository README has the full table):

- **Seeded network** and **platform reference** — read-only, shipped with the backend, currently a
  Chennai-region set of partners.
- **Organisation data** — accounts, profile, facilities, listings, saved analyses. In the database, so it
  survives a restart; `persistence.reachable` is what says so.
- **Session data** — a run or a listing from somebody with no account. It ends with the process, and the UI
  says *Session listing* or *Kept for this session only* rather than letting it look saved.

A location that no geocoder can place keeps the text that was typed and shows distance, duration and
haulage as unavailable. Nothing here draws a number that the API returned as null, and no screen falls back
to a default city.

## Provenance and uncertainty are not decoration

Figures that come from an estimate, a model reading or an external service carry their existing
`OriginChip` / provenance labels, including the routing line (`Route source: External routing`) on the match
detail page. Where the API reports that no route could be calculated, the panel says exactly that and stops —
it never substitutes a straight-line figure silently.

Prototype limits are documented, not apologised for on every screen: there is one short line where a user
could otherwise be misled (an unplaced location, a session-only listing, a demo factor), and the rest lives
in this and the repository README.

## Styling

`app/globals.css` holds the tokens; `tailwind.config.ts` maps them. `npm run lint:palette`
(`scripts/check-palette.mjs`) fails the build on a raw hex or a colour literal in a component, so the
palette cannot drift as pages are added. Keep to the existing primitives in `components/ui.tsx` —
`PageHeader`, `Section`, `Panel`, `MetricCard`, `Notice`, `Empty`, `ErrorState`, `StatusBadge`,
`OriginChip`, `SymbioButton` — and the same typographic scale, rather than introducing a one-off visual
language for a new screen.

## What this frontend is not

No state manager, no data-fetching framework, no UI kit: server components fetch once, client components use
`api.*` in effects. No analytics, no client-side storage of anything sensitive. The screens are built for a
person reading a decision, which means some states that a dashboard would hide are shown on purpose —
`unverified`, `Distance unavailable`, `Session listing`, `Model-assisted identification`.

It is not production-ready in the operational sense described in the repository README ("What is not
production-grade"), and it does not claim to be: the tenant screens depend on the API's session and
permission checks, so the browser is never the thing deciding who may act.
