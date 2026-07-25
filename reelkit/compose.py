"""
Stage 1 - scene images.

Two paths, chosen by the brain per scene:

  compose_animate  (the product is on screen)
      1. segment the REAL product out of the supplied photograph (BiRefNet)
      2. generate the background/scene described by scene.visual (Qwen-Image-2512)
      3. composite the real product PIXELS onto that scene at a sensible scale
         and placement
      4. harmonise the seam with PIL only - a light ambient colour pull and a
         soft contact shadow

      Step 4 is deliberately NOT a diffusion pass. A diffusion pass re-renders
      the product and garbles the printed label; that was measured on this box
      (HiDream-E1.1 turned "MEN" into "NEN"). Compositing kept the label
      byte-identical, so the product pixels are never handed to a sampler.

  generate_animate  (no product on screen - atmosphere / texture / b-roll)
      generate scene.visual directly, no compositing.
"""
import os

from PIL import Image, ImageFilter, ImageStat

import common

NEG = ("text, watermark, logo, brand name, signature, people, hands, "
       "cluttered, deformed, low quality, blurry, jpeg artifacts")

# Where the product sits in frame when composited.
PRODUCT_HEIGHT_FRAC = 0.52   # product occupies ~52% of frame height
PRODUCT_CENTER_Y = 0.55      # its centre sits slightly below the middle


# ---------------------------------------------------------------- segmentation
def segment(product_path, job_dir, tag):
    """Return (rgba_cutout_path, coverage_fraction). Uses BiRefNet in ComfyUI."""
    name = f"rk_src_{tag}{os.path.splitext(product_path)[1] or '.png'}"
    common.stage_input(product_path, name)

    wf = common.load_tpl("tpl_mask.api.json")
    common.set_class(wf, "LoadImage", image=name)
    common.set_class(wf, "SaveImage", filename_prefix=f"rk_mask_{tag}")
    outs = common.comfy_run(wf)
    if not outs:
        raise RuntimeError("segmentation produced no mask")
    mask_path = outs[0]

    src = Image.open(product_path).convert("RGB")
    mask = Image.open(mask_path).convert("L").resize(src.size, Image.LANCZOS)
    rgba = src.copy()
    rgba.putalpha(mask)
    bbox = mask.point(lambda p: 255 if p > 40 else 0).getbbox()
    if bbox:
        rgba = rgba.crop(bbox)
    cut = os.path.join(job_dir, f"cut_{tag}.png")
    rgba.save(cut)

    import numpy as np
    cov = float((np.asarray(mask) > 40).mean())
    common.log("compose", f"segmented {os.path.basename(product_path)} "
                          f"-> {rgba.size[0]}x{rgba.size[1]} ({cov*100:.0f}% of frame)")
    return cut, cov


# ------------------------------------------------------------------ generation
def generate_scene(prompt, w, h, out_prefix, seed=0, steps=50, cfg=4.0):
    wf = common.load_tpl("tpl_t2i_qwen.api.json")
    common.set_class(wf, "EmptySD3LatentImage", width=w, height=h, batch_size=1)
    common.set_prompts(wf, prompt, NEG)
    common.set_class(wf, "KSampler", seed=seed or 1, steps=steps, cfg=cfg,
                     sampler_name="euler", scheduler="simple", denoise=1.0)
    common.set_class(wf, "SaveImage", filename_prefix=out_prefix)
    outs = common.comfy_run(wf)
    if not outs:
        raise RuntimeError("scene generation produced no image")
    return outs[0]


# ----------------------------------------------------------------- harmonising
def _harmonise(prod_rgba, scene_img, strength=0.18):
    """
    Pull the cut-out's colour balance a little toward the scene's ambient.
    PIL arithmetic only - no model touches these pixels.
    """
    import numpy as np
    p = np.asarray(prod_rgba.convert("RGBA")).astype(np.float32)
    alpha = p[..., 3:4] / 255.0
    if alpha.sum() < 1:
        return prod_rgba
    scene_mean = np.asarray(ImageStat.Stat(scene_img.convert("RGB")).mean[:3],
                            dtype=np.float32)
    prod_mean = (p[..., :3] * alpha).reshape(-1, 3).sum(0) / max(float(alpha.sum()), 1.0)
    shift = (scene_mean - prod_mean) * strength
    p[..., :3] = np.clip(p[..., :3] + shift, 0, 255)
    return Image.fromarray(p.astype("uint8"), "RGBA")


def _contact_shadow(size, prod_rgba, y_bottom):
    """Soft elliptical shadow under the product so it sits in the scene."""
    w, h = size
    pw, ph = prod_rgba.size
    shadow = Image.new("L", size, 0)
    from PIL import ImageDraw
    d = ImageDraw.Draw(shadow)
    sw, sh = int(pw * 0.85), max(int(ph * 0.07), 8)
    x0 = (w - sw) // 2
    y0 = min(y_bottom - sh // 2, h - sh - 1)
    d.ellipse([x0, y0, x0 + sw, y0 + sh], fill=120)
    return shadow.filter(ImageFilter.GaussianBlur(radius=max(sh // 2, 6)))


def composite(cut_path, scene_path, out_path,
              height_frac=PRODUCT_HEIGHT_FRAC, center_y=PRODUCT_CENTER_Y):
    scene = Image.open(scene_path).convert("RGB")
    W, H = scene.size
    prod = Image.open(cut_path).convert("RGBA")

    target_h = int(H * height_frac)
    scale = target_h / prod.height
    prod = prod.resize((max(int(prod.width * scale), 1), target_h), Image.LANCZOS)
    if prod.width > int(W * 0.9):                      # never overflow the frame
        s2 = int(W * 0.9) / prod.width
        prod = prod.resize((int(prod.width * s2), int(prod.height * s2)), Image.LANCZOS)

    prod = _harmonise(prod, scene)

    x = (W - prod.width) // 2
    y = int(H * center_y) - prod.height // 2
    y = max(0, min(y, H - prod.height))

    out = scene.copy()
    sh = _contact_shadow((W, H), prod, y + prod.height)
    out = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), out, sh.point(
        lambda p: int(p * 0.55)))
    out.paste(prod, (x, y), prod)
    out.save(out_path)
    common.log("compose", f"composited -> {os.path.basename(out_path)} "
                          f"(product {prod.width}x{prod.height} at y={y})")
    return out_path


# -------------------------------------------------------------------- per scene
def scene_image(scene, product_path, w, h, job_dir, seed=0, cut_cache={}):
    """Produce the still for one storyboard scene. Returns its path."""
    n = scene["n"]
    tag = f"s{n}"
    prefix = f"rk_{os.path.basename(job_dir)}_{tag}"

    if scene["method"] == "compose_animate":
        if product_path not in cut_cache:
            cut_cache[product_path] = segment(product_path, job_dir, "prod")[0]
        cut = cut_cache[product_path]
        bg_prompt = (f"{scene['visual']}. Empty scene with no product and no objects "
                     f"in the centre, clean composition, photorealistic, cinematic lighting.")
        bg = generate_scene(bg_prompt, w, h, prefix + "_bg", seed=seed + n)
        out = os.path.join(job_dir, f"scene_{n}.png")
        return composite(cut, bg, out)

    out_gen = generate_scene(
        f"{scene['visual']}. Photorealistic, cinematic lighting, no text, no logos.",
        w, h, prefix + "_gen", seed=seed + n)
    out = os.path.join(job_dir, f"scene_{n}.png")
    Image.open(out_gen).convert("RGB").save(out)
    common.log("compose", f"generated -> {os.path.basename(out)}")
    return out
