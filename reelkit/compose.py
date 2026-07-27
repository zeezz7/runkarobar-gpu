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
import guards

# One global negative was being used for all three paths, which actively fought
# two of them: an edit is told to KEEP the person and the logo while "people,
# hands, logo, brand name" were being negatively prompted away.
# Invented text is the single most damaging failure this pipeline produces - a
# fake logo or a row of gibberish price tags ruins an otherwise good frame - so
# every text-shaped artefact is named explicitly. The garment/anatomy terms only
# make sense when a person is in shot; on a product-only scene they waste
# conditioning, so NEG_PRODUCT drops them.
NEG_TEXT = ("signature, handwriting, handwritten script, artist mark, corner text, "
            "watermark, text, lettering, letters, words, numbers, caption, "
            "subtitle, label, price tag, sticker, sign, logo, emblem, brand mark, "
            "gibberish text, garbled writing, fake logo, shop sign, signage, "
            "brand board, engraved plaque, printed box lid, poster")
NEG_EDIT = ("changed clothing, different garment, altered colours, warped fabric, "
            "distorted face, extra limbs, deformed hands, blurry, low quality, "
            "jpeg artifacts, " + NEG_TEXT)
NEG_PRODUCT = (NEG_TEXT + ", different product, altered design, changed colours, "
               "distorted shape, duplicated product, extra objects, people, hands, "
               "blurry, soft focus, low quality, jpeg artifacts")
NEG_BG = ("product, merchandise, clothing, garment, shirt, bottle, packaging, "
          "people, person, model, mannequin, hands, text, watermark, logo, "
          "brand name, cluttered, low quality, blurry")
NEG_GEN = ("text, watermark, logo, brand name, signature, deformed, extra limbs, "
           "deformed hands, low quality, blurry, jpeg artifacts")
NEG = NEG_GEN          # backwards-compatible default

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
# FAST path uses the installed 4-step Lightning LoRAs. Backgrounds sit behind a
# composited product and edits are graded afterwards, so the extra 46 steps buy
# very little here while costing ~117s per image (measured: 127s vs ~10s).
FAST = os.environ.get("REELKIT_FAST", "1") != "0"
T2I_LORA = "Qwen-Image-2512-Lightning-4steps.safetensors"
EDIT_LORA = "Qwen-Image-Edit-2511-Lightning-4steps.safetensors"


def _add_lora(wf, lora_name, after_node, sampler_node="17"):
    wf["900"] = {"class_type": "LoraLoaderModelOnly",
                 "inputs": {"lora_name": lora_name, "strength_model": 1.0,
                            "model": [after_node, 0]}}
    wf[sampler_node]["inputs"]["model"] = ["900", 0]
    return wf


def generate_scene(prompt, w, h, out_prefix, seed=0, steps=None, cfg=None,
                   negative=None):
    wf = common.load_tpl("tpl_t2i_qwen.api.json")
    if FAST:
        _add_lora(wf, T2I_LORA, "11")
        steps, cfg = steps or 4, cfg if cfg is not None else 1.0
    else:
        steps, cfg = steps or 50, cfg if cfg is not None else 4.0
    common.set_class(wf, "EmptySD3LatentImage", width=w, height=h, batch_size=1)
    common.set_prompts(wf, prompt, negative or NEG_GEN)
    common.set_class(wf, "KSampler", seed=seed or 1, steps=steps, cfg=cfg,
                     sampler_name="euler", scheduler="simple", denoise=1.0)
    common.set_class(wf, "SaveImage", filename_prefix=out_prefix)
    outs = common.comfy_run(wf)
    if not outs:
        raise RuntimeError("scene generation produced no image")
    return outs[0]


