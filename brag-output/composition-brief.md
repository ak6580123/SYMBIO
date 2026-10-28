# Hyperframes Composition Brief: Symbio

## Objective
Create a slow, readable, polished explainer-style launch video for Symbio — an AI-powered circular-economy waste
matchmaking platform. This run intentionally targets 2-3 minutes with long, legible holds (user-requested override
of /brag's default 15-25s), not a fast sting.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080, 30fps
- Duration: ~150 seconds (target range 140-165s) — see "Note on duration" in `brag-plan.md`

## Source Material
- Project root: `C:\Users\ASUS\Downloads\sprint4\symbio`
- Primary files read: `frontend/app/page.tsx` (landing page), `frontend/app/globals.css` (design tokens),
  `frontend/app/layout.tsx` (metadata), `frontend/tailwind.config.ts` (palette/fonts), `README.md` (product
  description, demo flow, scoring formula, safety rules)
- Product name: Symbio
- Tagline / strongest claim: "Find the next best use for your material." / "The language model never determines a
  match score."
- Key UI or visual moment to recreate: the homepage hero's live "Waste → Symbio → Next use" row, the `/analyze`
  flow (example chip → identification → top match), and the six-factor weighted score bars from the scoring
  section.
- Copy that must appear verbatim:
  - "Find the next best use for your material."
  - "The language model never determines a match score."
  - "Fly ash · 5 t/month · Chennai"
  - "Identified as Fly Ash" / "~80% confidence"
  - "Coromandel Cement Materials — Cement Manufacturing"
  - "Material compatibility 30 / Quantity fit 20 / Distance 15 / Sector fit 15 / Economic value 10 /
    Environmental benefit 10"
  - "Spent catalyst · hazardous"

## Creative Direction
- Tone preset: polished
- Creative direction: a quiet, confident explainer for an infrastructure-grade product — closer to an
  investor-deck demo film than a social sting. Restraint is the style; long holds, slow crossfades, generous
  letter-spacing, mixed-case type, one idea on screen at a time.
- Interpretation: this is the lever for the user's explicit request to slow the whole video down — no snappy
  slide-up-and-fade defaults, no rushing text off screen. Every held line gets real reading time; see per-scene
  durations in `brag-plan.md`.
- Angle: Symbio draws a hard, visible line between what its AI model is allowed to do (read, name, suggest) and
  what only a deterministic engine does (score, rank). The video states that boundary once, plainly, then proves
  it by walking one real stream — fly ash, 5 t/month, Chennai — through identification, ranking and the safety
  layer.
- Hook: "Every month, something is thrown away nearby that something else is waiting for." — full-bleed, alone,
  long settle.
- Outro / punchline: "Every score has a reason. Every reason has a source." — held alone, then wordmark + tagline
  + quiet CTA.
- Avoid:
  - Generic SaaS language ("streamline your workflow" etc.)
  - Abstract filler visuals / generic motion graphics
  - Any claim not grounded in the project's own copy, README or UI (see Grounding note below)
  - Fast cuts, snap transitions, or text pulled off screen before it can be read

## Visual Identity
- Background (canvas): `rgb(238 243 234)` — pale honeydew
- Card surface: `rgb(231 239 226)`
- Text strong: `rgb(16 31 36)` · Text body: `rgb(27 46 52)` · Text faint: `rgb(78 101 112)`
- Accent (CTA / insight / key metric — pale amber fill, text-safe variant for text use): fill `rgb(241 227 121)`,
  text `rgb(110 94 6)`
- Brand/teal (navigation, links, "safe/circular" — text-safe variant for text use): fill `rgb(135 187 162)`,
  text `rgb(47 107 84)`
- Danger/safety (cherry, used sparingly, only in the safety-layer scene): `rgb(80 3 3)`
- Display font: serif, closest bundled match to 'Iowan Old Style'/Palatino/Georgia — use **Playfair Display** or
  **EB Garamond** (both bundled) for headings only
- Body font: system sans in the real product (ui-sans-serif/system-ui) — use **Inter** (bundled) for body/UI text
- Visual references from the project: the homepage hero's live stream row, the six-weight scoring bar list, the
  seven-stage pipeline diagram from the README (`WASTE SOURCE → AI IDENTIFICATION → ... → ECONOMIC +
  ENVIRONMENTAL IMPACT`), the amber/teal/cherry chip system (`chip-amber`, `chip-teal`, `chip-cherry` in
  `globals.css`)

## Storyboard
Use the storyboard in `brag-plan.md` as the creative contract — 11 scenes, ~146s total, all durations and
sequential-reveal timings specified there. Scene summary:
1. Hook — 10s — the opening line, alone
2. Brand reveal — 10s — Symbio wordmark + tagline
3. The pipeline — 18s — 7-stage pipeline, node by node
4. The one rule — 14s — "the model never determines a match score" + the two-row split
5. Entry: Analyze a stream — 14s — `/analyze` example chip clicked, Analyze pressed
6. Identification resolves — 14s — Fly Ash, ~80% confidence, composition read out
7. Top match — 16s — Coromandel Cement Materials card + 5-stage pathway
8. The score, shown — 16s — six weighted bars filling in sequence
9. The safety layer — 12s — hazardous chip, excluded recipient types
10. Scale — 10s — materials/partners/tonnes/CO2e figures
11. Outro — 12s — closing line + wordmark + CTA

## Audio
- Audio role: warm, restrained bed under a mostly-quiet mix; supports the slow pacing, never pushes against it
- Audio arc: low and steady for nearly the whole runtime, one gentle swell across scenes 4 and 7 (the thesis
  statement and the top-match payoff), deliberately flat/non-dramatic in scene 9 (safety layer), fade to
  near-silence for the close
- Music: `happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` (steady and clean, recommended for `polished` /
  `cinematic` in `audio.md`), volume 0.3-0.35, never above 0.5
- Music treatment: enters just under audible under the hook, stays low through the explainer beats, one gentle
  swell under scenes 4 and 7, fades to near-silence for the outro hold
- Music cue guidance: no bundled cue preset exists for vol-12 yet — detect cues at composition time via
  `npx hyperframes beats brag-output/composition` (no Python needed) and use the highest-strength beats as
  informal "strong" points if `analyze_music_cues.py`/`uv` is unavailable. Given the 150s runtime (far longer
  than the usual 15-25s), use strong-cue locking sparingly — 2-3 locks total across the whole video (scene 4's
  headline landing, scene 7's match-card landing, and optionally scene 11's wordmark return), not per-scene.
  Sequential reveals (pipeline nodes, composition fields, score bars, excluded types, scale figures) should use
  their own natural, reading-paced timing from `brag-plan.md` rather than being snapped to the beat grid — at
  this slow pace, music pulse should stay in the background, not drive text reveals.
- Audio-reactive treatment: subtle only — a faint presence/glow on the amber accent during the scene 8 score-bar
  fill. No waveform/equalizer visuals, no strobing.
- Audio-coupled moments:
  - Scene 3 (pipeline) — a soft tick as each of the 7 nodes arrives
  - Scene 4 (the one rule) — a very soft tone under each of the two split rows
  - Scene 5 (analyze entry) — a soft UI tap on each simulated click
  - Scene 6 (identification) — a very soft tick per composition line
  - Scene 7 (top match) — one clear confirmation chime as the card settles; soft ticks as the pathway draws
  - Scene 8 (score bars) — a soft tick as each bar finishes filling
  - Scene 9 (safety layer) — a single low, dry tone under the first line; quiet ticks on each excluded type
  - Scene 10 (scale) — soft, even ticks as each figure lands
- SFX selection guidance: polished tone → minimal but present, per `audio.md`'s tone table (`interface/bong_001`
  for soft accents, `interface/drop_001`/`drop_002` for gentle reveals, nothing aggressive). Scene 9's "dry low
  tone" should come from a restrained impact/interface file, not an alarm-like sound — avoid `error_*` and
  `glitch_*` entirely; this scene is a calm statement of a rule, not a failure state.
