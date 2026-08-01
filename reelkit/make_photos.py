"""
The AI photo studio task - fully self-hosted (no WaveSpeed pixels).

    Haiku directs -> Qwen-Image-Edit-2511 renders -> OCR guard + Haiku QA
    validate -> MinIO. Same worker, same models, same guard stack as reels.

Two modes, mirroring StaffHQ's studio page:
  photos - clean catalog shots (3:4). A cheap Claude call (PHOTO_DIRECTOR_MODEL,
           default claude-haiku-4-5) looks at the product photos + the tenant's
           style note and writes N shot specs - varied background/staging, SAME
           product, and per-shot whether it is WORN by a model (apparel) or
           standalone. Each shot is a compose.scene_image edit of the real
           photo, policed by the OCR invented-text guard and one QA pass
           (PHOTO_QA_MODEL, default claude-haiku-4-5). Failing shots get one
           re-roll with the QA's correction; still-failing shots are DROPPED,
           never shipped (a photo set may shrink; a wrong photo may not exist).
  poster - 4:5 marketing creatives. The director expands the tenant's brief
           into N full poster prompts (text/typography ALLOWED - that is the
           point of a poster, and Qwen-Image's headline strength); rendered via
           the same edit path with the product photos as references. No OCR
           guard (posters legitimately carry lettering) and no QA drop - the
           tenant judges creatives.

Request (RunPod input):
    {"task": "photos", "product_images": [urls], "prompt": "...",
     "count": 1-8, "mode": "photos"|"poster", "config": {"trace": true}}
Result:
    {"results": [{"label", "url"}], "mode", "dropped": n,
     "cost_usd", "_cost", "_elapsedSec"}
"""
import json
import os
import time

import common
import costs
import llm

MAX_COUNT = 8
PHOTO_W, PHOTO_H = 1080, 1440    # 3:4 catalog portrait
POSTER_W, POSTER_H = 1080, 1350  # 4:5 social creative


def _director_model():
    return os.environ.get("PHOTO_DIRECTOR_MODEL", "claude-haiku-4-5")


def _qa_model():
    return os.environ.get("PHOTO_QA_MODEL", "claude-haiku-4-5")


def _extract_json(raw, prefer_obj=False):
    """Tolerant JSON array/object extraction (models love markdown fences).
    `prefer_obj`: try the OUTER object first. Needed when the payload is an
    object that CONTAINS an array (e.g. copy + an "angles" list) - otherwise the
    default array-first scan grabs the inner array and drops the object."""
    raw = (raw or "").strip()
    order = ((("{", "}"), ("[", "]")) if prefer_obj
             else (("[", "]"), ("{", "}")))
    for start, end in order:
        i, j = raw.find(start), raw.rfind(end)
        if i != -1 and j > i:
            try:
                return json.loads(raw[i:j + 1])
            except Exception:
                continue
    raise ValueError(f"no JSON found in: {raw[:200]}")


# ------------------------------------------------------------------ director
def _direct_photos(urls, style_note, count, model_gender=None):
    """Haiku writes the shot list: varied staging, same product, worn or not.
    `model_gender`: 'female' | 'male' -> worn shots use that model and apparel
    gets 2-3 of them; 'none' -> every shot is product-only; None -> the
    director decides freely (legacy behaviour)."""
    note = f' The seller\'s style note: "{style_note}".' if style_note else ""
    if model_gender == "none":
        gender_rule = ('- "worn" must be false for EVERY shot - the seller '
                       "wants product-only photos, no model.\n")
    elif model_gender in ("female", "male"):
        gender_rule = (f'- If the item is apparel/wearable, make 2-3 of the '
                       f'shots "worn": true - worn by a {model_gender} model '
                       f"- and say so in those shots' \"visual\". Standalone "
                       f'products stay worn=false.\n')
    else:
        gender_rule = ('- "worn": true ONLY if the item is apparel/wearable '
                       "AND worn shots suit it; a standalone product gets "
                       "worn=false.\n")
    prompt = (
        f"You are a catalog art director for an Indian e-commerce shop. Study "
        f"the attached product photograph(s) and plan {count} DISTINCT catalog "
        f"shots of this EXACT product.{note}\n"
        f"Rules:\n"
        f"- The product stays identical in every shot - never redesign it.\n"
        f"{gender_rule}"
        f'- "visual": one line describing the shot of THIS product (e.g. '
        f'"front-facing hero of this exact cream sweater, filling the frame").\n'
        f'- "setting": background/surface/light ONLY - never name the product '
        f"in it. Vary settings across shots (studio white, styled surface, "
        f"lifestyle); no two alike. No effects like smoke/steam/water unless "
        f"the product obviously calls for it.\n"
        f'- "label": short (Hero, Angle, Side, Lifestyle, Detail, Flat Lay...).\n'
        f"Return ONLY a JSON array of {count} objects: "
        f'[{{"label":"...","worn":false,"visual":"...","setting":"..."}}]')
    raw = llm.chat(prompt, system="You output ONLY strict JSON.", images=urls,
                   model=_director_model(), temperature=0.7, max_tokens=1200)
    shots = [s for s in _extract_json(raw) if isinstance(s, dict)]
    if not shots:
        raise ValueError("director returned no shots")
    return shots[:count]


