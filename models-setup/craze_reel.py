#!/usr/bin/env python
"""
"Craze" ad for the 4-colourway embroidered lawn suit set.

Brief: 4 scenes x 5s = 20s, one per colourway, with ROTATION and CLOSEUP, and
the product detailing must not change.

Why this does NOT go through compose.edit_animate
-------------------------------------------------
That is the pipeline's default scene builder and it is the wrong tool *for this
product*. Qwen-Image-Edit re-renders every pixel it touches at denoise 1.0; on a
plain printed label it holds up (it kept 11/11 Nivea tokens), but this garment is
dense hand-drawn embroidery - thousands of tiny motifs with no semantic anchor.
A re-render reinvents them, which is exactly the "product detailing should not
change" failure. FLOW.md already records that edit_animate re-renders the person
too, so faces drift between scenes - with four scenes of the same model that
would be very visible.

compose_animate is also out: segmenting a photo that contains a PERSON yields the
whole person, which then gets pasted onto a scene that may also contain one.

So the still for every scene is the ORIGINAL PHOTOGRAPH, and the only operations
applied to it are a PIL crop and a resize - arithmetic, not inference. Wan 2.2
i2v then animates it. The garment pixels reaching the video model are the real
ones. Closeups are a real crop of the 1600px source rather than a digital zoom
into an already-downscaled frame, which is what keeps the embroidery readable.

The brain still writes the ad: one real WaveSpeed any-llm/vision call sees all
four photographs and returns the concept, the per-scene direction and the
Hinglish voiceover.

  /venv/main/bin/python craze_reel.py
"""
import json
import os
import sys
import time

sys.path.insert(0, "/workspace/reelkit")
import common                                              # noqa: E402
import brain                                               # noqa: E402
import animate                                             # noqa: E402
import voiceover                                           # noqa: E402
import assemble                                            # noqa: E402
import make_reel as mr                                     # noqa: E402
from PIL import Image                                      # noqa: E402

BASE = "https://staging-storage.runkarobar.com/videos/uploads/"
IMAGES = [
    BASE + "1785150296652-826672de130d6770-WhatsApp_Image_2026-07-27_at_4.32.11_PM.jpg",
    BASE + "1785150297282-859fd5f2e20710a6-WhatsApp_Image_2026-07-27_at_4.32.12_PM__1_.jpg",
    BASE + "1785150298822-e5ffa3a97d7c4a88-WhatsApp_Image_2026-07-27_at_4.32.13_PM.jpg",
    BASE + "1785150298218-c778da8dca06b6a8-WhatsApp_Image_2026-07-27_at_4.32.12_PM.jpg",
]

BRIEF = (
    "20 second high-energy 'craze' fashion reel for a 4-colourway embroidered "
    "lawn suit collection - the kind of ad that makes people stop scrolling and "
    "want it immediately. Exactly 4 scenes, 5 seconds each, one per colourway. "
    "Hype, desire, urgency. Warm female Hinglish voiceover."
)

# Scene plan. Alternating wide/rotation and detail/closeup, as asked.
#   crop=None        -> the whole photograph, 9:16 framed
#   crop=(cx,cy,fh)  -> centre x, centre y and height as FRACTIONS of the source;
#                       a real crop of the 1600px original, not a digital zoom.
PLAN = [
    {"n": 1, "crop": None,              "shot": "full look, slow rotation"},
    {"n": 2, "crop": (0.50, 0.30, 0.34), "shot": "closeup on the neckline embroidery"},
    {"n": 3, "crop": None,              "shot": "full look, slow rotation"},
    {"n": 4, "crop": (0.50, 0.32, 0.38), "shot": "closeup on the embroidered panel"},
]

# Motion prompts. Wan reads these literally, so the rotation ones name an orbit
# and the closeup ones name a push-in; both say the garment must not change.
MOTION = {
    1: ("the model turns slowly toward camera and the camera orbits gently around "
        "her, the embroidered suit stays exactly the same, fabric and dupatta drift "
        "softly in the breeze, sharp detail, cinematic"),
    2: ("very slow push-in on the embroidery, threads and beadwork stay crisp and "
        "unchanged, fabric breathes slightly, shallow depth of field, cinematic"),
    3: ("the camera orbits slowly around the model as she turns, the printed suit "
        "stays exactly the same, dupatta lifts gently in the wind, sharp detail"),
    4: ("slow push-in across the embroidered panel, every motif stays identical and "
        "sharp, gentle fabric movement, soft light sweep, cinematic"),
}

W, H = 1080, 1920


