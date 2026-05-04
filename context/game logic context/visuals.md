# CHRONOS — Visuals

> Phase 3 scope. Scene illustrations that render alongside narrative text at moments of narrative weight. Not every turn. Augments text, never replaces it.

This document is the source of truth for CHRONOS imagery. It covers POV, body treatment, prompt construction, style, and provider choice. Phase 3 integration work references these rules.

## First-person POV is mandatory

Every CHRONOS scene illustration is rendered from the player character's first-person point of view. The viewer's own body appears in the lower foreground as the compositional anchor (hand, forearm, feet, lap, etc.), with the scene composed behind and around it. The camera is the character's eyes. No third-person framing. No visible face of the viewer. No photographer implied.

Scene framing (wide third-person shots, landscape establishers, crowd panoramas) was evaluated against POV framing in the POC (2026-04-22) and rejected. Third-person breaks the "you are this person" loop that is the core CHRONOS experience. The map is already a third-person view of space. Imagery is the first-person view of the moment.

When the scene has no natural body anchor (abstract moments, memory-fade), the viewer's body is still present, compositionally dominant, and dissolving or fading appropriately. It is never absent.

## Honest bodies

CHRONOS depicts ordinary historical people, not CGI action-movie extras. Diffusion models default to symmetric, muscular, young, attractive figures because their training data skews that way for tags like "warrior," "medieval," "historical." Prompts actively counter this default.

Every human figure in a CHRONOS image must read as a real person of their era and social class. For the CHRONOS target demographic (peasants, conscripts, minor provincial figures, plague victims, famine households), this means:

- Specified imperfections: missing teeth, crooked jawlines, cataracts, pockmarks from survived smallpox, broken noses, scarred cheeks, weathered sunburned skin, dirty broken fingernails, matted unwashed hair, lice, dirt ground into knuckles.
- Specified build for social class: thin wiry frames, stooped posture from subsistence labor, short stature, malnourishment. Not muscular.
- Specified grooming: patched clothing, fabric stained from months of wear and never washed, road dust, sweat, blood.
- Varied demographics: ordinary historical people were not uniformly young, white, symmetric, or healthy. Characters include older figures, gap-toothed figures, figures with visible disease, figures with broken bodies from accident or labor.

Anti-pattern vocabulary forbidden in prompts unless contextually correct for a named historical figure (a career sergeant, a named prince): *warrior, heroic, chiseled, muscular, handsome, beautiful, perfect, statuesque, athletic, strong, noble.*

The honest-bodies rule applies to every visible human, not only the viewer. Background crowds, corpses, guards, NPCs in scene all get the treatment.

## The v3 template

Every CHRONOS scene illustration prompt follows the same seven-part structural pattern, validated in POC (2026-04-22). Referred to in future work as "the v3 template."

