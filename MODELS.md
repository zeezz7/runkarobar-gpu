# Installed models — ComfyUI on Vast.ai RTX 5090

Host facts that drove the choices below:

| | |
|---|---|
| GPU | RTX 5090, **32 GB VRAM**, driver 580.95.05 / CUDA 13.2 |
| torch | 2.10.0+cu130 in `/venv/main` |
| ComfyUI | 0.28.0 at `/workspace/ComfyUI`, service `comfyui` on `127.0.0.1:18188` |
| System RAM | **32 GB** (low — constrains CPU offload) |
| Disk | single 164 GB overlay, 138 GB free at time of install |

> **Storage note:** `/workspace` is **not** a separate small volume on this box — it is
> the *same* overlay filesystem as `/` (identical fsid `954e51041545a61e`, confirmed by
> `stat -f` and a 1 GB test allocation). There was no need to relocate `models/` to a
> larger disk; it already sits on the 138 GB filesystem. `workspace_is_volume` is
> `false`, which means **nothing here survives a recycle/destroy** — re-run
> `download_models.sh` to rebuild.

Everything is fetched by `download_models.sh`, which is idempotent and size-verifies
each file against HuggingFace's `x-linked-size` header.

```bash
bash /workspace/download_models.sh all     # or: ltx | flux | wan
```

## Summary — all three verified on the 5090

| Model | Job | On-disk | Output | Render | Peak VRAM |
|---|---|---|---|---|---|
| LTXV 13B 0.9.8 fp8 | image→video | 15.7 GB | 768×512, 121f, 24 fps, 5.04 s | ~70 s | 20.3 GB |
| FLUX.1-dev fp8 | text→image | 12.5 GB | 1024×1024 | 25 s | 17.2 GB |
| Wan 2.2 I2V 14B fp8 | image→video | 35.6 GB | 720×480, 81f, 16 fps, 5.06 s | 240 s | **32.1 GB ⚠️** |

Shared T5 deduped once: **−5.16 GB**. Total on disk **~63.8 GB**, 93 GB free remaining.

**Run these serially, never concurrently** — 32 GB VRAM and only 30 GB usable system RAM.

API-format workflows (all executed and confirmed working):
`user/default/workflows/{ltxv13b_i2v_api,flux_t2i_api,wan22_i2v_api}.json`

Queue any of them with:
```bash
source /venv/main/bin/activate
python3 -c "
import json,urllib.request,uuid
p=json.load(open('/workspace/ComfyUI/user/default/workflows/flux_t2i_api.json'))
r=urllib.request.Request('http://127.0.0.1:18188/prompt',
  data=json.dumps({'prompt':p,'client_id':str(uuid.uuid4())}).encode(),
  headers={'Content-Type':'application/json'})
print(json.load(urllib.request.urlopen(r)))"
```

---

## Shared text encoder (deduped)

`models/text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors` — **5,157,348,688 bytes**

Downloaded once for LTX-Video and **reused by FLUX**. I verified these are the same
file rather than assuming: HuggingFace serves
`Comfy-Org/mochi_preview_repackaged/.../t5xxl_fp8_e4m3fn_scaled.safetensors` and
`comfyanonymous/flux_text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors` from the
identical xet content hash `31868d1bd1d855ac37b339079a06166ed46c230f9cce4904d7e09408a77a13e8`
at identical byte length. **Saves 5.16 GB.**

Wan 2.x does **not** share this — it uses UMT5-XXL, a different encoder, so it carries
its own.

---

## LTX-Video — LTXV 13B 0.9.8 dev (fp8) ✅ verified end-to-end

| File | Folder | Size |
|---|---|---|
| `ltxv-13b-0.9.8-dev-fp8.safetensors` | `models/checkpoints/` | 15,694,279,916 B (15.7 GB) |
| `t5xxl_fp8_e4m3fn_scaled.safetensors` | `models/text_encoders/` | shared, see above |

Source: `Lightricks/LTX-Video` (ungated).

**No separate VAE file.** The VAE is bundled inside the checkpoint — verified by
reading the safetensors index: 1444 tensors, including `vae.decoder.*` keys, mixed
BF16 + F8_E4M3 dtypes.

