#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mflux",
#   "pillow",
# ]
# ///
"""
CHRONOS image generation POC.

NOT production code. NOT integrated with backend/. Pure local generation
test to evaluate whether mflux on M4 Max can produce the imagery CHRONOS
needs before Phase 3 integration work begins. See README.md.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "out"

PROMPTS: dict[str, dict[str, str]] = {
    "hero_death": {
        "trigger_type": "player_death",
        "notes": "v3 photoreal-honest. Body-anchor lead, no painting refs, peasant conscript body.",
        "prompt": (
            "A thin grimy right hand — dirt ground under torn fingernails, "
            "a split callus on the thumb bleeding, tendons visible under "
            "sun-creased weather-worn skin, knuckles scabbed, a loose rusty "
            "iron ring-mail cuff fraying at the wrist, coarse undyed wool "
            "sleeve beneath — in the lower foreground of a first-person POV "
            "photograph. Low angle, camera approximately 2 feet off the "
            "ground, the viewer lying on the ground dying. Shot on Kodak "
            "Portra 400, 35mm film, 85mm lens, shallow depth of field, "
            "late autumn afternoon sunlight cutting low across wet trampled "
            "grass. Behind the hand: blurred boots and spear shafts of "
            "other soldiers moving past, a fallen painted wooden shield "
            "half-buried in mud, another dead conscript face-down a few "
            "feet away in a plain cheap leather jerkin — the unremarkable "
            "body of a peasant conscript, thin and short, grimy. Late "
            "medieval European battlefield, autumn. Blood on the grass, "
            "frozen breath, mud, scattered arrow shafts. Visible film "
            "grain, high dynamic range, historical reenactment documentary "
            "still, shot on location, unstaged. No visible face, no "
            "visible torso, no third-person framing, no photographer "
            "visible, camera at ground level, the viewer IS the camera."
        ),
    },
    "hero_erasure": {
        "trigger_type": "memory_fade_terminal",
        "notes": "v3 photoreal-honest. HAND fading. Ordinary hand, no painter refs.",
        "prompt": (
            "A thin weathered right hand extended into a thick grey fog in "
            "the lower foreground of a first-person POV photograph — the "
            "hand partially translucent, fingertips already invisible, "
            "knuckle outlines softening, the image itself washing out at "
            "the edges, coarse grey-brown woolen sleeve fraying into mist "
            "at the wrist, the hand of an ordinary person, short nails "
            "dirty, a small old scar across the back of the hand. Camera "
            "at eye level, approximately 5'4\" off the ground, the viewer "
            "walking slowly forward into the fog. Shot on Kodak Portra "
            "400, 35mm film, 85mm lens, shallow depth of field, overcast "
            "diffused dusk light, cold air. Behind the hand: thick grey "
            "fog, no landmarks, no landscape, unrecognizable terrain, no "
            "other figures, no sound, no season, no era — only fog. "
            "Desaturated muted palette, near-monochrome. Visible film "
            "grain, high dynamic range, historical reenactment documentary "
            "still, shot on location, unstaged. Deep silence. The hand "
            "smaller and fainter than it should be in the frame, as if "
            "the viewer themselves is fading. No visible face, no visible "
            "torso, no third-person framing, no photographer visible, the "
            "viewer IS the camera."
        ),
    },
    "battlefield_aftermath": {
        "trigger_type": "witness_battle_aftermath",
        "notes": "v3 photoreal-honest. FEET + cloak hem. Peasant-levy corpses, no painter refs.",
        "prompt": (
            "Two mud-caked worn leather boots stepping forward on frozen "
            "trampled wheat stubble in the lower foreground of a "
            "first-person POV photograph — one boot sole split at the "
            "toe, leather worn grey at the flex points, the hem of a "
            "heavy grey-brown wool traveler's cloak swaying at the knees, "
            "splattered with frozen mud and old dried blood. Camera at "
            "eye level, approximately 5'4\" off the ground, the viewer "
            "walking slowly across the aftermath. Shot on Kodak Portra "
            "400, 35mm film, 50mm lens, shallow depth of field, thin low "
            "winter morning sun, long blue shadows, breath-steam visible. "
            "Behind the boots: dozens of fallen fighters across the "
            "trampled field — plain cheap mail over dirty gambesons, "
            "Viking axes, spears snapped in half, Frankish and "
            "Scandinavian bodies mixed, the unremarkable bodies of "
            "peasant levies and conscripts, short, thin, mouths slack, "
            "eyes open to the sky. Three ravens pulling at a corpse a few "
            "paces ahead, flies despite the cold, a ribcage open, a "
            "cracked helmet beside a face staring up at nothing, a split "
            "shield half-buried in mud. 9th century Francia, winter "
            "morning, volumetric fog. Visible film grain, high dynamic "
            "range, historical reenactment documentary still, shot on "
            "location, unstaged. No visible face, no visible torso, no "
            "third-person framing, no photographer visible, the viewer "
            "IS the camera."
        ),
    },
    "plague_scene": {
        "trigger_type": "witness_plague",
        "notes": "v3 photoreal-honest. Body-anchor lead, Kodak Portra 400 color (not B&W), no painting refs.",
        "prompt": (
            "A bare thin forearm resting in the lower foreground of a "
            "first-person POV photograph — weathered sun-creased skin, "
            "faded scars and pockmarks from a survived childhood smallpox, "
            "dirty broken fingernails, two early black buboes swelling in "
            "the crease of the elbow and at the wrist, the flesh around "
            "them livid and purpling, beads of fever sweat caught in the "
            "fine arm hair, coarse yellowed linen shift sleeve pushed up "
            "unevenly. Camera at eye level, approximately 5'2\" off the "
            "ground, the viewer sitting on a straw-covered dirt floor. "
            "Shot on Kodak Portra 400, 35mm film, 50mm lens, shallow "
            "depth of field, single shaft of grey afternoon light from a "
            "shuttered window, deep shadow elsewhere. Behind the forearm: "
            "on the straw-strewn floor a few feet away, the body of an "
            "older woman in the same yellowed linen — short, gaunt, her "
            "flat-featured weathered face slack with death, gap-toothed "
            "mouth open, thinning grey hair plastered to her scalp with "
            "old sweat, larger black buboes livid on her neck and in her "
            "armpit, flies settling on her half-lidded eyes, hands "
            "crabbed with untreated arthritis. No crowd, no witnesses, "
            "no town visible, no one coming. 1348 Avignon, interior of a "
            "poor house. Visible film grain, high dynamic range, "
            "historical reenactment documentary still, shot on location, "
            "unstaged. Unflinching. No visible face, no visible torso, "
            "no third-person framing, no photographer visible, the "
            "viewer IS the camera."
        ),
    },
    "sack_of_rome_410": {
        "trigger_type": "witness_catastrophe_historical",
        "notes": "v3 photoreal-honest. FEET running embers. Visigoth as ordinary gap-toothed man.",
        "prompt": (
            "Two bare dusty feet in worn leather sandals running "
            "unsteadily across ash-streaked marble paving stones in the "
            "lower foreground of a first-person POV photograph — one "
            "sandal strap cut and flapping loose, a bleeding scrape "
            "across the right ankle, thin wiry legs half-seen, the dirty "
            "frayed hem of an off-white wool-and-linen tunic swinging at "
            "the knees, a plain working tunic not a fine toga. Camera at "
            "eye level, approximately 5'3\" off the ground, the viewer "
            "running. Shot on Fujifilm Superia, 35mm film, 35mm lens, "
            "shallow depth of field, late summer dusk light cutting amber "
            "through thick smoke. Behind the feet: a broad marble "
            "colonnade in smoke and flame, one Corinthian column cracked "
            "and leaning, a Visigothic raider in plain mail and "
            "fur-trimmed cloak dragging a silver reliquary across the "
            "stones directly in the viewer's path, his weathered "
            "unsymmetric face turning toward the camera, gap-toothed, a "
            "short thin man, not a heroic Viking. Further back: a villa "
            "burning, figures fleeing, a dead Roman in a torn tunic "
            "sprawled on the steps. Embers drifting, thick amber smoke, "
            "glowing ash on the stones. August 410 AD, Rome, the third "
            "day of the Visigothic sack. Visible film grain, high dynamic "
            "range, historical reenactment documentary still, shot on "
            "location, unstaged. The viewer's breathlessness implied. No "
            "visible face, no visible torso, no third-person framing, no "
            "photographer visible, the viewer IS the camera."
        ),
    },
    "siege_first_person": {
        "trigger_type": "player_active_combat",
        "notes": "v3 photoreal-honest. Body-anchor lead, gap-toothed cataract defender, no painting refs.",
        "prompt": (
            "Two grimy sunburned forearms in the lower foreground of a "
            "first-person POV photograph — the left wrapped in a fraying "
            "dirty linen bandage over an old scar, the right with a split "
            "callus on the thumb bleeding onto the oak-and-horn crossbow "
            "stock being cranked, fingernails dirty and broken, skin "
            "weather-creased, wiry thin forearms with old childhood burn "
            "scars. Camera at eye level, approximately 5'4\" off the "
            "ground. Shot on Fujifilm Superia, 35mm film, 35mm lens, "
            "shallow depth of field, midday Levantine sun directly "
            "overhead. Behind the arms: crenellated stone curtain wall, "
            "another defender slumped dead against a merlon three paces "
            "to the right — a short middle-aged man in a patched "
            "gambeson, gap-toothed mouth slack, one eye cloudy from an "
            "old cataract, an arrow through his throat. Beyond the wall: "
            "siege towers rolling forward, trebuchet stones in flight, "
            "arrows arcing up toward the camera, one just striking the "
            "stone inches from the left hand. 13th century Levant, siege "
            "defense, hot dust, heat shimmer. Visible film grain, high "
            "dynamic range, historical reenactment documentary still, "
            "shot on location, unstaged. No visible face, no visible "
            "torso, no third-person framing, no photographer visible, "
            "the viewer IS the camera."
        ),
    },
    "peasant_famine": {
        "trigger_type": "witness_commoner_suffering",
        "notes": "v3 photoreal-honest. LAP + own hands + empty bowl. Whole family malnourished.",
        "prompt": (
            "Two gaunt thin hands resting in the viewer's own lap in the "
            "lower foreground of a first-person POV photograph — dirty "
            "broken fingernails, chapped knuckles, skin thin over the "
            "tendons, a shallow wooden bowl held in the palms with only "
            "two shrivelled bean skins in it, coarse patched brown wool "
            "kirtle across the lap, stained and thin, the viewer sitting "
            "cross-legged on a packed dirt floor. Camera at eye level, "
            "approximately 5'0\" off the ground, viewer seated on the "
            "ground. Shot on Kodak Portra 400, 35mm film, 50mm lens, "
            "shallow depth of field, single tallow candle casting warm "
            "flickering light, deep shadows elsewhere, cold blue from a "
            "shuttered window. Behind the hands, across a few feet of "
            "dirt floor: a thin woman in the same coarse wool holding a "
            "sleeping infant swaddled in rags, her face hollow and "
            "weathered, staring past the viewer, older than her years, a "
            "few missing teeth visible. A boy of maybe six kneels on his "
            "heels beside her, short for his age from malnutrition, "
            "watching the empty bowl in the viewer's hands, mouth "
            "slightly open, eyes sunken. Walls of wattle and daub, frost "
            "on the inside of the shuttered window, breath visible. 14th "
            "century northern European peasant hovel, winter night. "
            "Visible film grain, high dynamic range, historical "
            "reenactment documentary still, shot on location, unstaged. "
            "Shame and hunger in the framing. No visible face, no "
            "visible torso, no third-person framing, no photographer "
            "visible, the viewer IS the camera."
        ),
    },
    "execution_scene": {
        "trigger_type": "witness_public_execution",
        "notes": "v3 photoreal-honest. HANDS on splintered railing. Crowd & condemned ordinary.",
        "prompt": (
            "Two weathered hands gripping a rough splintered wooden beam "
            "in the lower foreground of a first-person POV photograph — "
            "knuckles white, dirty broken fingernails, a dirty linen cuff "
            "at one wrist, a patched brown wool sleeve at the other, skin "
            "sunburned and creased, a small callus on the right thumb "
            "from daily work. Camera at eye level, approximately 5'4\" "
            "off the ground. Shot on Kodak Portra 400, 35mm film, 35mm "
            "lens, shallow depth of field, overcast noon diffused light, "
            "cold air. Bodies of other spectators pressed against the "
            "viewer's shoulders just at the edge of frame: on the left, "
            "an older man with a broken nose and dirty thinning hair; on "
            "the right, a short middle-aged woman in a stained headscarf "
            "crossing herself, her face pockmarked from old smallpox; "
            "behind, a wiry man holding a small grimy-faced child on his "
            "shoulders. Beyond the hands: the wooden scaffold, the "
            "headsman in a black hood, a double-handed sword resting on "
            "his shoulder, the kneeling condemned — a middle-aged man in "
            "a fine but torn doublet, hands bound behind, head already "
            "shaven at the nape, an ordinary tired face. Timbered facades "
            "around the square, pigeons, a stray dog underfoot, straw on "
            "the scaffold boards. 15th century Burgundy, a town square at "
            "noon. Visible film grain, high dynamic range, historical "
            "reenactment documentary still, shot on location, unstaged. "
            "No visible face, no visible torso, no third-person framing, "
            "no photographer visible, the viewer IS the camera."
        ),
    },
    "run_start_roman": {
        "trigger_type": "run_start",
        "notes": "v3 photoreal-honest. HANDS on reins. Auxiliary as ordinary scarred provincial conscript.",
        "prompt": (
            "Two dusty sunburned hands holding worn leather reins in the "
            "lower foreground of a first-person POV photograph — one "
            "knuckle scabbed from a recent scrape, fingernails dirty, "
            "travel grime ground into the creases of the palms, the hands "
            "of a traveler not a noble, short thick fingers, sleeves of "
            "a coarse undyed wool traveler's cloak visible at the wrists "
            "with road dust on the fabric. Camera at eye level, "
            "approximately 5'3\" off the ground, the viewer on horseback. "
            "Shot on Kodak Portra 400, 35mm film, 50mm lens, shallow "
            "depth of field, golden pink dawn light, long shadows, cold "
            "still air, breath of the horse visible. Behind the hands: "
            "the neck and ear of a weary chestnut horse, the gate of a "
            "small provincial Roman town directly ahead — stone walls "
            "patched with later paler mortar, weeds growing from the "
            "ramparts, the gate itself worn and dented. At the gate, a "
            "single bored auxiliary leaning on his pilum, yawning — a "
            "short stocky middle-aged man in worn scale armor that "
            "doesn't quite fit, cheek scarred from an old injury, teeth "
            "gapped, a provincial conscript not a heroic legionary. "
            "Vineyards half-seen to the left, cypresses along the road, "
            "thin smoke from a bread oven inside the town, a stray dog "
            "crossing the gate. Late 4th century AD, Gallia Narbonensis. "
            "Visible film grain, high dynamic range, historical "
            "reenactment documentary still, shot on location, unstaged. "
            "No visible face, no visible torso, no third-person framing, "
            "no photographer visible, the viewer IS the camera."
        ),
    },
    "byzantine_throne": {
        "trigger_type": "audience_with_ruler",
        "notes": "v3 photoreal-honest. FEET on marble. Varangian Guard ordinary-bodied.",
        "prompt": (
            "Two soft leather court shoes advancing slowly across polished "
            "marble tiles in the lower foreground of a first-person POV "
            "photograph — shoes clean and unremarkable, the hem of a "
            "plain silk-and-linen court tunic visible at the ankles, the "
            "short thin ankles of an ordinary person, not a tall noble, "
            "tiles reflecting candlelight in smears across the polished "
            "surface. Camera at eye level, approximately 5'3\" off the "
            "ground, the viewer walking down a long aisle. Shot on Kodak "
            "Portra 400, 35mm film, 35mm lens, shallow depth of field, "
            "incense-smoke air, shafts of coloured light from high "
            "windows cutting across the gloom. Behind the feet: a long "
            "marble aisle leading to the Emperor seated on an elevated "
            "gilded throne beneath an embroidered canopy, flanked by the "
            "mechanical golden lions and the singing tree described in "
            "the De Ceremoniis, Varangian Guard in scale armor standing "
            "motionless at the columns — ordinary weathered faces, a few "
            "missing teeth, one with a crooked jawline from an old break, "
            "not idealized warriors. Mosaics of Christ Pantocrator on "
            "the apse catching candlelight, deep reds, gold, lapis blue, "
            "thick incense smoke rising in layers. 10th century "
            "Constantinople, Magnaura palace interior. Visible film "
            "grain, high dynamic range, historical reenactment documentary "
            "still, shot on location, unstaged. Awe and fear in the "
            "framing. No visible face, no visible torso, no third-person "
            "framing, no photographer visible, the viewer IS the camera."
        ),
    },
}

MODEL_CHOICES = ("flux2-4b", "flux2-9b", "flux2-9b-base", "zimage-turbo")
DEFAULT_STEPS = {
    "flux2-4b": 4,
    "flux2-9b": 4,
    "flux2-9b-base": 30,
    "zimage-turbo": 9,
}
DEFAULT_GUIDANCE = {
    "flux2-4b": None,
    "flux2-9b": None,
    "flux2-9b-base": 1.5,
    "zimage-turbo": None,
}


def _build_model(model_name: str, quantize: int | None) -> Any:
    """Instantiate the requested mflux model. Import inside to keep argparse
    dry-runs (e.g. --help) cheap and dependency-free."""
    from mflux.models.common.config import ModelConfig

    if model_name == "flux2-4b":
        from mflux.models.flux2.variants import Flux2Klein
        return Flux2Klein(
            model_config=ModelConfig.flux2_klein_4b(),
            quantize=quantize,
        )
    if model_name == "flux2-9b":
        from mflux.models.flux2.variants import Flux2Klein
        return Flux2Klein(
            model_config=ModelConfig.flux2_klein_9b(),
            quantize=quantize,
        )
    if model_name == "flux2-9b-base":
        from mflux.models.flux2.variants import Flux2Klein
        return Flux2Klein(
            model_config=ModelConfig.flux2_klein_base_9b(),
            quantize=quantize,
        )
    if model_name == "zimage-turbo":
        from mflux.models.z_image import ZImage
        return ZImage(
            model_config=ModelConfig.z_image_turbo(),
            model_path="filipstrand/Z-Image-Turbo-mflux-4bit",
        )
    raise ValueError(f"Unknown model: {model_name}")


def _generate(
    model: Any,
    model_name: str,
    prompt: str,
    seed: int,
    steps: int,
    width: int,
    height: int,
    guidance: float | None,
) -> Any:
    """Call generate_image with the subset of kwargs each model accepts."""
    kwargs: dict[str, Any] = dict(
        prompt=prompt,
        seed=seed,
        num_inference_steps=steps,
        width=width,
        height=height,
    )
    if guidance is not None:
        kwargs["guidance"] = guidance
    return model.generate_image(**kwargs)


def _parse_prompt_keys(raw: str) -> list[str]:
    if raw == "all":
        return list(PROMPTS.keys())
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    unknown = [k for k in keys if k not in PROMPTS]
    if unknown:
        raise SystemExit(
            f"Unknown prompt key(s): {', '.join(unknown)}\n"
            f"Valid keys: {', '.join(PROMPTS.keys())}"
        )
    return keys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CHRONOS image generation POC (scratch-space; not production).",
    )
    parser.add_argument(
        "--model", choices=MODEL_CHOICES, default="flux2-4b",
        help="Which mflux model to use. Default: flux2-4b (fastest).",
    )
    parser.add_argument(
        "--steps", type=int, default=None,
        help=(
            "Inference steps. Defaults: flux2-4b=4, flux2-9b=4, "
            "flux2-9b-base=30, zimage-turbo=9."
        ),
    )
    parser.add_argument(
        "--guidance", type=float, default=None,
        help=(
            "Classifier-free guidance. Default: None for distilled "
            "models; 1.5 for flux2-9b-base. Only used if the model accepts it."
        ),
    )
    parser.add_argument(
        "--quantize", choices=("4", "8", "none"), default="8",
        help="Weight quantization for Flux2. Ignored for zimage-turbo (pre-quantized path).",
    )
    parser.add_argument(
        "--prompts", default="all",
        help="Comma-separated prompt keys, or 'all'. Default: all.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument(
        "--label", type=str, default=None,
        help="Optional label inserted into output filenames (e.g. "
             "'v3-photoreal-honest'). Safe-sluggified.",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List prompt keys and exit (no generation, no model load).",
    )
    args = parser.parse_args()

    if args.list:
        for key, meta in PROMPTS.items():
            print(f"{key:<22} {meta['trigger_type']}")
            print(f"{'':<22}  notes: {meta['notes']}")
        return 0

    keys = _parse_prompt_keys(args.prompts)
    steps = args.steps if args.steps is not None else DEFAULT_STEPS[args.model]
    guidance = (
        args.guidance if args.guidance is not None else DEFAULT_GUIDANCE[args.model]
    )
    quantize: int | None = None if args.quantize == "none" else int(args.quantize)
    args.output.mkdir(parents=True, exist_ok=True)

    print(f"[setup] model={args.model} steps={steps} guidance={guidance} "
          f"quantize={quantize} seed={args.seed} {args.width}x{args.height}")
    print(f"[setup] prompts: {', '.join(keys)}")
    print(f"[setup] output: {args.output}")
    print(f"[setup] loading model (first run downloads weights to ~/.cache/huggingface/)...")

    load_start = time.monotonic()
    try:
        model = _build_model(args.model, quantize=quantize)
    except Exception as exc:
        print(f"[fatal] failed to load model {args.model}: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 2
    load_duration = time.monotonic() - load_start
    print(f"[setup] model loaded in {load_duration:.1f}s")

    results: list[dict[str, Any]] = []
    for key in keys:
        meta = PROMPTS[key]
        prompt = meta["prompt"]
        stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        label_slug = ""
        if args.label:
            safe = "".join(
                c if c.isalnum() or c in "-_." else "-" for c in args.label
            ).strip("-_.")
            if safe:
                label_slug = f"-{safe}"
        base = f"{key}_{args.model}-{steps}step{label_slug}_{stamp}"
        png_path = args.output / f"{base}.png"
        json_path = args.output / f"{base}.json"

        print(f"[gen] {key}: starting ({len(prompt)} chars)...")
        t0 = time.monotonic()
        try:
            image = _generate(
                model=model,
                model_name=args.model,
                prompt=prompt,
                seed=args.seed,
                steps=steps,
                width=args.width,
                height=args.height,
                guidance=guidance,
            )
            image.save(path=str(png_path)) if hasattr(image, "save") else None
            if not png_path.exists():
                # Fallback: some mflux versions expose .image (PIL) or .save()
                # without `path=` kwarg.
                if hasattr(image, "image"):
                    image.image.save(png_path)
                elif callable(getattr(image, "save", None)):
                    image.save(png_path)
                else:
                    raise RuntimeError(
                        f"Don't know how to save generated image (type {type(image)!r})"
                    )
            duration = time.monotonic() - t0
            meta_out = {
                "key": key,
                "trigger_type": meta["trigger_type"],
                "prompt": prompt,
                "model": args.model,
                "steps": steps,
                "guidance": guidance,
                "quantize": quantize,
                "seed": args.seed,
                "width": args.width,
                "height": args.height,
                "duration_seconds": round(duration, 2),
                "output_png": str(png_path),
                "timestamp": stamp,
            }
            json_path.write_text(json.dumps(meta_out, indent=2))
            print(f"[gen] {key}: done in {duration:.1f}s -> {png_path.name}")
            results.append({
                "key": key,
                "model": args.model,
                "duration": f"{duration:.1f}s",
                "output_path": str(png_path),
                "status": "ok",
            })
        except Exception as exc:
            duration = time.monotonic() - t0
            print(
                f"[gen] {key}: FAILED after {duration:.1f}s: {exc}",
                file=sys.stderr,
            )
            traceback.print_exc()
            results.append({
                "key": key,
                "model": args.model,
                "duration": f"{duration:.1f}s",
                "output_path": "-",
                "status": f"FAILED: {type(exc).__name__}",
            })

    print("\n=== summary ===")
    print(f"{'key':<22} {'model':<14} {'duration':>10}  status / path")
    print("-" * 100)
    for r in results:
        status = r["status"] if r["status"] != "ok" else r["output_path"]
        print(f"{r['key']:<22} {r['model']:<14} {r['duration']:>10}  {status}")
    failures = sum(1 for r in results if r["status"] != "ok")
    print(f"\n{len(results) - failures}/{len(results)} succeeded.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
