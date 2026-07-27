# Reel run trace — `reel_15daf8c8`

Run directory: `/workspace/runkarobar-gpu/reelkit/runs/reel_15daf8c8`

> Items marked **NOT PERSISTED** were never written to disk for this run. They are reported as gaps rather than reconstructed. Runs made after the tracer was wired in capture all of them.


## 1. Request

```json
{
  "product_images": [
    "https://staging-storage.runkarobar.com/videos/uploads/1785150296652-826672de130d6770-WhatsApp_Image_2026-07-27_at_4.32.11_PM.jpg"
  ],
  "brief": "Premium reel for this embroidered lawn suit - aspirational, scroll-stopping, warm female Hinglish voiceover.",
  "config": {
    "lengthSec": 20,
    "resolution": "1080p",
    "aspectRatio": "9:16",
    "language": "hinglish",
    "brandName": "The Collection",
    "elevenVoiceId": "",
    "captions": false,
    "template": "testimonial",
    "trace": true
  }
}
```

Product files on disk: `product_1.jpg`

Template: `testimonial`

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

BRIEF: Premium reel for this embroidered lawn suit - aspirational, scroll-stopping, warm female Hinglish voiceover.
BRAND: The Collection
LANGUAGE: hinglish
TOTAL LENGTH: 20 seconds
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
      "method": "edit_animate|compose_animate|generate_animate|lipsync",
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
  "badges": [{"text": "<short on-screen badge, max 16 chars>", "color": "#RRGGBB"}],
  "notes": "<director rationale>"
}

HARD REQUIREMENTS
- 3 to 5 scenes. The scene durationSec values MUST sum to 20 (+/-1).
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
  * "lipsync" + mode "scene" - a PRESENTER speaks straight to camera. Only use it
    when the STYLE DIRECTIVE below asks for it; it is rendered by a remote
    talking-avatar model and costs real money per scene, so never add it
    uninvited. Its "vo" is the exact words the presenter says, and its "visual"
    must describe a person facing camera with an unobstructed face.
  Compositing a photo that contains a PERSON produces two overlapping people, so
  never pick compose_animate for a model shot.
- At least one scene must be edit_animate or compose_animate. Final scene = cta.
- Scenes with goal "reveal", "showcase", "detail", "wear" or "cta" show the product,
  so they must NEVER use generate_animate.
- "vo" must be written in hinglish and MUST fit its durationSec when spoken.
  Budget about 2.2 words per second and stay UNDER it - e.g. a 5s scene gets at
  most ~11 words, a 6s scene ~13. A line that overruns forces the clip to be
  stretched to cover it, which visibly degrades the shot. Short and punchy beats
  complete sentences.
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
- "badges" are short on-screen text chips burned over the reel (a price, an offer,
  a one-word benefit). Return an EMPTY array unless the STYLE DIRECTIVE asks for
  them. Max 6, each at most 16 characters, colour as #RRGGBB or omitted.
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

STYLE DIRECTIVE (template: testimonial):
Authentic UGC testimonial. ONE real-feeling person talks straight to camera about the product like a friend's recommendation - warm, honest, specific, a little imperfect. Not a polished ad read. EVERY scene is that person talking to camera: use method 'edit_animate' with mode 'scene', and write each vo as the exact words they say. The same person throughout. Cut away only if a scene genuinely needs to show the product detail they are describing.
Follow these unless the brief says otherwise:
  - aim for about 3 scenes (stay within 3-5)
  - end on an explicit call to action in the final scene's vo
  - write the vo as first-person speech from a person on camera, as if they are speaking the line themselves
The brief always outranks this directive. You still choose the scene count, methods, energy, motion and wording yourself.