**No custom nodes required.** ComfyUI core carries native LTXV support
(`comfy/ldm/lightricks/`, `comfy_extras/nodes_lt.py`), and the checkpoint is
recognised by the `adaln_single` key that `comfy/model_detection.py:362` keys off.

### Workflows
- `user/default/workflows/ltxv13b_i2v_api.json` — API format, the graph actually executed
- `user/default/workflows/LTXV 13B 0.9.8 fp8 - Image to Video.json` — GUI format, openable in the UI

Both are the **official bundled ComfyUI template** (`comfyui_workflow_templates_json/
templates/ltxv_image_to_video.json`) with the checkpoint and text encoder swapped to the
13B fp8 build and length raised 97 → 121 frames.

> **Trap worth recording:** the sibling template `api_ltxv_image_to_video.json` is *not*
> the API-format version of the local workflow. It drives `LtxvApiImageToVideo`, the
> **paid Lightricks cloud partner node**. Using it would have billed a remote API instead
> of running on this GPU.

### Settings
`768x512`, `length=121` (must satisfy `(n-1) % 8 == 0`), `strength=1.0`, 30 steps,
`cfg=3.0`, sampler `euler`, `LTXVScheduler(max_shift 2.05, base_shift 0.95, terminal 0.1)`,
`LTXVConditioning(frame_rate=25)`, `CreateVideo(fps=24)`.

Template default `strength` is `0.15`; I used `1.0` for tighter adherence to the input
frame, which held subject identity well.

### Verified result
- `output/video/ltxv13b_i2v_static_00001_.mp4` — 768x512, 121 frames, 24 fps, **5.04 s**, h264
- Render time **~70–80 s**; peak VRAM **20.3 GB / 32 GB** — comfortable, no offload
- Motion sanity-checked numerically: 121 frames decoded, mean inter-frame delta 2.09,
  **0 black frames, 0 static frames** (i.e. a real moving clip, not a frozen or empty file)

---

## FLUX.1-dev (fp8) ✅ verified end-to-end

| File | Folder | Size |
|---|---|---|
| `flux1-dev-fp8-e4m3fn.safetensors` | `models/diffusion_models/` | 11,901,525,888 B (11.9 GB) |
| `clip_l.safetensors` | `models/text_encoders/` | 246,144,152 B |
| `ae.safetensors` (FLUX VAE) | `models/vae/` | 335,304,388 B |
| `t5xxl_fp8_e4m3fn_scaled.safetensors` | `models/text_encoders/` | **reused from LTX — not downloaded** |

New bytes on disk: **12.48 GB** (not 17.2 GB — see below).

### Why split loader, not the all-in-one checkpoint
The documented all-in-one `flux1-dev-fp8.safetensors` is 17.2 GB and bundles its own
T5 + CLIP-L + VAE — which would have duplicated the 5.16 GB T5 already present. The
split setup (`UNETLoader` + `DualCLIPLoader` + `VAELoader`) costs 12.48 GB, reuses the
T5, and additionally supports LoRAs and explicit `FluxGuidance`.

### Licensing and sourcing caveats — read before commercial use
- **FLUX.1-dev is licensed NON-COMMERCIAL.**
- `black-forest-labs/FLUX.1-dev` is **gated** — returns 401 with no HF token on this box.
- `Comfy-Org/flux1-dev` (ungated) publishes **no split fp8 UNet**, only the 23.8 GB bf16
  file. The fp8 UNet therefore comes from **`Kijai/flux-fp8`** — ungated, ~75k
  downloads/30d, the standard community fp8 repackage. This is the one **non-first-party**
  artifact in this install. It was validated: safetensors header parsed to 780 tensors,
  all dtype `F8_E4M3`, with `double_blocks`/`single_blocks` present (correct FLUX
  architecture), and it renders correctly.
- `clip_l` and `ae` URLs are byte-for-byte the ones ComfyUI's own bundled template links to.

### Workflow
`user/default/workflows/flux_t2i_api.json`, mirroring the bundled official template
`flux_dev_full_text_to_image.json`:
`EmptySD3LatentImage` 1024×1024 (16-channel — **not** `EmptyLatentImage`),
`DualCLIPLoader` type `"flux"`, negative via `ConditioningZeroOut` off the positive
encode, KSampler steps=20 / cfg=1.0 / euler / simple.

