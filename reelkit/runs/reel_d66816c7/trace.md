# Reel run trace — `reel_d66816c7`

Run directory: `/workspace/reelkit/runs/reel_d66816c7`

> Items marked **NOT PERSISTED** were never written to disk for this run. They are reported as gaps rather than reconstructed. Runs made after the tracer was wired in capture all of them.


## 1. Request

```json
{
  "product_images": [
    "https://staging-storage.runkarobar.com/images/verify_t2i_pureglow.png"
  ],
  "brief": "15s premium skincare reel, warm female Hinglish voiceover",
  "config": {
    "lengthSec": 15,
    "resolution": "1080p",
    "aspectRatio": "9:16",
    "language": "hinglish",
    "brandName": "Pure Glow",
    "elevenVoiceId": "",
    "captions": false,
    "template": "showcase",
    "trace": true
  }
}
```

Product files on disk: `product_1.png`

Template: `showcase`

## 2. Vision captions

NOT PERSISTED

## 3. Brain prompt (exact string sent to the LLM)

Attempts until valid JSON: `NOT PERSISTED`

**NOT PERSISTED** — the assembled prompt string was not saved for this run.

## 4. Storyboard returned

```json
{
  "concept": "A clean, wet-stone reveal that lets the pack do the talking.",
  "voice": "warm female Hinglish",
  "scenes": [
    {
      "n": 1,
      "goal": "reveal",
      "method": "edit_animate",
      "mode": "product",
      "visual": "the tube standing on wet dark slate, water beading on it",
      "background": "wet dark slate surface, cool morning light raking from the left, soft blurred depth",
      "motion": "slow push-in",
      "energy": "fine rising steam",
      "transitionIn": "fade",
      "durationSec": 5.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "in",
        "start": 1.0,
        "end": 1.12,
        "xDrift": 0.0,
        "yDrift": -0.05,
        "rotateDeg": 0.0
      },
      "vo": "Subah ki freshness, har din."
    },
    {
      "n": 2,
      "goal": "detail",
      "method": "edit_animate",
      "mode": "product",
      "visual": "close on the pack, printed text crisp and readable",
      "background": "pale marble counter, warm sunlight, shallow depth",
      "motion": "slow orbit",
      "energy": "",
      "transitionIn": "cut",
      "durationSec": 5.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "in",
        "start": 1.0,
        "end": 1.1,
        "xDrift": 0.02,
        "yDrift": 0.0,
        "rotateDeg": 0.0
      },
      "vo": "Deep clean, har roz ke liye."
    },
    {
      "n": 3,
      "goal": "cta",
      "method": "edit_animate",
      "mode": "product",
      "visual": "the pack centred, light blooming behind it",
      "background": "soft neutral gradient surface, bright even light",
      "motion": "gentle crane down",
      "energy": "soft light bloom",
      "transitionIn": "fade",
      "durationSec": 5.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "out",
        "start": 1.1,
        "end": 1.0,
        "xDrift": 0.0,
        "yDrift": 0.03,
        "rotateDeg": 0.0
      },
      "vo": "Aaj hi try karein."
    }
  ],
  "notes": "Hand-written stand-in for the remote brain (account balance is $0)."
}
```

## 5. Per scene


### Scene 1 — reveal / edit_animate / mode=product / engine=video

**compose**

```json
{
  "path": "edit_animate",
  "model": "Qwen-Image-Edit-2511-fp8mixed",
  "fast_lightning_4step": true,
  "seed": 117,
  "positive_prompt": "Keep the subject exactly as photographed - same face, same pose, same garment, same colours, same fabric and the same embroidered logo, unchanged. Change only the surroundings to: wet dark slate surface, cool morning light raking from the left, soft blurred depth. Photorealistic editorial fashion photograph.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/reelkit/work/reel_d66816c7/product_1.png"
}
```
**guard**

