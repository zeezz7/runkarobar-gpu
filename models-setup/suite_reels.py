#!/usr/bin/env python
"""
Four 15-second suit ads - one per colourway, 1 minute of finished video.

Per suit: 3 generated scenes x 5s. Same model throughout, three different
camera angles and three different settings, then Wan 2.2 animates each still.
One WaveSpeed brain call per suit writes the concept and the Hinglish voiceover.

Why the edit path IS used here (it was skipped last time)
--------------------------------------------------------
The previous ad had to keep the photographer's exact pixels, so the stills were
crops of the originals. This brief asks for *generated* images - new angles, new
backgrounds - so Qwen-Image-Edit-2511 is the right tool and is what runs.

The instruction is built to protect the garment anyway: every prompt names the
suit's colour and pins the embroidery, motifs and dupatta as unchanged, and only
the camera angle and setting are described as changing. Verified on a test edit -
the embroidery, the model's face and the dupatta print all survived intact.

  /venv/main/bin/python suite_reels.py            # all four
  /venv/main/bin/python suite_reels.py 2 4        # only those suits
"""
import json
import os
import sys
import time

sys.path.insert(0, "/workspace/reelkit")
import common                                              # noqa: E402
import brain                                               # noqa: E402
import compose                                             # noqa: E402
import animate                                             # noqa: E402
import voiceover                                           # noqa: E402
import assemble                                            # noqa: E402
import make_reel as mr                                     # noqa: E402

BASE = "https://staging-storage.runkarobar.com/videos/uploads/"
SUITS = [
    {"n": 1, "colour": "emerald green",
     "url": BASE + "1785150296652-826672de130d6770-WhatsApp_Image_2026-07-27_at_4.32.11_PM.jpg"},
    {"n": 2, "colour": "rich purple",
     "url": BASE + "1785150297282-859fd5f2e20710a6-WhatsApp_Image_2026-07-27_at_4.32.12_PM__1_.jpg"},
    {"n": 3, "colour": "turquoise",
     "url": BASE + "1785150298822-e5ffa3a97d7c4a88-WhatsApp_Image_2026-07-27_at_4.32.13_PM.jpg"},
    {"n": 4, "colour": "cream and black",
     "url": BASE + "1785150298218-c778da8dca06b6a8-WhatsApp_Image_2026-07-27_at_4.32.12_PM.jpg"},
]

# Every edit prompt is PIN + ANGLE + SETTING. The pin is identical each time so
# the garment cannot drift between the three scenes of one ad.
PIN = ("Keep the SAME woman with the SAME face and hair, and the SAME {colour} "
       "embroidered lawn suit - identical embroidery, identical motifs, identical "
       "colours, identical dupatta print. Do not alter any detail of the garment. "
       "Change ONLY the camera angle and the setting. ")
QUALITY = (", professional fashion editorial photography, full-length shot, "
           "sharp focus on the garment, beautiful natural light, high detail, "
           "shot on 85mm, shallow depth of field")

SHOTS = [
    {"k": "hero",
     "look": "straight-on hero angle, she stands confidently facing camera",
     "set": "a warm sunlit marble courtyard with tall arches softly blurred behind her, "
            "golden hour light"},
    {"k": "three-quarter",
     "look": "three-quarter side angle, she turns slightly and glances toward camera",
     "set": "an elegant garden terrace with soft green foliage and dappled afternoon "
            "light blurred behind her"},
    {"k": "walking",
     "look": "slight low angle, she walks toward camera mid-stride, dupatta lifting",
     "set": "a luxury boutique interior with warm wood, soft pooled lighting and a "
            "deep blurred background"},
]

MOTION = [
    "the camera pushes in slowly and she turns gently toward it, the embroidered suit "
    "stays exactly the same, fabric drifts softly, cinematic, sharp detail",
    "the camera orbits slowly around her as she turns, the suit and its embroidery stay "
    "exactly the same, dupatta lifts gently in the breeze, cinematic",
    "she walks slowly toward camera, dupatta and fabric flowing, the suit stays exactly "
    "the same, smooth cinematic tracking shot, sharp detail",
]