# Canonical worn-model catalog poses, in order. When the seller picks a model
# (female/male) we shoot THIS set instead of a freeform director plan - the same
# model in the same outfit from every angle, which is what a clothing catalog
# actually needs. Shot 1 establishes the model; the rest re-frame it via the
# anchor carry (compose.scene_image), so the person and outfit stay identical.
_POSES = [
    ("Front", "full-length front view of the model wearing this exact outfit, "
              "standing straight and facing the camera, the whole garment "
              "visible from shoulders to hem"),
    ("Front Close-up", "waist-up front close-up of the SAME model in the SAME "
              "outfit, showing the neckline, fabric and detailing of this exact "
              "garment"),
    ("Right Side", "full-length right-side profile of the SAME model in the "
              "SAME outfit, body turned 90 degrees to their right, showing the "
              "side silhouette of the garment"),
    ("Left Side", "full-length left-side profile of the SAME model in the SAME "
              "outfit, body turned 90 degrees to their left"),
    ("Back", "full-length back view of the SAME model in the SAME outfit, "
              "facing away from the camera, showing the back of the garment"),
    ("Angle", "full-length three-quarter angle of the SAME model in the SAME "
              "outfit, body turned about 45 degrees, relaxed confident stance"),
    ("Detail", "close-up of the SAME outfit on the SAME model - sleeve, hem or "
              "print - showing the craftsmanship and fabric"),
    ("Seated", "the SAME model in the SAME outfit seated in a relaxed editorial "
              "pose, the full outfit visible"),
]


def _analyze_uploads(urls):
    """ONE Haiku pass over the uploaded photos that returns BOTH:
      - listing copy (name/brand/category/description/details/care/delivery/meta)
        so the wizard fills itself from the render (no WaveSpeed text call), and
      - an angle label per image (front/back/left/right/side/detail/other) so we
        hand each pose the RIGHT view regardless of upload order.
    Same images, same model, one round-trip. Returns ({}, []) on failure, so the
    caller degrades to plain upload order + no auto-copy."""
    keys = ("name", "brand", "category", "description", "details", "care",
            "delivery", "metaDescription")
    prompt = (
        "Study the product photo(s) and return STRICT JSON with these keys:\n"
        '"name": short catchy product title, max 8 words;\n'
        '"brand": brand ONLY if clearly visible on the product, else "";\n'
        '"category": one or two word category;\n'
        '"description": 2-3 sentence marketing description;\n'
        '"details": 3-5 short feature lines separated by newlines;\n'
        '"care": 1-2 care instructions;\n'
        '"delivery": a generic delivery line;\n'
        '"metaDescription": <=150 char SEO description;\n'
        '"angles": a JSON array labeling EACH image IN ORDER by camera angle - '
        "one of front, back, left, right, side, detail, other (front=facing "
        "camera, back=rear, left/right=that profile, side=profile you cannot "
        "tell L/R, detail=close-up of a part, other=flat-lay/unclear).\n"
        "Plain text values, no emojis, no markdown.")
    try:
        raw = llm.chat(prompt, system="You output ONLY strict JSON.",
                       images=urls, model=_director_model(),
                       temperature=0.5, max_tokens=1000)
        obj = _extract_json(raw, prefer_obj=True)
        if isinstance(obj, dict):
            copy = {k: str(obj.get(k) or "")[:2000] for k in keys}
            ang = obj.get("angles")
            angles = ([str(a).strip().lower() for a in ang]
                      if isinstance(ang, list) and len(ang) == len(urls) else [])
            return copy, angles
    except Exception as e:
        common.log("photos", f"upload analysis failed (non-fatal): {e}")
    return {}, []