Two deliberate departures from the template:
- **`FluxGuidance(3.5)`** added on the positive path — optional (ComfyUI defaults
  guidance to 3.5 when absent) but makes the knob explicit.
- **`weight_dtype: "fp8_e4m3fn"`** instead of the template's `"default"`. This matters:
  the template assumes the bf16 file, but ours is already fp8 on disk, and `"default"`
  can let ComfyUI upcast to bf16 (~23.8 GB VRAM) — a real OOM risk on a 32 GB card.
  Pinning holds it at ~11.9 GB.

### Verified result
`output/flux_t2i_00001_.png` — 1024×1024, render **25 s**, peak VRAM **17.2 GB / 32 GB**.

If fp8 proves slow, `fp8_e4m3fn_fast` enables fp8 matmul (sm120 supports it) for a
speedup at slight quality cost — untested.

## Wan 2.2 I2V 14B (fp8) ✅ verified end-to-end

| File | Folder | Size |
|---|---|---|
| `wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors` | `models/diffusion_models/` | 14,294,742,832 B |
| `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors` | `models/diffusion_models/` | 14,294,742,832 B |
| `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | `models/text_encoders/` | 6,735,906,897 B |
| `wan_2.1_vae.safetensors` | `models/vae/` | 253,815,318 B |

Total **35.58 GB**, all from `Comfy-Org/Wan_2.2_ComfyUI_Repackaged` (first-party, ungated).

**Two files that are easy to get wrong, both confirmed rather than assumed:**
- The VAE is **`wan_2.1_vae.safetensors`**, not `wan2.2_vae.safetensors`. The 2.2 VAE
  exists in the same repo but serves the **5B ti2v** model only.
- The text encoder is **UMT5**, a different model from the T5-XXL used by LTX/FLUX —
  it **cannot** be shared. `CLIPLoader`'s type enum has a distinct `"wan"` entry.

### Two-expert wiring
Wan 2.2 14B is a **two-expert** model — the high-noise and low-noise files are both
required, not alternatives. Parameters were read out of ComfyUI's bundled template
`video_wan2_2_14B_i2v.json` (whose sampler settings route through `ComfySwitchNode`
toggles selecting a 4-step-LoRA path vs a plain path; the plain branch,
`PrimitiveBoolean=False`, is the one used here):

- Each expert gets its **own** `ModelSamplingSD3(shift=5.0)`.
- **Pass 1 — high-noise:** `add_noise=enable`, steps 20, cfg 3.5, euler/simple,
  `start_at_step=0`, `end_at_step=10`, `return_with_leftover_noise=enable`.
- **Pass 2 — low-noise:** `add_noise=disable`, same steps/cfg/sampler,
  `start_at_step=10`, `end_at_step=10000`, `return_with_leftover_noise=disable`,
  consuming pass 1's latent.
- Both samplers share the conditioning from `WanImageToVideo`. No CLIP-Vision node —
  the official 2.2 I2V template doesn't use one.

`WanImageToVideo.length` has `step=4` (the 4n+1 constraint): **81 frames @ 16 fps = 5.06 s**.
Resolution 720×480 — Wan's native 480p tier, preserving the 3:2 aspect of the input.

### Workflow
`user/default/workflows/wan22_i2v_api.json`

### Verified result
`output/video/Wan2.2_i2v_00001_.mp4` — 720×480, 81 frames, 16 fps, **5.06 s**, h264.
Render **240 s**. Motion check: 0 black frames, 0 static frames, mean inter-frame delta 3.40.

### ⚠️ VRAM headroom is thin — measured, not theoretical
Observed peak **32,056 MiB of 32,607 MiB** — about **550 MB from OOM** at 720×480/81 frames.
This is the tightest model in this install. Before raising resolution or frame count,
expect to need mitigation:
- add `--lowvram` / `--novram` to `COMFYUI_ARGS`, or
- fetch the 4-step **lightx2v** LoRAs the official template references, which cut steps
  20 → 4 and greatly reduce both time and memory pressure (not installed — out of scope).

**System RAM is also a genuine constraint.** 30 GB usable + 8 GB swap vs ~35.3 GB of
weights across both experts plus the encoder — they cannot all stay resident, so the
step-10 expert swap re-reads 14.3 GB from disk. Run the three model families
**serially, never concurrently**.
