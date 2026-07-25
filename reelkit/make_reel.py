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

DEFAULT_CONFIG = {
    "lengthSec": 20,
    "resolution": "1080p",
    "aspectRatio": "9:16",
    "language": "en",
    "brandName": "",
    "elevenVoiceId": "",
    "captions": True,
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

    jid, jd = common.new_job("reel")
    common.log("job", f"{jid}  len={cfg['lengthSec']}s  aspect={cfg['aspectRatio']}  "
                      f"lang={cfg['language']}")

    # ---- fetch product images ------------------------------------------------
    products = []
    for i, u in enumerate(product_urls, 1):
        dst = os.path.join(jd, f"product_{i}{os.path.splitext(u)[1][:5] or '.jpg'}")
        common.fetch_url(u, dst) if u.startswith("http") else common.run(["cp", u, dst])
        products.append(dst)
    common.log("job", f"{len(products)} product image(s)")

    # ---- STAGE 0: brain ------------------------------------------------------
    import brain
    _free_comfy_vram()
    sb = brain.storyboard(brief, cfg, products)
    brain.unload_brain()
    json.dump(sb, open(os.path.join(jd, "storyboard.json"), "w"),
              indent=2, ensure_ascii=False)

    # ---- STAGE 3 first: audio leads video ------------------------------------
    import voiceover
    vo = voiceover.voice_scenes(sb, cfg, jd)

    # ---- STAGE 1 + 2 + 2b ----------------------------------------------------
    import animate
    import compose
    aspect = cfg["aspectRatio"]
    w, h = (1080, 1080) if aspect == "1:1" else (768, 1376)   # generation size
    guard_log, clips, stills = [], [], []
    cut_cache = {}

    for sc, v in zip(sb["scenes"], vo):
        n = sc["n"]
        still = compose.scene_image(sc, products[0], w, h, jd,
                                    seed=abs(hash(jid)) % 10000, cut_cache=cut_cache)
        stills.append(still)

        if sc["method"] == "compose_animate":
            ok, detail = animate.guard_composite(still, products[0])
            guard_log.append({"scene": n, "ok": ok, "detail": detail})
            common.log("guard", f"scene {n}: {'PASS' if ok else 'FAIL'} - {detail}")
            if not ok:
                common.log("guard", f"scene {n}: re-compositing larger/higher")
                still = compose.scene_image(
                    sc, products[0], w, h, jd,
                    seed=abs(hash(jid)) % 10000 + 77, cut_cache=cut_cache)
                ok2, detail2 = animate.guard_composite(still, products[0])
                guard_log.append({"scene": n, "ok": ok2, "detail": detail2,
                                  "retry": True})
                common.log("guard", f"scene {n} retry: "
                                    f"{'PASS' if ok2 else 'STILL FAIL'} - {detail2}")
                stills[-1] = still

        clip, _ = animate.animate_scene(sc, still, products[0], jd,
                                        480 if aspect != "1:1" else 720,
                                        832 if aspect != "1:1" else 720,
                                        v["duration"], guard_log=None)
        clips.append(clip)

    # ---- STAGE 4: assemble ---------------------------------------------------
    import assemble
    outs = assemble.assemble(clips, vo, sb, jd, jid, aspect, bool(cfg["captions"]))

    # ---- STAGE 5: upload + return -------------------------------------------
    result = {
        "reel_1080p_url": _upload(outs["1080p"], "reels"),
        "reel_720p_url": _upload(outs["720p"], "reels"),
        "scene_image_urls": [_upload(s, "images", key=f"{jid}_s{i}.png")
                             for i, s in enumerate(stills, 1)],
        "storyboard": sb,
        "durationSec": outs["durationSec"],
    }
    result["_guard"] = guard_log
    result["_elapsedSec"] = round(time.time() - t_start, 1)
    json.dump(result, open(os.path.join(jd, "result.json"), "w"),
              indent=2, ensure_ascii=False)
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
