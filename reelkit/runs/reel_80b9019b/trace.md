# Reel run trace — `reel_80b9019b`

Run directory: `/workspace/reelkit/runs/reel_80b9019b`

> Items marked **NOT PERSISTED** were never written to disk for this run. They are reported as gaps rather than reconstructed. Runs made after the tracer was wired in capture all of them.


## 1. Request

```json
{
  "product_images": [
    "https://staging-storage.runkarobar.com/videos/uploads/1785024038395-942338becf561e5f-Screenshot_2026-07-26_at_2.40.44___AM.jpg"
  ],
  "brief": "15s high-energy face-wash ad for Nivea Men Protect & Care Deep Cleaning Face Wash. Fresh, cool, water-splash mood — morning bathroom and post-gym freshness. Show the tube as the hero, highlight deep cleaning and aloe vera. Punchy male Hinglish voiceover, end on the brand.",
  "config": {
    "lengthSec": 15,
    "resolution": "1080p",
    "aspectRatio": "9:16",
    "language": "hinglish",
    "brandName": "Nivea Men",
    "elevenVoiceId": "",
    "captions": false,
    "template": "ai-director",
    "trace": true
  }
}
```

Product files on disk: `product_1.jpg`

Template: `ai-director`

## 2. Vision captions

**image 1** (verbatim (persisted by tracer)):

> This product is a face wash. It is from the brand NIVEA MEN and the specific product name is "PROTECT & CARE DEEP CLEANING FACE WASH". The packaging is a blue tube with a ribbed cap at the top. The text on the packaging reads:

NIVEA
MEN
PROTECT & CARE
DEEP CLEANING
FACE WASH
Thoroughly cleans
and refreshes
WITH ALOE VERA
100 ml


## 3. Brain prompt (exact string sent to the LLM)

Attempts until valid JSON: `1`

