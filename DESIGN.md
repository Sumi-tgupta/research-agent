# Design Direction — "Emerald Horizon"

Visual identity for the research system. Companion to `BEST_OF_BEST_PLAN.md` and `PHASES.md`.

## Reference note

Requested reference: **ThreeUI `StructureFlowCollection`, variant "Emerald Horizon"** (Three.js
r128–r160). I could not fetch `threeui.com` — it's blocked by this environment's network
allowlist — so this direction is an **informed reconstruction** from the reference brief ("authored
Three.js field studies… particle domes, horizons, orbital systems, fluid fields, embers, vortexes")
plus standard Three.js particle-field technique. **If you paste the `StructureFlowCollection.tsx`
source, I'll match its exact motion, shaders, and parameters** when we build.

## Design thesis

The product explores a vast field of knowledge and makes *structure* out of it — decomposing a
question, sweeping web + academic sources, resolving them into a cited report. The interface should
feel like standing at the edge of that field. So "Emerald Horizon" isn't wallpaper: **the particle
field is the knowledge field, and it visibly forms structure as your answer forms.** That is the one
bold, ownable move — a background coupled to the live research pipeline — surrounded by quiet,
journal-grade reading.

- **Subject:** a multi-agent research assistant.
- **Audience:** researchers, knowledge workers, students.
- **The page's one job:** earn trust in the depth of the research, make watching it happen feel
  alive, then get out of the way for reading.

## Palette — jewel-toned emerald, not neon

Deliberately avoids the generic "near-black + acid-green" AI default: the emerald is a deep,
painterly viridian with atmospheric gradients, and a warm **Champagne** gold is the counterpoint
accent so the palette never reads monochrome.

| Token | Hex | Use |
|---|---|---|
| Abyss | `#05110D` | app base, deepest background |
| Deep Pine | `#0B241C` | gradient depth, panels, ink (light mode) |
| Viridian | `#1B8A64` | primary emerald — structure, primary actions |
| Aurora | `#46C7B8` | secondary glow, hovers, links |
| Horizon Glow | `#8FF0CB` | luminous horizon line + active particles (used sparingly) |
| Champagne | `#E7D3A1` | warm accent — citations, active focus, key numbers |
| Mist | `#E7F1EB` | primary text on dark |
| Sage | `#8FA79C` | muted labels, secondary text |

**Light mode** ("misted dawn"): pale mint-white base (`#F2F7F4`), Deep Pine ink, Viridian accents;
the full particle field is a dark-mode signature, so light mode tones it to a soft, static
pale-emerald gradient to protect readability.

## Typography — editorial-scientific, dual body

- **Display — Fraunces** (variable, high optical contrast). Headlines, the hero question, section
  titles. Editorial, scientific-journal warmth; not the default Inter/Geist everyone reaches for.
- **UI — Geist Sans.** Controls, nav, source cards, chrome. Clean and quiet.
- **Report body — Newsreader (serif).** The research report reads like a field journal — a
  deliberate serif contrast against the sans UI that signals "this is the considered output."
- **Utility — Geist Mono.** Citations `[1]`, source metadata, timestamps, and the agent-tracker
  step labels — the "instrument" voice.

All four are open-source (OFL / MIT) — free, in keeping with the project's free-only rule.

## Layout — Perplexity-style

**Hero / empty state** — the field is a star; the ask box floats over it.

```
          ~ Emerald Horizon field, full-bleed, gently flowing ~
       (Abyss → Viridian gradient, luminous mint horizon line)

                  Research, from the field up.            ← Fraunces display
           Ask anything. Watch sources become structure.

        ┌────────────────────────────────────────────────┐
        │  Ask a research question…               ⏎ Ask   │  ← glass ask box
        └────────────────────────────────────────────────┘
           Try:  caffeine half-life · microplastics · fasting
                     recent from your library ▸
```

**Answer view** — the field recedes; reading comes forward.

```
┌ ask box (docked, glass) ───────────────────────────────────────────┐
│ Does intermittent fasting boost metabolism?                   ⏎     │
└─────────────────────────────────────────────────────────────────────┘
┌ agent instrument strip (mono) ─────────────────────────────────────┐
│  ● Plan ─ ● Search ─ ● Papers ─ ◐ Verify ─ ○ Write ─ ○ Review       │
└─────────────────────────────────────────────────────────────────────┘
      ── background dims + blurs; glow only at the edges ──
┌ Report (Newsreader serif, journal-like) ──────┐  ┌ Sources ────────┐
│ Findings                                       │  │ Web (7)         │
│ Fasting improves insulin sensitivity [1][2]…   │  │ [1] NIH …       │
│ …though sources disagree on weight loss ⚠      │  │ Papers (4)      │
│ [interactive Recharts chart]                   │  │ [3] arXiv …     │
└────────────────────────────────────────────────┘  └─────────────────┘
   Follow-ups:  ( Risks? ) ( Who benefits most? ) ( vs. caloric restriction? )
```

## Signature — "the field that forms structure"

The particle field flows like a horizon at rest. As the pipeline runs, particles **converge from a
diffuse flow into a more ordered lattice** — literal *structure flow* — then calm when the report is
ready. Emerald atmosphere throughout; the warm **Champagne** appears *only* on citations and active
focus, so the eye is guided to what matters. This ties the ambient 3D to the real work of the app
instead of decorating over it.

## The Emerald Horizon background — spec

**Visual:** a large particle system (Three.js `BufferGeometry` points) forming a horizon plane that
recedes to a vanishing point; vertex displacement for slow flowing waves; additive mint glow near
the horizon; depth fog; a slow camera drift. Abyss→Viridian gradient sky.

**Reactive behavior (v2):** *idle/hero* = gentle flow · *running* = converge + energize, stepped by
the SSE pipeline stage · *complete* = settle to calm — synced with the agent tracker.

**Prominence (my recommendation — tell me to change):** full presence on the hero/empty state;
recedes to a dim, blurred, low-FPS ambient behind content while reading, so text always sits on an
AA-contrast surface.

## Performance & accessibility (non-negotiable)

- **Three.js r128** (matches the reference runtime and our CDN constraint). Loaded via **dynamic
  import** with a CSS-gradient placeholder that the canvas fades into — it never blocks first paint
  or the research flow.
- **Cap `devicePixelRatio`**, scale particle count to viewport/GPU, run ambient at ~30fps, and
  **pause rendering when the tab is hidden or the canvas is offscreen** (battery- and free-host
  friendly).
- **`prefers-reduced-motion`** and **no-WebGL** → static emerald gradient; plus a visible **Motion
  toggle** in settings.
- Background is `aria-hidden`; all content sits on a dim/blur scrim to hold **AA contrast**.

## How this maps to the build

- **Phase 8** — load the four typefaces + palette tokens; ship background **v1**: static gradient +
  a calm ambient canvas, with reduced-motion/no-WebGL fallbacks and the pause logic. Non-reactive
  first, so nothing is fragile.
- **Phase 9** — background **v2**: couple it to the live pipeline (converge/settle), add the glass
  reading panels and Champagne citation accents, and do final motion tuning.