def edit_scene(product_path, instruction, out_prefix, seed=0, steps=None, cfg=None,
               ref_paths=None, negative=None):
    """
    Qwen-Image-Edit-2511: keep the supplied photograph's subject, change its
    world. This is the right tool when the product is photographed IN CONTEXT -
    worn by a model, held in a hand, staged on a set.

    Compositing cannot handle those: segmenting a model shot yields the whole
    PERSON, which then gets pasted over a generated scene that also contains a
    person, producing two overlapping faces (observed on the Snitch run).

    `ref_paths` are EXTRA reference images wired into the encoder's spare
    `image2`/`image3` slots. That is how same-model anchoring works: a follow-on
    scene passes the ANCHOR frame as `product_path` (so it is `image1`, the
    thing being re-framed, which is what the SAME_MODEL guard calls "the FIRST
    reference image") and the original product photo as a ref, so the garment
    stays honest while the face carries over. Without this every edit re-rolled
    the person and the model's face changed between scenes.
    """
    name = f"rk_edit_{os.path.basename(out_prefix)}{os.path.splitext(product_path)[1] or '.png'}"
    common.stage_input(product_path, name)
    wf = common.load_tpl("tpl_qwen_edit.api.json")
    common.set_class(wf, "LoadImage", image=name)

    for slot, extra in enumerate(( ref_paths or [])[:2], start=2):
        if not extra or not os.path.isfile(extra):
            continue
        rname = f"rk_ref{slot}_{os.path.basename(out_prefix)}.png"
        Image.open(extra).convert("RGB").save(
            os.path.join(common.COMFY_INPUT, rname))
        load_id, scale_id = f"9{slot}0", f"9{slot}1"
        wf[load_id] = {"class_type": "LoadImage",
                       "inputs": {"image": rname, "upload": "image"}}
        # Same scaling the template applies to image1 - an unscaled reference at
        # a different resolution shifts the latent and washes the edit out.
        wf[scale_id] = {"class_type": "FluxKontextImageScale",
                        "inputs": {"image": [load_id, 0]}}
        for _, node in common.nodes_of(wf, "TextEncodeQwenImageEditPlus"):
            node["inputs"][f"image{slot}"] = [scale_id, 0]
        common.log("compose", f"  + reference image{slot}: {os.path.basename(extra)}")

    if FAST:
        for _, node in common.nodes_of(wf, "PrimitiveBoolean"):
            node["inputs"]["value"] = True          # template's Lightning switch
        steps, cfg = steps or 4, cfg if cfg is not None else 1.0
    else:
        for _, node in common.nodes_of(wf, "PrimitiveBoolean"):
            node["inputs"]["value"] = False
        steps, cfg = steps or 40, cfg if cfg is not None else 4.0
    for _, node in common.nodes_of(wf, "LoraLoaderModelOnly"):
        node["inputs"]["lora_name"] = EDIT_LORA
    common.set_prompts(wf, instruction, negative or NEG_EDIT,
                       cls="TextEncodeQwenImageEditPlus", field="prompt")
    common.set_class(wf, "KSampler", seed=seed or 1, denoise=1.0)
    common.set_class(wf, "SaveImage", filename_prefix=out_prefix)
    outs = common.comfy_run(wf)
    if not outs:
        raise RuntimeError("scene edit produced no image")
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
def scene_shows_person(scene, tpl_defaults=None):
    """
    Does this scene contain a person?

    One definition, used by BOTH the guard selection here and the anchor choice
    in make_reel. They were duplicated and drifted: make_reel required
    mode=="scene", but the brain routinely returns mode "product" for an
    outfit-check scene (the outfit IS the product), so the anchor never got set
    and outfit-check silently lost same-model consistency.
    """
    d = tpl_defaults or {}
    return (scene.get("mode") == "scene" or scene.get("method") == "lipsync"
            or bool(d.get("anchorModel")))


