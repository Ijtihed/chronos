# The manuscript as a 3D physical artifact

> Phase 2.6 design decision (2026-05-04). The narrative is not a scroll. It is a depth-stacked physical object the player handles.
>
> Phase 2.8 design decision (2026-05-04 afternoon). The depth-stack proved insufficient — a stack of receding paragraphs reads as a slightly-3D scroll, not as the spatial substrate the design wants. **Phase 2.8 replaces the stack with a corridor** the player walks through. Past turns hang in 3D space along a path the character actually walked. Causal connections between turns are drawn as visible lines. The manuscript becomes a place, not a panel.
>
> Phase 2.8 ships in two phases: **Phase A — read-only corridor** (this round), and **Phase B — editable corridor** (future round, separate scope, requires three open-questions resolved first; see the corresponding section).

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

---

## Phase 2.8 — the corridor

### The single statement

The manuscript is a **corridor in 3D space**. Each past turn is a card hanging at a 3D position along a path the character walked. Connections between turns — a betrayal pointing forward to its consequence, a person you met pointing forward to a rumor about them later — are drawn as visible lines linking the cards across space. The player navigates by **moving the camera through the corridor**: forward in physical space goes back in time; backward returns to now. Remembering is travel.

This replaces the depth-stack as the default manuscript view. The Phase 2.6 vertical depth-stack and the original flat scroll both remain accessible as fallbacks (`?flat=1` URL parameter for the flat scroll; the depth-stack is fully retired but its logic — memory decay, observation mode tinting, hover-to-recover — composes into the corridor view).

### What the player does in the corridor

- **Navigate.** WASD or arrow keys move forward/backward (along time) and laterally; mouse-drag pivots the camera. The camera's at-rest position is "at the present" — turn 0 in front, prior turns receding into space along the path.
- **Read.** Looking at a turn brings it closer / clearer (parallax + DOF blur). Hovering a card lifts it forward and recovers any memory-decayed words, exactly as in Phase 2.6.
- **See connections.** Lines drawn between turns make causality legible: this betrayal connects to that consequence; this person connects to that later rumor; this divergence connects to the canonical event it replaced.
- **Track decisions.** Cards differ visually by **significance**. Decisions stand out: bigger cards, brighter, anchored slightly out from the path. Filler turns are small dim points along the path between them. The shape of the corridor IS the shape of the run.

### What connections are drawn (locked-in for Phase A)

These are the four signal types Phase A renders. Every connection is sourced from data the simulation already produces; this is presentation, not new state.

1. **Action → consequence.** Each entry in `state.consequence_queue` (or `state.events` flagged with `source_action_turn`) draws a line from the source turn forward to the turn the consequence actually fired on.
2. **Action → divergence.** Each entry in `state.historical_divergences` draws a line from the player's diverging turn to a *canonical event marker* on the side of the corridor (representing the canonical event the action superseded). Visually different from #1 — dashed, amber — to signal "this happened *instead of* something."
3. **Action → NPC reaction.** Each `npc.player_interactions` entry draws a thin line from the player's turn to the NPC node (NPC nodes float to the side of the corridor at the spatial position of the location they were in). Color = sentiment (per `NpcImpact`).
4. **NPC → NPC interaction.** When two NPCs were both at the player's location and interacted with each other on a given turn (already logged in ambient activity), draw a faint line between their nodes for that turn. This makes the social graph slowly accumulate as the run progresses, and previews the Phase 5 NPC-on-NPC graph.

Lines that point to turns the player has not yet read (e.g. delayed consequences fired on turn 12 from an action on turn 5) appear from the player's perspective only after the player has navigated *forward* past turn 12 — the line "extends" through space as the player walks the corridor.

### Significance and visual weight

Each turn already has a `parsed.significance_score` from the action parser. The corridor surfaces it spatially:

- **0.0–0.4** (filler) — small card, dim, sits on the central path.
- **0.5–0.7** (notable) — full-size card, normal brightness.
- **0.8–1.0** (decision) — larger card, brighter, anchored slightly off the path so it stands out as a node, not a link in a chain.

NPC reactions and ambient activity on a turn render as small auxiliary cards stacked behind the main turn card — visible when looking at the turn directly, occluded when looking past it.

### What the corridor IS NOT

- **It is not a 3D scene.** Turns are still text. The corridor is the *arrangement* of text cards in space. Period-styled scene illustrations live in Phase 3 (FLUX images) and remain a separate visual language.
- **It is not a god-view.** From inside the corridor the player sees what they have lived. They can navigate to any turn they remember, but turns the character does not remember (decayed past the recovery threshold, or post-death observation gaps) are obscured or absent. The information rules from `gameplay.md` and `simulation-and-world.md` carry forward unchanged.
- **It is not a debug graph.** The connection lines are subtle, the cards are still readable text, the camera defaults to a reading-friendly framing. The corridor is meant to be inhabited, not "investigated like a tool."