```text
===== SYSTEM =====
You are a senior creative director for short vertical product ads. You reply with a single JSON object and nothing else - no prose, no markdown fence.

===== USER =====
Write the storyboard for a vertical social ad.

BRIEF: 15s high-energy face-wash ad for Nivea Men Protect & Care Deep Cleaning Face Wash. Fresh, cool, water-splash mood — morning bathroom and post-gym freshness. Show the tube as the hero, highlight deep cleaning and aloe vera. Punchy male Hinglish voiceover, end on the brand.
BRAND: Nivea Men
LANGUAGE: hinglish
TOTAL LENGTH: 15 seconds
PRODUCT (what the supplied photographs actually show):
  - image 1: This product is a face wash. It is from the brand NIVEA MEN and the specific product name is "PROTECT & CARE DEEP CLEANING FACE WASH". The packaging is a blue tube with a ribbed cap at the top. The text on the packaging reads:

NIVEA
MEN
PROTECT & CARE
DEEP CLEANING
FACE WASH
Thoroughly cleans
and refreshes
WITH ALOE VERA
100 ml

Return EXACTLY this JSON shape:
{
  "concept": "<one-line creative concept>",
  "voice": "<voice direction, e.g. 'male energetic Hinglish'>",
  "scenes": [
    {
      "n": 1,
      "goal": "reveal|showcase|detail|wear|lifestyle|cta",
      "method": "edit_animate|compose_animate|generate_animate",
      "mode": "product|scene",
      "visual": "<the on-screen shot description>",
      "background": "<ONLY the setting/environment for this shot - the place, surface, light and mood. Never mention the product, clothing or any person.>",
      "motion": "<camera move, e.g. 'slow push-in', 'orbit', 'crane down'>",
      "energy": "<a visual effect such as 'water splash' or 'rising steam', or empty string for clean>",
      "transitionIn": "cut|fade|whip|zoom",
      "durationSec": 4,
      "motionEngine": "video",
      "kenburns": {"zoom": "in", "start": 1.0, "end": 1.12, "xDrift": 0.0, "yDrift": -0.05, "rotateDeg": 0.0},
      "vo": "<the spoken line for this scene, in hinglish>"
    }
  ],
  "notes": "<director rationale>"
}

HARD REQUIREMENTS
- 2 to 4 scenes. The scene durationSec values MUST sum to 15 (+/-1).
- Choose the method from what the SUPPLIED PHOTOGRAPHS actually show:
  * "edit_animate" + mode "product" - THE DEFAULT for product shots. The real photo
    is kept and its whole world is re-imagined around it, which gives a rich,
    filmic frame. Use it for clothing, anything worn or held, AND for packaged
    products you want to drop into a dramatic setting.
  * "compose_animate" + mode "product" - use ONLY if the caller demands a provably
    pixel-exact label. It pastes the cut-out onto a generated backdrop and looks
    noticeably flatter than an edit. Prefer edit_animate.
  * "generate_animate" + mode "scene" - ONLY for shots where NEITHER the product
    NOR anyone wearing/holding it is visible: an empty location, a texture, a
    detail of the surroundings. If a person appears wearing anything like the
    product, the model invents a DIFFERENT product and the ad shows the wrong
    item - so any shot featuring the product, or a person wearing it, MUST be
    edit_animate (or compose_animate for an isolated product).
  Compositing a photo that contains a PERSON produces two overlapping people, so
  never pick compose_animate for a model shot.
- At least one scene must be edit_animate or compose_animate. Final scene = cta.
- Scenes with goal "reveal", "showcase", "detail", "wear" or "cta" show the product,
  so they must NEVER use generate_animate.
- "vo" must be written in hinglish and be speakable in roughly its durationSec.
- CLAIMS: the voiceover may ONLY state benefits that are actually printed on the
  packaging as transcribed above. Do not invent or imply medical, dermatological or
  efficacy claims - no curing, removing or eliminating acne, pimples, spots,
  wrinkles, hair loss or any condition - unless those exact words appear on the
  product. If you are unsure whether a claim is printed, describe the product or the
  feeling instead. Wrong claims are a legal problem, not a style problem.
- "energy" is your free choice per scene - describe the effect in plain words, or
  leave it "" for a clean shot. Do not repeat the same energy in every scene.
- "motion" should vary between scenes; name a concrete camera move.
- "background" is used to build the scene BEHIND the product, so it must describe
  ONLY the environment: the place, the surface it sits on, the light and the mood.
  Never name the product, clothing, packaging or a person in "background" - if you
  do, the backdrop is generated containing a second copy of the product.
  Describe a CLOSE, shallow-depth product surface and its light - not a wide room.
  A wide interior puts furniture and fixtures in shot and dwarfs the product.
  Good: "wet dark stone surface, water droplets, cool morning light raking from
  the left, soft blurred background". Bad: "a bathroom with a window and a sink"
  (that renders the whole room, toilet included).
- For "generate_animate" scenes the "visual" must NOT mention the product, the
  garment or anyone wearing it - that shot is generated from nothing, so naming
  the product makes the model invent a DIFFERENT one and the ad shows the wrong
  item. Describe only surroundings, texture or atmosphere.
- "kenburns" gives the EXACT numbers for the camera move on product scenes, so the
  renderer applies them directly instead of guessing from your words:
    zoom   "in" or "out"
    start  starting zoom factor, 1.0 = no zoom (range 0.9-1.6)
    end    ending zoom factor   (range 0.9-1.6; use end<start for a pull-out)
    xDrift horizontal pan across the whole shot, fraction of width  (-0.2 to 0.2)
    yDrift vertical pan across the whole shot, fraction of height   (-0.2 to 0.2)
    rotateDeg total rotation across the shot in degrees (-12 to 12). Use this for
      any turning, tilting, orbiting or dutch-angle feel. 0 = no rotation.
  Make these match your "motion" wording and VARY THEM between scenes - do not
  make every scene a zoom. If your "motion" says orbit, turn, rotate, tilt or
  dutch angle, rotateDeg MUST be non-zero.
- "motionEngine" picks how the shot moves:
    "kenburns" - the still is scaled, panned and rotated. Fast, and the product
      stays pixel-perfect. Good for push-ins, pans, tilts and gentle turns.
    "video" - ALWAYS use this. Every scene must be a real animated shot.
  Do not use "kenburns"; a reel built from zooming stills looks cheap.
- "vo" lines must be long enough to actually SPEAK for their durationSec at a
  natural ad pace - roughly 2.5 words per second. A 4 second scene needs about
  10 words, not 4.
Return only the JSON object.

```

## 4. Storyboard returned

