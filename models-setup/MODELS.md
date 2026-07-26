# ComfyUI model bake-off set

Box: Vast RTX PRO 6000 Blackwell (96 GB VRAM, cc 12.0, driver 595.71.05),
torch 2.10.0+cu130, ComfyUI **0.28.0** at `/workspace/ComfyUI`.

Everything here was downloaded **directly over HTTPS, no git**, from repos that
return HTTP 200 **anonymously** (no HuggingFace token is configured on this box).
Every file was byte-verified against the remote `x-linked-size` header.

```
/workspace/models-setup/
  download_models.sh      re-runnable downloader (every URL -> exact folder)
  validate_image.py       Qwen2.5-VL guard -> JSON verdict
  MODELS.md               this file
  lib/fetch.sh            disk-safe, size-verifying fetch helper
  lib/verify.sh           re-verify everything on disk vs remote
  workflows/*.api.json    one API-format workflow per model
  logs/m_*.tsv            per-file download manifest (url, bytes, status)
```

---

## 1. What is installed

> **CURRENT STATE (updated 2026-07-26).** **Section 1 below is the current installed
> set.** Sections 2-7 keep the original bake-off's licence / trap / dedup notes for
> reference — some mention models that have since been removed, but the notes
> themselves remain accurate. Section 8 is the live pipeline stage map.
> **REMOVED** - HiDream-I1-Full + HiDream-E1.1, LTX-Video 0.9.8, LTX-2.3, Mochi 1,
> and the orphaned `t5xxl_fp8` / `clip_l` / `ae` encoders.
> **ADDED** - Qwen-Image-2512, Qwen-Image-Edit-2511, **HunyuanVideo I2V**, BiRefNet,
> 4x-UltraSharp, and the Qwen2.5-Instruct brain.
> **KEPT** - Wan 2.2 I2V + LightX2V (default video engine), Qwen2.5-VL-7B.

Per-row sizes are **measured on disk** (byte-verified against the remote
`x-linked-size`). Run `bash lib/verify.sh` to re-check on any box.

| Model | Role | Size | Folder | License | Workflow |
|---|---|---:|---|---|---|
| **Qwen2.5-14B-Instruct** fp8 | Brain — storyboard (**active**) | 16 GB | `/workspace/models/brain/` | **Apache-2.0** | `brain.py` |
| **Qwen2.5-32B-Instruct** fp8-dynamic | Brain — stronger, kept (not default) | 34 GB | `/workspace/models/` | **Apache-2.0** | `brain.py` |
| **Qwen2.5-VL-7B-Instruct** | Product captions + Stage 2b OCR guard | 16.6 GB | `/workspace/models/qwen2.5-vl/` | **Apache-2.0** | `validate_image.py` |
| **Qwen-Image-2512** fp8 | Image — scene backdrops (text-to-image) | 20.4 GB | `diffusion_models/` | **Apache-2.0** | `reelkit/workflows/tpl_t2i_qwen`, `tpl_scene_image` |
| **Qwen-Image-Edit-2511** fp8mixed | Image — `edit_animate`, **default** scene builder | 20.5 GB | `diffusion_models/` | **Apache-2.0** | `reelkit/workflows/tpl_qwen_edit` |
| **Wan 2.2 I2V 14B** fp8 + LightX2V | Video — motion (**default**) + energy | 38.0 GB | `diffusion_models/`, `text_encoders/`, `vae/`, `loras/` | **Apache-2.0** | `reelkit/workflows/tpl_wan_i2v` |
| **HunyuanVideo I2V** 720p bf16 | Video — motion (**alternative**), image+text -> video | 35.9 GB | `diffusion_models/`, `text_encoders/`, `vae/` | Tencent Community (**restricted — excl. EU/UK/KR**) | `reelkit/workflows/tpl_hunyuan_i2v` |
| **BiRefNet** | Segmentation for `compose_animate` | 0.44 GB | `background_removal/` | MIT | — |
| **4x-UltraSharp** | Upscaling | 0.07 GB | `upscale_models/` | permissive (ESRGAN) | — |

The video engine is chosen at runtime by `REELKIT_VIDEO_MODEL` (Wan default /
Hunyuan alternative). The **reelkit-only working set is ~110 GB**; a box may hold
more if the bake-off leftovers were not pruned.

