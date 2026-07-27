#!/usr/bin/env python
"""
End-to-end pipeline test with the two EXTERNALLY BLOCKED steps stubbed out.

ONE thing cannot run on this box, and it is not a code problem:

  * Stage 0, the WaveSpeed brain - the account balance is $0.00, and a vision
    call costs $0.05, so every submit is rejected with "Insufficient credits".

EVERYTHING ELSE IS REAL, including the MinIO upload: compose (Qwen-Image-Edit),
the Qwen2.5-VL OCR guard, animate (Wan 2.2 i2v), the live ElevenLabs voiceover,
ffmpeg assembly, and the real PUT to staging-storage. So when the credits land,
the only untested link in the whole pipeline is one HTTP call.

The storyboard below is hand-written to the SAME schema the brain emits and is
pushed through brain.validate(), so it is rejected here for exactly the reasons
the real brain's output would be.

  /venv/main/bin/python e2e_local.py
"""
import json
import os
import sys
import time

sys.path.insert(0, "/workspace/reelkit")
import common                                              # noqa: E402
import brain                                               # noqa: E402
import make_reel as mr                                     # noqa: E402

# A real product photo with real printed text, hosted on the real MinIO endpoint -
# so the label-fidelity guard has something meaningful to check.
PRODUCT = "https://staging-storage.runkarobar.com/images/verify_t2i_pureglow.png"

STORYBOARD = {
    "concept": "A clean, wet-stone reveal that lets the pack do the talking.",
    "voice": "warm female Hinglish",
    "scenes": [
        {"n": 1, "goal": "reveal", "method": "edit_animate", "mode": "product",
         "visual": "the tube standing on wet dark slate, water beading on it",
         "background": "wet dark slate surface, cool morning light raking from the "
                       "left, soft blurred depth",
         "motion": "slow push-in", "energy": "fine rising steam",
         "transitionIn": "fade", "durationSec": 5, "motionEngine": "video",
         "kenburns": {"zoom": "in", "start": 1.0, "end": 1.12,
                      "xDrift": 0.0, "yDrift": -0.05, "rotateDeg": 0.0},
         "vo": "Subah ki freshness, har din."},
        {"n": 2, "goal": "detail", "method": "edit_animate", "mode": "product",
         "visual": "close on the pack, printed text crisp and readable",
         "background": "pale marble counter, warm sunlight, shallow depth",
         "motion": "slow orbit", "energy": "",
         "transitionIn": "cut", "durationSec": 5, "motionEngine": "video",
         "kenburns": {"zoom": "in", "start": 1.0, "end": 1.10,
                      "xDrift": 0.02, "yDrift": 0.0, "rotateDeg": 0.0},
         "vo": "Deep clean, har roz ke liye."},
        {"n": 3, "goal": "cta", "method": "edit_animate", "mode": "product",
         "visual": "the pack centred, light blooming behind it",
         "background": "soft neutral gradient surface, bright even light",
         "motion": "gentle crane down", "energy": "soft light bloom",
         "transitionIn": "fade", "durationSec": 5, "motionEngine": "video",
         "kenburns": {"zoom": "out", "start": 1.10, "end": 1.0,
                      "xDrift": 0.0, "yDrift": 0.03, "rotateDeg": 0.0},
         "vo": "Aaj hi try karein."},
    ],
    "notes": "Hand-written stand-in for the remote brain (account balance is $0).",
}


def main():
    common.load_env()
    length = 15.0

    # Same validator the real brain output goes through - no shortcut.
    sb = brain.validate(json.loads(json.dumps(STORYBOARD)), length)
    print(f"[stub] storyboard passed brain.validate(): {len(sb['scenes'])} scenes, "
          f"{sum(s['durationSec'] for s in sb['scenes']):.0f}s")

    brain.storyboard = lambda *a, **k: sb            # Stage 0 stub (no credits)

    t0 = time.time()
    res = mr.make_reel({
        "product_images": [PRODUCT],
        "brief": "15s premium skincare reel, warm female Hinglish voiceover",
        "config": {"lengthSec": 15, "aspectRatio": "9:16", "language": "hinglish",
                   "brandName": "Pure Glow", "captions": False,
                   "template": "showcase", "trace": True},
    })
    print(f"\n=== finished in {time.time() - t0:.1f}s")
    print(json.dumps({k: v for k, v in res.items() if k != "storyboard"},
                     indent=2)[:2500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