```json
{
  "concept": "High-energy morning and gym freshness with Nivea Men Protect & Care",
  "voice": "male energetic Hinglish",
  "scenes": [
    {
      "n": 1,
      "goal": "showcase",
      "method": "edit_animate",
      "mode": "product",
      "visual": "The blue tube of Nivea Men Protect & Care Deep Cleaning Face Wash with a ribbed cap on a wet dark stone surface. Water droplets glisten around it.",
      "background": "Wet dark stone surface, water droplets, cool morning light raking from the left, soft blurred background",
      "motion": "slow push-in",
      "energy": "water splash",
      "transitionIn": "zoom",
      "durationSec": 4.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "in",
        "start": 1.0,
        "end": 1.12,
        "xDrift": 0.0,
        "yDrift": -0.05,
        "rotateDeg": 0.0
      },
      "vo": "Start your day fresh! Thoroughly cleans & refreshes."
    },
    {
      "n": 2,
      "goal": "reveal",
      "method": "edit_animate",
      "mode": "product",
      "visual": "The Nivea Men face wash being applied to a hand in a bathroom with steam rising from the shower",
      "background": "Steam rises from the shower, bathroom foggy, cool morning light",
      "motion": "crane down",
      "energy": "rising steam",
      "transitionIn": "fade",
      "durationSec": 5.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "out",
        "start": 1.12,
        "end": 1.0,
        "xDrift": 0.0,
        "yDrift": 0.0,
        "rotateDeg": 0.0
      },
      "vo": "With Aloe Vera, soothes skin too!"
    },
    {
      "n": 3,
      "goal": "cta",
      "method": "edit_animate",
      "mode": "product",
      "visual": "Close-up of the blue tube against a blurred backdrop of water droplets and steam, Nivea Men logo clearly visible",
      "background": "Blurred backdrop of water droplets and steam, cool morning light",
      "motion": "tilt up",
      "energy": "",
      "transitionIn": "fade",
      "durationSec": 6.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "in",
        "start": 1.12,
        "end": 1.12,
        "xDrift": 0.0,
        "yDrift": -0.05,
        "rotateDeg": 4.0
      },
      "vo": "Nivea Men Protect & Care Deep Cleaning Face Wash. Feel fresh all day!"
    }
  ],
  "notes": "Show the product in a morning and gym context, highlighting freshness and deep cleaning properties. Voiceover emphasizes benefits mentioned on packaging."
}
```

## 5. Per scene


### Scene 1 — showcase / edit_animate / mode=product / engine=video

**compose**

```json
{
  "path": "edit_animate",
  "model": "Qwen-Image-Edit-2511-fp8mixed",
  "fast_lightning_4step": true,
  "seed": 501,
  "positive_prompt": "Keep the subject exactly as photographed - same face, same pose, same garment, same colours, same fabric and the same embroidered logo, unchanged. Change only the surroundings to: Wet dark stone surface, water droplets, cool morning light raking from the left, soft blurred background. Photorealistic editorial fashion photograph.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/reelkit/work/reel_80b9019b/product_1.jpg"
}
```
**guard**

```json
{
  "scene": 1,
  "pass": true,
  "detail": "source=['ALOE', 'CARE', 'CLEANING', 'DEEP', 'FACE', 'MEN', 'NIVEA', 'PROTECT', 'VERA', 'WASH', 'WITH'] composite=['ALOE', 'CARE', 'CLEANING', 'DEEP', 'FACE', 'MEN', 'NIVEA', 'PROTECT', 'VERA', 'WASH', 'WITH'] kept=100%",
  "retries": 0
}
```
**animate**

```json
{
  "engine": "wan",
  "path": "video_i2v",
  "motion_prompt_verbatim": "slow push-in",
  "energy_prompt_verbatim": "water splash",
  "full_prompt_sent": "slow push-in. The blue tube of Nivea Men Protect & Care Deep Cleaning Face Wash with a ribbed cap on a wet dark stone surface. Water droplets glisten around it.. water splash.",
  "input_still": "/workspace/reelkit/work/reel_80b9019b/scene_1.png",
  "requested_duration": 4.0,
  "clip_path": "/workspace/reelkit/work/reel_80b9019b/clip_1.mp4",
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
  "vo_text": "Start your day fresh! Thoroughly cleans & refreshes.",
  "voice_id": "IKne3meq5aSn9XLyUdCD",
  "model_id": "eleven_multilingual_v2",
  "mp3_path": "/workspace/reelkit/work/reel_80b9019b/audio/scene_1.mp3",
  "measured_duration": 4.0,
  "planned_duration": 4.0
}
```