def scene_image(scene, product_path, w, h, job_dir, seed=0, cut_cache={},
                bg_cache=None, height_frac=PRODUCT_HEIGHT_FRAC,
                center_y=PRODUCT_CENTER_Y, tracer=None, tpl_defaults=None,
                anchor=None):
    """
    Produce the still for one storyboard scene. Returns its path.

    `bg_cache` lets a re-composite (guard retry) reuse the already-generated
    background and only change the product's scale/placement. Regenerating the
    scene costs another ~127s diffusion for no reason - the brief asks a retry to
    "reposition/rescale", not to redraw the world.
    """
    n = scene["n"]
    tag = f"s{n}"
    prefix = f"rk_{os.path.basename(job_dir)}_{tag}"
    d = tpl_defaults or {}
    # A scene shows a person when the brain framed it that way, or when the
    # template is inherently about a person (outfit-check, ad, testimonial).
    shows_person = scene_shows_person(scene, d)

    if scene["method"] in ("edit_animate", "lipsync"):
        setting = (scene.get("background") or scene["visual"]).strip().rstrip(".")
        setting = guards.desexualise(setting)
        # A follow-on person scene re-frames the ANCHOR instead of the product
        # photo, so the same face carries the reel.
        primary, refs = product_path, []
        followon = False
        if shows_person and d.get("anchorModel") and anchor and anchor != product_path:
            primary, refs, followon = anchor, [product_path], True

        shot = guards.desexualise((scene.get("visual") or "").strip().rstrip("."))
        if followon:
            lead = (f"Keep the SAME person and the SAME outfit exactly as in this "
                    f"photograph - identical face, hair, skin tone and clothing. "
                    f"Re-frame them for this new shot: {shot}. Setting: {setting}.")
        else:
            lead = (f"Keep the product exactly as photographed - identical shape, "
                    f"colours, materials and every detail, unchanged. Change only "
                    f"the surroundings to: {setting}.")
        instruction = lead + (guards.person_guards(d, is_followon=followon)
                              if shows_person else guards.product_guards())
        negative = NEG_EDIT if shows_person else NEG_PRODUCT
        instruction += " Photorealistic editorial photograph, sharp detail."
        if tracer:
            tracer.write_json(f"scene_{n}_compose.json", {
                "path": scene["method"], "model": "Qwen-Image-Edit-2511-fp8mixed",
                "fast_lightning_4step": FAST, "seed": seed + n,
                "positive_prompt": instruction, "negative_prompt": negative,
                "source_photo": primary, "anchor_used": followon,
                "extra_refs": refs, "shows_person": shows_person})
        out_edit = edit_scene(primary, instruction, prefix + "_edit",
                              seed=seed + n, ref_paths=refs, negative=negative)
        out = os.path.join(job_dir, f"scene_{n}.png")
        Image.open(out_edit).convert("RGB").save(out)
        common.log("compose", f"scene {n}: edited real photo -> {os.path.basename(out)}")
        return out

    if scene["method"] == "compose_animate":
        if product_path not in cut_cache:
            cut_cache[product_path] = segment(product_path, job_dir, "prod")[0]
        cut = cut_cache[product_path]
        key = f"bg_{n}"
        if bg_cache is not None and key in bg_cache:
            bg = bg_cache[key]
            common.log("compose", f"scene {n}: reusing generated background")
        else:
            # Use the brain's SETTING-ONLY description. Feeding scene['visual']
            # here produced self-contradictory prompts like "close-up of the polo
            # ... empty scene with no product", so the backdrop contained the
            # product and we then composited a product on top of a product.
            setting = (scene.get("background") or "").strip()
            if not setting:
                setting = "a clean seamless studio backdrop with soft directional light"
            bg_prompt = (f"{setting}. Completely empty scene: no product, no people, "
                         f"nothing in the centre of frame. Photorealistic, "
                         f"cinematic lighting, professional product photography backdrop.")
            if tracer:
                tracer.write_json(f"scene_{n}_compose.json", {
                    "path": "compose_animate", "model": "Qwen-Image-2512-fp8",
                    "fast_lightning_4step": FAST, "seed": seed + n,
                    "positive_prompt": bg_prompt, "negative_prompt": NEG_BG,
                    "segmentation_model": "BiRefNet", "cutout": cut,
                    "source_photo": product_path,
                    "placement": {"height_frac": height_frac, "center_y": center_y}})
            bg = generate_scene(bg_prompt, w, h, prefix + "_bg", seed=seed + n,
                                negative=NEG_BG)
            if bg_cache is not None:
                bg_cache[key] = bg
        out = os.path.join(job_dir, f"scene_{n}.png")
        return composite(cut, bg, out, height_frac=height_frac, center_y=center_y)

    gen_prompt = f"{scene['visual'].rstrip('.')}. Photorealistic, cinematic lighting."
    if tracer:
        tracer.write_json(f"scene_{n}_compose.json", {
            "path": "generate_animate", "model": "Qwen-Image-2512-fp8",
            "fast_lightning_4step": FAST, "seed": seed + n,
            "positive_prompt": gen_prompt, "negative_prompt": NEG_GEN})
    out_gen = generate_scene(
        gen_prompt,
        w, h, prefix + "_gen", seed=seed + n, negative=NEG_GEN)
    out = os.path.join(job_dir, f"scene_{n}.png")
    Image.open(out_gen).convert("RGB").save(out)
    common.log("compose", f"generated -> {os.path.basename(out)}")
    return out