```json
{
  "scene": 1,
  "pass": true,
  "detail": "only 2 token(s) readable on the source (['GLOW', 'PURE']) - too weak to diff, guard skipped",
  "retries": 0
}
```
**animate**

```json
{
  "engine": "wan",
  "path": "video_i2v",
  "motion_prompt_verbatim": "slow push-in",
  "energy_prompt_verbatim": "fine rising steam",
  "full_prompt_sent": "slow push-in. the tube standing on wet dark slate, water beading on it. fine rising steam.",
  "input_still": "/workspace/reelkit/work/reel_d66816c7/scene_1.png",
  "requested_duration": 5.0,
  "clip_path": "/workspace/reelkit/work/reel_d66816c7/clip_1.mp4",
  "kenburns": {
    "zoom": "in",
    "start": 1.0,
    "end": 1.12,
    "xDrift": 0.0,
    "yDrift": -0.05,
    "rotateDeg": 0.0
  }
}
```
**voiceover**

```json
{
  "vo_text": "Subah ki freshness, har din.",
  "voice_id": "IKne3meq5aSn9XLyUdCD",
  "model_id": "eleven_multilingual_v2",
  "mp3_path": "/workspace/reelkit/work/reel_d66816c7/audio/scene_1.mp3",
  "measured_duration": 5.0,
  "planned_duration": 5.0
}
```

### Scene 2 — detail / edit_animate / mode=product / engine=video

**compose**

```json
{
  "path": "edit_animate",
  "model": "Qwen-Image-Edit-2511-fp8mixed",
  "fast_lightning_4step": true,
  "seed": 118,
  "positive_prompt": "Keep the subject exactly as photographed - same face, same pose, same garment, same colours, same fabric and the same embroidered logo, unchanged. Change only the surroundings to: pale marble counter, warm sunlight, shallow depth. Photorealistic editorial fashion photograph.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/reelkit/work/reel_d66816c7/product_1.png"
}
```
**guard**

```json
{
  "scene": 2,
  "pass": true,
  "detail": "only 2 token(s) readable on the source (['GLOW', 'PURE']) - too weak to diff, guard skipped",
  "retries": 0
}
```
**animate**

```json
{
  "engine": "wan",
  "path": "video_i2v",
  "motion_prompt_verbatim": "slow orbit",
  "energy_prompt_verbatim": "",
  "full_prompt_sent": "slow orbit. close on the pack, printed text crisp and readable.",
  "input_still": "/workspace/reelkit/work/reel_d66816c7/scene_2.png",
  "requested_duration": 5.0,
  "clip_path": "/workspace/reelkit/work/reel_d66816c7/clip_2.mp4",
  "kenburns": {
    "zoom": "in",
    "start": 1.0,
    "end": 1.1,
    "xDrift": 0.02,
    "yDrift": 0.0,
    "rotateDeg": 0.0
  }
}
```
**voiceover**

```json
{
  "vo_text": "Deep clean, har roz ke liye.",
  "voice_id": "IKne3meq5aSn9XLyUdCD",
  "model_id": "eleven_multilingual_v2",
  "mp3_path": "/workspace/reelkit/work/reel_d66816c7/audio/scene_2.mp3",
  "measured_duration": 5.0,
  "planned_duration": 5.0
}
```

### Scene 3 — cta / edit_animate / mode=product / engine=video

**compose**

```json
{
  "path": "edit_animate",
  "model": "Qwen-Image-Edit-2511-fp8mixed",
  "fast_lightning_4step": true,
  "seed": 119,
  "positive_prompt": "Keep the subject exactly as photographed - same face, same pose, same garment, same colours, same fabric and the same embroidered logo, unchanged. Change only the surroundings to: soft neutral gradient surface, bright even light. Photorealistic editorial fashion photograph.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/reelkit/work/reel_d66816c7/product_1.png"
}
```
**guard**