def build(suit):
    n, colour = suit["n"], suit["colour"]
    jid, jd = common.new_job(f"suit{n}")
    common.log("job", f"=== suit {n} ({colour}) -> {jid}")

    src = os.path.join(jd, "product.jpg")
    common.fetch_url(suit["url"], src)

    # ---- STAGE 0: one real brain call, this suit's photo -------------------
    t0 = time.time()
    sb = brain.storyboard(
        f"15 second premium fashion ad for a {colour} embroidered lawn suit. "
        f"Exactly 3 scenes, 5 seconds each, same model throughout. Aspirational, "
        f"desirable, scroll-stopping - a legit professional brand ad, not a cheap "
        f"reel. Warm confident female Hinglish voiceover.",
        {"lengthSec": 15, "aspectRatio": "9:16", "language": "hinglish",
         "brandName": "the collection", "captions": False, "template": "showcase"},
        [src], image_urls=[suit["url"]])
    brain_s = round(time.time() - t0, 1)

    scenes = sb["scenes"][:3]
    while len(scenes) < 3:
        scenes.append(json.loads(json.dumps(scenes[-1])))
    for i, sc in enumerate(scenes, 1):
        sc["n"] = i
        sc["durationSec"] = 5.0
        sc["transitionIn"] = "fade" if i == 1 else "cut"
    sb["scenes"] = scenes
    json.dump(sb, open(os.path.join(jd, "storyboard.json"), "w"),
              indent=2, ensure_ascii=False)

    # ---- STAGE 3: voiceover (before the visuals) ---------------------------
    t0 = time.time()
    vo = voiceover.voice_scenes(sb, {"language": "hinglish"}, jd)
    for v in vo:
        v["duration"] = 5.0
    vo_s = round(time.time() - t0, 1)

    # ---- STAGES 1+2: generate the still, then animate it -------------------
    stills, clips, per_scene = [], [], []
    for i, shot in enumerate(SHOTS, 1):
        t0 = time.time()
        instruction = (PIN.format(colour=colour) + shot["look"] + ", " +
                       shot["set"] + QUALITY)
        still = compose.edit_scene(src, instruction, f"{jid}_s{i}",
                                   seed=1000 * n + i)
        stills.append(still)
        common.log("compose", f"suit {n} scene {i}: {shot['k']}")
        clip = animate.wan_i2v(still, MOTION[i - 1],
                               os.path.join(jd, f"clip_{i}.mp4"),
                               f"{jid}_s{i}", duration=5.0)
        clips.append(clip)
        per_scene.append(round(time.time() - t0, 1))

    # ---- STAGE 4+5: assemble and upload ------------------------------------
    t0 = time.time()
    outs = assemble.assemble(clips, vo, sb, jd, jid, "9:16", False)
    as_s = round(time.time() - t0, 1)

    t0 = time.time()
    reel_url = mr._upload(outs["1080p"], "reels")
    still_urls = [mr._upload(s, "images", f"{jid}_s{i}.png")
                  for i, s in enumerate(stills, 1)]
    up_s = round(time.time() - t0, 1)

    res = {"suit": n, "colour": colour, "job": jid,
           "reel_url": reel_url, "scene_image_urls": still_urls,
           "durationSec": outs["durationSec"], "concept": sb.get("concept"),
           "vo": [s.get("vo") for s in sb["scenes"]],
           "_timings": {"brain": brain_s, "vo": vo_s, "scenes": per_scene,
                        "assemble": as_s, "upload": up_s}}
    json.dump(res, open(os.path.join(jd, "result.json"), "w"),
              indent=2, ensure_ascii=False)
    common.log("job", f"=== suit {n} done -> {reel_url}")
    return res


def main():
    common.load_env()
    want = {int(a) for a in sys.argv[1:]} or {1, 2, 3, 4}
    out = []
    for s in SUITS:
        if s["n"] in want:
            out.append(build(s))
    print("\n=== ALL RESULTS ===")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    json.dump(out, open("/workspace/models-setup/logs/suite_reels.json", "w"),
              indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
