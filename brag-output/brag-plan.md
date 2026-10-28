# Brag Plan: Symbio

## What is this app?
Symbio takes a messy description of a waste stream, has a local model name the material, runs a deterministic
engine against a knowledge base to find who can actually reuse it, and shows a ranked, explainable match with its
economic and environmental upside — built around one hard rule: the language model never determines a match score.

## The angle
This is not a joke project, so the angle is not a punchline — it's the architecture itself. In a year when every
product claims "AI-powered," Symbio draws a hard, visible line: the model reads and names, a deterministic engine
scores, and the two never swap jobs. The video plays that boundary completely straight, then proves it by walking
one real stream — fly ash, 5 tonnes a month, Chennai — all the way through identification, ranking, and the safety
layer that can refuse a match the model would have allowed.

## Hook (first 2-3 seconds)
A single line, serif display type, full-bleed on the honeydew canvas, nothing else on screen:
"Every month, something is thrown away nearby that something else is waiting for."
Long settle before anything else happens — the first beat of a slow, confident video, not a fast one.

## Key moments (the middle)
- The pipeline stated once, node by node, with a line drawing itself between each step — not a bullet list.
- "The language model never determines a match score." — the one architectural claim the whole product is built
  around, held long enough to actually land, then proven by a two-row split: what the model is allowed to do,
  and what only the deterministic engine does.
- The six-factor score breakdown filling in bar by bar (compatibility, quantity, location, sector, value,
  environmental) — the arithmetic behind a single ranked match, not an abstract chart.
- The safety layer refusing a hazardous stream — "Spent catalyst · hazardous" routed only to licensed recyclers,
  every household/farm/artisan recipient excluded and named as excluded.

## Outro / punchline
"Every score has a reason. Every reason has a source." — held on empty canvas, then the Symbio wordmark, the
tagline, and a quiet CTA. No swell, no slam-in. The video ends the way it opens: unhurried.

## User flow worth showing
The centerpiece of the video is the real analyze flow, not the landing page:
1. **Entry** — `/analyze`, the "Fly ash · 5 t/month · Chennai" example chip, clicked, then "Analyze with Symbio" pressed.
2. **Key action** — identification resolves: Fly Ash, ~80% confidence, composition read out field by field
   (SiO₂ 55%, Al₂O₃ 25%, CaO 8%, Fe₂O₃ 6%).
3. **Result** — the top match, Coromandel Cement Materials (Cement Manufacturing, ~10 km, ~₹9,750/month,
   1.8 t CO₂e avoided/month), with the pathway drawn left to right: Industrial Waste → Fly Ash → Processing →
   Cement Manufacturing → Blended Cement / Concrete.

## Tone
- Preset: polished
- Creative direction: a quiet, confident explainer for an infrastructure-grade product — closer to an investor-deck
  demo film than a social sting. Restraint is the style.
- Interpretation: long holds, slow crossfades, generous letter-spacing, mixed-case type, one idea on screen at a
  time. Pacing stays unhurried throughout — this is the single biggest lever for the user's explicit request that
  the video read slowly and clearly rather than move fast.

## Format: landscape — 1920x1080
## Duration: 150 seconds (target range 140-165s)

**Note on duration:** this intentionally overrides the skill's default 15-25s creative law. The user explicitly
asked for a 2-3 minute runtime with deliberately slow pacing, because prior /brag output moved too fast to read.
Every scene below is held well past the minimum reading floor — this is a slow explainer cut, not a compressed
sting stretched thin.

## Visual identity (from the project)
- Background (canvas): `rgb(238 243 234)` — pale honeydew
- Card surface: `rgb(231 239 226)`
- Accent (CTA / insight / key metric, pale amber fill): `rgb(241 227 121)`, text-safe amber: `rgb(110 94 6)`
- Brand/teal (navigation, links, "safe/circular"): `rgb(135 187 162)`, text-safe: `rgb(47 107 84)`
- Danger/safety (cherry, used sparingly): `rgb(80 3 3)`
- Text strong: `rgb(16 31 36)` · Text body: `rgb(27 46 52)` · Text faint: `rgb(78 101 112)`
- Display font: serif — 'Iowan Old Style' / Palatino / Georgia (headings only)
- Body font: system sans stack (ui-sans-serif / system-ui / Segoe UI / Roboto)
- Strongest visual element: the live "Waste → Symbio → Next use" three-column row from the homepage hero, and the
  six-factor weighted score bars from the scoring section — both are real product material, not invented graphics.