- SFX analysis guidance: read `<hyperframes skill dir>/assets/sfx/sfx-analysis.md` (via the `media-use` skill)
  before final selection; prefer low/medium high-frequency-risk files given how many times a soft tick repeats
  across this video's 20+ sequential reveals.
- Exact SFX choice: Hyperframes chooses exact filenames, timestamps, density and volume once the animation
  exists.
- Audio files: copy the chosen music (and any Hyperframes-selected SFX) into
  `brag-output/composition/assets/music/` and `brag-output/composition/assets/sfx/...` before rendering.

## Hyperframes Instructions
Load the composition-building Hyperframes skills — `hyperframes` (composition contract + `data-*` timing,
`references/format.md`; motion, eases and seek-safe keyframes in `references/motion.md`; look in
`references/look.md`), `hyperframes-registry` (ready-made effects, transitions, titles), `media-use` (music, SFX,
audio-reactive data), and `hyperframes-cli` (lint/check/render). This is `/brag`'s own workflow: skip the
`hyperframes` storyline step — don't read `references/types/*` or `references/story.md`, don't propose
storylines, and don't write a `SPEC.md`. `brag-plan.md` and this brief replace them, including the LOOK line
`references/look.md` asks for (declare the palette/fonts above as composition variables on the root `<html>`).
Also skip its `usage`, `history`, `feedback` and `REVIEW.md` steps; `hyperframes check` is brag's single gate.
Do not route into the generic launch-video workflow. Prefer native Hyperframes conventions over anything stated
here when they conflict.