**FLUX.1-dev is not installed** — its licence is non-commercial. Qwen-Image is the
commercial-safe, best-in-class-text image model in its place.

---

## 2. Shared encoders (deduped)

> **Historical.** These shared encoders served HiDream / LTX / Mochi / HunyuanVideo
> T2V — all removed — and the orphaned `t5xxl_fp8` / `clip_l` / `ae` were deleted.
> The live models bundle their own: Qwen-Image → Qwen2.5-VL, Wan 2.2 → UMT5-XXL,
> HunyuanVideo I2V → llava + clip. Kept for reference.

These are downloaded **once** and referenced by several models. Dedupe was
confirmed by SHA256/byte-size equality across the source repos, not assumed.

| File | Bytes | Folder | Shared by |
|---|---:|---|---|
| `t5xxl_fp8_e4m3fn_scaled.safetensors` | 5,157,348,688 | `text_encoders/` | HiDream I1 + E1.1, LTX-0.9.8, Mochi |
| `clip_l.safetensors` | 246,144,152 | `text_encoders/` | HunyuanVideo |
| `ae.safetensors` | 335,304,388 | `vae/` | HiDream I1 + E1.1 (and FLUX if re-enabled) |

`t5xxl_fp8_e4m3fn_scaled.safetensors` is byte-identical (SHA256
`a498f048…557a`) across `comfyanonymous/flux_text_encoders`,
`Comfy-Org/HiDream-I1_ComfyUI` and `Comfy-Org/mochi_preview_repackaged`.
`ae.safetensors` is identical across the Lumina and HiDream repos.

**Not shareable, despite the names:**
- `clip_l_hidream.safetensors` (247,586,528 B) is **Long-CLIP-L** and is a
  different file from `clip_l.safetensors` (246,144,152 B). Same for
  `clip_g_hidream`. Substituting them will silently degrade HiDream.
- LTX-2.3 uses a **Gemma-3-12B** text encoder, not T5 — it shares nothing.
- Wan 2.2 uses **UMT5-XXL**, not T5 — it shares nothing.

### One deliberate deviation from the official templates
ComfyUI's LTX-0.9.8 and Mochi templates default to **`t5xxl_fp16`** (9.79 GB).
We use the **fp8 scaled** T5 for both instead. It is the same T5-XXL, is
published by Comfy-Org for both models, and saves 9.79 GB — which is what let
the full set fit. If LTX prompt adherence ever looks weak, run
`./download_models.sh t5fp16` and change that workflow's `CLIPLoader.clip_name`
to `t5xxl_fp16.safetensors`.

---

## 3. Licence notes worth reading before commercial use

- **HiDream I1 / E1.1 — MIT on the transformer weights**, and the I1 card states
  outputs are free for commercial use. But the stack **cannot run without**
  `llama_3.1_8b_instruct_fp8_scaled`, which is under the **Llama 3.1 Community
  License** (700M-MAU threshold, "Built with Llama" attribution). The VAE and T5
  are Apache-2.0. So "MIT" covers the model but not the whole pipeline.
- **HunyuanVideo — Tencent Hunyuan Community License. Read this one.** The grant
  is explicitly limited to a "Territory" that **excludes the EU, the UK and South
  Korea**. If your output or service reaches users there, you are outside the
  licence entirely. There is also a 100M-MAU ceiling above which you must obtain
  a separate licence from Tencent.
- **LTX-Video 0.9.8 / LTX-2.3** — both carry a **$10M annual revenue threshold**
  above which a paid commercial licence from Lightricks is required. Below it,
  commercial use is permitted. LTX-2.3's Gemma encoder adds Google's Gemma Terms.
- **Wan 2.2, Mochi 1, Qwen2.5-VL — Apache-2.0.** No territorial or MAU limits.
  These are the unambiguously clean ones.
- **FLUX.1-dev (not installed)** — non-commercial only.

---

## 4. Traps that are already handled

These are baked into `download_models.sh` and the saved workflows — listed so
they don't get reintroduced.

