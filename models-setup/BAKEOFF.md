# Render bake-off — results and decision table

Box: RTX PRO 6000 Blackwell (96 GB, cc 12.0), ComfyUI 0.28.0, all models fp8.
Reproduce with `./bakeoff.sh all <ref-image>`. Raw rows: `logs/bakeoff_results.tsv`.

Nothing here is optimised — ComfyUI runs **without `--fast`**, every workflow loads
`weight_dtype="default"`, and all video jobs were forced to ~5 s (121 frames), which
is well above several templates' defaults. Times are comparable to each other, not
best-case.

---

## Decision table

| Model | Job | Time | Peak VRAM | Output URL | Quality note |
|---|---|---:|---:|---|---|
| **HiDream-I1-Full** fp8 | text→image, UHD | 90 s | ~40 GB | [hidream_uhd_00001_.png](https://staging-storage.runkarobar.com/images/hidream_uhd_00001_.png) | Excellent. Sharp 3840×2160 after 4x-UltraSharp. **Best image quality in the set.** |
| **HiDream-E1.1** fp8 | product hero (edit) | 75 s | 64.2 GB | [hero_hidream.png](https://staging-storage.runkarobar.com/images/hero_hidream.png) | **Product fidelity FAIL.** Headlines survive; "MEN"→"NEN", "Facewash"/"AHA"/"VITAMIN C" garbled. |
| HiDream-E1.1 | dress bg swap, denoise 1.0 | ~75 s | ~64 GB | [dress_bg_dn1p0.png](https://staging-storage.runkarobar.com/images/dress_bg_dn1p0.png) | Background cleanly replaced, but embroidery redrawn, dupatta oversaturated, face changed. |
| HiDream-E1.1 | dress bg swap, denoise 0.6 | ~75 s | ~64 GB | [dress_bg_dn0p6.png](https://staging-storage.runkarobar.com/images/dress_bg_dn0p6.png) | **Pure noise — total failure.** E1.1 requires denoise=1.0. |
| **LTX-Video 13B 0.9.8** fp8 | image→video 5.0 s | 130 s | 86.8 GB | [bakeoff_ltx098.mp4](https://staging-storage.runkarobar.com/reels/bakeoff_ltx098.mp4) | Weakest i2v. Product cropped, drifts and shrinks, label total mush. |
| **LTX-2.3 22B** fp8 | image→video 4.8 s | 171 s | **97.2 GB** | [bakeoff_ltx23.mp4](https://staging-storage.runkarobar.com/reels/bakeoff_ltx23.mp4) | Best text/label stability, but near-static motion + one hallucinated object. 654 MiB from OOM. |
| **Wan 2.2 I2V +LightX2V** fp8 | image→video 5.1 s | **70 s** | 96.3 GB | [bakeoff_wan22_turbo.mp4](https://staging-storage.runkarobar.com/reels/bakeoff_wan22_turbo.mp4) | **Winner.** Real cinematic pull-back to lit studio set, product coherent, label as legible as source. |
| Wan 2.2 I2V baseline | image→video 5.1 s | 391 s | 97.0 GB | [bakeoff_wan22_base.mp4](https://staging-storage.runkarobar.com/reels/bakeoff_wan22_base.mp4) | Same fidelity as turbo, plainer scene. **No reason to use over turbo.** |
| **HunyuanVideo 720p** fp8 | text→video 5.0 s | 385 s | 96.1 GB | [bakeoff_hunyuan.mp4](https://staging-storage.runkarobar.com/reels/bakeoff_hunyuan.mp4) | Beautiful photoreal lighting, but invented a *different* product and barely moves. |
| **Mochi 1** fp8 | text→video 5.0 s | 390 s | 97.2 GB | [bakeoff_mochi.mp4](https://staging-storage.runkarobar.com/reels/bakeoff_mochi.mp4) | Weakest overall. Blank unbranded tube, soft focus, minimal motion. |
| **Qwen2.5-VL-7B** | vision guard | 11 s | 48.4 GB | `logs/guard_hero.json` | Runs, returns valid JSON — but **unreliable**, see below. |

Reference input: [product_ref](https://staging-storage.runkarobar.com/videos/ref/312246c7-89cc-458e-8f37-dedb6451797a-0.jpg) ·
dress source: [dress_src](https://staging-storage.runkarobar.com/videos/src/53a2cc8d-fbd6-4402-bc47-29e3835a220e-0.jpg)

---

## Winners

| Category | Winner | Why |
|---|---|---|
| **Best image** | **HiDream-I1-Full** | Only model producing clean, sharp, artefact-free output. But it is text→image only — it cannot preserve an existing product. |
| **Best fast video** | **Wan 2.2 + LightX2V (4-step)** | 70 s for 5 s of video, **5.6× faster** than its own baseline with no visible quality loss. |
| **Best hero video** | **Wan 2.2 + LightX2V** | Also wins here. It is the only model that produced genuine, purposeful camera motion while keeping the product intact. |
| **Best label stability** | LTX-2.3 | Holds text best across frames, but at 97.2 GB VRAM and with almost no motion — a niche win. |
| **Guard working?** | ⚠️ **Partially** | Runs reliably and returns parseable JSON, but its judgements cannot be trusted as a gate. |

**Wan 2.2 + LightX2V is the clear overall winner for video.** Use it as the default.

---

## The critical finding: no model preserves a product

Both fidelity tests failed, in the same way:

- **Nivea label:** "MEN"→"NEN", "Facewash"/"AHA"/"VITAMIN C" destroyed.
- **Dress:** embroidery redrawn, dupatta recoloured, face changed.

Two hypotheses were tested and **both were disproved**:

1. *"Higher resolution will preserve detail"* — at 2 MP the label got **much worse**
   ("NIVEA"→"MYM"). E1.1 is trained near 1 MP; going off-distribution collapses it.
2. *"Lower denoise will preserve the original"* — at denoise 0.6 the output was
   **pure noise**. E1.1's InstructPixToPix conditioning requires `denoise=1.0`;
   the sampler injects full noise regardless, so a truncated sigma schedule cannot resolve.

**Conclusion: a diffusion edit re-renders everything it touches.** Any pipeline that
needs an accurate label or garment must not let the model draw that region.

### SOLVED — masked compositing (`workflows/run_dress_composite.api.json`)

The fix works and is verified. Pipeline:

1. `LoadBackgroundRemovalModel` + `RemoveBackground` (BiRefNet) → foreground mask
2. `GrowMask -2` + `FeatherMask` → tighten edge so no old background haloes through
3. HiDream-I1-Full generates a new backdrop at **exactly** the source resolution
   (no resampling, so the composite aligns pixel-for-pixel)
4. `ImageCompositeMasked` lays the **original pixels** over the generated backdrop

Result: [dress_bg_composite.png](https://staging-storage.runkarobar.com/images/dress_bg_composite.png)

Measured over 196,783 foreground pixels vs the source:

| Metric | Value |
|---|---|
| Max channel deviation | 11 / 255 (4%) |
| Mean channel deviation | 1.48 / 255 (0.6%) |
| Pixels within 2 levels | 93% |
| Background pixels changed | 99.9% |

The residual is soft-edge alpha blending + JPEG→PNG rounding, not redrawing. Embroidery,
sequins, dupatta lace, palazzo stitching and face are all preserved exactly.

Requires `Comfy-Org/BiRefNet` → `models/background_removal/birefnet.safetensors` (444 MB),
now installed. The same pattern is the fix for the Nivea label.

| Attempt | Dress | Background |
|---|---|---|
| E1.1 denoise 1.0 | ❌ embroidery redrawn, face changed | ✅ replaced |
| E1.1 denoise 0.6 | ❌ pure noise | ❌ pure noise |
| **Masked composite** | ✅ **pixel-exact** | ✅ replaced |

Because every i2v run started from the already-damaged hero, the video rows rank
**motion and coherence only** — they cannot rank product fidelity.

---

## Vision guard: works mechanically, unreliable in judgement

Raw output on the product hero:

```json
{
  "branding": {"pass": true,
    "detected": ["NIVEA","NEN","DARK SPOT REDUCTION","3D ACTIONS","GLUTA","ALPHA","VITAMIN C"],
    "notes": "Brand and product details clearly visible."},
  "modesty": {"pass": true, "rating": "safe", "notes": "No nudity or inappropriate content."},
  "quality": {"pass": true, "score": 8, "issues": "No apparent artifacts or compression issues.",
    "notes": "High-quality image with clear details."},
  "overall_pass": true
}
```

Three defects, all observed:

1. **Branding logic inverted.** The prompt says `pass=false` if any brand/logo is
   visible. It listed NIVEA and still returned `pass=true`. On a different image
   (a landscape with no branding at all) it returned `pass=false` claiming
   "Watermark present." It gets the rule backwards in *both* directions.
2. **Blind to the actual defect.** It scored quality **8/10** with "no apparent
   artifacts" on an image whose label text is visibly corrupted.
3. **Type instability.** `quality.issues` came back as a string here and as a list
   elsewhere; do not parse assuming a type.

**Do not use it as an automated gate as configured.** It is usable as a *triage*
signal, and there is one genuinely valuable behaviour: its `detected` array
transcribes label text literally — it independently returned **"NEN"** and
**"ALPHA"** where the source reads "MEN" and "AHA". Diffing that array against
expected label strings is a far better product-fidelity check than its own
`pass` booleans.

---

## Performance levers (none applied)

| Lever | Expected gain |
|---|---|
| Use distilled/turbo paths | **5.6× measured** on Wan |
| Launch ComfyUI with `--fast` / `weight_dtype=fp8_e4m3fn_fast` | ~20–40% on fp8 weights (sm_120 supports it) |
| Drop to native frame counts (Hunyuan 73, Mochi 37 vs the 121 forced here) | up to ~3× on Mochi |
| Keep one model resident instead of round-robin | removes 16–43 GB of reload per job |
