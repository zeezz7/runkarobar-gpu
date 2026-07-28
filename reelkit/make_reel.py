"""
Reel pipeline - orchestrator.

One call in, one finished vertical reel out. Everything runs on this box:
    brain -> scene images -> video -> voiceover -> stitch -> upload

STAGES
  0  brain.py      Qwen2.5-32B-Instruct-FP8 writes the storyboard (sees the
                   product via Qwen2.5-VL captions). Unloaded before stage 1.
  1  compose.py    BiRefNet segment + Qwen-Image-2512 scene + PIL composite.
                   Product pixels are never passed through a sampler.
  2  animate.py    Ken-Burns over sharp composites (label cannot warp) or
                   Wan 2.2 I2V + LightX2V for non-product scenes. Optional
                   energy plate rendered on black and screen-blended.
  2b animate.guard_composite  Qwen2.5-VL OCR-diff against the source product.
  3  voiceover.py  ElevenLabs TTS. Real durations drive clip lengths.
  4  assemble.py   ffmpeg fit + fade + VO mux + captions -> 1080p and 720p.
  5  minio_upload  upload, return public URLs (no bucket segment).

MODELS USED
  Qwen2.5-32B-Instruct-FP8-dynamic   brain            /workspace/models/brain
  Qwen2.5-VL-7B-Instruct             captions + guard /workspace/models/qwen2.5-vl
  Qwen-Image-2512 fp8                scene generation ComfyUI diffusion_models
  Wan 2.2 I2V 14B fp8 + LightX2V     motion           ComfyUI diffusion_models
  BiRefNet                           segmentation     ComfyUI background_removal

HARD RULES
  * voiceover only - never any music or background track
  * no hardcoded fx/energy/product behaviour; the brain decides, we render
  * product fidelity via masked composite, harmonised with PIL only
"""
import json
import os
import subprocess
import sys
import time

import common
import costs

DEFAULT_CONFIG = {
    "lengthSec": 20,
    "resolution": "1080p",
    "aspectRatio": "9:16",
    "language": "en",
    "brandName": "",
    "elevenVoiceId": "",
    "captions": True,
    # creative-direction preset for the brain only; the renderer is unaware of it
    "template": "ai-director",
    # False = product only (no people/hands anywhere). StaffHQ's default.
    "includeHuman": False,
    # write a full per-run audit trail under runs/<run_id>/ (logging only)
    "trace": True,
}


def _free_comfy_vram():
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{common.COMFY}/free", method="POST",
            data=json.dumps({"unload_models": True, "free_memory": True}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=60).read()
    except Exception as e:
        common.log("vram", f"comfy free failed (non-fatal): {e}")


# Peak VRAM across the whole run. ComfyUI runs in its OWN process, so torch.cuda
# in THIS process can't see the diffusion models' usage - nvidia-smi reports the
# whole-GPU total, which is exactly the ceiling that decides what card fits.
_VRAM_PEAK_MB = 0


def _gpu_mem_mb():
    """(used_mb, total_mb) for GPU 0 across all processes, or (-1, -1)."""
    global _VRAM_PEAK_MB
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10).stdout.strip().splitlines()[0]
        used, total = (int(x.strip()) for x in out.split(","))
        _VRAM_PEAK_MB = max(_VRAM_PEAK_MB, used)
        return used, total
    except Exception:
        return -1, -1


def _gpu_str():
    used, total = _gpu_mem_mb()
    if used < 0:
        return "vram n/a"
    return (f"vram {used / 1024:.1f}/{total / 1024:.1f}GB "
            f"(peak {_VRAM_PEAK_MB / 1024:.1f}GB)")


