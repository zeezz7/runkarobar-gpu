# Reel run trace — `reel_701eb62f`

Run directory: `/workspace/runkarobar-gpu/reelkit/runs/reel_701eb62f`

> Items marked **NOT PERSISTED** were never written to disk for this run. They are reported as gaps rather than reconstructed. Runs made after the tracer was wired in capture all of them.


## 1. Request

```json
{
  "product_images": [
    "https://staging-storage.runkarobar.com/videos/uploads/1785150296652-826672de130d6770-WhatsApp_Image_2026-07-27_at_4.32.11_PM.jpg"
  ],
  "brief": "15s punchy reel for this embroidered lawn suit",
  "config": {
    "lengthSec": 15,
    "resolution": "1080p",
    "aspectRatio": "9:16",
    "language": "hinglish",
    "brandName": "Test",
    "elevenVoiceId": "",
    "captions": true,
    "template": "ai-director",
    "trace": true
  }
}
```

Product files on disk: `product_1.jpg`

Template: `ai-director`

## 2. Vision captions

**image 1** (verbatim (persisted by tracer)):

> Stage 0 is a vision model now - no separate captioning pass. Images sent to the brain:
https://staging-storage.runkarobar.com/videos/uploads/1785150296652-826672de130d6770-WhatsApp_Image_2026-07-27_at_4.32.11_PM.jpg


## 3. Brain prompt (exact string sent to the LLM)

Attempts until valid JSON: `NOT PERSISTED`

```text
===== SYSTEM =====
You are a senior creative director for short vertical product ads. You reply with a single JSON object and nothing else - no prose, no markdown fence.

===== USER =====
Write the storyboard for a vertical social ad.

BRIEF: 15s punchy reel for this embroidered lawn suit
BRAND: Test
LANGUAGE: hinglish
TOTAL LENGTH: 15 seconds
PRODUCT: study the attached photograph(s). Read every word printed on the
packaging and treat that text as the only source of truth about the product -
the voiceover may claim nothing that is not printed there.

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
- LANGUAGE, restated because it overrides everything above: every "vo" line MUST be
  written in hinglish. If hinglish is "hinglish", write natural spoken Hinglish -
  Hindi sentence structure in Latin script, mixing in the English words an Indian ad
  would actually use (e.g. "Subah ki freshness, har din - deep clean, aloe vera ke
  saath"). Do NOT fall back to plain English. If hinglish is "hi" or "ur", write in
  that language. The claims rule above still applies, in that language.
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

===== IMAGES =====
https://staging-storage.runkarobar.com/videos/uploads/1785150296652-826672de130d6770-WhatsApp_Image_2026-07-27_at_4.32.11_PM.jpg
```

## 4. Storyboard returned