1. **Body anchor lead.** The viewer's own body part, its clothing, its condition (wounds, dirt, disease, callus, scar). This is the first sentence of the prompt.
2. **Camera.** Height from ground (specify in feet or inches, historically plausible for the character's build), angle (low, eye-level, high), what the viewer is doing (lying, walking, running, sitting, on horseback).
3. **Film stack.** Named film stock (Kodak Portra 400 for warm color defaults, Fujifilm Superia for hot or saturated scenes, Ilford HP5 for black-and-white when thematically required), film gauge, lens focal length, depth of field, ambient light.
4. **Scene behind the anchor.** The world the viewer is looking at. Figures, architecture, weather, event in progress. Every human figure in the scene gets the honest-bodies treatment.
5. **Period anchor.** Year, region, named location, period-specific clothing, period weapons, period disease.
6. **Documentary tags.** Visible film grain, high dynamic range, historical reenactment documentary still, shot on location, unstaged.
7. **POV negatives.** No visible face, no visible torso, no third-person framing, no photographer visible, the viewer IS the camera.

Trigger-specific variations (camera height matches body posture, lighting matches scene, film stock matches mood) are allowed and encouraged. The seven-part structure is not optional.

Specific prompt strings for specific trigger types are production artifacts and live in `prompts/` at Phase 3 integration, not in this design doc.

## No painting references in prompts

Artistic references to specific painters (Goya, Caravaggio, Bruegel, Rembrandt, Wyeth, Friedrich) and painterly vocabulary (*oil painting, painterly, etching, chiaroscuro, tenebrism, oil on canvas*) are excluded from CHRONOS production prompts. They are aesthetically tempting because CHRONOS wants emotional weight. In practice they fight with photorealism: the model averages between the painter signal and the photo signal and produces painted output, which reads as stylized rather than honest.

Aesthetic style differentiation for CHRONOS, if pursued, comes from a LoRA trained on a curated corpus of historical paintings (Goya's *Disasters of War* is a candidate training set) applied on top of the photoreal base at generation time. This keeps prompts clean, reproducible, and photoreal by default, while leaving room for a style pass later. LoRA work is not currently scoped. Documented here as the intended path if style polish is wanted at Phase 3 integration.

## Provider

Current candidate, soft-locked by POC (2026-04-22):

- **Runtime:** `mflux` on Apple Silicon (MLX-native).
- **Model:** FLUX.2 Klein 9B distilled. 4 steps. Q8 quantization. Guidance at mflux default.
- **Measured on M4 Max / 64 GB:** ~60 seconds per image at 1024x1024, steady state. One-time ~10 minute Q8 quantization cache warmup on first load per tier.
- **Cost per run:** $0. No API calls. No content filter. All 10 CHRONOS scene types generated successfully in POC.

Final commit to this provider happens at Phase 3 integration kickoff. Commitment is soft until that point because production integration can reveal issues not visible in a 10-image POC: latency under concurrent load with active Ollama NPC inference, prompt stability across seed variation, runtime memory pressure, etc.

**Named fallback** if integration reveals blocking issues: `fal.ai` Flux 2 Dev API at approximately $0.025 per image. A full run of ~6 images costs ~$0.15 via fallback. This violates the local-first principle but stays within acceptable cost bounds.

Fallback is permitted only with a specific and documented local failure mode.

## Trigger count per run

Scene illustrations are reserved for moments of narrative weight. Standard trigger set:

1. **Run start.** Who the character is and where they are, as the first image of the run.
2. **Character death.** The moment the character dies, first-person from the viewer's own body.
3. **Erasure.** The final memory-fade moment, the viewer fading from the world.
4. **Two or three major narrative moments across the run body.** Candidates: a decisive player action (significance >= 0.8), a witnessed canonical historical event the character is present for, first arrival at a new location.

**Implementation status (2026-05-01).** The trigger detector in `backend/scene_triggers.py` implements run_start, character_death, erasure, and three signals for major_narrative_moment (high-significance player action, witnessed canonical event, first arrival at a new location). It does NOT implement a "first conversation in Addressed mode" trigger -- the file's docstring (lines 21-22) explicitly defers Signal 3 ("first encounter with a major NPC") because there is no first-class "major" flag on NPC today. A previous draft of this doc (2026-04-27) listed Addressed-mode first contact as a candidate trigger; that trigger does not exist in code. Deferred until **Phase 3 Step 3.3** ships actual image generation, at which point the trigger pipeline will be revisited end-to-end. The honest-bodies rule still applies: when image generation does ship, character descriptions in image prompts must be based on role, archetype, and era context, not hero-trope defaults.

Introspective turns ("I sit with this a while," "I think about what happened") are an aspirational extension and are also not currently triggered. Same deferral.

Typical run produces 5 to 6 images. Uneventful runs may produce as few as 3 (start, death, erasure). Exceptionally eventful runs rarely exceed 8. Triggers are gated on narrative weight, not turn count.

Images are ephemeral by design. They render in the UI alongside the narrative text for the triggered turn, remain visible during that turn, and are not persisted beyond the session. The narrative text is the durable record of a run. Images are the flash of recognition in the moment.
