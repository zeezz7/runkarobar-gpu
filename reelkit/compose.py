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
# All STILLS are rendered remotely by seedream-v4 via WaveSpeed (ws_image.py).
# The local Qwen image models are GONE: the 8-step Lightning path produced waxy
# humans, stamped invented lettering on plain fabric and could not re-pose a
# person baked into image1 - one suit reel burned two days of retries on those
# failures while the stills themselves cost Rs 9 of a Rs 90 reel. seedream-v4
# fixes all three for $0.028/image (photo-studio bake-off, 2026-08-01). The
# GPU now does video (Wan/Hunyuan), BiRefNet masks and the OCR guard only.
# NOTE: seedream takes no negative prompt and no seed - the `negative`,
# `seed`, `steps`, `cfg` and `denoise` parameters below are kept so call
# sites (make_reel, make_photos, guard retries) stay untouched, but only the
# positive instruction steers the render. Every retry is a fresh roll, which
# is what the guard retry wanted from a new seed anyway.


def generate_scene(prompt, w, h, out_prefix, seed=0, steps=None, cfg=None,
                   negative=None):
    import ws_image
    return ws_image.generate(prompt, f"/tmp/{out_prefix}.png",
                             f"{int(w)}*{int(h)}")


def edit_scene(product_path, instruction, out_prefix, seed=0, steps=None, cfg=None,
               ref_paths=None, negative=None, denoise=1.0, target_wh=None):
    """
    seedream-v4 edit via WaveSpeed: keep the referenced subject, draw the
    world (and the pose) the instruction asks for. The right tool when the
    product is photographed IN CONTEXT - worn by a model, held in a hand,
    staged on a set. Compositing cannot handle those: segmenting a model shot
    yields the whole PERSON pasted over a scene that also contains a person.

    Image ORDER is the contract: `product_path` goes first, so same-model
    anchoring works exactly as before - a follow-on scene passes the ANCHOR
    frame first (the "first reference image" the SAME_MODEL guard talks
    about) and the real product photo in `ref_paths`, so the garment stays
    honest while the face carries over. Unlike the old Qwen edit, seedream
    actually CAN re-pose the anchored person instead of cloning image1's
    composition - that failure is why Qwen is gone.
    """
    import ws_image
    size = (f"{int(target_wh[0])}*{int(target_wh[1])}" if target_wh
            else "1080*1920")
    return ws_image.edit(instruction, [product_path] + list(ref_paths or []),
                         f"/tmp/{out_prefix}.png", size)


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
                anchor=None, include_human=True, emphasis="", force_size=False,
                extra_refs=None):
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
    # The includeHuman toggle is binary and authoritative: True = a model wears
    # the product in EVERY scene, False = a hard no-person product reel. Force it
    # regardless of how the brain framed the shot.
    if not include_human:
        shows_person = False
    else:
        shows_person = True

    # EDIT PATH: edit the REAL uploaded product photo via edit_scene. Runs for
    # EVERY edit_animate scene - product-only AND include_human. This block used to
    # be nested inside the include_human branch, so PRODUCT-ONLY reels never reached
    # edit_scene and fell straight through to text-to-image (generate_scene) -
    # inventing the product from the brain's words instead of editing the uploaded
    # photo (the shoe-colourway drift, source_photo=None in the trace). Gate on the
    # METHOD, not include_human, so the photo is used whenever the brain wants an edit.
    if scene["method"] == "edit_animate":
        setting = (scene.get("background") or scene["visual"]).strip().rstrip(".")
        setting = guards.desexualise(setting)
        # Re-frame the SAME subject from the ANCHOR (the first scene's still)
        # once one exists: for anchor templates AND for ANY includeHuman reel.
        # This is what keeps ONE model in the EXACT SAME outfit across every
        # angle - without it, each scene re-dresses a fresh model from the
        # flat-lay and drifts to a different outfit (the kurti-reel failure).
        primary, refs = product_path, []
        followon = False
        want_anchor = bool(d.get("anchorModel")) or include_human
        if want_anchor and anchor and anchor != product_path:
            primary, refs, followon = anchor, [product_path], True
        # Show Qwen the OTHER uploaded angles too, not just one photo - so a
        # back/side shot has the REAL garment from that view to copy instead of
        # inventing it. Qwen-Edit takes image1 + 2 refs, so we fill the two ref
        # slots from (existing refs + the uploaded angle pool), deduped and
        # never repeating the primary/anchor.
        pool, seen, merged = list(refs) + list(extra_refs or []), set(), []
        for p in pool:
            if p and p != primary and p not in seen:
                seen.add(p)
                merged.append(p)
        refs = merged[:2]

        shot = guards.desexualise((scene.get("visual") or "").strip().rstrip("."))
        if followon:
            lead = (f"Keep the SAME person and the EXACT SAME outfit as in this "
                    f"photograph - identical face, hair and skin tone, and the "
                    f"identical garment: same colours, same embroidery and prints, "
                    f"same fabric, every detail unchanged. Do NOT change the outfit. "
                    f"Re-frame them for this new shot: {shot}. Setting: {setting}.")
        elif not include_human:
            # PRODUCT-ONLY reel from a photo that may show a model wearing the
            # item. "Keep the product, change the background" would keep the
            # person, so instead order them removed and the garment presented as
            # a ghost-mannequin product shot (hollow, holds its worn shape,
            # nobody inside). This is what makes includeHuman=False actually
            # human-free instead of just re-backgrounding the model.
            lead = (
                "Show ONLY the product itself, with absolutely NO person in frame. "
                "If a model or any person wears or holds it in this photograph, "
                "remove them completely - no body, no head, no face, no arms, no "
                "hands, no skin, no legs, no one inside the garment. Present it as a "
                "premium ghost-mannequin product shot: a hollow garment that keeps "
                "its natural worn shape with nobody in it - and NO stand, hanger, "
                "ring, collar-support or any rig visible at the neck or anywhere "
                "else. Keep its exact shape, colours, materials, prints, logos "
                "and every detail identical. "
                f"Place it in: {setting}.")
        elif shows_person and include_human:
            # includeHuman ESTABLISHING scene. The source is usually a flat-lay or
            # a product shot, so ORDER the garment worn on a model - "keep exactly
            # as photographed" (flat) fought WEAR_GUARD ("worn by a model") and the
            # edit drifted to a random outfit. Be explicit: dress a model in THIS
            # exact garment, changing nothing about the garment itself.
            lead = (
                "Show this EXACT outfit worn by a full-body model. Take the "
                "garment(s) in the photograph and dress the model in them, keeping "
                "the identical fabric, colours, prints, embroidery, lace and cut of "
                "EVERY piece completely unchanged - do NOT restyle, recolour, "
                "simplify or swap it for a different garment. The complete outfit "
                f"worn naturally on the body. Setting: {setting}.")
        else:
            lead = (f"Keep the product exactly as photographed - identical shape, "
                    f"colours, materials and every detail, unchanged. Change only "
                    f"the surroundings to: {setting}.")
        # A followon shot is always a person shot (it re-frames the worn outfit),
        # so it must get the person/wear guards even if the brain tagged the
        # scene mode 'product'.
        person_shot = shows_person or followon
        # The negative prompt alone does not stop the 8-step Lightning edit from
        # stamping invented brand text on blank surfaces (observed: mirrored
        # gibberish printed on the blank insoles of a pump). State it as a
        # positive instruction too - blank stays blank, existing text is frozen.
        text_rule = (
            " Printed text rule: any text, logo or stamp on the product stays "
            "EXACTLY as photographed, letter for letter - and every surface "
            "that is blank in the photograph STAYS blank. Do not print, engrave "
            "or stamp ANY new text, lettering, branding or label anywhere. Any "
            "print or graphic on the product is reproduced stroke for stroke, "
            "and NO texture, embossing, weave or pattern is added that the "
            "photograph does not show - plain fabric stays plain. Lighting "
            "effects (glow, halo, rim light) belong to the SCENE - never "
            "painted onto the product or its print.")
        instruction = ((emphasis + " ") if emphasis else "") + lead + text_rule + (
                              guards.person_guards(d, is_followon=followon)
                              if person_shot else guards.product_guards())
        negative = NEG_EDIT if person_shot else NEG_PRODUCT
        if not include_human:
            # Push the person out hard on the negative side too.
            negative += (", person, people, model, human, man, woman, body, face, "
                         "head, arms, hands, fingers, skin, legs, portrait")
        instruction += " Photorealistic editorial photograph, sharp detail."
        if tracer:
            import ws_image
            tracer.write_json(f"scene_{n}_compose.json", {
                "path": scene["method"], "model": ws_image.EDIT_MODEL,
                "positive_prompt": instruction,
                "source_photo": primary, "anchor_used": followon,
                "extra_refs": refs, "shows_person": shows_person})
        # Log the EXACT edit request so it shows in the worker logs - this is
        # where outfit drift is born, so we want it visible, not buried.
        common.log("compose", f"scene {n} EDIT primary={os.path.basename(primary)} "
                              f"refs={[os.path.basename(r) for r in refs]} "
                              f"followon={followon} shows_person={shows_person}")
        common.log("compose", f"scene {n} INSTRUCTION: {instruction[:500]}")
        # Always render on the reel's native canvas - seedream draws the right
        # aspect directly, no post-hoc crop/upscale.
        out_edit = edit_scene(primary, instruction, prefix + "_edit",
                              seed=seed + n, ref_paths=refs, negative=negative,
                              target_wh=(w, h))
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
                import ws_image
                tracer.write_json(f"scene_{n}_compose.json", {
                    "path": "compose_animate", "model": ws_image.T2I_MODEL,
                    "positive_prompt": bg_prompt,
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
        import ws_image
        tracer.write_json(f"scene_{n}_compose.json", {
            "path": "generate_animate", "model": ws_image.T2I_MODEL,
            "positive_prompt": gen_prompt})
    out_gen = generate_scene(
        gen_prompt,
        w, h, prefix + "_gen", seed=seed + n, negative=NEG_GEN)
    out = os.path.join(job_dir, f"scene_{n}.png")
    Image.open(out_gen).convert("RGB").save(out)
    common.log("compose", f"generated -> {os.path.basename(out)}")
    return out