```json
{
  "concept": "Elegant emerald embroidery meets modern confidence",
  "voice": "female warm hinglish",
  "scenes": [
    {
      "n": 1,
      "goal": "reveal",
      "method": "edit_animate",
      "mode": "product",
      "visual": "Close-up on the intricate silver embroidery details on emerald green fabric",
      "background": "soft golden hour lighting on textured marble surface, warm ambient glow with shallow depth",
      "motion": "slow push-in",
      "energy": "golden light particles",
      "transitionIn": "fade",
      "durationSec": 4.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "in",
        "start": 1.0,
        "end": 1.15,
        "xDrift": 0.0,
        "yDrift": -0.03,
        "rotateDeg": 0.0
      },
      "vo": "Dekho kya beautiful embroidery hai - har thread mein elegance"
    },
    {
      "n": 2,
      "goal": "wear",
      "method": "edit_animate",
      "mode": "product",
      "visual": "Model confidently walking and posing in the complete embroidered lawn suit with dupatta",
      "background": "urban architectural backdrop with warm afternoon light, blurred city buildings creating depth",
      "motion": "gentle orbit",
      "energy": "soft fabric flutter",
      "transitionIn": "whip",
      "durationSec": 5.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "in",
        "start": 1.12,
        "end": 1.12,
        "xDrift": 0.05,
        "yDrift": 0.0,
        "rotateDeg": 3.0
      },
      "vo": "Lawn ki comfort aur embroidery ki luxury - perfect combination for special occasions"
    },
    {
      "n": 3,
      "goal": "showcase",
      "method": "edit_animate",
      "mode": "product",
      "visual": "Full suit display showing the complete three-piece set with coordinated dupatta",
      "background": "pristine white marble platform with dramatic side lighting, minimalist luxury setting",
      "motion": "crane down",
      "energy": "",
      "transitionIn": "zoom",
      "durationSec": 3.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "in",
        "start": 1.12,
        "end": 1.12,
        "xDrift": -0.02,
        "yDrift": 0.05,
        "rotateDeg": -1.5
      },
      "vo": "Complete three piece lawn suit - ab tumhara style statement ready hai"
    },
    {
      "n": 4,
      "goal": "cta",
      "method": "edit_animate",
      "mode": "product",
      "visual": "Model's confident smile and final pose showcasing the outfit's elegance",
      "background": "soft bokeh lights with warm golden tones, elegant evening atmosphere",
      "motion": "slow push-in",
      "energy": "sparkle highlights",
      "transitionIn": "fade",
      "durationSec": 3.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "in",
        "start": 1.0,
        "end": 1.12,
        "xDrift": 0.0,
        "yDrift": -0.04,
        "rotateDeg": 0.0
      },
      "vo": "Test brand se - order karo aur feel karo luxury embroidery"
    }
  ],
  "notes": "Showcases the intricate embroidery work and lawn fabric comfort through progressive reveals, ending with brand recall and purchase motivation. Each scene builds elegance while highlighting different aspects of the three-piece suit."
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
  "seed": 2116,
  "positive_prompt": "Keep the subject exactly as photographed - same face, same pose, same garment, same colours, same fabric and the same embroidered logo, unchanged. Change only the surroundings to: soft golden hour lighting on textured marble surface, warm ambient glow with shallow depth. Photorealistic editorial fashion photograph.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/runkarobar-gpu/reelkit/work/reel_701eb62f/product_1.jpg"
}
```
**guard**

```json
{
  "scene": 1,
  "pass": true,
  "detail": "source had no readable label text - guard skipped",
  "retries": 0
}
```
**animate**

```json
{
  "engine": "wan",
  "path": "video_i2v",
  "motion_prompt_verbatim": "slow push-in",
  "energy_prompt_verbatim": "golden light particles",
  "full_prompt_sent": "slow push-in. Close-up on the intricate silver embroidery details on emerald green fabric. golden light particles.",
  "input_still": "/workspace/runkarobar-gpu/reelkit/work/reel_701eb62f/scene_1.png",
  "requested_duration": 4.612,
  "clip_path": "/workspace/runkarobar-gpu/reelkit/work/reel_701eb62f/clip_1.mp4",
  "kenburns": {
    "zoom": "in",
    "start": 1.0,
    "end": 1.15,
    "xDrift": 0.0,
    "yDrift": -0.03,
    "rotateDeg": 0.0
  }
}
```
**voiceover**

```json
{
  "vo_text": "Dekho kya beautiful embroidery hai - har thread mein elegance",
  "voice_id": "RAPmAZHXSuTrzY9pjpR3",
  "model_id": "eleven_v3",
  "mp3_path": "/workspace/runkarobar-gpu/reelkit/work/reel_701eb62f/audio/scene_1.mp3",
  "measured_duration": 4.612,
  "planned_duration": 4.0
}
```

### Scene 2 — wear / edit_animate / mode=product / engine=video

**compose**

```json
{
  "path": "edit_animate",
  "model": "Qwen-Image-Edit-2511-fp8mixed",
  "fast_lightning_4step": true,
  "seed": 2117,
  "positive_prompt": "Keep the subject exactly as photographed - same face, same pose, same garment, same colours, same fabric and the same embroidered logo, unchanged. Change only the surroundings to: urban architectural backdrop with warm afternoon light, blurred city buildings creating depth. Photorealistic editorial fashion photograph.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/runkarobar-gpu/reelkit/work/reel_701eb62f/product_1.jpg"
}
```
**guard**

```json
{
  "scene": 2,
  "pass": true,
  "detail": "source had no readable label text - guard skipped",
  "retries": 0
}
```
**animate**