def _pref_angle(label):
    lab = (label or "").lower()
    if "back" in lab:
        return "back"
    if "left" in lab:
        return "left"
    if "right" in lab:
        return "right"
    return "front"      # front / close-up / angle / seated / detail default here


def _ordered_refs(label, products, angles):
    """Order the uploaded angle pool so the pose-matched angle is FIRST (smart),
    then the rest (simple). Qwen keeps only the first couple after the primary/
    anchor are removed, so the matched view lands in a ref slot."""
    if not angles or len(angles) != len(products):
        return list(products)      # simple: plain upload order
    pref = _pref_angle(label)

    def score(i):
        a = angles[i] or ""
        if a == pref:
            return 0
        if pref in ("left", "right") and a == "side":
            return 1               # a generic side beats nothing for L/R
        if a == "front":
            return 2               # the front is a decent all-purpose ref
        return 3

    return [products[i] for i in sorted(range(len(products)),
                                        key=lambda i: (score(i), i))]


def _shot_inputs(label, worn, products, angles, anchor_still):
    """Edit base, extra refs, anchor and anchor mode for one shot.

    A follow-on WORN shot edits the angle-matched UPLOAD with the anchor
    passed as an identity REFERENCE - editing the anchor render itself just
    reproduced its pose in every shot, because Qwen-Edit keeps image1's
    subject and composition (job photos_9dd8313e: scenes 2-5 all came out as
    the front pose). Everything else edits the (front) upload directly."""
    xrefs = _ordered_refs(label, products, angles)
    anc = anchor_still if worn else None
    if anc is not None:
        base = xrefs[0] if xrefs else products[0]
        return base, [p for p in xrefs if p != base], anc, "identity"
    return products[0], xrefs, anc, "edit"


def _pose_plan(gender, style_note, count):
    """Fixed worn-model pose set (front, close-up, sides, back, ...), one shared
    setting so the set is cohesive. All shots worn by the chosen model."""
    setting = (style_note.strip() or
               "clean seamless studio backdrop, soft even lighting")
    shots = []
    for k, (label, visual) in enumerate(_POSES[:count]):
        v = f"A poised {gender} fashion model. " + visual if k == 0 else visual
        shots.append({"label": label, "worn": True, "visual": v,
                      "setting": setting})
    return shots


def _direct_posters(urls, brief, count):
    """Haiku expands the tenant's brief into N full poster prompts."""
    base = brief.strip() or (
        "A premium promotional poster for this product - bold headline, "
        "tasteful colours, modern layout.")
    prompt = (
        f"You are a graphic designer. Using the attached product photo(s) as "
        f"the subject, write {count} complete image-generation prompts for "
        f"4:5 marketing posters based on this brief: \"{base}\".\n"
        f"Rules:\n"
        f"- Keep the EXACT product from the photos as the hero of each poster.\n"
        f"- Headline/offer text belongs IN the poster - spell out the exact "
        f"words to render, in quotes, and keep any wording the brief demands.\n"
        f"- Each of the {count} prompts keeps the same concept but a clearly "
        f"different colour palette/styling.\n"
        f"- Family-friendly; any person fully and modestly dressed.\n"
        f"Return ONLY a JSON array: "
        f'[{{"label":"Poster 1","prompt":"..."}}]')
    raw = llm.chat(prompt, system="You output ONLY strict JSON.", images=urls,
                   model=_director_model(), temperature=0.8, max_tokens=1600)
    posters = [p for p in _extract_json(raw) if isinstance(p, dict)]
    if not posters:
        raise ValueError("director returned no posters")
    return posters[:count]