def _upload(path, prefix, key=None):
    """
    Upload via minio_upload.py (its nginx bucket-rewrite signing is untouched).
    Credentials come from the environment / /workspace/.env - never hardcoded.
    `key` gives the object an explicit, job-unique name so two jobs cannot
    overwrite each other's stills.
    """
    env = dict(os.environ)
    for var in ("MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "MINIO_BUCKET"):
        if var not in env:
            raise RuntimeError(f"{var} not set (expected in /workspace/.env)")
    cmd = [sys.executable, os.path.join(common.REELKIT, "minio_upload.py"), path]
    cmd += ["--key", f"{prefix}/{key}"] if key else ["--prefix", prefix]
    p = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if p.returncode != 0:
        raise RuntimeError(f"upload failed for {path}: {p.stderr[-400:]}")
    return p.stdout.strip().split()[0]


def make_reel(request):
    """request -> result, both exactly as specified in the brief."""
    t_start = time.time()
    common.load_env()

    product_urls = request.get("product_images") or []
    brief = request.get("brief") or ""
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(request.get("config") or {})
    if not product_urls:
        raise ValueError("product_images is required")
    if not brief:
        raise ValueError("brief is required")

    # Template defaults. The REQUEST shape is untouched - config.template already
    # travels in it - but a template carries its own natural length and voice, so
    # apply those unless the caller stated one explicitly.
    import brain as _brain
    tpl_key, tpl_spec = _brain.resolve_template(cfg.get("template"))
    tpl_defaults = tpl_spec.get("defaults") or {}
    if "lengthSec" not in (request.get("config") or {}) and tpl_defaults.get("lengthSec"):
        cfg["lengthSec"] = tpl_defaults["lengthSec"]
        common.log("job", f"template '{tpl_key}' default length {cfg['lengthSec']}s")
    # outfit-check / testimonial / ad ARE about a person - StaffHQ only offers the
    # toggle on product-centric templates, so a person template implies it rather
    # than rendering an outfit-check with nobody in it.
    if (tpl_defaults.get("anchorModel") or tpl_defaults.get("presenterFace")) \
            and "includeHuman" not in (request.get("config") or {}):
        cfg["includeHuman"] = True
        common.log("job", f"template '{tpl_key}' features a person - includeHuman=True")
    if tpl_defaults.get("forceFemaleVoice") and not (cfg.get("elevenVoiceId") or "").strip():
        import voiceover as _vo
        cfg["elevenVoiceId"] = _vo.female_voice(cfg.get("language"))
        common.log("job", f"template '{tpl_key}' forces a female voice")

    jid, jd = common.new_job("reel")
    # LOGGING ONLY - the tracer never affects what is rendered.
    import tracer as _tracer
    tr = _tracer.Tracer(jid, enabled=bool(cfg.get("trace", True)))
    tr.write_json("request.json", {"product_images": product_urls,
                                   "brief": brief, "config": cfg})
    costs.reset()
    common.log("job", f"{jid}  len={cfg['lengthSec']}s  aspect={cfg['aspectRatio']}  "
                      f"lang={cfg['language']}  template={cfg.get('template')}")

    # ---- fetch product images ------------------------------------------------
    products = []
    for i, u in enumerate(product_urls, 1):
        dst = os.path.join(jd, f"product_{i}{os.path.splitext(u)[1][:5] or '.jpg'}")
        common.fetch_url(u, dst) if u.startswith("http") else common.run(["cp", u, dst])
        products.append(dst)
    common.log("job", f"{len(products)} product image(s)")

    # ---- STAGE 0: brain ------------------------------------------------------
    # Remote now (WaveSpeed any-llm/vision) - it holds no VRAM, needs no unload,
    # and takes seconds instead of the minutes the local 14B/32B checkpoint cost.
    # The ORIGINAL urls go to the brain, not the local copies: any-llm/vision
    # accepts URLs only. The local copies exist for the renderers.
    import brain
    sb = brain.storyboard(brief, cfg, products, tracer=tr,
                          image_urls=product_urls)
    tr.mark("brain")
    json.dump(sb, open(os.path.join(jd, "storyboard.json"), "w"),
              indent=2, ensure_ascii=False)
    tr.write_json("storyboard.json", sb)

    # NOTE: voiceover is generated LATER now - after the stills exist and Sonnet
    # has re-written the VO grounded in the ACTUAL images (see Stage 1b). Audio
    # still leads video: the VO's measured durations drive the Wan clip lengths.

    # ---- STAGE 1 + 2 + 2b ----------------------------------------------------
    import animate
    import compose
    aspect = cfg["aspectRatio"]
    # HD generation. Ken-Burns crops into the still, so generating at the final
    # delivery resolution keeps product scenes genuinely sharp instead of
    # upscaling a small still at assembly time.
    w, h = (1080, 1080) if aspect == "1:1" else (1080, 1920)
    include_human = bool(cfg.get("includeHuman", False))
    common.log("job", f"includeHuman={include_human} - "
                      + ("a person may feature" if include_human
                         else "PRODUCT ONLY, no person in any scene"))
    guard_log, clips, stills = [], [], []
    cut_cache, bg_cache = {}, {}
    anchor_still = None          # B1: the frame that fixes the model's identity
    # Default: free the edit models ONCE before motion (Stage 2 peak = just Wan,
    # ~28GB - safe on any card). Set REELKIT_KEEP_RESIDENT=1 to hold edit+Wan
    # resident (no free at all) once the VRAM probe confirms it fits the card.
    keep_resident = os.environ.get("REELKIT_KEEP_RESIDENT", "0").lower() in (
        "1", "true", "yes")
    common.log("vram", f"render start - {_gpu_str()}")

    # ===== STAGE 1: ALL scene images, edit model loaded ONCE =================
    # Batched on purpose. Generating every still before any motion keeps the edit
    # model resident across scenes instead of reloading it once per scene. On
    # serverless the weights live on the network volume, so a reload is a slow
    # network read - the biggest slice of render time. The old per-scene
    # _free_comfy_vram() existed to survive a 34GB LOCAL brain that is gone (the
    # brain is a remote WaveSpeed call now), so it is removed; we free at most
    # ONCE, between images and motion, and not at all when REELKIT_KEEP_RESIDENT
    # is set (a >=80GB card holds edit+Wan together, ~48GB of weights).
    t_img = time.time()
    for si, sc in enumerate(sb["scenes"]):
        n = sc["n"]
        product = products[si % len(products)]
        seed = abs(hash(jid)) % 10000
        t_s = time.time()
        still = compose.scene_image(sc, product, w, h, jd, seed=seed,
                                    cut_cache=cut_cache, bg_cache=bg_cache,
                                    tracer=tr, tpl_defaults=tpl_defaults,
                                    anchor=anchor_still, include_human=include_human)
        stills.append(still)
        common.log("time", f"image scene {n}: {time.time() - t_s:.1f}s  {_gpu_str()}")
        # The FIRST person scene becomes the anchor; later person scenes re-frame
        # from it, so one face carries the whole reel.
        if (anchor_still is None and tpl_defaults.get("anchorModel")
                and compose.scene_shows_person(sc, tpl_defaults)):
            anchor_still = still
            common.log("compose", f"scene {n}: ANCHOR set - later person scenes "
                                  f"re-frame this model")
        if sc["method"] in ("compose_animate", "edit_animate"):
            ok, detail = animate.guard_composite(still, product)
            guard_log.append({"scene": n, "ok": ok, "detail": detail})
            tr.write_json(f"scene_{n}_guard.json", {
                "scene": n, "pass": ok, "detail": detail, "retries": 0})
            common.log("guard", f"scene {n}: {'PASS' if ok else 'FAIL'} - {detail}")
            if not ok:
                # reuse the background; only change placement (PIL, ~1s)
                common.log("guard", f"scene {n}: re-compositing larger/higher "
                                    f"(reusing background)")
                still = compose.scene_image(
                    sc, product, w, h, jd, seed=abs(hash(jid)) % 10000,
                    cut_cache=cut_cache, bg_cache=bg_cache,
                    height_frac=0.62, center_y=0.50, include_human=include_human)
                ok2, detail2 = animate.guard_composite(still, product)
                guard_log.append({"scene": n, "ok": ok2, "detail": detail2,
                                  "retry": True})
                tr.write_json(f"scene_{n}_guard.json", {
                    "scene": n, "pass": ok2, "detail": detail2, "retries": 1,
                    "first_attempt": {"pass": ok, "detail": detail}})
                common.log("guard", f"scene {n} retry: "
                                    f"{'PASS' if ok2 else 'STILL FAIL'} - {detail2}")
                stills[-1] = still
    common.log("time", f"ALL {len(stills)} images in {time.time() - t_img:.1f}s  "
                       f"{_gpu_str()}")
    animate.unload_guard()      # release the 16GB VL guard before motion

    # ===== STAGE 1b: Sonnet validation gate (remote vision) =================
    # Upload the stills now - these URLs are the final ones too, so nothing is
    # re-uploaded later - show them to Sonnet and check each is usable BEFORE
    # spending GPU minutes on Wan. Log-only for now: flagged, not blocked.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as ex:
        scene_image_urls = list(ex.map(
            lambda ip: _upload(ip[1], "images", f"{jid}_s{ip[0]}.png"),
            list(enumerate(stills, 1))))
    tr.mark("images")
    # Sonnet DIRECTS from the real stills: validate each + write the motion and
    # VO grounded in what was ACTUALLY generated (not the pre-render plan). This
    # is the video-quality lift - the motion now matches the image, and the VO
    # describes what is really on screen while keeping the brief's story + CTA.
    directions = brain.direct_from_stills(scene_image_urls, sb, cfg,
                                          include_human, tracer=tr)
    by_scene = {d.get("scene"): d for d in directions}
    for sc in sb["scenes"]:
        d = by_scene.get(sc["n"])
        if not d:
            continue
        if d.get("motion"):
            sc["motion"] = d["motion"]
        if d.get("vo"):
            sc["vo"] = d["vo"]
    sonnet_checks = [{"scene": d.get("scene"), "pass": bool(d.get("pass", True)),
                      "issue": d.get("issue", "")} for d in directions]
    for c in sonnet_checks:
        common.log("validate", f"scene {c['scene']}: "
                              f"{'PASS' if c['pass'] else 'FAIL'} {c['issue']}")
    if any(not c["pass"] for c in sonnet_checks):
        common.log("validate", "some scenes flagged by Sonnet - proceeding "
                              "(gate is log-only for now)")

    # ---- STAGE 3: voiceover (now, from the grounded lines) -------------------
    # Audio leads video: the VO's measured durations drive the Wan clip lengths.
    import voiceover
    vo = voiceover.voice_scenes(sb, cfg, jd)
    for v in vo:
        sc = next((x for x in sb["scenes"] if x["n"] == v["n"]), None)
        if sc:
            tr.write_json(f"scene_{v['n']}_vo.json", {
                "vo_text": sc.get("vo"), "voice_id": voiceover.pick_voice(cfg),
                "model_id": voiceover.model_id(), "mp3_path": v.get("audio"),
                "measured_duration": v["duration"],
                "planned_duration": sc.get("durationSec")})
    tr.mark("voiceover")

    if not keep_resident:
        _free_comfy_vram()      # single edit->motion swap on a smaller card
        common.log("vram", f"freed edit models before motion - {_gpu_str()}")

    # ===== STAGE 2: ALL motion clips, Wan loaded ONCE =======================
    t_vid = time.time()
    for si, (sc, v) in enumerate(zip(sb["scenes"], vo)):
        n = sc["n"]
        product = products[si % len(products)]
        # Product-only reels use REAL generative motion, never a Ken-Burns zoom.
        if not include_human:
            sc["motionEngine"] = "video"
        t_s = time.time()
        clip, _ = animate.animate_scene(sc, stills[si], product, jd, w, h,
                                        v["duration"], guard_log=None, tracer=tr)
        clips.append(clip)
        common.log("time", f"video scene {n}: {time.time() - t_s:.1f}s  {_gpu_str()}")
        tr.mark(f"scene_{n}")
    common.log("time", f"ALL {len(clips)} videos in {time.time() - t_vid:.1f}s  "
                       f"{_gpu_str()}")

    # ---- STAGE 4: assemble ---------------------------------------------------
    import assemble
    outs = assemble.assemble(clips, vo, sb, jd, jid, aspect, bool(cfg["captions"]),
                             tracer=tr)
    tr.mark("assemble")

    # ---- STAGE 5: upload + return -------------------------------------------
    # Stills were already uploaded in Stage 1b (for the Sonnet gate) - reuse
    # those URLs, no re-upload. Here we ship the final reel + the per-scene motion
    # clips (raw Wan renders, before the VO + captions + crossfades of assemble),
    # which the VPS keeps as reusable b-roll.
    jobs = [("reel1080", outs["1080p"], "reels", None)]
    jobs += [(f"clip{i}", p, "clips", f"{jid}_c{i}.mp4")
             for i, p in enumerate(clips, 1) if p and os.path.isfile(p)]
    t_up = time.time()
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {name: ex.submit(_upload, path, prefix, key)
                for name, path, prefix, key in jobs}
        urls = {name: f.result() for name, f in futs.items()}
    common.log("upload", f"{len(jobs)} files in {time.time() - t_up:.1f}s (parallel)")

    result = {
        "reel_1080p_url": urls["reel1080"],
        # kept in the contract for compatibility; 720p is no longer rendered
        "reel_720p_url": "",
        "scene_image_urls": scene_image_urls,
        "scene_clip_urls": [urls[k] for i in range(1, len(clips) + 1)
                            if (k := f"clip{i}") in urls],
        "storyboard": sb,
        "durationSec": outs["durationSec"],
    }
    costs.current().stop_clock()
    _cost = costs.current().summary()
    # Load-bearing key for the caller's billing; the breakdown is diagnostic.
    result["cost_usd"] = _cost["total_usd"]
    result["_cost"] = _cost
    result["_guard"] = guard_log
    result["_elapsedSec"] = round(time.time() - t_start, 1)
    # What Sonnet actually decided (its "vision" of the reel) + the per-scene
    # validation verdicts, surfaced as first-class fields so the VPS can show
    # them next to the reel URL instead of digging into the raw storyboard.
    result["includeHuman"] = include_human
    result["brain"] = {
        "model": _brain.brain_model(),
        "concept": sb.get("concept"),
        "voice": sb.get("voice"),
        "notes": sb.get("notes"),
        "scenes": [
            {"n": s.get("n"), "goal": s.get("goal"), "method": s.get("method"),
             "visual": s.get("visual"), "motion": s.get("motion"),
             "vo": s.get("vo"), "durationSec": s.get("durationSec")}
            for s in sb.get("scenes", [])
        ],
    }
    result["validations"] = [
        {"scene": g.get("scene"), "pass": g.get("ok"), "detail": g.get("detail"),
         "retry": bool(g.get("retry"))}
        for g in guard_log
    ]
    # Sonnet's pre-motion QA verdicts (the gate that ran before Wan).
    result["sonnet_validation"] = sonnet_checks
    result["_vramPeakGB"] = round(_VRAM_PEAK_MB / 1024, 1) if _VRAM_PEAK_MB else None
    json.dump(result, open(os.path.join(jd, "result.json"), "w"),
              indent=2, ensure_ascii=False)
    tr.mark("upload")
    trace_dir = tr.rollup(result)
    if trace_dir:
        result["_traceDir"] = trace_dir
        common.log("trace", f"audit trail -> {trace_dir}")
    common.log("job", f"done in {result['_elapsedSec']}s -> {result['reel_1080p_url']}")
    return result


if __name__ == "__main__":
    req = (json.load(open(sys.argv[1])) if len(sys.argv) > 1 else {
        "product_images": ["/workspace/bakeoff/ref/nivea_ref.jpg"],
        "brief": "15s energetic ad for Nivea Men face wash, fresh gym vibe, male VO",
        "config": {"lengthSec": 15, "aspectRatio": "9:16", "language": "en",
                   "brandName": "Nivea Men", "captions": True},
    })
    out = make_reel(req)
    print(json.dumps(out, indent=2, ensure_ascii=False))
