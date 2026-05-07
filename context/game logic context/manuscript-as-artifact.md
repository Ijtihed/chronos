# The manuscript and the pinboard

> Phase 2.6 design decision (2026-05-04). The narrative is not a scroll. It is a depth-stacked physical object the player handles.
>
> Phase 2.8 design decision (2026-05-04 afternoon). Tried a 3D corridor manuscript as the primary view. Shipped, lived three commits, and **failed the design intent**: forced 3D camera control to read a paragraph. Player feedback: "lets get this game finished e2e."
>
> Phase 2.9 design decision (2026-05-07). **The 3D corridor is deleted.** The legacy scrollable manuscript is the only manuscript. The "spatial" interaction lives in a separate **pinboard panel** to the right of the manuscript. Pins are passages the player highlights and clips; connections between pins are auto-proposed by the system but always from the player's perspective (`PlayerView`, never `WorldState`).

This doc is the source of truth for how the manuscript reads and how the pinboard composes with it. It is the textual counterpart to [visuals.md](visuals.md) (scene illustrations) and [simulation-and-world.md](simulation-and-world.md) (the world's spatial surfaces — globe and war-table).

## The single statement

The manuscript is **flat reading**. Words on a column. The player scrolls.

The pinboard is the **spatial layer**. The player highlights text in the manuscript, the highlighted passage becomes a pin on the right-side panel, and the player drags / connects / cuts pins as they curate their own understanding of the run. The manuscript answers *what happened*; the pinboard answers *what the player thinks it means*.

The depth-stack from Phase 2.6 (`body.chronos-stacked-manuscript`) **stays alive** as the manuscript's recession metaphor — past turn-blocks recede in z as new turns land, hovering recovers them, scrolling pulls back through depth. That is not a separate view; it is the way the legacy manuscript reads. Phase 2.9 only deleted the 3D *corridor* surface (Phase 2.8) and its persisted state.

## Why this exists

CHRONOS's whole thesis is the world is much larger than the player and they are a lens, not a center. The player's only durable artifact across a run is the narrative they have generated. The 3D corridor tried to make navigating that artifact a spatial experience and overshot — it forced 3D camera handling for a fundamentally textual object.

The pinboard is the design's second answer: keep the manuscript as readable text, but give the player a separate space to *act on* the text. Highlight what mattered. Drag the highlighted moments around. Draw lines between them. Cut the lines that don't hold up. The player is doing what a real reader of a chronicle does: making notes in the margin, not navigating the text in 3D.

## The two surfaces, on screen at once

```
┌──────────────────────────────────────────┐ ┌────────────────────┐
│                                          │ │                    │
│                                          │ │                    │
│        manuscript (left, 60%)            │ │   pinboard (40%)   │
│        scrollable column                 │ │   pinned passages  │
│        depth-stack recession applied     │ │   + connections    │
│                                          │ │                    │
│                                          │ │                    │
└──────────────────────────────────────────┘ └────────────────────┘
                  bottom input bar (full width)
```

The pinboard is **always visible** when a run is active. There is no toggle. The split is fixed at 60/40 by default; the user can drag the divider in a future commit but not in 2.9.

## What a pin is

A pin is a passage of text the player has selected from their manuscript and clicked **Pin this**. The selected text, the source turn id, and the offsets within that turn are saved server-side. The pin appears as a small absolutely-positioned card on the pinboard panel.

A pin carries a `source_confidence` field, classified at the moment of pinning by reading [PlayerView](../../backend/player_knowledge.py), not WorldState. The confidence values:

| value | meaning |
|---|---|
| `observed` | The player character witnessed it directly. The selected text comes from the player's first-person turn or its immediate sensory context. |
| `told_by` | An NPC told the player. The text was inside an NPC speech act in the source turn (`npc_responses[].text`). The pin remembers WHO. |
| `rumor` | The player overheard or heard secondhand. The text was inside an ambient activity entry or a reported-rumor narrative beat. |
| `inferred` | None of the above. The text was framing/atmosphere/narrator-grade prose; the character did not strictly observe it but reasonably knows it. Default fallback. |

The pinboard renders each pin's border to reflect its confidence — solid for `observed`, dashed for `told_by`, dotted for `rumor`, faint solid for `inferred`. The player sees uncertainty as soon as they pin, not after a tooltip.

This is a **player-perspective** field on `WorldState` and `PlayerView`. It is the first piece of persisted state in CHRONOS that explicitly encodes "what the character knew at the time of recording" rather than ground truth. See `open-questions.md` Phase 2.9 entry for why.

## What a pin connection is

A pin connection is a line drawn between two pins. Connections come in two flavors:

- **`player`** — the player drew the line themselves. They clicked one pin, then a second pin; a connection appeared. They can cut any player-drawn connection by clicking it.
- **`auto`** — the system proposed a line. Phase 2.9 ships with no auto-proposals (the data plumbing is ready but the proposer is not). Phase 2.10 (next commit, "propose / agree / edit / reject + before/after") adds the proposer behind the same data model.

A cut connection persists with `cut: true`. The simulation does not change when a connection is cut. Cuts are **visual + explanatory** in the same sense the corridor's cuts were. Phase B simulation rewinds remain blocked by the same three open questions; the answer to "what does cut mean mechanically" is still pending.

## What stays the same

- The reading column width, type sizes, line heights, ground name, edge vignette, season tint, memory motes, chrome handles, bottom bar, time-skip control, hamburger panel, status indicators, and all click affordances introduced in passes 1–7 (`act-name`, `act-rumor`, `act-year`, ground-click-to-travel) remain exactly as they are.
- Memory decay still strips words from old turns. The pinboard pin captures the *original text* at the time of pinning — a pin is a permanent record even if the underlying turn's words later decay. (This is a deliberate choice: the player's own notes don't fade. Future Phase 6 may revisit.)
- Inner thought (Phase 2.7) still renders inside the front-most turn-block.
- Observation mode (post-death) tints the manuscript with the existing `observation-muted` filter. The pinboard panel inherits the same tint.
- Erasure remains the existing fade overlay; pins fade out with the rest of the run when erasure begins. There is no special pinboard erasure animation.

## What is explicitly NOT in scope (Phase 2.9)

- **Auto-proposed connections.** Plumbing is ready (`PinConnection.kind = "auto"` is a valid value), but no proposer fires. Phase 2.10 adds it.
- **Connection labels.** Player-drawn connections have no label in 2.9. Pin connections in 2.10's propose flow get an editable label per the user's "edit_label_and_meta" decision.
- **Connection cut semantics that affect simulation.** Still blocked by Phase B open questions.
- **3D pinboard.** No.
- **Drag-to-resize the divider.** Fixed 60/40 split. A future commit can add resize.
- **Pinboard search / filter.** A future commit can add. Pins are sorted by creation time and rendered as-is.

## What the manuscript is NOT

- Not a book. There is no page-flip metaphor, no spine, no binding.
- Not a scroll. There is no parchment texture.
- Not skeuomorphic of any historical document type. The artifact metaphor is generic — "a record made of moments" — so it works in 410 AD Italia, 1453 Constantinople, and 1990s Mogadishu equally.
- Not interactive in a "click words to do things" sense. Selection-to-pin is the only new interaction the manuscript surface added in 2.9. Existing affordances (NPC names that travel, location names that show region info) continue to work.

## Implementation notes (design-relevant only)

- The 3D corridor is deleted: `frontend/corridor.js`, the `<canvas id="corridor-canvas">`, `body.chronos-corridor-manuscript`, the corridor CSS block (~290 lines), and the `/api/run/{id}/board` endpoint were all removed in the same commit. The `WorldState.board_state` and `WorldState.cut_threads` fields were also dropped; sessions saved with them load via Pydantic's default `extra="ignore"` and the next save rewrites without them. No migration code.
- The pinboard runs on `frontend/pinboard.js` as vanilla DOM + SVG. No Three.js. Pins are absolutely-positioned `<div>`s; connections are SVG `<line>`s in a single `<svg>` overlay. Drag uses pointer events.
- Pin selection-to-pin uses the native `selectionchange` event on `#manuscript`. After 150ms of stable selection (>3 chars), a small **Pin this** floater appears near the selection. Click → POST `/api/run/{id}/pin`.
- Pin classification (`source_confidence`) runs server-side on POST `/pin`. It reads `PlayerView` for the relevant turn (npc_responses, ambient_activity, narrative segment offsets) and decides which bucket. **Deterministic.** No LLM call.
- Persistence: POST `/api/run/{id}/pinboard` accepts `{pins?, pin_connections?}` with partial-update semantics. The server replaces whichever field is sent and leaves the other untouched. POST `/api/run/{id}/pin` accepts a single new pin and returns the classified pin object so the frontend can render it immediately.
- Feature flag for the legacy manuscript fallback: `?flat=1` still disables the depth-stack class. The pinboard runs regardless.

## Phase 2.10 — propose / agree / edit / reject (shipped 2026-05-07)

The pinboard becomes *active*: after each turn (gated), the system proposes a connection between same-turn pins it thinks belong together; the player adjudicates.

### Decisions locked in (2026-05-07)

| topic | decision |
|---|---|
| **Trigger** | Auto, but gated. Proposer fires only when the player has ≥3 unconnected pins **and** ≥2 turns have passed since the last proposal. The frontend (`pinboard.js`) owns the gate. |
| **Scope** | **Same `source_turn_id` only.** The proposer never links pins from different turns. Tightest semantics; cheapest LLM call; honors information-as-geography (a connection between same-turn pins is something the character could plausibly recognize in the moment). |
| **Output** | **Claim only.** One short sentence asserting the connection. No before/after counterfactual. The "what would change" framing was rejected because it would lie about Phase B (simulation rewinds remain blocked). Honest about what we know. |
| **Edit policy** | When the player edits a proposal, the player's text replaces the system's; we set `PinConnection.meta.was_edited = true` but do NOT keep the system's original. Middle ground; doesn't hoard data. |
| **Reject policy** | **Tombstone.** Rejected pin pairs are persisted in `WorldState.rejected_pin_pairs`. Same pair (in either direction) is never re-proposed. Cascade-dropped when either pin is deleted. |
| **Popup placement** | Anchored at the proposed line's midpoint. Spatial — the player adjudicates where they'll see the result. |

### How the LLM call works

- New call site `connection_proposal` (Gemini Flash Lite via `call_llm`).
- Prompt template `prompts/connection_proposal.md` — 5 examples, JSON-shaped output, returns `{"claim": "..."}` or `{"claim": ""}` for "no connection."
- Per-call cost: ~$0.00006 (~120 input + ~30 output tokens). With the threshold gate, ~$0.0001-$0.0003 per typical 10-turn run. Far below the €0.022 median target.
- Failure mode: NoOp / circuit-breaker open / parse error → the proposer returns empty, the orchestrator skips the pair, the pinboard never blocks. Same robustness pattern as `inner_thought`.

### Three connection kinds, three visuals

| kind | visual | semantics |
|---|---|---|
| `player` | solid emerald line | Player drew it. Click cuts (visual only). |
| `auto_proposed` | dashed faint yellow line + small "?" marker at midpoint | System proposal awaiting adjudication. Click opens the popup. |
| `auto` | solid amber line | System proposal the player agreed (or edited) into. Click cuts (visual only). |

Cuts on `auto_proposed` connections are not allowed — the player must adjudicate first (agree, edit, or reject). After agreement the connection becomes `auto` and is cuttable like any other.

### Phase B still blocked

The same three open questions that blocked the cancelled Phase 2.8 Phase B carry forward: cut semantics, persistence model, NPC memory consistency under past-edits. **Phase 2.10 does NOT add simulation rewinds.** The player can agree / edit / reject and cut connections; the simulation does not respond. Phase B is unblocked only when the three questions are answered in writing.

## What is NOT in scope (Phase 2.10)

- **Simulation rewinds.** Still blocked.
- **Cross-turn proposals.** Same-turn-only is the rule.
- **Counterfactual narration.** Claim-only; no "without this, X would not have happened."
- **Player-typed connection labels for player-drawn lines.** Phase 2.9 lines stay label-less; only system-proposed lines have labels (which the player can edit on agree).
- **Multiple pending proposals at once.** One adjudicate popup at a time. Future commit can add a queue.
- **Proposal history / audit log.** A rejected pair is tombstoned; we don't keep a log of *which* proposals were rejected when. If you want a "you rejected 3 things this turn" UI, future commit.