===== IMAGES =====
https://staging-storage.runkarobar.com/videos/uploads/1785150296652-826672de130d6770-WhatsApp_Image_2026-07-27_at_4.32.11_PM.jpg
```

## 4. Storyboard returned

```json
{
  "concept": "Friend's authentic recommendation for premium embroidered lawn suit",
  "voice": "warm female Hinglish",
  "scenes": [
    {
      "n": 1,
      "goal": "wear",
      "method": "edit_animate",
      "mode": "scene",
      "visual": "Young woman in green embroidered lawn suit speaking warmly to camera with genuine smile",
      "background": "Urban street scene with classic architecture, soft golden hour lighting, blurred city backdrop",
      "motion": "slow push-in",
      "energy": "gentle breeze effect",
      "transitionIn": "cut",
      "durationSec": 7.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "in",
        "start": 1.0,
        "end": 1.15,
        "xDrift": 0.0,
        "yDrift": 0.0,
        "rotateDeg": 0.0
      },
      "vo": "Yaar, The Collection ka yeh embroidered lawn suit dekho - kitna beautiful hai na! Main toh completely in love hun iske saath."
    },
    {
      "n": 2,
      "goal": "showcase",
      "method": "edit_animate",
      "mode": "scene",
      "visual": "Same woman gesturing toward the intricate embroidery details on her suit, touching the fabric lovingly",
      "background": "Urban street scene with classic architecture, soft golden hour lighting, blurred city backdrop",
      "motion": "gentle tilt down",
      "energy": "soft fabric shimmer",
      "transitionIn": "cut",
      "durationSec": 6.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "in",
        "start": 1.12,
        "end": 1.2,
        "xDrift": 0.05,
        "yDrift": 0.1,
        "rotateDeg": 2.0
      },
      "vo": "Dekho kitna premium quality hai - embroidery toh ekdum perfect hai aur fabric bhi so comfortable."
    },
    {
      "n": 3,
      "goal": "cta",
      "method": "edit_animate",
      "mode": "scene",
      "visual": "Woman looking directly at camera with confident smile, holding dupatta naturally",
      "background": "Urban street scene with classic architecture, soft golden hour lighting, blurred city backdrop",
      "motion": "slight orbit",
      "energy": "",
      "transitionIn": "fade",
      "durationSec": 7.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "out",
        "start": 1.2,
        "end": 1.12,
        "xDrift": -0.03,
        "yDrift": 0.0,
        "rotateDeg": -1.5
      },
      "vo": "Trust me girls, The Collection mein jaake definitely try karna - you'll love it! Main toh already next piece order kar chuki hun."
    }
  ],
  "badges": [],
  "notes": "Authentic testimonial feel with natural gestures and genuine enthusiasm. Focuses on the premium embroidered lawn suit quality while maintaining conversational Hinglish tone throughout."
}
```

## 5. Per scene


### Scene 1 — wear / edit_animate / mode=scene / engine=video

**compose**

```json
{
  "path": "edit_animate",
  "model": "Qwen-Image-Edit-2511-fp8mixed",
  "fast_lightning_4step": true,
  "seed": 862,
  "positive_prompt": "Keep the subject exactly as photographed - same face, same garment, same colours, same fabric and the same printed branding, unchanged. Change only the surroundings to: Urban street scene with classic architecture, soft golden hour lighting, blurred city backdrop. The model WEARS the complete outfit, with any dupatta or scarf draped naturally on the body. Show ONLY the person wearing it - absolutely no clothing rack, coat stand, hanger, mannequin or separately-displayed garment anywhere in the frame. CRITICAL: every garment piece keeps its OWN exact colour from the reference - never recolour, tint or harmonise one piece to match another (e.g. if the trousers are black and the dupatta is purple, the trousers stay black and the dupatta stays purple). STRICT: the person must be fully and MODESTLY dressed at all times - absolutely no nudity, no cleavage, no bare shoulders, midriff or legs, and no revealing, tight, sheer or sexy clothing. Keep it decent, elegant and family-friendly. The presenter faces the camera directly with a clear, well-lit, UNOBSTRUCTED front view of the whole face (both eyes and the mouth fully visible) - the product must not cover the face - a natural, confident expression ready to speak to the viewer. ABSOLUTE REQUIREMENT - override any other wording: the person wears a high-necked, fully-covering outfit that completely covers the chest, cleavage, shoulders, midriff and legs. NO exposed skin below the collarbone, NO cleavage, NO revealing, low-cut, plunging, strapless, off-shoulder or sheer clothing. If a necklace is worn it rests on a COVERED high neckline. Decent, elegant, family-friendly ONLY. Photorealistic editorial photograph, sharp detail.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/runkarobar-gpu/reelkit/work/reel_15daf8c8/product_1.jpg",
  "anchor_used": false,
  "extra_refs": [],
  "shows_person": true
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
  "energy_prompt_verbatim": "gentle breeze effect",
  "full_prompt_sent": "slow push-in. Young woman in green embroidered lawn suit speaking warmly to camera with genuine smile. gentle breeze effect.",
  "input_still": "/workspace/runkarobar-gpu/reelkit/work/reel_15daf8c8/scene_1.png",
  "requested_duration": 7.355,
  "clip_path": "/workspace/runkarobar-gpu/reelkit/work/reel_15daf8c8/clip_1.mp4",
  "kenburns": {
    "zoom": "in",
    "start": 1.0,
    "end": 1.15,
    "xDrift": 0.0,
    "yDrift": 0.0,
    "rotateDeg": 0.0
  }
}
```
**voiceover**

```json
{
  "vo_text": "Yaar, The Collection ka yeh embroidered lawn suit dekho - kitna beautiful hai na! Main toh completely in love hun iske saath.",
  "voice_id": "RAPmAZHXSuTrzY9pjpR3",
  "model_id": "eleven_v3",
  "mp3_path": "/workspace/runkarobar-gpu/reelkit/work/reel_15daf8c8/audio/scene_1.mp3",
  "measured_duration": 7.355,
  "planned_duration": 7.0
}
```

### Scene 2 — showcase / edit_animate / mode=scene / engine=video

**compose**

```json
{
  "path": "edit_animate",
  "model": "Qwen-Image-Edit-2511-fp8mixed",
  "fast_lightning_4step": true,
  "seed": 863,
  "positive_prompt": "Keep the SAME person and the SAME outfit exactly as in this photograph - identical face, hair, skin tone and clothing. Re-frame them for this new shot: Same woman gesturing toward the intricate embroidery details on her suit, touching the fabric lovingly. Setting: Urban street scene with classic architecture, soft golden hour lighting, blurred city backdrop. The model WEARS the complete outfit, with any dupatta or scarf draped naturally on the body. Show ONLY the person wearing it - absolutely no clothing rack, coat stand, hanger, mannequin or separately-displayed garment anywhere in the frame. CRITICAL: every garment piece keeps its OWN exact colour from the reference - never recolour, tint or harmonise one piece to match another (e.g. if the trousers are black and the dupatta is purple, the trousers stay black and the dupatta stays purple). STRICT: the person must be fully and MODESTLY dressed at all times - absolutely no nudity, no cleavage, no bare shoulders, midriff or legs, and no revealing, tight, sheer or sexy clothing. Keep it decent, elegant and family-friendly. The presenter faces the camera directly with a clear, well-lit, UNOBSTRUCTED front view of the whole face (both eyes and the mouth fully visible) - the product must not cover the face - a natural, confident expression ready to speak to the viewer. Use the SAME person as in the FIRST reference image - identical face, hair, skin tone and body - only the pose, angle or framing changes. ABSOLUTE REQUIREMENT - override any other wording: the person wears a high-necked, fully-covering outfit that completely covers the chest, cleavage, shoulders, midriff and legs. NO exposed skin below the collarbone, NO cleavage, NO revealing, low-cut, plunging, strapless, off-shoulder or sheer clothing. If a necklace is worn it rests on a COVERED high neckline. Decent, elegant, family-friendly ONLY. Photorealistic editorial photograph, sharp detail.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/runkarobar-gpu/reelkit/work/reel_15daf8c8/scene_1.png",
  "anchor_used": true,
  "extra_refs": [
    "/workspace/runkarobar-gpu/reelkit/work/reel_15daf8c8/product_1.jpg"
  ],
  "shows_person": true
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
  "motion_prompt_verbatim": "gentle tilt down",
  "energy_prompt_verbatim": "soft fabric shimmer",
  "full_prompt_sent": "gentle tilt down. Same woman gesturing toward the intricate embroidery details on her suit, touching the fabric lovingly. soft fabric shimmer.",
  "input_still": "/workspace/runkarobar-gpu/reelkit/work/reel_15daf8c8/scene_2.png",
  "requested_duration": 6.624,
  "clip_path": "/workspace/runkarobar-gpu/reelkit/work/reel_15daf8c8/clip_2.mp4",
  "kenburns": {
    "zoom": "in",
    "start": 1.12,
    "end": 1.2,
    "xDrift": 0.05,
    "yDrift": 0.1,
    "rotateDeg": 2.0
  }
}
```
**voiceover**

```json
{
  "vo_text": "Dekho kitna premium quality hai - embroidery toh ekdum perfect hai aur fabric bhi so comfortable.",
  "voice_id": "RAPmAZHXSuTrzY9pjpR3",
  "model_id": "eleven_v3",
  "mp3_path": "/workspace/runkarobar-gpu/reelkit/work/reel_15daf8c8/audio/scene_2.mp3",
  "measured_duration": 6.624,
  "planned_duration": 6.0
}
```

### Scene 3 — cta / edit_animate / mode=scene / engine=video

**compose**

```json
{
  "path": "edit_animate",
  "model": "Qwen-Image-Edit-2511-fp8mixed",
  "fast_lightning_4step": true,
  "seed": 864,
  "positive_prompt": "Keep the SAME person and the SAME outfit exactly as in this photograph - identical face, hair, skin tone and clothing. Re-frame them for this new shot: Woman looking directly at camera with confident smile, holding dupatta naturally. Setting: Urban street scene with classic architecture, soft golden hour lighting, blurred city backdrop. The model WEARS the complete outfit, with any dupatta or scarf draped naturally on the body. Show ONLY the person wearing it - absolutely no clothing rack, coat stand, hanger, mannequin or separately-displayed garment anywhere in the frame. CRITICAL: every garment piece keeps its OWN exact colour from the reference - never recolour, tint or harmonise one piece to match another (e.g. if the trousers are black and the dupatta is purple, the trousers stay black and the dupatta stays purple). STRICT: the person must be fully and MODESTLY dressed at all times - absolutely no nudity, no cleavage, no bare shoulders, midriff or legs, and no revealing, tight, sheer or sexy clothing. Keep it decent, elegant and family-friendly. The presenter faces the camera directly with a clear, well-lit, UNOBSTRUCTED front view of the whole face (both eyes and the mouth fully visible) - the product must not cover the face - a natural, confident expression ready to speak to the viewer. Use the SAME person as in the FIRST reference image - identical face, hair, skin tone and body - only the pose, angle or framing changes. ABSOLUTE REQUIREMENT - override any other wording: the person wears a high-necked, fully-covering outfit that completely covers the chest, cleavage, shoulders, midriff and legs. NO exposed skin below the collarbone, NO cleavage, NO revealing, low-cut, plunging, strapless, off-shoulder or sheer clothing. If a necklace is worn it rests on a COVERED high neckline. Decent, elegant, family-friendly ONLY. Photorealistic editorial photograph, sharp detail.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/runkarobar-gpu/reelkit/work/reel_15daf8c8/scene_1.png",
  "anchor_used": true,
  "extra_refs": [
    "/workspace/runkarobar-gpu/reelkit/work/reel_15daf8c8/product_1.jpg"
  ],
  "shows_person": true
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
  "motion_prompt_verbatim": "slight orbit",
  "energy_prompt_verbatim": "",
  "full_prompt_sent": "slight orbit. Woman looking directly at camera with confident smile, holding dupatta naturally.",
  "input_still": "/workspace/runkarobar-gpu/reelkit/work/reel_15daf8c8/scene_3.png",
  "requested_duration": 7.199,
  "clip_path": "/workspace/runkarobar-gpu/reelkit/work/reel_15daf8c8/clip_3.mp4",
  "kenburns": {
    "zoom": "out",
    "start": 1.2,
    "end": 1.12,
    "xDrift": -0.03,
    "yDrift": 0.0,
    "rotateDeg": -1.5
  }
}
```
**voiceover**

```json
{
  "vo_text": "Trust me girls, The Collection mein jaake definitely try karna - you'll love it! Main toh already next piece order kar chuki hun.",
  "voice_id": "RAPmAZHXSuTrzY9pjpR3",
  "model_id": "eleven_v3",
  "mp3_path": "/workspace/runkarobar-gpu/reelkit/work/reel_15daf8c8/audio/scene_3.mp3",
  "measured_duration": 7.199,
  "planned_duration": 7.0
}
```

## 6. Assemble

```json
{
  "per_scene": [
    {
      "scene": 1,
      "fitted_duration": 7.355,
      "transition_in": "cut",
      "dipped_through_black": false
    },
    {
      "scene": 2,
      "fitted_duration": 6.624,
      "transition_in": "cut",
      "dipped_through_black": false
    },
    {
      "scene": 3,
      "fitted_duration": 7.199,
      "transition_in": "fade",
      "dipped_through_black": true
    }
  ],
  "transition_fallbacks": [],
  "total_duration": 20.98,
  "master_resolution": "1080x1920",
  "captions_burned": false,
  "fps": 30,
  "outputs": {
    "1080p": "/workspace/runkarobar-gpu/reelkit/work/reel_15daf8c8/reel_15daf8c8_1080p.mp4"
  }
}
```

## 7. Upload

```json
{
  "reel_1080p_url": "https://staging-storage.runkarobar.com/reels/reel_15daf8c8_1080p.mp4",
  "reel_720p_url": "",
  "scene_image_urls": [
    "https://staging-storage.runkarobar.com/images/reel_15daf8c8_s1.png",
    "https://staging-storage.runkarobar.com/images/reel_15daf8c8_s2.png",
    "https://staging-storage.runkarobar.com/images/reel_15daf8c8_s3.png"
  ],
  "log": "NOT PERSISTED"
}
```

## 8. Timings & model load order

```json
{
  "total_wall_clock_sec": 290.81,
  "per_stage": [
    {
      "stage": "brain",
      "seconds": 19.62
    },
    {
      "stage": "voiceover",
      "seconds": 10.83
    },
    {
      "stage": "scene_1",
      "seconds": 90.64
    },
    {
      "stage": "scene_2",
      "seconds": 94.36
    },
    {
      "stage": "scene_3",
      "seconds": 60.11
    },
    {
      "stage": "assemble",
      "seconds": 11.25
    },
    {
      "stage": "upload",
      "seconds": 4.01
    }
  ],
  "model_load_order": [
    {
      "model": "wavespeed:anthropic/claude-sonnet-4",
      "action": "remote",
      "t": 1.6
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 72.89
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 179.12
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 233.49
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
  }
]
```