## Share copy (draft)
Symbio tells you what your waste actually is, who wants it, and why — the model identifies, it never decides the score.

## Audio direction
- Role: warm, restrained bed under a mostly-quiet mix; audio supports the slow pacing, never pushes against it
- Music: a calm, low-key ambient / minimal-piano-adjacent bed — unhurried tempo, no aggressive percussion
- Music treatment: starts under the hook at low volume, stays low and steady through the explainer beats, allowed
  one gentle swell under the score-bars and safety-layer scenes, fades to near-silence for the outro line before
  the logo
- Music cue guidance: no bundled track selected yet — detect cues at composition time (`npx hyperframes beats` or
  `analyze_music_cues.py`). Target 2 strong cues: one under the "one rule" statement (scene 4) and one under the
  top-match reveal (scene 7). Sequential reveals (pipeline nodes, score bars) should snap to every other beat, not
  every beat, so each label still gets its full reading hold.
- Audio-reactive treatment: subtle only — a faint presence/glow on the amber accent during the score-bar fill,
  nothing louder than that
- SFX posture: sparse. A soft tick on each pipeline node arriving, a single quiet confirmation chime when the top
  match card settles, a dry low tone (not an alarm) under the safety-layer refusal. No whoosh, no cartoon stings.
- Audio-coupled moments: the composition field reading out line by line, the six score bars filling one at a time,
  the pipeline nodes connecting in sequence, the excluded-recipient list appearing one by one in the safety scene
- Restraint rule: audio must never rush a reveal to hit a beat, must never be louder than the narration-free
  reading rhythm calls for, and must stay out of the way during every held text line

## Storyboard

### Scene 1 — Hook — 10s
Full-bleed honeydew canvas. One serif display line fades and settles, center, generous margins:
"Every month, something is thrown away nearby that something else is waiting for."
Nothing else on screen. No logo yet.
Sequential/interaction: none
Audio intent: quiet, open, a held breath before the product starts speaking
Audio-coupled idea: none — let the line sit in near-silence
Music: calm ambient bed entering just under audible, almost nothing yet
Transition mood: soft crossfade → Scene 2

### Scene 2 — Brand reveal — 10s
The hook line fades. "Symbio" wordmark settles center in tracked-out uppercase eyebrow style, then the real
tagline beneath it in serif display: "Find the next best use for your material." Both lines fully settled and
held — this is the only place the logo appears alone.
Sequential/interaction: wordmark arrives first, tagline follows ~1s after, both then hold together
Audio intent: a single calm confirmation the product has a name
Audio-coupled idea: one soft chime on the wordmark's arrival
Music: bed stays low
Transition mood: soft crossfade → Scene 3

### Scene 3 — The pipeline — 18s
The seven-stage pipeline from the project's own framing, read left to right, one node revealing at a time with a
thin connecting line drawing between each pair as it arrives, each node held before the next appears:
WASTE SOURCE → AI IDENTIFICATION → MATERIAL KNOWLEDGE BASE → POTENTIAL USERS → MATCHING ENGINE →
RANKED OPPORTUNITIES → ECONOMIC + ENVIRONMENTAL IMPACT.
By the end all seven are on screen together, connected, held for a beat as a whole shape.
Sequential/interaction: yes — 7 nodes arrive one by one (~2.2s apart), each gets a settled hold before the next
Audio intent: steady build, mechanical confidence, not excitement
Audio-coupled idea: a soft tick on each node's arrival, synced to the reveal
Music: bed holds steady under the sequence
Transition mood: clean crossfade → Scene 4

### Scene 4 — The one rule — 14s
Full-bleed statement, serif display, center: "The language model never determines a match score." Held alone for
several seconds. Then it shrinks to the top and a simple two-row split appears beneath it, each row settling in
turn: "The model reads, names, and suggests." / "The deterministic engine scores, every time, the same way."
Sequential/interaction: yes — headline holds alone, then the two rows arrive one after the other and both hold
Audio intent: this is the thesis statement of the whole video — let it breathe, no rush
Audio-coupled idea: none on the headline; a very soft tone under each of the two rows arriving
Music: one gentle swell begins under this scene
Transition mood: soft crossfade → Scene 5

