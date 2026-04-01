# Design System Document: Chronos

## 1. Overview & Creative North Star
This design system is built upon the Creative North Star of **"Chronos."** We are not building an interface; we are composing a historical record. Unlike traditional games that rely on heavy HUDs and flashing indicators, this system embraces the austerity of a literary folio. It is intentional, quiet, and authoritative.

The aesthetic rejects modern digital crutches—gradients, blurs, and rounded corners—in favor of a high-contrast, flat, and centered experience. By restricting the layout to a fixed **560px centered column**, we force the player’s focus onto the narrative, treating the screen as a singular page of history rather than a piece of software.

## 2. Colors & Tonal Hierarchy
The palette is rooted in the "Ink and Earth" philosophy. We use a deep, obsidian background to simulate the void of history, with text tones that mimic aged parchment and dried ink.

### The Palette
- **Background (`surface` / `#0e0c09`):** The absolute foundation. It must remain flat and void-like.
- **Primary Text (`on_surface` / `#c8b89a`):** Used for the primary narrative. This is your "fresh ink" on parchment.
- **Secondary Text (`on_secondary_container` / `#7a6a54`):** Used for flavor text, dates, and non-essential narrative.
- **Accent/Highlight (`tertiary` / `#8a7040`):** Reserved exclusively for critical player choices or significant historical entities.
- **Structural/Rules (`surface_container` / `#2a2218`):** The only color permitted for container backgrounds or "system" areas.

### The "No-Line" Rule
To maintain the editorial feel, **1px solid borders are strictly prohibited.** Boundaries must be defined solely through background shifts. If you need to separate the narrative from the system logic, place the system content within a `surface_container` (`#2a2218`) block. The transition from `#0e0c09` to `#2a2218` is the only "line" the user should see.

### Surface Hierarchy & Nesting
Depth is achieved through "Tonal Recess" rather than elevation:
1.  **Level 0 (Surface):** The narrative layer.
2.  **Level 1 (Surface-Container):** The structural layer (rules, stats).
3.  **Level 2 (Surface-Container-Lowest):** A deeper recess for "inset" information, like a footnote or a mechanical detail.

*Director’s Note: While modern systems use glass and gradients to create "soul," we achieve it through pure, flat contrast. Do not add glows or shadows. The power of this system lies in its absolute stillness.*

## 3. Typography
The typographic soul of the system is a tension between the **Scribe** (Narrative) and the **Record** (System).

- **Narrative (IM Fell English):** This is used for all `display`, `headline`, and `body` tokens. It represents the human element of history. It should feel organic and slightly irregular.
- **Structural (Special Elite):** This is used for all `label` and `title-sm` tokens. It represents the mechanical "truth" of the simulation—the cold, hard data of history.

### Typography Scale
- **Display-LG (IM Fell English, 3.5rem):** Chapter headings. Use sparingly.
- **Body-LG (IM Fell English, 1rem):** The primary reading experience. Ensure line-height is generous (1.6x) to facilitate long-form reading.
- **Label-MD (Special Elite, 0.75rem):** System data, tooltips, and mechanical "rules" text.

## 4. Elevation & Depth
Traditional depth (shadows and glass) is forbidden. Instead, we use **Tonal Layering** to convey hierarchy.

- **The Layering Principle:** To "elevate" a piece of information, do not bring it toward the user with a shadow. Instead, "recess" the background behind it. A block of text becomes a "card" by simply sitting on a `surface_container` (`#2a2218`) background.
- **Ghost Borders:** If a container requires a visual boundary for accessibility, use a **10% opacity** `outline_variant`. It should be felt rather than seen—a "ghost" of a border that guides the eye without breaking the flat aesthetic.
- **The 2px Constraint:** All containers, if they must have a shape, are restricted to a **2px corner radius**. This creates a "hand-cut" feel, avoiding the mechanical coldness of 0px while staying far away from the "app-like" feel of rounded buttons.

## 5. Components

### Interaction: The Ink Underline
There are no "Buttons" in this system. Interaction is treated as an **annotation**. 
- **Links/Actions:** Appear as standard text in `tertiary` (#8a7040).
- **Hover State:** An "Ink Underline" appears. This should be a 1px or 2px solid line directly under the text.
- **Active State:** The text shifts slightly in color to `primary_fixed` (#f2e1c1).

### Cards & Lists
- **No Dividers:** Never use horizontal lines to separate list items. Use **Spacing Scale 4 (1.4rem)** to create breathing room between items.
- **Recessed Cards:** Use `surface_container` for the card background. Ensure no shadow is applied.

### Inputs & Selection
- **Input Fields:** A simple `surface_container_lowest` (#100e0b) block. The cursor should be a simple vertical pipe.
- **Checkboxes/Radios:** Use the `Special Elite` font to render an "X" for selected states. Do not use standard rounded radio buttons; use square boxes with a 2px radius.

### Tooltips
Tooltips should appear as "Marginalia." Position them to the left or right of the 560px column when space permits, using the `label-sm` (Special Elite) typography to indicate they are "meta" information.

## 6. Do's and Don'ts

### Do:
- **Respect the Column:** Keep all primary content within the 560px center. The "white space" (black space) on the sides is as important as the text.
- **Embrace Asymmetry:** While the column is centered, text within it can be ragged-right. Avoid justified text to maintain the "hand-written" manuscript feel.
- **Use "Special Elite" for Logic:** Whenever the game is talking about *mechanics* (e.g., "+5 Loyalty"), use the system font. Whenever it is telling a *story*, use IM Fell English.

### Don't:
- **No Gradients:** Flat color only. Soul comes from typography and spacing, not color ramps.
- **No HUD Elements:** Do not pin elements to the corners of the 1920x1080 canvas. Everything must flow within the manuscript column.
- **No Standard Buttons:** If it looks like a "button" from a website, it is wrong. It should look like a word you are choosing to emphasize.