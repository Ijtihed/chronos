# Phase 2d — Map Integration Manual Test Cases

> These tests verify WebGL rendering behavior that cannot be covered by backend unit tests or headless automation. Re-run whenever the frontend map code changes.
>
> Prerequisites: server running (`uvicorn backend.main:app --reload`), Ollama running with `llama3.1:8b`.

---

## Test 1: Toggle map mid-run — markers reflect current visited state

**Steps:**
1. Start a new run (click "Begin")
2. Take 2-3 actions in the starting location
3. Press `M` to toggle the map

**Expected:**
- Globe appears with coastlines and era borders visible
- Player marker (bright, glowing) is at the starting location
- NPC markers at the starting location are **visited** style (brighter, larger)
- NPCs at other locations (if any) are **unvisited** style (small, dim dots)
- "M to return" hint visible in bottom-right corner

**Pass/fail:** [ ]

---

## Test 2: Travel + toggle — new location is visited, camera panned

**Steps:**
1. From an active run, type "travel to Ravenna" (or equivalent destination)
2. Wait for the turn to resolve
3. Press `M` to open the map

**Expected:**
- Camera is focused on Ravenna (or the new location), not the old starting location
- Ravenna marker shows as **visited** (brighter)
- Starting location still shows as visited
- NPCs at Ravenna are visited-style markers

**Pass/fail:** [ ]

---

## Test 3: Observation mode — player marker at 40% opacity, NPC markers fade proportionally

**Steps:**
1. Force death (type something risky until you die, or use API: `curl -X POST .../turn -d '{"player_input":"charge the enemy army alone"}'`)
2. Press `M` to open the map

**Expected:**
- Player marker is **dimmed** (40% opacity, color shifted to 0x706050), not full brightness
- NPC markers are visible but **faded proportional to their memory_of_player value** — NPCs you interacted with more are brighter, NPCs you barely met are nearly invisible
- This is NOT a flat fade — different NPCs should be at different opacities

**Pass/fail:** [ ]

---

## Test 4: NPC with memory=0 — marker disappears, not just fades

**Steps:**
1. In observation mode, type travel commands repeatedly to advance time and decay memories
2. Check the map periodically (press M)

**Expected:**
- As NPC memories reach 0, their markers **disappear entirely** from the globe (not just fully transparent — the mesh should not be added to the scene)
- NPCs with remaining memory still show at reduced opacity

**Pass/fail:** [ ]

---

## Test 5: Erasure — all markers gone

**Steps:**
1. Continue traveling in observation mode until the last NPC memory reaches 0
2. The narrative should show the erasure passage
3. Press `M` to toggle the map

**Expected:**
- **No markers at all** — no player marker, no NPC markers
- The globe shows only coastlines and borders — an empty world
- The globe is still interactive (rotate/zoom works)

**Pass/fail:** [ ]

---

## Test 6: Rapid toggle — no race conditions or stale state

**Steps:**
1. During an active run, press `M` rapidly 10+ times in quick succession
2. Take a turn, then press `M` rapidly again

**Expected:**
- No errors in the browser console
- Map always shows the correct current state when visible
- No duplicate markers (multiple player markers, etc.)
- No "flash" of stale state followed by correction

**Pass/fail:** [ ]

---

## Test 7: State sync is always fresh — not cached

**Steps:**
1. Open the map (M), note the player position
2. Return to narrative (M), take a turn or travel
3. Open the map again (M)

**Expected:**
- The map reflects the **new** state after the turn, not the state from the previous toggle
- This should be true every time — the map never shows stale data
- Verify in the browser Network tab: each toggle to map makes a fresh `GET /api/run/{id}?_t=...` request with a unique timestamp

**Pass/fail:** [ ]

---

## Notes

- If any test fails, note the browser, OS, and console errors
- All tests assume the default Three.js globe view (no terrain in Phase 2)
- The `_t=Date.now()` cache-buster on the state fetch prevents browser caching