```json
{
  "engine": "wan",
  "path": "video_i2v",
  "motion_prompt_verbatim": "gentle orbit",
  "energy_prompt_verbatim": "soft fabric flutter",
  "full_prompt_sent": "gentle orbit. Model confidently walking and posing in the complete embroidered lawn suit with dupatta. soft fabric flutter.",
  "input_still": "/workspace/runkarobar-gpu/reelkit/work/reel_701eb62f/scene_2.png",
  "requested_duration": 6.049,
  "clip_path": "/workspace/runkarobar-gpu/reelkit/work/reel_701eb62f/clip_2.mp4",
  "kenburns": {
    "zoom": "in",
    "start": 1.12,
    "end": 1.12,
    "xDrift": 0.05,
    "yDrift": 0.0,
    "rotateDeg": 3.0
  }
}
```
**voiceover**

```json
{
  "vo_text": "Lawn ki comfort aur embroidery ki luxury - perfect combination for special occasions",
  "voice_id": "RAPmAZHXSuTrzY9pjpR3",
  "model_id": "eleven_v3",
  "mp3_path": "/workspace/runkarobar-gpu/reelkit/work/reel_701eb62f/audio/scene_2.mp3",
  "measured_duration": 6.049,
  "planned_duration": 5.0
}
```

### Scene 3 — showcase / edit_animate / mode=product / engine=video

**compose**

```json
{
  "path": "edit_animate",
  "model": "Qwen-Image-Edit-2511-fp8mixed",
  "fast_lightning_4step": true,
  "seed": 2118,
  "positive_prompt": "Keep the subject exactly as photographed - same face, same pose, same garment, same colours, same fabric and the same embroidered logo, unchanged. Change only the surroundings to: pristine white marble platform with dramatic side lighting, minimalist luxury setting. Photorealistic editorial fashion photograph.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/runkarobar-gpu/reelkit/work/reel_701eb62f/product_1.jpg"
}
```
**guard**

```json
{
  "scene": 3,
  "pass": true,
  "detail": "source had no readable label text - guard skipped",
  "retries": 0
}
```
**animate**

```json
{
  "engine": "wan",
  "path": "video_i2v",
  "motion_prompt_verbatim": "crane down",
  "energy_prompt_verbatim": "",
  "full_prompt_sent": "crane down. Full suit display showing the complete three-piece set with coordinated dupatta.",
  "input_still": "/workspace/runkarobar-gpu/reelkit/work/reel_701eb62f/scene_3.png",
  "requested_duration": 4.534,
  "clip_path": "/workspace/runkarobar-gpu/reelkit/work/reel_701eb62f/clip_3.mp4",
  "kenburns": {
    "zoom": "in",
    "start": 1.12,
    "end": 1.12,
    "xDrift": -0.02,
    "yDrift": 0.05,
    "rotateDeg": -1.5
  }
}
```
**voiceover**

```json
{
  "vo_text": "Complete three piece lawn suit - ab tumhara style statement ready hai",
  "voice_id": "RAPmAZHXSuTrzY9pjpR3",
  "model_id": "eleven_v3",
  "mp3_path": "/workspace/runkarobar-gpu/reelkit/work/reel_701eb62f/audio/scene_3.mp3",
  "measured_duration": 4.534,
  "planned_duration": 3.0
}
```

### Scene 4 — cta / edit_animate / mode=product / engine=video

**compose**

```json
{
  "path": "edit_animate",
  "model": "Qwen-Image-Edit-2511-fp8mixed",
  "fast_lightning_4step": true,
  "seed": 2119,
  "positive_prompt": "Keep the subject exactly as photographed - same face, same pose, same garment, same colours, same fabric and the same embroidered logo, unchanged. Change only the surroundings to: soft bokeh lights with warm golden tones, elegant evening atmosphere. Photorealistic editorial fashion photograph.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/runkarobar-gpu/reelkit/work/reel_701eb62f/product_1.jpg"
}
```
**guard**

```json
{
  "scene": 4,
  "pass": true,
  "detail": "source had no readable label text - guard skipped",
  "retries": 0
}
```
**animate**