```json
{
  "scene": 3,
  "pass": true,
  "detail": "only 2 token(s) readable on the source (['GLOW', 'PURE']) - too weak to diff, guard skipped",
  "retries": 0
}
```
**animate**

```json
{
  "engine": "wan",
  "path": "video_i2v",
  "motion_prompt_verbatim": "gentle crane down",
  "energy_prompt_verbatim": "soft light bloom",
  "full_prompt_sent": "gentle crane down. the pack centred, light blooming behind it. soft light bloom.",
  "input_still": "/workspace/reelkit/work/reel_d66816c7/scene_3.png",
  "requested_duration": 5.0,
  "clip_path": "/workspace/reelkit/work/reel_d66816c7/clip_3.mp4",
  "kenburns": {
    "zoom": "out",
    "start": 1.1,
    "end": 1.0,
    "xDrift": 0.0,
    "yDrift": 0.03,
    "rotateDeg": 0.0
  }
}
```
**voiceover**

```json
{
  "vo_text": "Aaj hi try karein.",
  "voice_id": "IKne3meq5aSn9XLyUdCD",
  "model_id": "eleven_multilingual_v2",
  "mp3_path": "/workspace/reelkit/work/reel_d66816c7/audio/scene_3.mp3",
  "measured_duration": 5.0,
  "planned_duration": 5.0
}
```

## 6. Assemble

```json
{
  "per_scene": [
    {
      "scene": 1,
      "fitted_duration": 5.0,
      "transition_in": "fade",
      "dipped_through_black": false
    },
    {
      "scene": 2,
      "fitted_duration": 5.0,
      "transition_in": "cut",
      "dipped_through_black": false
    },
    {
      "scene": 3,
      "fitted_duration": 5.0,
      "transition_in": "fade",
      "dipped_through_black": true
    }
  ],
  "transition_fallbacks": [],
  "total_duration": 15.0,
  "master_resolution": "1080x1920",
  "captions_burned": false,
  "fps": 30,
  "outputs": {
    "1080p": "/workspace/reelkit/work/reel_d66816c7/reel_d66816c7_1080p.mp4"
  }
}
```

## 7. Upload

```json
{
  "reel_1080p_url": "https://staging-storage.runkarobar.com/reels/reel_d66816c7_1080p.mp4",
  "reel_720p_url": "",
  "scene_image_urls": [
    "https://staging-storage.runkarobar.com/images/reel_d66816c7_s1.png",
    "https://staging-storage.runkarobar.com/images/reel_d66816c7_s2.png",
    "https://staging-storage.runkarobar.com/images/reel_d66816c7_s3.png"
  ],
  "log": "NOT PERSISTED"
}
```

## 8. Timings & model load order

```json
{
  "total_wall_clock_sec": 333.86,
  "per_stage": [
    {
      "stage": "brain",
      "seconds": 2.48
    },
    {
      "stage": "voiceover",
      "seconds": 2.75
    },
    {
      "stage": "scene_1",
      "seconds": 57.83
    },
    {
      "stage": "scene_2",
      "seconds": 51.32
    },
    {
      "stage": "scene_3",
      "seconds": 48.4
    },
    {
      "stage": "assemble",
      "seconds": 8.56
    },
    {
      "stage": "upload",
      "seconds": 162.5
    }
  ],
  "model_load_order": [
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 29.92
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 84.33
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 132.73
    }
  ]
}
```

## Guard summary

```json
[
  {
    "scene": 1,
    "ok": true,
    "detail": "only 2 token(s) readable on the source (['GLOW', 'PURE']) - too weak to diff, guard skipped"
  },
  {
    "scene": 2,
    "ok": true,
    "detail": "only 2 token(s) readable on the source (['GLOW', 'PURE']) - too weak to diff, guard skipped"
  },
  {
    "scene": 3,
    "ok": true,
    "detail": "only 2 token(s) readable on the source (['GLOW', 'PURE']) - too weak to diff, guard skipped"
  }
]
```