def frame_still(src_path, dst_path, crop):
    """
    Build the 9:16 still WITHOUT any generative step.

    A crop plus a Lanczos resize - the garment pixels are the photographer's.
    """
    im = Image.open(src_path).convert("RGB")
    sw, sh = im.size
    if crop:
        cx, cy, fh = crop
        ch = sh * fh
        cw = ch * 9 / 16
        left = max(0, min(sw - cw, cx * sw - cw / 2))
        top = max(0, min(sh - ch, cy * sh - ch / 2))
        im = im.crop((int(left), int(top), int(left + cw), int(top + ch)))
    else:
        # centre-crop the full photo to 9:16 rather than squashing it
        target = 9 / 16
        if sw / sh > target:
            cw = sh * target
            im = im.crop((int((sw - cw) / 2), 0, int((sw + cw) / 2), sh))
        else:
            ch = sw / target
            im = im.crop((0, int((sh - ch) / 2), sw, int((sh + ch) / 2)))
    im = im.resize((W, H), Image.LANCZOS)
    im.save(dst_path, quality=96)
    return dst_path


def main():
    common.load_env()
    jid, jd = common.new_job("craze")
    common.log("job", f"{jid} -> {jd}")

    # ---- fetch the four originals -------------------------------------------
    srcs = []
    for i, u in enumerate(IMAGES, 1):
        dst = os.path.join(jd, f"product_{i}.jpg")
        common.fetch_url(u, dst)
        srcs.append(dst)
    common.log("job", f"{len(srcs)} product image(s)")

    # ---- STAGE 0: the real WaveSpeed brain, one call, all four photos --------
    t_brain = time.time()
    sb = brain.storyboard(
        BRIEF,
        {"lengthSec": 20, "aspectRatio": "9:16", "language": "hinglish",
         "brandName": "the collection", "captions": False, "template": "showcase"},
        srcs, image_urls=IMAGES)
    brain_s = round(time.time() - t_brain, 1)
    common.log("brain", f"stage took {brain_s}s")

    # The brain writes the ad; this script owns the execution, so force the plan
    # the brief specified: 4 scenes of exactly 5s.
    scenes = sb["scenes"][:4]
    while len(scenes) < 4:
        scenes.append(json.loads(json.dumps(scenes[-1])))
    for i, sc in enumerate(scenes, 1):
        sc["n"] = i
        sc["durationSec"] = 5.0
        sc["transitionIn"] = "cut" if i > 1 else "fade"
    sb["scenes"] = scenes
    json.dump(sb, open(os.path.join(jd, "storyboard.json"), "w"),
              indent=2, ensure_ascii=False)
    print(json.dumps(sb, indent=2, ensure_ascii=False))

    # ---- STAGE 3: voiceover (runs before the visuals) ------------------------
    t_vo = time.time()
    vo = voiceover.voice_scenes(sb, {"language": "hinglish"}, jd)
    for v in vo:                       # hard 5s slots - the brief is explicit
        v["duration"] = 5.0
    vo_s = round(time.time() - t_vo, 1)

    # ---- STAGES 1+2: real still -> Wan i2v ----------------------------------
    stills, clips, timings = [], [], []
    for p, sc in zip(PLAN, sb["scenes"]):
        n = p["n"]
        t0 = time.time()
        still = frame_still(srcs[n - 1], os.path.join(jd, f"scene_{n}.png"), p["crop"])
        stills.append(still)
        common.log("compose", f"scene {n}: {p['shot']} (real pixels, crop+resize only)")
        clip = animate.wan_i2v(still, MOTION[n], os.path.join(jd, f"clip_{n}.mp4"),
                               f"{jid}_s{n}", duration=5.0)
        clips.append(clip)
        timings.append(round(time.time() - t0, 1))
        common.log("animate", f"scene {n}: {timings[-1]}s")

    # ---- STAGE 4: assemble ---------------------------------------------------
    t_as = time.time()
    outs = assemble.assemble(clips, vo, sb, jd, jid, "9:16", False)
    as_s = round(time.time() - t_as, 1)

    # ---- STAGE 5: upload -----------------------------------------------------
    t_up = time.time()
    reel_url = mr._upload(outs["1080p"], "reels")
    still_urls = [mr._upload(s, "images", f"{jid}_s{i}.png")
                  for i, s in enumerate(stills, 1)]
    up_s = round(time.time() - t_up, 1)

    result = {
        "reel_1080p_url": reel_url,
        "scene_image_urls": still_urls,
        "durationSec": outs["durationSec"],
        "_timings": {"brain": brain_s, "voiceover": vo_s,
                     "scenes": timings, "assemble": as_s, "upload": up_s},
        "storyboard": sb,
    }
    json.dump(result, open(os.path.join(jd, "result.json"), "w"),
              indent=2, ensure_ascii=False)
    print("\n=== RESULT ===")
    print(json.dumps({k: v for k, v in result.items() if k != "storyboard"},
                     indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
