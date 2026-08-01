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


def _extract_json(raw):
    """Tolerant JSON array/object extraction (models love markdown fences)."""
    raw = (raw or "").strip()
    for start, end in (("[", "]"), ("{", "}")):
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
        + (" - INTENTIONALLY worn by a model; the person is correct, judge "
           "only the product's fidelity" if worn_flags[i] else
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
    results, dropped = [], 0

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
        shots = _direct_photos(urls, prompt, count, model_gender=gender)
        tr.write_json("director.json", shots)
        stills, shot_urls, labels = [], [], []
        for i, shot in enumerate(shots, 1):
            worn = bool(shot.get("worn"))
            sc = _scene(i, shot)
            try:
                still = compose.scene_image(
                    sc, products[0], PHOTO_W, PHOTO_H, jd,
                    seed=abs(hash(f"{jid}s{i}")) % 10000, tracer=tr,
                    include_human=worn, emphasis=FILL_FRAME)
                ok, detail = animate.guard_composite(still, products[0])
                tr.write_json(f"shot_{i}_guard.json", {"pass": ok,
                                                       "detail": detail})
                if not ok:     # invented/changed lettering: one fresh re-roll
                    common.log("photos", f"shot {i} guard fail - re-roll "
                                         f"({detail[:80]})")
                    still = compose.scene_image(
                        sc, products[0], PHOTO_W, PHOTO_H, jd,
                        seed=abs(hash(f"{jid}retry{i}")) % 10000, tracer=tr,
                        include_human=worn,
                        emphasis=FILL_FRAME + f" CRITICAL: the previous render "
                                 f"was WRONG ({detail}). Blank surfaces stay "
                                 f"blank; printed text stays exact.")
                    ok2, _ = animate.guard_composite(still, products[0])
                    if not ok2:
                        dropped += 1
                        common.log("photos", f"shot {i} still failing OCR "
                                             f"guard - dropped")
                        continue
                stills.append((i, shot, still))
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
            try:
                still2 = compose.scene_image(
                    sc, products[0], PHOTO_W, PHOTO_H, jd,
                    seed=abs(hash(f"{jid}fix{i}")) % 10000, tracer=tr,
                    include_human=bool(shot.get("worn")),
                    emphasis=FILL_FRAME + f" CRITICAL: a previous attempt was "
                             f"WRONG ({v.get('issue')}). Match the reference "
                             f"product EXACTLY.")
                u2 = _upload(_fit(still2, PHOTO_W, PHOTO_H),
                             "products/ai", f"{jid}-{i}-fixed.jpg")
                results.append({"label": label, "url": u2})
            except Exception as e:
                dropped += 1
                common.log("photos", f"shot {i} corrected re-roll failed "
                                     f"({e}) - dropped")

    _free_comfy_vram()      # leave a clean GPU for the next (reel) job
    costs.current().stop_clock()
    _cost = costs.current().summary()
    result = {
        "results": results,
        "mode": mode,
        "dropped": dropped,
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
