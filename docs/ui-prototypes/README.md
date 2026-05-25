# UI prototypes

Reference mockups for the CHRONOS frontend redesign. These are **design
artifacts**, not part of the running application — the shipped UI lives in
[`frontend/`](../../frontend/).

Each folder under `stitch/` is one screen, with both:

- `screen.png` — the rendered Stitch mockup
- `code.html` — the raw HTML/CSS Stitch emitted for that screen

The design system the mockups follow is documented in
[`stitch/chronos_archive/DESIGN.md`](stitch/chronos_archive/DESIGN.md)
(palette, typography, "no-line" rule, tonal layering, components).

## Screens

| Folder | What it shows |
|---|---|
| `start_screen/` | Pre-run landing — era selection / continue |
| `loading_screen_text_only/` | Character generation loading state |
| `game_active/` | Main turn loop — narrative + input |
| `observation_mode/` | Post-death, memory-decay observation |
| `erasure/` | Final erasure passage when the run ends |
| `hamburger_panel/` | Side menu (Map, Connections, New Run) |
| `chronos_archive/` | Design system reference (see `DESIGN.md`) |