# ------------------------------------------------------------------------ QA
def _qa_shots(ref_urls, shot_urls, labels, worn_flags=None):
    """One vision pass over the whole set: per-shot pass/issue/fix.
    `worn_flags[i]` tells the judge shot i is INTENTIONALLY worn by a model,
    so a person there is correct - without it the QA flagged every worn
    lifestyle shot as "added person" and burned a pointless re-roll."""
    worn_flags = worn_flags or [False] * len(shot_urls)
    lines = "\n".join(
        f"  shot {i + 1} ({labels[i]})"
        + (" - INTENTIONALLY worn by a model; the person is correct. Judge "
           "the product's fidelity AND that the shot matches its label's "
           "camera angle/framing" if worn_flags[i] else
           " - product only; a person here is a FAIL")
        for i in range(len(shot_urls)))
    prompt = (
        f"IMAGES 1-{len(ref_urls)} are the REFERENCE product photographs. "
        f"IMAGES {len(ref_urls) + 1}-{len(ref_urls) + len(shot_urls)} are "
        f"generated catalog shots, IN ORDER:\n{lines}\n"
        f"For EACH generated shot, in order, return pass=true ONLY if it shows "
        f"the SAME product as the references (same type, colours, design, "
        f"prints), with NOTHING added that the references do not show (no "
        f"scarf/drape/jewellery/accessory - and no person UNLESS that shot is "
        f"marked intentionally worn, no invented lettering, labels or "
        f"embossing - blank surfaces stay blank), and the product clearly "
        f"FILLS the frame (never a small object floating in empty space). "
        f"A worn shot must ALSO match its label: Back = the model seen from "
        f"BEHIND (back of the garment, face away), Left/Right Side = a side "
        f"PROFILE, Close-up/Detail = a TIGHT crop (NOT full-length), Front = "
        f"full-length facing the camera. A worn shot at the wrong angle or "
        f"framing for its label FAILS - describe the correct angle in the "
        f'"fix". '
        f'On fail, give a short "issue" and a one-line corrected "fix" visual. '
        f"Return ONLY a JSON array: "
        f'[{{"shot":1,"pass":true,"issue":"","fix":""}}]')
    raw = llm.chat(prompt, system="You output ONLY strict JSON.",
                   images=list(ref_urls) + list(shot_urls),
                   model=_qa_model(), temperature=0.2, max_tokens=1200)
    out = {}
    for i, item in enumerate(_extract_json(raw), 1):
        if isinstance(item, dict):
            out[item.get("shot", i)] = {
                "pass": bool(item.get("pass", True)),
                "issue": str(item.get("issue") or "")[:150],
                "fix": str(item.get("fix") or "")[:300],
            }
    return out


# ------------------------------------------------------------------- helpers
def _scene(i, shot):
    """Minimal storyboard-shaped dict so compose.scene_image just works."""
    return {
        "n": i,
        "method": "edit_animate",
        "mode": "product",
        "visual": (shot.get("visual") or "this exact product, catalog shot"),
        "background": (shot.get("setting")
                       or "clean seamless studio, soft directional light"),
        "energy": "",
    }


FILL_FRAME = (
    " FRAMING: the product is the unmistakable subject and FILLS the frame - "
    "roughly 75-90% of frame height when worn and 65-85% standalone, tight "
    "confident cropping; NEVER a small object floating in empty space.")


# Human-realism cues for worn shots - the 8-step edit model tends to render a
# waxy, mannequin-like person, so steer it toward a real photograph. (Prompt
# only; the deeper fix is more sampling steps, which we're not paying for here.)
_REALISM = (
    " REALISM: a REAL photograph of a real human, shot on an 85mm portrait lens "
    "in soft natural daylight - authentic skin with visible pores and natural "
    "texture and subtle imperfections, natural catchlights in the eyes, real "
    "hair strands, lifelike proportions and a relaxed natural expression. NOT a "
    "3D render, NOT CGI, NOT a video-game character, NOT a mannequin or "
    "dummy - no plastic, waxy, airbrushed or smoothed-over skin, no dead eyes.")