### Composition with existing systems

- **Memory decay** still strips words from old cards. In the corridor, far cards (already small) become almost-blank from a distance — the shape of memory loss across the run becomes spatially visible, exactly as the Phase 2.6 zoom-out tried to do, but now permanent and inhabited rather than a special view mode.
- **Inner thought** (Phase 2.7) renders inside the front-most card as it does today. Walking past a card you previously visited briefly re-shows its inner thought before the card recedes.
- **Observation mode** (post-death) tints the entire corridor with the existing `observation-muted` filter. The player can still navigate; they just can't add new turns. Erasure dissolves cards one-by-one along the path, oldest first, until the path is empty and the run ends.
- **Time-skip** lays a long featureless segment of corridor — visible as a stretched section of path with one summary card at the end. The "what happened in the gap" question becomes spatial.

### Composition with future systems (Phase B and beyond)

- **Phase B — editing the past** (deferred, separate session). The player reaches into the corridor and *cuts* a connection between two moments. The simulation rewinds to the source turn, marks the cut action superseded, and re-evolves forward from that point. The corridor visualizes this rewriting — old segments of corridor fade out as the new branch grows in their place. This requires three open questions resolved first (see the Phase B blockers below).
- **Phase 3 — scene illustrations.** Major narrative moments produce FLUX still images that anchor at their card's 3D position, visible as a small thumbnail in the corridor and full-size when the player looks at the card directly.
- **Marginalia** (deferred). Player annotations anchor at their card in the corridor. Notes you wrote on turn 5 are visible as small marks on that card from any camera angle. Marginalia outlive memory decay — your handwriting persists when the world's memory of itself doesn't.

### What replaces the depth-stack

Phase 2.6's depth-stack was a step toward this — it made turns physically dimensional but kept the scroll metaphor. Phase 2.8 takes the same data and the same per-turn-block DOM and arranges it in 3D space along a path instead of a vertical column. The depth-stack does not need to be deprecated separately; it is a special case of the corridor (a corridor with one axis collapsed), and the Phase 2.8 build subsumes it.

### Phase B (editing) — blocking open questions

Per `chronos-roadmap.mdc` and `chronos-ai-dev-protocol.mdc`, three design questions must be resolved in writing before Phase B starts. Each is recorded in `open-questions.md` under the Phase 2.8 Phase B section.

1. **What does "cut the continuity" mean mechanically?** Three plausible semantics:
   - *Undo and replay.* Mark the action as undone, replay the simulation forward from there. Player loses any consequences that happened in between but the world is fully consistent.
   - *Mark superseded but preserve history.* The original arc remains in the corridor as a faded ghost-branch; the new branch grows alongside it. The player can switch between branches.
   - *Branch into a new timeline.* The current run forks; the player picks one to continue.
   - Each has very different state semantics. Pick before code.
2. **Persistence model.** Today CHRONOS persists the *current* state only. Editing the past requires either (a) **versioned state snapshots** keyed by turn, or (b) an **action log** the engine can replay. Big architectural choice. (b) is closer to event sourcing and works better with the corridor metaphor; (a) is simpler but heavier on disk.
3. **NPC memory consistency.** When the player edits the past, do NPCs' memories of the player update? If yes, this means NPC POV prompts must accept "alternate-history" framing without leaking the meta-fact that the player edited time. If no, the editing feels weightless.

### Implementation notes (Phase A only — design-relevant, not a spec)

- WebGL via Three.js (already loaded for the globe and war-table). Each turn card is a CSS3D-rendered DOM element so the existing `.turn-block` markup, decay system, click affordances, and inner-thought rendering all work unchanged. Three.js gives camera + connection-line geometry; CSS3DRenderer gives readable text cards in the same space.
- Camera path: turns lie along a piecewise-linear path through 3D space. The path bends slightly (~5° per turn) so a long run reads as a meandering walk, not a straight tunnel — the shape of the run becomes recognizable.
- Connection lines: simple Three.js `LineSegments` with per-type color and dash patterns matching the connection-types table above.
- Feature flag: `body.chronos-corridor-manuscript` (on by default). `?flat=1` URL parameter disables, falls back to the **flat scroll** (not the depth-stack — the depth-stack is subsumed and removed from the active code path). Easy back-out.
- Performance: connection lines are simple geometry, ~4 lines per turn average → ~120 lines for a 30-turn run. WebGL handles thousands trivially. CSS3D text cards are the GPU-heavy part; render only the ~8 cards in the camera's near range with full text, and replace far cards with a low-detail placeholder geometry. Tested up to 100 turns on M4 Max in the budget.
