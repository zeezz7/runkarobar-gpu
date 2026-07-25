# runkarobar-gpu

Reproducible ComfyUI generation stack for a **Vast.ai RTX 5090** box (32 GB VRAM,
CUDA 13.2). This repo is the **recipe** — scripts and workflows only. No model
weights and no generated media are committed; `download_models.sh` rebuilds the
~64 GB of weights from scratch.

## What's in here

| Path | What it is |
|---|---|
| `setup.sh` | One-shot bootstrap: downloads models, installs workflows |
| `download_models.sh` | Idempotent, size-verified model downloader (`ltx` / `flux` / `wan` / `all`) |
| `MODELS.md` | Exact files + folders, settings, measured VRAM/render times, and the traps |
| `workflows/` | API-format ComfyUI workflows, all executed and confirmed working |

## Quick start

On a Vast.ai ComfyUI instance (ComfyUI already at `/workspace/ComfyUI`):

```bash
bash setup.sh all        # or: ltx | flux | wan
supervisorctl restart comfyui
```

## Models

All fp8-quantized and chosen to fit a 32 GB card. Every row below was verified by
actually rendering, not just by loading.

| Model | Job | On-disk | Output | Render | Peak VRAM |
|---|---|---|---|---|---|
| LTXV 13B 0.9.8 fp8 | image→video | 15.7 GB | 768×512, 121f, 24 fps, 5.04 s | ~70 s | 20.3 GB |
| FLUX.1-dev fp8 | text→image | 12.5 GB | 1024×1024 | 25 s | 17.2 GB |
| Wan 2.2 I2V 14B fp8 | image→video | 35.6 GB | 720×480, 81f, 16 fps, 5.06 s | 240 s | **32.1 GB ⚠️** |

The T5-XXL text encoder is shared between LTX and FLUX (verified byte-identical by
HuggingFace content hash), saving 5.16 GB. Wan uses UMT5, a different encoder, so it
carries its own.

## Read before you scale anything up

- **Wan 2.2 peaked at 32,056 MiB of 32,607 MiB** — ~550 MB from OOM at only 720×480.
  Raising resolution or frame count will likely OOM. See `MODELS.md` for mitigations.
- **Run the three model families serially, never concurrently.** 32 GB VRAM and only
  ~30 GB usable system RAM.
- **FLUX.1-dev is licensed non-commercial.**
- `black-forest-labs/FLUX.1-dev` is gated; the scripts use ungated mirrors. No
  HuggingFace token is required.

## Note on persistence

On these instances `/workspace` is **not** necessarily a persistent volume — check
`vast-capabilities | jq '.instance.workspace_is_volume'`. When it is `false`, a
recycle or destroy wipes everything, which is precisely why the weights are
reproducible from `download_models.sh` rather than stored.
