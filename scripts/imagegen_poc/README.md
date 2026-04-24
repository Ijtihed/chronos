# imagegen_poc — CHRONOS local image generation proof of concept

**Status:** Scratch-space POC. **Not** production code. Nothing in this directory is wired into `backend/`, the trigger system, the UI, or any other part of CHRONOS. Delete this directory at any time and the main codebase is unaffected.

## Purpose

Validate whether local diffusion on M4 Max / 64 GB can produce imagery CHRONOS needs before Phase 3 integration begins. Specifically: photorealistic, historically grounded, first-person POV where relevant, gore-tolerant, era-appropriate. Per `roadmap.md` Phase 3, the diffusion provider is an open decision and must be prototyped before integration.

This POC tests **local `mflux`** on three architectures:

| Model | Size | Steps | Why |
|---|---|---|---|
| `flux2-4b` — FLUX.2 Klein 4B (distilled) | ~15 GB raw / ~7.5 GB Q8 | 4 | Fastest modern Flux. Released Jan 2026. |
| `flux2-9b` — FLUX.2 Klein 9B (distilled) | ~32 GB raw / ~16 GB Q8 | 4 | Higher quality Flux, same step count. |
| `zimage-turbo` — Z-Image Turbo (pre-quantized 4-bit) | ~6 GB | 9 | Alternative architecture for comparison. Released Nov 2025. |

Legacy FLUX.1 (`dev`/`schnell`) is intentionally skipped — the mflux author now flags it as legacy.

## Run it

You need [`uv`](https://github.com/astral-sh/uv) on your PATH. If you don't have it:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
```

The script declares its dependencies inline, so `uv run` handles everything:

```sh
# From project root
cd scripts/imagegen_poc

# Fastest first pass: all 10 prompts on FLUX.2 4B distilled, Q8, seed 42
uv run generate_samples.py --model flux2-4b

# Single prompt
uv run generate_samples.py --model flux2-4b --prompts hero_death

# Multiple prompts
uv run generate_samples.py --model flux2-4b --prompts hero_death,plague_scene

# Higher-quality pass on a subset with the 9B model
uv run generate_samples.py --model flux2-9b --prompts hero_death,hero_erasure,plague_scene

# Alternative architecture
uv run generate_samples.py --model zimage-turbo --prompts hero_death
```

Alternative install path (traditional pip, if you prefer not to use `uv run`):

```sh
uv venv -p 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
python generate_samples.py --model flux2-4b
```

## First-run expectations

- **First invocation of each model downloads weights from Hugging Face to `~/.cache/huggingface/`.**
  - FLUX.2 Klein 4B Q8: ~7–15 GB download
  - FLUX.2 Klein 9B Q8: ~16–32 GB download
  - Z-Image Turbo pre-quantized 4-bit: ~6 GB download
- **Expected per-image generation time on M4 Max / 64 GB:**
  - FLUX.2 4B distilled (4 steps, Q8, 1024²): **~8–15 s** (educated guess — this POC is part of measuring that)
  - FLUX.2 9B distilled (4 steps, Q8, 1024²): **~30–60 s**
  - Z-Image Turbo (9 steps, 4-bit, 1024²): **~10–20 s**
- **Model load time:** adds a one-time overhead per script invocation (seconds to tens of seconds depending on model size).
- **Subsequent runs:** weights are cached; only model load time applies.

## Output

Each generation writes two files to `out/`:

```
out/
  hero_death_flux2-4b_2026-04-22T14-07-33.png
  hero_death_flux2-4b_2026-04-22T14-07-33.json
```

The `.json` sidecar records `{prompt, model, steps, quantize, seed, width, height, duration_seconds}` so you can correlate outputs with exact parameters later.

Failures in one prompt do not kill the batch; full tracebacks go to stderr, and a summary table is printed at the end.

## Clean up

```sh
# Remove output images and metadata
rm -rf scripts/imagegen_poc/out/

# Remove this entire POC
rm -rf scripts/imagegen_poc/

# Remove downloaded model weights (frees 15–50+ GB)
rm -rf ~/.cache/huggingface/hub/models--black-forest-labs--FLUX.2-klein-4b
rm -rf ~/.cache/huggingface/hub/models--black-forest-labs--FLUX.2-klein-9b
rm -rf ~/.cache/huggingface/hub/models--filipstrand--Z-Image-Turbo-mflux-4bit
# Or nuke the whole HF cache:
# rm -rf ~/.cache/huggingface
```

## What this POC is **not**

- Not integrated with `backend/`, `frontend/`, or any trigger system
- Not a decision — it produces evidence for the Phase 3 provider decision in `roadmap.md`
- Not style-consistent — the 10 prompts intentionally mix painterly references (Goya, Bruegel, Caravaggio, Rembrandt, Wyeth) to discover which register the model handles best. Production will lock to one style.
- Not exhaustive — if FLUX.2 outputs are unacceptable we'd reopen and test SDXL or API options; that's out of scope here.