def _worn_emphasis(gender, label):
    """Prepended (via `emphasis`) to every worn pose shot. compose.py's worn
    lead never carries the gender or the camera angle, so we inject both here:
    the establishing shot was defaulting to a female model, and the side/back
    re-frames were coming out front-facing because the 'keep everything
    identical' lead drowned the small pose line."""
    g = (f" The model is a {gender} person - clearly and unmistakably {gender}, "
         f"a {gender} fashion model." + _REALISM
         if gender in ("male", "female") else "")
    lab = (label or "").lower()
    if "close" in lab or "detail" in lab:
        # Without this the close-up got NO framing steering, so it re-framed from
        # the full-length front anchor and just reproduced the front - it never
        # zoomed in. Force an explicit tight crop.
        pose = (" CAMERA MOVED IN CLOSE: a TIGHT waist-up crop - ONLY the upper "
                "body and the garment's detail (neckline, fabric, texture, print, "
                "stitching) fill the frame. This is NOT a full-length shot: the "
                "legs and feet are OUT of frame. Same person and outfit, MUCH "
                "closer framing than the full-length shots.")
    elif "back" in lab:
        pose = (" CAMERA ANGLE: the model has turned ALL THE WAY AROUND, BACK to "
                "the camera - we see the back of the head, the shoulders and the "
                "GARMENT'S BACK; the face is NOT visible. This is a different "
                "camera angle of the same person and outfit, NOT a front view."
                # Big blank denim backs make the edit model stamp gibberish
                # brand text; the OCR guard then drops the whole shot. Forbid it.
                " The back of the garment is PLAIN fabric - do NOT print, stamp, "
                "emboss or add ANY brand name, logo, letters, numbers, words or "
                "graphic anywhere on the back; blank fabric stays completely "
                "blank.")
    elif "left" in lab:
        pose = (" CAMERA ANGLE: the model has physically rotated to face their "
                "LEFT - photograph the LEFT-SIDE PROFILE (the side of the body "
                "and face), NOT a front view. Same person and outfit, new "
                "orientation.")
    elif "right" in lab:
        pose = (" CAMERA ANGLE: the model has physically rotated to face their "
                "RIGHT - photograph the RIGHT-SIDE PROFILE (the side of the body "
                "and face), NOT a front view. Same person and outfit, new "
                "orientation.")
    else:
        pose = ""
    return FILL_FRAME + g + pose


def _fit(path, w, h):
    """Cover-crop to the target aspect and resize - the edit model outputs at
    its own resolution, but a catalog shot must be a true 3:4 (poster 4:5)."""
    from PIL import Image
    img = Image.open(path).convert("RGB")
    want = w / h
    have = img.width / img.height
    if abs(have - want) > 0.01:
        if have > want:                      # too wide -> crop sides
            nw = int(img.height * want)
            x = (img.width - nw) // 2
            img = img.crop((x, 0, x + nw, img.height))
        else:                                # too tall -> crop top/bottom
            nh = int(img.width / want)
            y = (img.height - nh) // 2
            img = img.crop((0, y, img.width, y + nh))
    if img.width != w:
        img = img.resize((w, h), Image.LANCZOS)
    out = os.path.splitext(path)[0] + f"_{w}x{h}.jpg"
    img.save(out, "JPEG", quality=92)
    return out