```json
{
  "engine": "wan",
  "path": "video_i2v",
  "motion_prompt_verbatim": "slow push-in",
  "energy_prompt_verbatim": "sparkle highlights",
  "full_prompt_sent": "slow push-in. Model's confident smile and final pose showcasing the outfit's elegance. sparkle highlights.",
  "input_still": "/workspace/runkarobar-gpu/reelkit/work/reel_701eb62f/scene_4.png",
  "requested_duration": 4.769,
  "clip_path": "/workspace/runkarobar-gpu/reelkit/work/reel_701eb62f/clip_4.mp4",
  "kenburns": {
    "zoom": "in",
    "start": 1.0,
    "end": 1.12,
    "xDrift": 0.0,
    "yDrift": -0.04,
    "rotateDeg": 0.0
  }
}
```
**voiceover**

```json
{
  "vo_text": "Test brand se - order karo aur feel karo luxury embroidery",
  "voice_id": "RAPmAZHXSuTrzY9pjpR3",
  "model_id": "eleven_v3",
  "mp3_path": "/workspace/runkarobar-gpu/reelkit/work/reel_701eb62f/audio/scene_4.mp3",
  "measured_duration": 4.769,
  "planned_duration": 3.0
}
```

## 6. Assemble

```json
{
  "per_scene": [
    {
      "scene": 1,
      "fitted_duration": 4.612,
      "transition_in": "fade",
      "dipped_through_black": false
    },
    {
      "scene": 2,
      "fitted_duration": 6.049,
      "transition_in": "whip",
      "dipped_through_black": true
    },
    {
      "scene": 3,
      "fitted_duration": 4.534,
      "transition_in": "zoom",
      "dipped_through_black": true
    },
    {
      "scene": 4,
      "fitted_duration": 4.769,
      "transition_in": "fade",
      "dipped_through_black": true
    }
  ],
  "transition_fallbacks": [
    "scene 2: 'whip' not implemented -> fade",
    "scene 3: 'zoom' not implemented -> fade"
  ],
  "total_duration": 19.93,
  "master_resolution": "1080x1920",
  "captions_burned": true,
  "fps": 30,
  "outputs": {
    "1080p": "/workspace/runkarobar-gpu/reelkit/work/reel_701eb62f/reel_701eb62f_1080p.mp4"
  }
}
```

## 7. Upload

```json
{
  "reel_1080p_url": "https://staging-storage.runkarobar.com/reels/reel_701eb62f_1080p.mp4",
  "reel_720p_url": "",
  "scene_image_urls": [
    "https://staging-storage.runkarobar.com/images/reel_701eb62f_s1.png",
    "https://staging-storage.runkarobar.com/images/reel_701eb62f_s2.png",
    "https://staging-storage.runkarobar.com/images/reel_701eb62f_s3.png",
    "https://staging-storage.runkarobar.com/images/reel_701eb62f_s4.png"
  ],
  "log": "NOT PERSISTED"
}
```

## 8. Timings & model load order

```json
{
  "total_wall_clock_sec": 995.93,
  "per_stage": [
    {
      "stage": "brain",
      "seconds": 17.4
    },
    {
      "stage": "voiceover",
      "seconds": 11.47
    },
    {
      "stage": "scene_1",
      "seconds": 63.77
    },
    {
      "stage": "scene_2",
      "seconds": 46.1
    },
    {
      "stage": "scene_3",
      "seconds": 45.5
    },
    {
      "stage": "scene_4",
      "seconds": 45.92
    },
    {
      "stage": "assemble",
      "seconds": 292.6
    },
    {
      "stage": "upload",
      "seconds": 473.17
    }
  ],
  "model_load_order": [
    {
      "model": "wavespeed:anthropic/claude-sonnet-4",
      "action": "remote",
      "t": 1.59
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 59.48
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 111.69
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 157.15
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 203.1
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
    "detail": "source had no readable label text - guard skipped"
  },
  {
    "scene": 2,
    "ok": true,
    "detail": "source had no readable label text - guard skipped"
  },
  {
    "scene": 3,
    "ok": true,
    "detail": "source had no readable label text - guard skipped"
  },
  {
    "scene": 4,
    "ok": true,
    "detail": "source had no readable label text - guard skipped"
  }
]
```
