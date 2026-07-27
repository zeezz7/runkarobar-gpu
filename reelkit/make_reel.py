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


def _lipsync_scene(jid, n, still, vo_track, sb, jd):
    """
    Render one talking-presenter scene. Returns a clip path, or None to fall back.

    The avatar service fetches its inputs itself, so the still and the scene's
    mp3 must be PUBLIC first - hence the two uploads. Failure is never fatal: the
    caller animates the still normally instead, so a flaky avatar costs polish,
    not the reel.
    """
    import avatar
    try:
        img_url = _upload(still, "images", f"{jid}_s{n}_presenter.png")
        aud_url = _upload(vo_track["audio"], "audio", f"{jid}_s{n}_vo.mp3")
    except Exception as e:
        common.log("avatar", f"scene {n}: could not publish inputs ({e})")
        return None
    out = os.path.join(jd, f"clip_{n}_talk.mp4")
    got = avatar.lipsync(img_url, aud_url, out,
                         item_name=(sb.get("concept") or "the product")[:60])
    if got:
        avatar.note_cost(float(vo_track.get("duration") or 5))
        common.log("avatar", f"scene {n}: lip-synced presenter clip")
    return got


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

    # ---- STAGE 3 first: audio leads video ------------------------------------
    import voiceover
    vo = voiceover.voice_scenes(sb, cfg, jd)
    for v in vo:
        sc = next(x for x in sb["scenes"] if x["n"] == v["n"])
        tr.write_json(f"scene_{v['n']}_vo.json", {
            "vo_text": sc.get("vo"), "voice_id": voiceover.pick_voice(cfg),
            "model_id": voiceover.model_id(), "mp3_path": v.get("audio"),
            "measured_duration": v["duration"],
            "planned_duration": sc.get("durationSec")})
    tr.mark("voiceover")

    # ---- STAGE 1 + 2 + 2b ----------------------------------------------------
    import animate
    import compose
    aspect = cfg["aspectRatio"]
    # HD generation. Ken-Burns crops into the still, so generating at the final
    # delivery resolution keeps product scenes genuinely sharp instead of
    # upscaling a small still at assembly time.
    w, h = (1080, 1080) if aspect == "1:1" else (1080, 1920)
    guard_log, clips, stills = [], [], []
    cut_cache, bg_cache = {}, {}
    anchor_still = None          # B1: the frame that fixes the model's identity
    lipsync_budget = int(tpl_defaults.get("lipsyncScenes") or 0)

    for si, (sc, v) in enumerate(zip(sb["scenes"], vo)):
        n = sc["n"]
        # A reel mixes three model families - Qwen-Image-Edit (20GB), Qwen-Image
        # (20GB) and Wan 2.2 (28GB). ComfyUI will happily hold all of them, which
        # reached 80.5GB of this 95GB card and then OOMed on the next allocation.
        # Freeing between scenes costs a reload but keeps the job alive.
        _free_comfy_vram()
        # rotate through the supplied product photos so multiple angles get used
        # rather than repeating image 1 in every scene
        product = products[si % len(products)]
        seed = abs(hash(jid)) % 10000
        still = compose.scene_image(sc, product, w, h, jd, seed=seed,
                                    cut_cache=cut_cache, bg_cache=bg_cache,
                                    tracer=tr, tpl_defaults=tpl_defaults,
                                    anchor=anchor_still)
        stills.append(still)
        # The FIRST person scene becomes the anchor; every later person scene is
        # re-framed FROM it, so one face carries the whole reel.
        if anchor_still is None and tpl_defaults.get("anchorModel") and (
                sc.get("mode") == "scene" or sc["method"] == "lipsync"):
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
                    height_frac=0.62, center_y=0.50)
                ok2, detail2 = animate.guard_composite(still, product)
                guard_log.append({"scene": n, "ok": ok2, "detail": detail2,
                                  "retry": True})
                tr.write_json(f"scene_{n}_guard.json", {
                    "scene": n, "pass": ok2, "detail": detail2, "retries": 1,
                    "first_attempt": {"pass": ok, "detail": detail}})
                common.log("guard", f"scene {n} retry: "
                                    f"{'PASS' if ok2 else 'STILL FAIL'} - {detail2}")
                stills[-1] = still

        animate.unload_guard()      # release 16GB before the diffusion work

        # Ken-Burns renders at full delivery resolution (it is pure ffmpeg, so
        # there is no reason to downscale). Wan is capped internally at 480x832
        # by VRAM, which is a model limit rather than a choice.
        # A lipsync scene is rendered by the remote avatar model instead of i2v.
        # It needs the scene's OWN voiceover audio, which stage 3 already made.
        if sc["method"] == "lipsync" and lipsync_budget > 0 and v.get("audio"):
            lipsync_budget -= 1
            talk = _lipsync_scene(jid, n, still, v, sb, jd)
            if talk:
                clips.append(talk)
                tr.mark(f"scene_{n}")
                continue
            common.log("avatar", f"scene {n}: falling back to i2v")

        clip, _ = animate.animate_scene(sc, still, product, jd, w, h,
                                        v["duration"], guard_log=None, tracer=tr)
        clips.append(clip)
        tr.mark(f"scene_{n}")

    # ---- STAGE 4: assemble ---------------------------------------------------
    import assemble
    outs = assemble.assemble(clips, vo, sb, jd, jid, aspect, bool(cfg["captions"]),
                             tracer=tr)
    tr.mark("assemble")

    # ---- STAGE 5: upload + return -------------------------------------------
    # Uploads are network-bound and independent, so run them together: serial
    # upload of 2 videos + N stills was ~60s of pure waiting.
    from concurrent.futures import ThreadPoolExecutor
    jobs = [("reel1080", outs["1080p"], "reels", None)]
    jobs += [(f"still{i}", p, "images", f"{jid}_s{i}.png")
             for i, p in enumerate(stills, 1)]
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
        "scene_image_urls": [urls[f"still{i}"] for i in range(1, len(stills) + 1)],
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