### Scene 2 — reveal / edit_animate / mode=product / engine=video

**compose**

```json
{
  "path": "edit_animate",
  "model": "Qwen-Image-Edit-2511-fp8mixed",
  "fast_lightning_4step": true,
  "seed": 502,
  "positive_prompt": "Keep the subject exactly as photographed - same face, same pose, same garment, same colours, same fabric and the same embroidered logo, unchanged. Change only the surroundings to: Steam rises from the shower, bathroom foggy, cool morning light. Photorealistic editorial fashion photograph.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/reelkit/work/reel_80b9019b/product_1.jpg"
}
```
**guard**

```json
{
  "scene": 2,
  "pass": true,
  "detail": "source=['ALOE', 'CARE', 'CLEANING', 'DEEP', 'FACE', 'MEN', 'NIVEA', 'PROTECT', 'VERA', 'WASH', 'WITH'] composite=['ALOE', 'AND', 'CARE', 'CLEANING', 'CLEANS', 'DEEP', 'FACE', 'MEN', 'NIVEA', 'PROTECT', 'REFRESHES', 'THOROUGHLY', 'VERA', 'WASH', 'WITH'] kept=100%",
  "retries": 0
}
```
**animate**

```json
{
  "engine": "wan",
  "path": "video_i2v",
  "motion_prompt_verbatim": "crane down",
  "energy_prompt_verbatim": "rising steam",
  "full_prompt_sent": "crane down. The Nivea Men face wash being applied to a hand in a bathroom with steam rising from the shower. rising steam.",
  "input_still": "/workspace/reelkit/work/reel_80b9019b/scene_2.png",
  "requested_duration": 5.0,
  "clip_path": "/workspace/reelkit/work/reel_80b9019b/clip_2.mp4",
  "kenburns": {
    "zoom": "out",
    "start": 1.12,
    "end": 1.0,
    "xDrift": 0.0,
    "yDrift": 0.0,
    "rotateDeg": 0.0
  }
}
```
**voiceover**

```json
{
  "vo_text": "With Aloe Vera, soothes skin too!",
  "voice_id": "IKne3meq5aSn9XLyUdCD",
  "model_id": "eleven_multilingual_v2",
  "mp3_path": "/workspace/reelkit/work/reel_80b9019b/audio/scene_2.mp3",
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
  "seed": 503,
  "positive_prompt": "Keep the subject exactly as photographed - same face, same pose, same garment, same colours, same fabric and the same embroidered logo, unchanged. Change only the surroundings to: Blurred backdrop of water droplets and steam, cool morning light. Photorealistic editorial fashion photograph.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/reelkit/work/reel_80b9019b/product_1.jpg"
}
```
**guard**

```json
{
  "scene": 3,
  "pass": true,
  "detail": "source=['ALOE', 'CARE', 'CLEANING', 'DEEP', 'FACE', 'MEN', 'NIVEA', 'PROTECT', 'VERA', 'WASH', 'WITH'] composite=['ALOE', 'CARE', 'CLEANING', 'DEEP', 'FACE', 'MEN', 'NIVEA', 'PROTECT', 'VERA', 'WASH', 'WITH'] kept=100%",
  "retries": 0
}
```
**animate**

```json
{
  "engine": "wan",
  "path": "video_i2v",
  "motion_prompt_verbatim": "tilt up",
  "energy_prompt_verbatim": "",
  "full_prompt_sent": "tilt up. Close-up of the blue tube against a blurred backdrop of water droplets and steam, Nivea Men logo clearly visible.",
  "input_still": "/workspace/reelkit/work/reel_80b9019b/scene_3.png",
  "requested_duration": 6.0,
  "clip_path": "/workspace/reelkit/work/reel_80b9019b/clip_3.mp4",
  "kenburns": {
    "zoom": "in",
    "start": 1.12,
    "end": 1.12,
    "xDrift": 0.0,
    "yDrift": -0.05,
    "rotateDeg": 4.0
  }
}
```
**voiceover**