Requirements:
- Show at least one real UI, copy, or visual element from the source project in nearly every scene (this video is
  built almost entirely from real product material — see Storyboard above).
- Keep all text readable in the final render — this is the user's primary request. Err toward longer holds, not
  shorter, if in doubt.
- Keep total duration in the 140-165 second range (overriding /brag's usual 15-25s default — see
  `brag-plan.md`'s "Note on duration").
- Include the planned music/SFX layer; it was not disabled and the tone (`polished`) explicitly calls for a
  restrained bed rather than silence.
- Treat the `/brag` audio notes above as guidance, not a fixed cue sheet; choose exact SFX after the visual
  animation exists.
- Treat music cue metadata as optional timing hints only; ignore cues that would rush a reading-paced reveal.
- Given the long runtime, 2-3 strong-cue locks total (not per-scene) is the right budget — see Music cue guidance
  above.
- Use SFX to support motion and interaction: card/drop sounds for sequential reveals, a single soft announcement
  cue for the two true payoffs (scene 4's thesis line landing, scene 7's match card landing), restrained tap
  sounds for the two simulated clicks in scene 5.
- Honor the planned music treatment (low entry, one gentle double-swell across scenes 4 and 7, flat scene 9,
  fade to near-silence at the close) using the best Hyperframes-supported implementation.
- Wire the subtle audio-reactive glow described above via the `media-use` audio-reactive workflow; if extraction
  is unavailable (no helper, or ffmpeg missing), note it and skip rather than blocking the render.
- Use local assets for audio and any required runtime/media dependencies.
- Run `hyperframes check` before render — it is brag's single gate.
- Keep creation and rendering local. Remote or publishing workflows require a separate explicit user request.
- **System note:** `hyperframes doctor` reported low available memory (~1.5 GB free of 15.4 GB total) on this
  machine. If a full-resolution render is unstable, prefer fewer parallel render workers / lower concurrency over
  silently dropping scenes or shortening the video, and surface the tradeoff before changing scope.

## Grounding note
Every factual claim in the video (names, numbers, capabilities, the scoring weights, the fly-ash example, the
safety-layer behavior) must trace back to `README.md` or the live `frontend/` source quoted in Source Material
above — all of it already does, per the storyboard. Tone, framing, the hook sentence, and the outro line are
original writing and are not claims about the product, so they do not need grounding.