1. **Wan 2.2 VAE.** The 14B I2V models need `wan_2.1_vae.safetensors`
   (253,815,318 B). `wan2.2_vae.safetensors` is for the **5B TI2V** model only
   (48-channel vs 16-channel latent) and will not work. The 2.2 VAE is not
   downloaded at all.
2. **`UNETLoader.weight_dtype`.** It is an `advanced` (hidden) widget that
   defaults to `"default"`, i.e. full precision. Every workflow here either
   loads a genuinely pre-quantized fp8 file with `"default"` (correct), or pins
   `fp8_e4m3fn` explicitly. If you re-enable FLUX, its diffusion model **must**
   be loaded with `weight_dtype="fp8_e4m3fn"` or it loads bf16 and OOMs.
3. **LTX's paid cloud nodes.** ComfyUI 0.28.0 ships `api_ltxv_text_to_video.json`
   and `api_ltxv_image_to_video.json`, whose only real node is
   `LtxvApiTextToVideo` / `LtxvApiImageToVideo` — these bill LTX Studio credits
   and do **zero** local compute. Lightricks' own `example_workflows/2.3/*.json`
   are also compromised: they use `GemmaAPITextEncode`, which POSTs to
   `api.ltx.video` for conditioning. **Every workflow saved here is 100% local**
   and the validator hard-fails on any node whose class name contains `Api`.
   The same applies to the `Wan*Api` node family.
4. **FLUX gating.** `black-forest-labs/FLUX.1-dev` is gated (401 anonymously),
   and so is `Comfy-Org/Flux_Dev_ComfyUI_Repackaged` — the mirror most guides
   recommend is *not* actually ungated. The downloader uses `Kijai/flux-fp8`.
5. **No fp8 published for some models.** HiDream-E1.1 and HunyuanVideo have no
   official fp8 build. We use a community fp8 repack for E1.1 (17.11 GB instead
   of 34.21 GB) and Kijai's fp8 for HunyuanVideo (13.19 GB instead of 25.64 GB).
   Both halve the disk cost; both are loaded with `weight_dtype="default"`
   because they are already quantized.
6. **Frame counts are quantized per model** and are silently floored if wrong:
   Wan/LTX `length` must be `4n+1` (81, 97…), Hunyuan `4n+1` (73),
   Mochi `6n+1` (37). LTX-2.3 additionally needs width/height divisible by 32.

---

## 5. Re-running and verifying

```bash
cd /workspace/models-setup

./download_models.sh                 # everything (skips what is already complete)
./download_models.sh wan22 hunyuan   # just those families
MIN_FREE_GB=20 ./download_models.sh  # raise the disk floor

bash lib/verify.sh                   # re-check every file on disk vs remote size
python workflows/_validate_workflows.py   # structural check, runs nothing
```

`download_models.sh` is idempotent: a file whose local size already equals the
remote size is skipped, a partial file resumes, and any download that would take
free space below `MIN_FREE_GB` (default 12 GiB) is aborted rather than filling
the disk.

---

## 6. Running a model

> **Historical (bake-off).** Of the models below only **Wan 2.2** is still on disk;
> HiDream, LTX 0.9.8, LTX-2.3, Mochi and the HunyuanVideo **T2V** graph were deleted.
> The live pipeline runs `reelkit/workflows/*` (Qwen-Image, Qwen-Image-Edit,
> Wan 2.2, HunyuanVideo **I2V**). See section 8 / `reelkit/FLOW.md` for the live set.

Every workflow is API-format, so it goes straight to ComfyUI's `/prompt`
endpoint. `run_and_upload.py` queues it, waits, and reports the output file:

```bash
cd /workspace/models-setup
/venv/main/bin/python run_and_upload.py workflows/<name>.api.json --no-upload
```

Per model:

```bash
# images
python run_and_upload.py workflows/hidream_i1_full_t2i.api.json --no-upload
python run_and_upload.py workflows/hidream_i1_full_uhd.api.json  --no-upload   # 3840x2160
python run_and_upload.py workflows/hidream_e1_1_edit.api.json    --no-upload   # needs an input image

# video
python run_and_upload.py workflows/wan22_i2v_14B.api.json    --no-upload
python run_and_upload.py workflows/ltx098_t2v.api.json       --no-upload
python run_and_upload.py workflows/ltx098_i2v.api.json       --no-upload
python run_and_upload.py workflows/ltx23_t2v.api.json        --no-upload
python run_and_upload.py workflows/ltx23_i2v.api.json        --no-upload
python run_and_upload.py workflows/hunyuanvideo_t2v.api.json --no-upload
python run_and_upload.py workflows/mochi1_t2v.api.json       --no-upload
```

