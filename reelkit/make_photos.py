"""
The AI photo studio - the SIMPLE version.

NOTE: the primary photo studio now lives in the staffhq API
(PhotoStudioService, seedream-v4 + Haiku). This worker task stays alive
because PRODUCTION's API still dispatches task:"photos" here until its next
deploy - and it renders through the same seedream-v4 path now
(compose.edit_scene -> ws_image; the local Qwen models are gone).
Prompts are SHORT - the old pipeline stacked ~3,400 characters of guards
around a one-line pose, and the pose drowned (job photos_9dd8313e).

What stayed, because it demonstrably worked:
  - one Haiku pass over the uploads -> listing copy (wizard auto-fill) + a
    camera-angle label per photo (front/back/left/right/...)
  - angle-matched edit bases: a pose shot edits the UPLOAD closest to its
    angle (Back edits the real back photo), never a previous render - Qwen
    keeps image1's pose, so editing a front render returns the front pose
  - the establishing shot rides along in a reference slot for follow-on
    poses so ONE model persists across the set
  - OCR invented-text guard per shot + one pose-aware QA pass, with a SHARED
    re-roll budget so a bad job cannot silently double its own GPU bill

photos - fixed catalog poses when the seller picked a model gender
         (Front / Close-up / Right / Left / Back / ...), all worn; no gender
         picked -> product-only preset shots. 3:4 catalog portrait.
poster - Haiku expands the brief into N poster prompts, rendered as direct
         edits of the first upload. Text is allowed (that is the point of a
         poster); no OCR guard and no QA - the tenant judges creatives. 4:5.

Request (RunPod input):
    {"task": "photos", "product_images": [urls], "prompt": "...",
     "count": 1-8, "mode": "photos"|"poster", "model_gender": "female"|
     "male"|"none", "config": {"trace": true}}
Result:
    {"results": [{"label", "url"}], "mode", "dropped": n, "copy": {...},
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
MAX_REROLLS = 2                  # per JOB, shared by guard + QA corrections


def _director_model():
    return os.environ.get("PHOTO_DIRECTOR_MODEL", "claude-haiku-4-5")


def _qa_model():
    return os.environ.get("PHOTO_QA_MODEL", "claude-haiku-4-5")


def _extract_json(raw, prefer_obj=False):
    """Tolerant JSON array/object extraction (models love markdown fences).
    `prefer_obj`: try the OUTER object first - needed when the payload is an
    object that CONTAINS an array, or the array-first scan eats the object."""
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


# ------------------------------------------------------------------ shot plans
# Worn catalog poses, in order. Shot 1 establishes the model; later poses are
# drawn fresh from the angle-matched upload with shot 1 as the identity ref.
_WORN_POSES = [
    ("Front", "Full-length front view: standing straight, facing the camera, "
              "the whole garment visible from shoulders to hem."),
    ("Front Close-up", "Tight waist-up front crop: the neckline, fabric and "
              "stitching fill the frame; legs and feet are OUT of frame."),
    ("Right Side", "Full-length right-side profile: the body turned a full "
              "90 degrees, showing the side of the body and the garment's "
              "side silhouette."),
    ("Left Side", "Full-length left-side profile: the body turned a full "
              "90 degrees the other way."),
    ("Back", "Full-length view from directly behind: the back of the garment "
              "fills the frame, the face is not visible."),
    ("Angle", "Full-length three-quarter view: the body turned about "
              "45 degrees, relaxed confident stance."),
    ("Detail", "Very tight close-up on the garment itself - sleeve, hem or "
              "print - showing the fabric and craftsmanship."),
    ("Seated", "Seated editorial pose with the full outfit visible."),
]

# Product-only preset shots (no model picked). Product-agnostic on purpose.
_PRODUCT_SHOTS = [
    ("Hero", "straight-on hero shot, the product centred and filling most of "
             "the frame"),
    ("Angle", "three-quarter angle view of the product"),
    ("Detail", "tight macro close-up of the product's finest detail and "
               "texture"),
    ("Side", "clean side-profile view of the product"),
    ("Lifestyle", "the product staged naturally in an in-use setting"),
    ("Top", "overhead top-down view of the product"),
    ("Back", "the product seen from behind"),
    ("Styled", "a second styled arrangement of the product"),
]
_PRODUCT_SETTINGS = [
    "clean seamless white studio, soft even light",
    "warm neutral surface, soft directional light",
    "dark slate surface, moody premium light",
    "light linen backdrop, bright morning light",
]


# ----------------------------------------------------------------- upload scan
def _analyze_uploads(urls):
    """ONE Haiku pass over the uploaded photos that returns BOTH:
      - listing copy (name/brand/category/description/details/care/delivery/
        meta) so the wizard fills itself from the render, and
      - an angle label per image (front/back/left/right/side/detail/other) so
        each pose is handed the RIGHT view regardless of upload order.
    Returns ({}, []) on failure - callers degrade to plain upload order."""
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
    return "front"      # front / close-up / angle / seated / detail default


def _ordered_refs(label, products, angles):
    """Order the upload pool so the pose-matched angle comes FIRST."""
    if not angles or len(angles) != len(products):
        return list(products)      # plain upload order
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


# --------------------------------------------------------------------- prompts
# The "blank stays blank" wording is battle-tested: the Lightning edit stamps
# invented brand text and embossed gibberish onto plain fabric unless told,
# POSITIVELY and at length, not to - the negative prompt does nothing at
# CFG 1.0. The rewrite trimmed this to one sentence and the sleeve-gibberish
# came straight back (job photos_044e0350). Do not shorten it again.
_RULES = (
    " Printed text rule: any lettering, logo or stamp that IS on the product "
    "stays exactly as photographed, letter for letter - and every surface "
    "that is blank in the photograph STAYS blank. Do not print, engrave, "
    "emboss or stamp ANY new text, brand name, logo, patch or graphic "
    "anywhere - not on the product, not on any other clothing in the frame, "
    "not in the background. Add NO texture, embossing, weave or pattern that "
    "the photograph does not show - plain fabric stays plain and smooth. "
    "No watermark, no signature; remove any seller watermark, price sticker "
    "or screenshot UI from the source photo. Photorealistic, sharp detail.")


def _worn_prompt(gender, pose, setting, followon, is_back):
    p = (f"A real photograph of a {gender} fashion model wearing this exact "
         f"garment - properly worn on the body, arms through the sleeves, "
         f"identical colours, fabric, prints and cut, nothing added, nothing "
         f"removed. {pose} The model fills the frame. Setting: {setting}. "
         f"A real human with natural skin texture and a relaxed expression - "
         f"not a mannequin, not CGI. Fully and modestly dressed, "
         f"family-friendly.")
    if followon:
        p += (" The model is the SAME person as the model in the reference "
              "photograph - same face, same hair, same build, the same "
              "photoshoot continued.")
    if is_back:
        p += (" The back of the garment stays exactly as photographed - do "
              "not stamp any new lettering, logo or graphic onto it.")
    return p + _RULES


def _product_prompt(visual, setting):
    return (f"Keep the product exactly as photographed - identical shape, "
            f"colours, materials and every detail. {visual.capitalize()}. "
            f"Setting: {setting}. No person in the frame." + _RULES)


# -------------------------------------------------------------------------- QA
def _qa_shots(ref_urls, shot_urls, labels, worn_flags=None):
    """One vision pass over the whole set: per-shot pass/issue/fix. Judges
    product fidelity for every shot, and camera angle/framing for worn shots."""
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
        f"FILLS the frame. "
        f"A worn shot must ALSO match its label: Back = the model seen from "
        f"BEHIND (face away), Left/Right Side = a side PROFILE, "
        f"Close-up/Detail = a TIGHT crop (NOT full-length), Front = "
        f"full-length facing the camera. Wrong angle or framing FAILS. "
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


# ------------------------------------------------------------------- rendering
def _render(jid, jd, i, base, refs, text, worn, tag):
    """One direct 8-step Lightning edit -> jd/scene_i.png."""
    import compose
    from PIL import Image
    neg = (compose.NEG_EDIT if worn else
           compose.NEG_PRODUCT + ", person, model, human, face, hands")
    out = compose.edit_scene(
        base, text, f"rk_{jid}_s{i}{tag}",
        seed=abs(hash(f"{jid}{tag}{i}")) % 10000,
        ref_paths=[r for r in refs if r][:2], negative=neg,
        target_wh=(PHOTO_W, PHOTO_H))
    dst = os.path.join(jd, f"scene_{i}.png")
    Image.open(out).convert("RGB").save(dst)
    return dst


def _fit(path, w, h):
    """Cover-crop to the target aspect and resize - a catalog shot must be a
    true 3:4 (poster 4:5) whatever resolution the edit model produced."""
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


# ------------------------------------------------------------------------ main
def make_photos(request):
    t0 = time.time()
    common.load_env()
    import animate      # local imports keep handler boot light
    import guards
    from make_reel import _free_comfy_vram, _upload

    urls = [u for u in (request.get("product_images") or []) if u][:8]
    if not urls:
        raise ValueError("product_images is required")
    style = guards.desexualise((request.get("prompt") or "").strip())
    mode = "poster" if request.get("mode") == "poster" else "photos"
    gender = (request.get("model_gender") or "").strip().lower() or None
    count = max(1, min(MAX_COUNT, int(request.get("count") or 5)))
    cfg = request.get("config") or {}

    jid, jd = common.new_job("photos")
    import tracer as _tracer
    tr = _tracer.Tracer(jid, enabled=bool(cfg.get("trace", True)))
    tr.write_json("request.json", {"product_images": urls, "prompt": style,
                                   "mode": mode, "count": count,
                                   "gender": gender})
    costs.reset()
    common.log("job", f"{jid} photos task: mode={mode} count={count} "
                      f"refs={len(urls)} gender={gender or 'none'}")

    products = []
    for i, u in enumerate(urls, 1):
        dst = os.path.join(jd, f"product_{i}{os.path.splitext(u)[1][:5] or '.jpg'}")
        common.fetch_url(u, dst)
        products.append(dst)

    _free_comfy_vram()      # clean GPU regardless of the previous job
    results, dropped, copy = [], 0, {}

    if mode == "poster":
        import compose
        posters = _direct_posters(urls, style, count)
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
                    ref_paths=products[1:3],
                    target_wh=(POSTER_W, POSTER_H))
                url = _upload(_fit(img, POSTER_W, POSTER_H),
                              "products/ai", f"{jid}-{i}-poster.jpg")
                results.append({"label": label, "url": url})
                tr.write_json(f"poster_{i}.json", {"label": label,
                                                   "prompt": text, "url": url})
            except Exception as e:
                dropped += 1
                common.log("photos", f"poster {i} failed ({e}) - dropped")
    else:
        copy, angles = _analyze_uploads(urls)
        if angles:
            # A front-labelled photo leads: establishing base + guard reference.
            fronts = [k for k, a in enumerate(angles) if a == "front"]
            if fronts and fronts[0] != 0:
                j = fronts[0]
                products[0], products[j] = products[j], products[0]
                angles[0], angles[j] = angles[j], angles[0]
            tr.write_json("angles.json",
                          [{"i": k, "angle": a} for k, a in enumerate(angles)])

        worn = gender in ("female", "male")
        if worn:
            setting = style or "clean seamless studio backdrop, soft even light"
            plan = [{"label": l, "visual": v, "worn": True, "setting": setting}
                    for l, v in _WORN_POSES[:count]]
        else:
            plan = [{"label": l, "visual": v, "worn": False,
                     "setting": style or _PRODUCT_SETTINGS[k % len(_PRODUCT_SETTINGS)]}
                    for k, (l, v) in enumerate(_PRODUCT_SHOTS[:count])]
        tr.write_json("director.json", plan)

        rerolls = MAX_REROLLS
        anchor = None       # the establishing worn still (identity reference)
        stills = []         # (i, shot, still_path, base, refs, prompt)
        for i, shot in enumerate(plan, 1):
            followon = shot["worn"] and anchor is not None
            xrefs = _ordered_refs(shot["label"], products, angles)
            if shot["worn"]:
                base = (xrefs[0] if followon and xrefs else products[0])
                refs = (([anchor] if followon else [])
                        + [p for p in xrefs if p != base])
                text = _worn_prompt(gender, shot["visual"], shot["setting"],
                                    followon,
                                    is_back="back" in shot["label"].lower())
            else:
                base = products[0]
                refs = [p for p in xrefs if p != base]
                text = _product_prompt(shot["visual"], shot["setting"])
            tr.write_json(f"scene_{i}_compose.json", {
                "label": shot["label"], "worn": shot["worn"],
                "base": os.path.basename(base),
                "refs": [os.path.basename(r) for r in refs[:2]],
                "followon": followon, "prompt": text})
            try:
                still = _render(jid, jd, i, base, refs, text, shot["worn"], "a")
                ok, detail = animate.guard_composite(still, products[0])
                tr.write_json(f"shot_{i}_guard.json", {"pass": ok,
                                                       "detail": detail})
                if not ok and rerolls > 0:      # invented text: one re-roll
                    rerolls -= 1
                    common.log("photos", f"shot {i} guard fail - re-roll "
                                         f"({detail[:80]})")
                    still = _render(jid, jd, i, base, refs,
                                    text + f" CRITICAL: the previous render "
                                           f"was WRONG ({detail}). Blank "
                                           f"surfaces stay blank; printed "
                                           f"text stays exact.",
                                    shot["worn"], "b")
                    ok, _ = animate.guard_composite(still, products[0])
                if not ok:
                    dropped += 1
                    common.log("photos", f"shot {i} failing OCR guard - "
                                         f"dropped")
                    continue
                stills.append((i, shot, still, base, refs, text))
                if shot["worn"] and anchor is None:
                    anchor = still   # establish the model for the rest
            except Exception as e:
                dropped += 1
                common.log("photos", f"shot {i} render failed ({e}) - dropped")
        animate.unload_guard()

        # Upload all shots, then ONE QA pass over the whole set.
        shot_urls, labels = [], []
        for i, shot, still, *_ in stills:
            slug = str(shot["label"]).lower().replace(" ", "-")[:24]
            shot_urls.append(_upload(_fit(still, PHOTO_W, PHOTO_H),
                                     "products/ai", f"{jid}-{i}-{slug}.jpg"))
            labels.append(str(shot["label"]))
        verdicts = {}
        try:
            verdicts = _qa_shots(urls, shot_urls, labels,
                                 [s["worn"] for _, s, *_ in stills])
            tr.write_json("qa.json", verdicts)
        except Exception as e:
            common.log("photos", f"QA pass failed (non-fatal, keeping all "
                                 f"shots): {e}")
        for k, (entry, u, label) in enumerate(
                zip(stills, shot_urls, labels), 1):
            i, shot, still, base, refs, text = entry
            v = verdicts.get(k, {"pass": True})
            if v.get("pass", True) or rerolls <= 0:
                # Out of budget -> ship the original; fidelity was OCR-guarded,
                # a framing miss is not worth an unbounded GPU bill.
                results.append({"label": label, "url": u})
                continue
            rerolls -= 1
            common.log("photos", f"shot {i} QA fail ({v.get('issue')}) - "
                                 f"corrected re-roll")
            try:
                still2 = _render(jid, jd, i, base, refs,
                                 text + f" CRITICAL: a previous attempt was "
                                        f"WRONG ({v.get('issue')}). "
                                        f"{v.get('fix') or ''}",
                                 shot["worn"], "c")
                results.append({"label": label,
                                "url": _upload(_fit(still2, PHOTO_W, PHOTO_H),
                                               "products/ai",
                                               f"{jid}-{i}-fixed.jpg")})
            except Exception as e:
                common.log("photos", f"shot {i} re-roll failed ({e}) - "
                                     f"keeping original")
                results.append({"label": label, "url": u})

    # copy came from the same pre-render pass that labeled the angles.
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