# ---------------------------------------------------------------------- main
def make_photos(request):
    t0 = time.time()
    common.load_env()
    import animate      # local imports keep handler boot light
    import compose
    from make_reel import _free_comfy_vram, _upload

    urls = [u for u in (request.get("product_images") or []) if u][:8]
    if not urls:
        raise ValueError("product_images is required")
    prompt = (request.get("prompt") or "").strip()
    mode = "poster" if request.get("mode") == "poster" else "photos"
    gender = (request.get("model_gender") or "").strip().lower() or None
    count = max(1, min(MAX_COUNT, int(request.get("count") or 5)))
    cfg = request.get("config") or {}

    jid, jd = common.new_job("photos")
    import tracer as _tracer
    tr = _tracer.Tracer(jid, enabled=bool(cfg.get("trace", True)))
    tr.write_json("request.json", {"product_images": urls, "prompt": prompt,
                                   "mode": mode, "count": count})
    costs.reset()
    common.log("job", f"{jid} photos task: mode={mode} count={count} "
                      f"refs={len(urls)} gender={gender or 'auto'}")

    products = []
    for i, u in enumerate(urls, 1):
        dst = os.path.join(jd, f"product_{i}{os.path.splitext(u)[1][:5] or '.jpg'}")
        common.fetch_url(u, dst)
        products.append(dst)

    _free_comfy_vram()      # clean GPU regardless of the previous job
    results, dropped, copy = [], 0, {}

    if mode == "poster":
        posters = _direct_posters(urls, prompt, count)
        tr.write_json("director.json", posters)
        for i, p in enumerate(posters, 1):
            label = str(p.get("label") or f"Poster {i}")[:40]
            text = (str(p.get("prompt") or "").strip()
                    + " One single 4:5 poster image, photorealistic product, "
                      "family-friendly, any person fully and modestly dressed. "
                      "No watermark.")
            try:
                img = compose.edit_scene(
                    products[0], text, f"{jid}_p{i}",
                    seed=abs(hash(f"{jid}poster{i}")) % 10000,
                    ref_paths=products[1:3])
                url = _upload(_fit(img, POSTER_W, POSTER_H),
                              "products/ai", f"{jid}-{i}-poster.jpg")
                results.append({"label": label, "url": url})
                tr.write_json(f"poster_{i}.json", {"label": label,
                                                   "prompt": text, "url": url})
            except Exception as e:
                dropped += 1
                common.log("photos", f"poster {i} failed ({e}) - dropped")
    else:
        # Picking a model (female/male) means "shoot this apparel on a model" -
        # use the fixed catalog pose set + anchor carry for ONE consistent
        # model. No model (none) / unspecified keeps the freeform director.
        worn_poses = gender in ("female", "male")
        shots = (_pose_plan(gender, prompt, count) if worn_poses
                 else _direct_photos(urls, prompt, count, model_gender=gender))
        tr.write_json("director.json", shots)

        # ONE Haiku pass over the uploads gives us BOTH the listing copy and an
        # angle label per photo, so each pose can be handed the RIGHT view (back
        # shot -> the back photo) no matter the upload order. Falls back to plain
        # order if labeling fails. Put a front-labelled photo first so it's the
        # establishing base + guard reference.
        copy, angles = _analyze_uploads(urls)
        if angles:
            fronts = [k for k, a in enumerate(angles) if a == "front"]
            if fronts and fronts[0] != 0:
                j = fronts[0]
                products[0], products[j] = products[j], products[0]
                angles[0], angles[j] = angles[j], angles[0]
            tr.write_json("angles.json",
                          [{"i": k, "angle": a} for k, a in enumerate(angles)])
        stills, shot_urls, labels = [], [], []
        # The first worn still becomes the anchor every later worn shot re-frames
        # from, so the same person + outfit appears in every angle.
        anchor_still = None
        for i, shot in enumerate(shots, 1):
            worn = bool(shot.get("worn"))
            sc = _scene(i, shot)
            # Worn pose shots need gender + camera-angle steering injected;
            # product-only / freeform shots just get the framing rule.
            emph = (_worn_emphasis(gender, shot.get("label"))
                    if worn_poses else FILL_FRAME)
            base, xrefs, anc, amode = _shot_inputs(
                shot.get("label"), worn, products, angles, anchor_still)
            try:
                still = compose.scene_image(
                    sc, base, PHOTO_W, PHOTO_H, jd,
                    seed=abs(hash(f"{jid}s{i}")) % 10000, tracer=tr,
                    anchor=anc, anchor_mode=amode, include_human=worn,
                    emphasis=emph, force_size=worn, extra_refs=xrefs,
                    quality=True)
                ok, detail = animate.guard_composite(still, products[0])
                tr.write_json(f"shot_{i}_guard.json", {"pass": ok,
                                                       "detail": detail})
                if not ok:     # invented/changed lettering: one fresh re-roll
                    common.log("photos", f"shot {i} guard fail - re-roll "
                                         f"({detail[:80]})")
                    still = compose.scene_image(
                        sc, base, PHOTO_W, PHOTO_H, jd,
                        seed=abs(hash(f"{jid}retry{i}")) % 10000, tracer=tr,
                        anchor=anc, anchor_mode=amode, include_human=worn,
                        force_size=worn, extra_refs=xrefs, quality=True,
                        emphasis=emph + f" CRITICAL: the previous render "
                                 f"was WRONG ({detail}). Blank surfaces stay "
                                 f"blank; printed text stays exact.")
                    ok2, _ = animate.guard_composite(still, products[0])
                    if not ok2:
                        dropped += 1
                        common.log("photos", f"shot {i} still failing OCR "
                                             f"guard - dropped")
                        continue
                stills.append((i, shot, still))
                if worn and anchor_still is None:
                    anchor_still = still     # establish the model for the rest
            except Exception as e:
                dropped += 1
                common.log("photos", f"shot {i} render failed ({e}) - dropped")
        animate.unload_guard()

        # Upload, then ONE QA pass over the whole set.
        for i, shot, still in stills:
            u = _upload(_fit(still, PHOTO_W, PHOTO_H), "products/ai",
                        f"{jid}-{i}-{str(shot.get('label') or i).lower().replace(' ', '-')[:24]}.jpg")
            shot_urls.append(u)
            labels.append(str(shot.get("label") or f"Shot {i}"))
        verdicts = {}
        try:
            verdicts = _qa_shots(urls, shot_urls, labels,
                                 [bool(s.get("worn")) for _, s, _ in stills])
            tr.write_json("qa.json", verdicts)
        except Exception as e:
            common.log("photos", f"QA pass failed (non-fatal, keeping all "
                                 f"shots): {e}")
        for k, ((i, shot, still), u, label) in enumerate(
                zip(stills, shot_urls, labels), 1):
            v = verdicts.get(k, {"pass": True})
            if v.get("pass", True):
                results.append({"label": label, "url": u})
                continue
            # One corrected re-roll from the QA's fix; still bad -> drop.
            common.log("photos", f"shot {i} QA fail ({v.get('issue')}) - "
                                 f"corrected re-roll")
            sc = _scene(i, {"visual": v.get("fix") or shot.get("visual"),
                            "setting": shot.get("setting")})
            worn = bool(shot.get("worn"))
            emph = (_worn_emphasis(gender, shot.get("label"))
                    if worn_poses else FILL_FRAME)
            base, xrefs, anc, amode = _shot_inputs(
                shot.get("label"), worn, products, angles, anchor_still)
            try:
                still2 = compose.scene_image(
                    sc, base, PHOTO_W, PHOTO_H, jd,
                    seed=abs(hash(f"{jid}fix{i}")) % 10000, tracer=tr,
                    anchor=anc, anchor_mode=amode, quality=True,
                    include_human=worn, force_size=worn, extra_refs=xrefs,
                    emphasis=emph + f" CRITICAL: a previous attempt was "
                             f"WRONG ({v.get('issue')}). Match the reference "
                             f"product EXACTLY.")
                u2 = _upload(_fit(still2, PHOTO_W, PHOTO_H),
                             "products/ai", f"{jid}-{i}-fixed.jpg")
                results.append({"label": label, "url": u2})
            except Exception as e:
                dropped += 1
                common.log("photos", f"shot {i} corrected re-roll failed "
                                     f"({e}) - dropped")

    # `copy` came from the same _analyze_uploads pass that labeled the angles
    # (photos mode, pre-render) - drop it if nothing rendered.
    if not results:
        copy = {}
    if copy:
        tr.write_json("copy.json", copy)

    _free_comfy_vram()      # leave a clean GPU for the next (reel) job
    costs.current().stop_clock()
    _cost = costs.current().summary()
    result = {
        "results": results,
        "mode": mode,
        "dropped": dropped,
        "copy": copy,
        "cost_usd": _cost["total_usd"],
        "_cost": _cost,
        "_elapsedSec": round(time.time() - t0, 1),
    }
    common.log("job", f"{jid} done: {len(results)} {mode} shot(s), "
                      f"{dropped} dropped, ${_cost['total_usd']}")
    trace_dir = tr.rollup(result)
    if trace_dir:
        try:
            import tarfile
            tgz = os.path.join(jd, f"{jid}_trace.tgz")
            with tarfile.open(tgz, "w:gz") as t:
                t.add(trace_dir, arcname=jid)
            result["trace_url"] = _upload(tgz, "traces", f"{jid}_trace.tgz")
        except Exception as e:
            common.log("trace", f"trace upload failed: {e}")
    return result