### Scene 5 — Entry: Analyze a stream — 14s
Recreation of the `/analyze` screen. The "Fly ash · 5 t/month · Chennai" example chip sits on screen; a cursor
moves to it and clicks — the chip highlights and the form fields populate. The cursor then moves to the
"Analyze with Symbio" button and presses it; a brief, calm loading state plays.
Sequential/interaction: yes — simulated click on the chip, fields populate, simulated click on Analyze
Audio intent: the UI feels real and used, not narrated
Audio-coupled idea: a soft UI tap on each simulated click
Music: bed continues, unobtrusive
Transition mood: clean crossfade → Scene 6

### Scene 6 — Identification resolves — 14s
Result panel settles: "Identified as Fly Ash" with "~80% confidence" beside it. Beneath, the composition reads out
field by field, each line arriving and holding before the next: SiO₂ 55%, Al₂O₃ 25%, CaO 8%, Fe₂O₃ 6%.
Sequential/interaction: yes — 4 composition lines arrive one by one with a settled hold each (~1.3s apart)
Audio intent: precise, factual, almost clinical calm
Audio-coupled idea: a very soft tick per composition line
Music: bed steady
Transition mood: soft crossfade → Scene 7

### Scene 7 — Top match — 16s
The ranked match card settles: "Coromandel Cement Materials — Cement Manufacturing," ~10 km, ~₹9,750/month,
1.8 t CO₂e avoided/month. Beneath it the pathway draws left to right, one link at a time, each held:
Industrial Waste → Fly Ash → Processing → Cement Manufacturing → Blended Cement / Concrete.
Sequential/interaction: yes — the card settles first and holds, then the 5-stage pathway draws in sequence
Audio intent: the payoff of the whole flow — this is the "proof" moment, give it the most room
Audio-coupled idea: one clear confirmation chime as the match card settles; soft ticks as the pathway draws
Music: the gentle swell from Scene 4 can peak quietly here, then begin easing back
Transition mood: soft crossfade → Scene 8

### Scene 8 — The score, shown — 16s
The six weighted components from the real scoring model fill in as horizontal bars, one at a time, each labeled
and held before the next starts: Material compatibility 30, Quantity fit 20, Distance 15, Sector fit 15,
Economic value 10, Environmental benefit 10.
Sequential/interaction: yes — 6 bars fill in sequence (~2.2s apart), each fully settled before the next begins
Audio intent: methodical, transparent — the arithmetic made visible
Audio-coupled idea: a soft tick as each bar finishes filling
Music: bed eases back toward calm
Transition mood: clean crossfade → Scene 9

### Scene 9 — The safety layer — 12s
The "Spent catalyst · hazardous" chip appears, then a plain-stated line settles beneath it: "Hazardous streams go
only to licensed recyclers." Beneath that, the excluded recipient types appear one by one, each named: household,
farm, artisan — each with a small refusal mark, not a dramatic red flash.
Sequential/interaction: yes — 3 excluded recipient types arrive one by one, each held
Audio intent: serious but calm — a rule being enforced, not an alarm
Audio-coupled idea: a single low, dry tone under the first line; soft, quiet ticks on each excluded type
Music: bed stays low and steady, no swell here — this scene earns restraint, not drama
Transition mood: soft crossfade → Scene 10

### Scene 10 — Scale — 10s
A quiet row of figures settles together, not counting up chaotically but arriving as a held set: materials known,
partners who can take something, tonnes diverted, CO₂e avoided. All four present together by the end, held.
Sequential/interaction: yes — 4 figures arrive in quick succession (~0.9s apart) then hold as a full row
Audio intent: a calm sense of real scale, not a hype montage
Audio-coupled idea: soft, even ticks as each figure lands
Music: bed begins its fade toward the outro
Transition mood: soft crossfade → Scene 11

### Scene 11 — Outro — 12s
Full-bleed canvas. Serif display line settles center: "Every score has a reason. Every reason has a source." Held
alone for several seconds, then fades as the Symbio wordmark and tagline return beneath it, with a small, quiet
"Analyze a material" line as the closing CTA. Long hold to the end, no slam-in.
Sequential/interaction: none — this scene is deliberately static and held
Audio intent: the video closing the way it opened — unhurried, settled
Audio-coupled idea: none
Music: fades to near-silence under the final hold
Transition mood: slow fade to end

**Music mood for this video:** calm, restrained, confident — closer to a quiet ambient bed than a music-led edit.
**Audio summary:** The mix stays low and steady for almost the entire runtime, with one gentle swell across the
thesis statement and the top-match payoff (scenes 4 and 7), a deliberately flat, non-dramatic treatment of the
safety-layer scene, and a fade to near-silence for the close — audio reinforces the slow, readable pace rather than
pushing against it.
