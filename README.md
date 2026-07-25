# runkarobar-gpu

Reproducible ComfyUI generation stack for a **Vast.ai RTX 5090** box (32 GB VRAM,
CUDA 13.2). This repo is the **recipe** — scripts and workflows only. No model
weights and no generated media are committed; `download_models.sh` rebuilds the
~64 GB of weights from scratch.

## What's in here

| Path | What it is |
|---|---|
| `make_reel.py` | **Product image in, finished vertical reel out**, uploaded to MinIO |
| `reelkit/` | Helpers: ComfyUI client, graph builders, framing, ffmpeg, storage |
| `setup.sh` | One-shot bootstrap: downloads models, installs workflows |
| `download_models.sh` | Idempotent, size-verified model downloader (`ltx` / `flux` / `wan` / `all`) |
| `MODELS.md` | Exact files + folders, settings, measured VRAM/render times, and the traps |
| `workflows/` | API-format ComfyUI workflows, all executed and confirmed working |

## Making a reel

```bash
pip install -r requirements.txt
export MINIO_ENDPOINT=staging-storage.runkarobar.com   # host only, no scheme
export MINIO_ACCESS_KEY=... MINIO_SECRET_KEY=... MINIO_BUCKET=runkarobar

python make_reel.py samples/product.png            # LTX only,  ~5.8 min
python make_reel.py samples/product.png --hero     # + Wan shot, ~10 min
```

Prints the public URL on success; exits non-zero on any failure.

| Stage | What it does | Time |
|---|---|---|
| FLUX img2img | one clean product hero still, denoise 0.40 so branding survives | ~15–30 s |
| LTX i2v ×3 | three 5.04 s scenes at 576×1024 | ~110 s each |
| Wan i2v ×1 | optional money shot, 432×768, `--hero` only | ~225 s |
| ffmpeg | 1080×1920, cross-fades + fade in/out, **silent** | ~5 s |
| MinIO | `reels/<timestamp>.mp4`, verified publicly readable | ~4 s |

Output is 14.1 s without `--hero`, 18.7 s with it.

### Two things learned the hard way

**Scene variety comes from framing, not from the video model.** LTX only keeps a
product faithful at guide `strength=1.0`, which yields little camera movement. Dropping
to the stock template's `0.15` measures as *more* motion but achieves it by letting the
product drift out of frame and inventing a replacement object — useless for an ad. So
`strength` stays at 1.0 and `SCENES` varies the crop of the hero still per scene
(`zoom`/`anchor`), which is deterministic and never risks the product's identity.

**The MinIO endpoint is behind a bucket-scoped nginx proxy.** It rewrites `/<key>` to
`/<bucket>/<key>`, so the host root *is* the bucket. The `minio` SDK cannot be used
against it as-is: the SDK sends `/<bucket>/<key>`, the proxy makes that
`/<bucket>/<bucket>/<key>`, and since SigV4 signs the pre-rewrite path every request
fails `SignatureDoesNotMatch` even with correct credentials. `reelkit/storage.py`
detects the layout at runtime and uses the SDK for standard endpoints, or signs the
post-rewrite path for this one. Public URLs here are
`https://<endpoint>/reels/<name>.mp4` — **no bucket segment**.

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