The i2v / edit workflows default to ComfyUI's bundled `input/example.png`. To
use your own, drop it in `/workspace/ComfyUI/input/` and change the `LoadImage`
node's `image` field.

### Vision guard

```bash
/venv/main/bin/python validate_image.py /workspace/ComfyUI/output/<file>.png
```
Prints a JSON verdict (branding / modesty / quality) and exits non-zero if any
check fails, so it can gate a pipeline directly:
```bash
python validate_image.py out.png >/dev/null && echo SHIP || echo REJECT
```

**Dependency:** requires `accelerate` (installed). Despite the common claim that
a single-device `device_map="cuda:0"` avoids it, transformers 5.14.0 raises
`ValueError: Using a device_map ... requires accelerate` regardless. Installed
with `/venv/main/bin/uv pip install accelerate`.

**Calibration caveat — verified, not theoretical.** On its first real run against
the HiDream UHD landscape the guard returned `branding.pass=false` with
`"detected": ["landscape photography"], "notes": "Watermark present."` on an
image containing **no watermark and no branding**. It also returned
`quality.issues` as a *string* where the prompt asks for a list. So:
- treat `branding.pass=false` as "needs a human look", not as proof of branding;
- do not parse `issues`/`detected` assuming a list type;
- the strictness is deliberate ("when uncertain, fail") but it does over-trigger.
Loosen the branding rule in `PROMPT` if the false-positive rate is too high for
your volume.

### Uploading to MinIO

The `staging-storage.runkarobar.com` endpoint sits behind a **bucket-scoped
nginx** that rewrites `/<key>` -> `/<bucket>/<key>`. Standard S3 clients sign
the path they transmit, so the signature is computed over the pre-rewrite path
while MinIO verifies the post-rewrite one — **both the `minio` Python SDK and
`mc` fail here with `SignatureDoesNotMatch`, regardless of credentials.**

`minio_upload.py` handles it by transmitting `/<key>` while signing
`/<bucket>/<key>`:

```bash
export MINIO_ENDPOINT=staging-storage.runkarobar.com
export MINIO_ACCESS_KEY=runkarobar
export MINIO_SECRET_KEY=...            # keep out of shell history
export MINIO_BUCKET=runkarobar

python minio_upload.py out.png            --prefix images
python minio_upload.py reel.mp4           --prefix reels
```
Public URLs carry **no bucket segment**: `https://<host>/<prefix>/<file>`.

---

## 7. Persistence warning

> **This instance has no persistent volume.** `vast-capabilities` reports
> `workspace_is_volume: false`, so `/workspace` is ordinary container storage.
> It survives stop/start but a **recycle or destroy wipes all ~198 GB**. Keep
> this directory (it is small) to rebuild from scratch.

---

## 8. Reel pipeline (reelkit/) — models and stages

The self-contained reel pipeline lives in `/workspace/reelkit`. One HTTP call in,
one finished vertical reel out; everything runs on this box.

### Models it uses

| Model | Role | Location | Size |
|---|---|---|---:|
| **Qwen2.5-14B-Instruct-FP8** | Stage 0 brain — writes the storyboard (**active**) | `/workspace/models/brain/` | 16 GB |
| **Qwen2.5-32B-Instruct-FP8-dynamic** | stronger brain, **kept but not default** — switch back for better copy / Hinglish quality | `/workspace/models/` | 34 GB |
| **Qwen2.5-VL-7B-Instruct** | product captions for the brain + Stage 2b OCR guard | `/workspace/models/qwen2.5-vl/` | 16.6 GB |
| **Qwen-Image-2512** fp8 | Stage 1 scene backdrops (text-to-image) | `ComfyUI/models/diffusion_models/` | 20.4 GB |
| **Qwen-Image-Edit-2511** fp8mixed | Stage 1 `edit_animate` — **default** scene builder (re-images the world around the product) | `ComfyUI/models/diffusion_models/` | 20.5 GB |
| **Wan 2.2 I2V 14B** fp8 + LightX2V | Stage 2 motion (**default**) + energy plates | `ComfyUI/models/diffusion_models/` | 38.0 GB |
| **HunyuanVideo I2V** 720p bf16 | Stage 2 motion (**alternative**; image+text -> video, 720x1280 native, no distilled path so slower) | `ComfyUI/models/diffusion_models/` | 35.9 GB |
| **BiRefNet** | Stage 1 `compose_animate` product segmentation | `ComfyUI/models/background_removal/` | 0.44 GB |
| **4x-UltraSharp** | upscaling | `ComfyUI/models/upscale_models/` | 0.07 GB |
| ElevenLabs (`eleven_multilingual_v2`) | Stage 3 voiceover | remote API | — |

