#!/usr/bin/env python
"""
20-second ad for the ruby-stone necklace and earring set. 4 scenes x 5s.

The source is a hand-held phone snap on a palm - correct product, wrong context
for an ad. Qwen-Image-Edit restages it on proper jewellery display surfaces with
studio lighting, and each prompt pins the piece itself so the stone count, the
settings and the layout cannot drift between scenes.

Jewellery is less forgiving than the lawn suits: the value is in the stones and
the pave settings, so every prompt names them explicitly and the shots stay
close. Wan then adds slow moves that read as "expensive" - push-ins, a gentle
orbit, a light sweep across the facets.

  /venv/main/bin/python jewel_reel.py
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

PRODUCT = ("https://staging-storage.runkarobar.com/videos/uploads/"
           "1785153610027-1b1f13313a6cd8b1-WhatsApp_Image_2026-07-23_at_9.13.15_PM.jpg")

BRIEF = ("20 second premium jewellery ad for a ruby-red stone necklace and "
         "matching drop earrings set in sparkling white pave stones. Exactly 4 "
         "scenes, 5 seconds each. Luxurious, aspirational, festive - the kind of "
         "ad a real jewellery brand runs. Warm confident female Hinglish voiceover.")

# The pin is identical in every prompt so the piece cannot change between scenes.
PIN = ("Keep the SAME jewellery set EXACTLY as photographed - the same ruby-red "
       "square and pear-cut stones, the same number of stones, the same white "
       "pave-stone halos and settings, the same necklace layout and the same drop "
       "earrings. Do not redesign, add or remove any stone. Change ONLY the "
       "presentation and the lighting. ")
QUALITY = (", luxury jewellery advertising photography, studio lighting, crisp "
           "specular sparkle on every facet, macro detail, shallow depth of field, "
           "clean elegant composition, high end catalogue quality")

SHOTS = [
    {"k": "hero on velvet",
     "set": "the set arranged on deep black velvet, a single soft key light "
            "raking across the stones so they burn bright against the dark"},
    {"k": "bust display",
     "set": "the necklace displayed on an elegant cream jewellery bust, the "
            "earrings resting beside it, warm boutique lighting, softly blurred "
            "background"},
    {"k": "macro detail",
     "set": "an extreme close-up of the centre stones and their pave halos filling "
            "the frame, dark reflective surface, dramatic directional light"},
    {"k": "festive styling",
     "set": "the set on a polished marble surface with soft gold bokeh lights "
            "behind it, warm festive glow"},
]

MOTION = [
    "very slow push-in on the jewellery, light glints travel across the stones, "
    "the piece stays exactly the same, sparkling highlights, cinematic macro",
    "the camera orbits slowly around the display, the necklace stays exactly the "
    "same, gentle light sweep across the stones, cinematic",
    "extremely slow macro push-in across the stones, facets catch and release the "
    "light, the piece stays exactly the same, shimmering detail",
    "slow gentle pull-back revealing the full set, warm bokeh drifts behind, the "
    "jewellery stays exactly the same, elegant cinematic reveal",
]


def main():
    common.load_env()
    jid, jd = common.new_job("jewel")
    common.log("job", f"{jid} -> {jd}")

    src = os.path.join(jd, "product.jpg")
    common.fetch_url(PRODUCT, src)

    # ---- STAGE 0: one real WaveSpeed brain call ---------------------------
    t0 = time.time()
    sb = brain.storyboard(
        BRIEF,
        {"lengthSec": 20, "aspectRatio": "9:16", "language": "hinglish",
         "brandName": "the collection", "captions": False, "template": "showcase"},
        [src], image_urls=[PRODUCT])
    brain_s = round(time.time() - t0, 1)

    scenes = sb["scenes"][:4]
    while len(scenes) < 4:
        scenes.append(json.loads(json.dumps(scenes[-1])))
    for i, sc in enumerate(scenes, 1):
        sc["n"] = i
        sc["durationSec"] = 5.0
        sc["transitionIn"] = "fade" if i == 1 else "cut"
    sb["scenes"] = scenes
    json.dump(sb, open(os.path.join(jd, "storyboard.json"), "w"),
              indent=2, ensure_ascii=False)
    print(json.dumps(sb, indent=2, ensure_ascii=False))

    # ---- STAGE 3: voiceover -- Zara, eleven_v3 -----------------------------
    t0 = time.time()
    vo = voiceover.voice_scenes(
        sb, {"language": "hinglish",
             "elevenVoiceId": voiceover.ZARA_SOCIAL}, jd)
    for v in vo:
        v["duration"] = 5.0
    vo_s = round(time.time() - t0, 1)

    # ---- STAGES 1+2 --------------------------------------------------------
    stills, clips, per_scene = [], [], []
    for i, shot in enumerate(SHOTS, 1):
        t0 = time.time()
        mr._free_comfy_vram()
        still = compose.edit_scene(src, PIN + shot["set"] + QUALITY,
                                   f"{jid}_s{i}", seed=4200 + i)
        stills.append(still)
        common.log("compose", f"scene {i}: {shot['k']}")
        clip = animate.wan_i2v(still, MOTION[i - 1],
                               os.path.join(jd, f"clip_{i}.mp4"),
                               f"{jid}_s{i}", duration=5.0)
        clips.append(clip)
        per_scene.append(round(time.time() - t0, 1))

    # ---- STAGE 4+5 ---------------------------------------------------------
    t0 = time.time()
    outs = assemble.assemble(clips, vo, sb, jd, jid, "9:16", False)
    as_s = round(time.time() - t0, 1)

    t0 = time.time()
    reel_url = mr._upload(outs["1080p"], "reels")
    still_urls = [mr._upload(s, "images", f"{jid}_s{i}.png")
                  for i, s in enumerate(stills, 1)]
    up_s = round(time.time() - t0, 1)

    res = {"job": jid, "reel_url": reel_url, "scene_image_urls": still_urls,
           "durationSec": outs["durationSec"], "concept": sb.get("concept"),
           "vo": [s.get("vo") for s in sb["scenes"]],
           "voice": "Zara (eleven_v3)",
           "_timings": {"brain": brain_s, "vo": vo_s, "scenes": per_scene,
                        "assemble": as_s, "upload": up_s}}
    json.dump(res, open(os.path.join(jd, "result.json"), "w"),
              indent=2, ensure_ascii=False)
    print("\n=== RESULT ===")
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
