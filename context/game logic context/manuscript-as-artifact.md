# The manuscript as a 3D physical artifact

> Phase 2.6 design decision (2026-05-04). The narrative is not a scroll. It is a depth-stacked physical object the player handles.

This doc is the source of truth for how the manuscript reads, behaves, and feels as a dimensional surface. It is the textual counterpart to [visuals.md](visuals.md) (which governs scene illustrations) and [simulation-and-world.md](simulation-and-world.md) (which governs the world's spatial surfaces — globe and war-table).

## The single statement

The manuscript is a **physical object**. Each turn is a layer in a stack. The current turn is closest to the player, in front of the screen. Older turns recede into z, atmospherically dimmed by distance in time. Scrolling pulls the camera **back through the stack** along the depth axis, not down a flat scroll. Hovering a deep block lifts it forward toward the camera, clears its haze, and (because of the existing memory-decay system) reveals its lost words.

This is not skeuomorphism. It is the design's claim that **the run is an artifact** — a thing made out of moments, with weight and depth. When the player engages with their past, they reach *into* the manuscript, not *up* it. When the run ends and erasure begins, what is dimming and dispersing is a *physical record*, not a transcript.

## Why this exists

CHRONOS's whole thesis is the world is much larger than the player and they are a lens, not a center. The player's only durable artifact across a run is the narrative they have generated. Phase 2 made the manuscript visually serious (typography, ground name, ambient noise, the chrome handles). Phase 2.5 made each turn legible as a discrete entity (turn blocks, year stamps, voices/scene split). Phase 2.6 makes the entire stack of turns **physically dimensional**: the run has *depth* you can feel.

The benefit is not visual. It is **felt time**. A 30-turn run that scrolls flatly looks like a long document. A 30-turn run that recedes into z looks like a stretch of life that happened to a person.

## Composition with existing systems

This is a presentation change. No backend, no LLM, no prompt, no schema. The data layer is unchanged.

- **Memory decay** (`m-word`, `m-word--lost`, `m-word--ellipsis`) reads as both word loss (existing) and atmospheric distance (new). They compose: a deep, decayed turn looks far away *and* missing words. Hovering it (`.recovering`) brings it forward *and* recovers its words.
- **Zoom-out** (`Z` key, `manuscript.zoomed-out`) becomes a **pull-back through the stack** rather than a 2D scale. The constellation effect emerges naturally as parallax.
- **Observation mode** (`observation-muted` filter) composes with the depth filters. The post-death manuscript still recedes; it just does so under the muted color treatment.
- **Erasure** is preserved in shape — the existing erasure overlay still owns the final fade. A future iteration could let the artifact close as a physical object before the overlay takes over (a Phase 2.7 or Phase 6 idea), but that is not in scope here.

## Composition with future systems (deferred, documented)

- **Marginalia** (deferred to a separate session) anchors at the depth of its turn. Notes the player wrote on a turn 25 turns ago sit *with that turn* in z — visible as small marks on the recessed page when zoomed-out, fully readable on hover-to-recover.
- **Pinboard** (deferred): physically separate surface, not part of the manuscript stack.
- **3D scenes for events** (deferred — a Phase 3 pivot conversation): would render in front of the stack at z=0 as part of the current turn block, then fade with the turn as it recedes.

## What the manuscript is NOT

- It is not a book. There is no page-flip metaphor, no spine, no binding.
- It is not a scroll. There is no parchment texture, no rolled top/bottom.
- It is not skeuomorphic of any specific historical document type. The artifact metaphor is generic — "a record made of moments" — so it works in 410 AD Italia, 1453 Constantinople, and 1990s Mogadishu equally.
- It is not interactive in a "click to do things" sense. The interaction is **handling** — scrolling through depth, hovering to lift, zooming out to see the shape of the run. It does not contain action affordances.

## What stays the same

- The reading column width, type sizes, line heights, ground name, edge vignette, season tint, memory motes, chrome handles, bottom bar, time-skip control, hamburger panel, status indicators, and all click affordances introduced in passes 1–5 (`act-name`, `act-rumor`, `act-year`, ground-click-to-travel) remain exactly as they are. Pass 6 (depth) sits underneath all of them and changes the *spatial relationship between turn blocks*, not the per-block presentation.

## Implementation notes (design-relevant only — not a spec)

- CSS 3D transforms only. No WebGL. No new dependencies.
- Feature flag: `body.chronos-stacked-manuscript` (on by default). `?flat=1` URL parameter disables, falls back to the pre-Pass-6 vertical scroll. Easy back-out if the depth treatment hurts long-run reading or breaks on unforeseen browsers.
- Browser caveat: Safari has historic 3D context bugs. If a user's browser breaks under the depth treatment, we ship a `body.chronos-no-3d` opt-out rather than degrade silently.