The video engine is selected by `REELKIT_VIDEO_MODEL` — **Wan 2.2** (default) or
**HunyuanVideo I2V**. Same call signature, so nothing else changes. Wan is
**Apache-2.0**; HunyuanVideo's licence **excludes the EU, UK and South Korea**
(section 3), so Wan is the safe default for those markets.

Added for this pipeline: the Qwen2.5-Instruct brain (14B active, 32B kept),
Qwen-Image-2512, Qwen-Image-Edit-2511, BiRefNet, 4x-UltraSharp, and
**HunyuanVideo I2V**, plus `compressed-tensors`, `fastapi`, `uvicorn`,
`accelerate` in `/venv/main`.

Removed (lost the video bake-off / superseded, unused by the pipeline):
**HiDream-I1-Full, HiDream-E1.1, LTX-Video 0.9.8, LTX-2.3, Mochi 1**, and the
orphaned `t5xxl_fp8`, `clip_l` and `ae` encoders.

### Stages

| Stage | File | What it does |
|---|---|---|
| 0 | `brain.py` | The Qwen2.5-Instruct brain (14B active, 32B available) writes the storyboard JSON (schema-validated, 3 retries). Sees the product via Qwen2.5-VL captions. Unloaded before image models load. |
| 1 | `compose.py` | `edit_animate` (**default**): Qwen-Image-Edit-2511 re-images the world around the product. `compose_animate`: BiRefNet segment → Qwen-Image backdrop → PIL composite of the REAL product pixels → PIL colour harmonise + contact shadow (**pixel-exact — no sampler touches the product**). `generate_animate`: direct generation, no product on screen. |
| 2 | `animate.py` | Still → clip via `video_i2v()` — Wan 2.2 I2V (default) or HunyuanVideo I2V, selected by `REELKIT_VIDEO_MODEL`. `energy` rendered on pure black, luma-checked, screen-blended. (Ken-Burns still exists in code but is unreachable from a valid storyboard — every scene is a real clip now.) |
| 2b | `animate.guard_composite` | OCR-diff via `validate_image.py` — label tokens from the render vs the source product. <50% overlap → re-composite. Skips when the source yields <3 readable tokens (small embroidered logos are unverifiable). |
| 3 | `voiceover.py` | Runs BEFORE the visuals (audio leads video). ElevenLabs TTS per scene, real durations via ffprobe. **Voiceover only — never music.** |
| 4 | `assemble.py` | Fit clips to VO, fade (0.15s)/cut transitions, continuous VO track, optional burned ASS captions, **1080×1920 only** (the 720p result key is kept empty for compatibility), 30fps, yuv420p, faststart. |
| 5 | `make_reel.py` | Orchestrates 0→4, uploads reel + stills to MinIO in parallel, returns the Result JSON. |
| 6 | `server.py` | FastAPI: `POST /make-reel`, `GET /health`, port 8189. |

### Secrets

All in `/workspace/.env` (mode 600), never in source: `ELEVEN_API_KEY`,
`MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`.
The ElevenLabs key is IP-restricted — this box (`198.53.64.194`) is allowlisted.

### Run it

```bash
cd /workspace/reelkit
python make_reel.py                 # direct, uses the built-in demo request
python server.py                    # API on :8189
curl -X POST localhost:8189/make-reel -H 'Content-Type: application/json' \
     --data-binary @work/api_req.json
```