```json
{
  "vo_text": "Nivea Men Protect & Care Deep Cleaning Face Wash. Feel fresh all day!",
  "voice_id": "IKne3meq5aSn9XLyUdCD",
  "model_id": "eleven_multilingual_v2",
  "mp3_path": "/workspace/reelkit/work/reel_80b9019b/audio/scene_3.mp3",
  "measured_duration": 6.0,
  "planned_duration": 6.0
}
```

## 6. Assemble

```json
{
  "per_scene": [
    {
      "scene": 1,
      "fitted_duration": 4.0,
      "transition_in": "zoom",
      "dipped_through_black": false
    },
    {
      "scene": 2,
      "fitted_duration": 5.0,
      "transition_in": "fade",
      "dipped_through_black": true
    },
    {
      "scene": 3,
      "fitted_duration": 6.0,
      "transition_in": "fade",
      "dipped_through_black": true
    }
  ],
  "transition_fallbacks": [
    "scene 1: 'zoom' not implemented -> fade"
  ],
  "total_duration": 15.0,
  "master_resolution": "1080x1920",
  "captions_burned": false,
  "fps": 30,
  "outputs": {
    "1080p": "/workspace/reelkit/work/reel_80b9019b/reel_80b9019b_1080p.mp4"
  }
}
```

## 7. Upload

```json
{
  "reel_1080p_url": "https://staging-storage.runkarobar.com/reels/reel_80b9019b_1080p.mp4",
  "reel_720p_url": "",
  "scene_image_urls": [
    "https://staging-storage.runkarobar.com/images/reel_80b9019b_s1.png",
    "https://staging-storage.runkarobar.com/images/reel_80b9019b_s2.png",
    "https://staging-storage.runkarobar.com/images/reel_80b9019b_s3.png"
  ],
  "log": [
    "[upload] 4 files in 55.7s (parallel)"
  ]
}
```

## 8. Timings & model load order

```json
{
  "total_wall_clock_sec": 470.8,
  "per_stage": [
    {
      "stage": "brain",
      "seconds": 107.87
    },
    {
      "stage": "voiceover",
      "seconds": 3.9
    },
    {
      "stage": "scene_1",
      "seconds": 102.46
    },
    {
      "stage": "scene_2",
      "seconds": 96.98
    },
    {
      "stage": "scene_3",
      "seconds": 96.32
    },
    {
      "stage": "assemble",
      "seconds": 7.55
    },
    {
      "stage": "upload",
      "seconds": 55.72
    }
  ],
  "model_load_order": [
    {
      "model": "Qwen2.5-VL-7B (captions)",
      "action": "load",
      "t": 1.27
    },
    {
      "model": "Qwen2.5-14B-Instruct-FP8-dynamic",
      "action": "load",
      "t": 10.45
    },
    {
      "model": "brain LLM",
      "action": "unload",
      "t": 108.13
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 141.74
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 241.58
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 338.14
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
    "detail": "source=['ALOE', 'CARE', 'CLEANING', 'DEEP', 'FACE', 'MEN', 'NIVEA', 'PROTECT', 'VERA', 'WASH', 'WITH'] composite=['ALOE', 'CARE', 'CLEANING', 'DEEP', 'FACE', 'MEN', 'NIVEA', 'PROTECT', 'VERA', 'WASH', 'WITH'] kept=100%"
  },
  {
    "scene": 2,
    "ok": true,
    "detail": "source=['ALOE', 'CARE', 'CLEANING', 'DEEP', 'FACE', 'MEN', 'NIVEA', 'PROTECT', 'VERA', 'WASH', 'WITH'] composite=['ALOE', 'AND', 'CARE', 'CLEANING', 'CLEANS', 'DEEP', 'FACE', 'MEN', 'NIVEA', 'PROTECT', 'REFRESHES', 'THOROUGHLY', 'VERA', 'WASH', 'WITH'] kept=100%"
  },
  {
    "scene": 3,
    "ok": true,
    "detail": "source=['ALOE', 'CARE', 'CLEANING', 'DEEP', 'FACE', 'MEN', 'NIVEA', 'PROTECT', 'VERA', 'WASH', 'WITH'] composite=['ALOE', 'CARE', 'CLEANING', 'DEEP', 'FACE', 'MEN', 'NIVEA', 'PROTECT', 'VERA', 'WASH', 'WITH'] kept=100%"
  }
]
```
