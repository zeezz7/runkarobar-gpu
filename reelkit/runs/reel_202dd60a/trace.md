# Reel run trace — `reel_202dd60a`

Run directory: `/workspace/runkarobar-gpu/reelkit/runs/reel_202dd60a`

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
    "elevenVoiceId": "RAPmAZHXSuTrzY9pjpR3",
    "captions": false,
    "template": "outfit-check",
    "trace": true
  }
}
```

Product files on disk: `product_1.jpg`

Template: `outfit-check`

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

STYLE DIRECTIVE (template: outfit-check):
A first-person 'outfit check' mirror-selfie reel, the way it is actually posted: ONE confident woman standing in front of a large full-length mirror in a tastefully styled modern room, holding her phone up to take the mirror photo, wearing the exact outfit, visible head-to-toe. The SAME woman carries every scene - she never changes. Each scene is a fresh beat: establish the full look, then turn to a flattering three-quarter angle, then a closer waist-up framing on the fabric and detailing, ending on a confident look to camera. She keeps the phone raised in every shot. Write the vo as casual, trendy FIRST-PERSON lines - 'obsessed with this fit', 'the drape on this is unreal' - like a real girl showing off her outfit, NOT an ad read. The last line is a call to action to shop.
Follow these unless the brief says otherwise:
  - aim for about 3 scenes (stay within 3-5)
  - favour dynamic camera movement
  - end on an explicit call to action in the final scene's vo
  - favour scenes with a person using or wearing the product over isolated packshots
The brief always outranks this directive. You still choose the scene count, methods, energy, motion and wording yourself.

===== IMAGES =====
https://staging-storage.runkarobar.com/videos/uploads/1785150296652-826672de130d6770-WhatsApp_Image_2026-07-27_at_4.32.11_PM.jpg
```

## 4. Storyboard returned

```json
{
  "concept": "First-person outfit check showcasing premium embroidered lawn suit in mirror selfie style",
  "voice": "warm female Hinglish",
  "scenes": [
    {
      "n": 1,
      "goal": "reveal",
      "method": "edit_animate",
      "mode": "product",
      "visual": "Confident woman in full embroidered green lawn suit standing in front of large mirror, holding phone up for mirror selfie, head-to-toe view showing complete outfit",
      "background": "Modern stylish bedroom with soft natural light streaming through large windows, minimalist decor with warm neutral tones",
      "motion": "slow push-in",
      "energy": "golden hour glow",
      "transitionIn": "fade",
      "durationSec": 6.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "in",
        "start": 1.0,
        "end": 1.15,
        "xDrift": 0.0,
        "yDrift": -0.03,
        "rotateDeg": 0.0
      },
      "vo": "Guys, this embroidered lawn suit se main totally obsessed hun! The Collection ka yeh piece is just perfection"
    },
    {
      "n": 2,
      "goal": "detail",
      "method": "edit_animate",
      "mode": "product",
      "visual": "Same woman turned to flattering three-quarter angle, phone still raised, showcasing the intricate embroidery work and fabric drape from waist-up",
      "background": "Same modern bedroom setting with soft diffused lighting highlighting the fabric texture",
      "motion": "gentle orbit",
      "energy": "subtle shimmer",
      "transitionIn": "cut",
      "durationSec": 6.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "in",
        "start": 1.12,
        "end": 1.25,
        "xDrift": 0.05,
        "yDrift": 0.0,
        "rotateDeg": 3.0
      },
      "vo": "Dekho yeh embroidery work kitni detailed hai, aur lawn fabric ka drape bhi bohot elegant lag raha hai"
    },
    {
      "n": 3,
      "goal": "cta",
      "method": "edit_animate",
      "mode": "product",
      "visual": "Woman facing camera directly with confident smile, phone raised, full suit visible with focus on the premium quality and overall styling",
      "background": "Same bedroom mirror setting with perfect lighting creating an aspirational mood",
      "motion": "slow zoom out",
      "energy": "",
      "transitionIn": "whip",
      "durationSec": 8.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "out",
        "start": 1.2,
        "end": 1.12,
        "xDrift": 0.0,
        "yDrift": 0.02,
        "rotateDeg": -2.0
      },
      "vo": "Premium quality aur yeh gorgeous embroidery - trust me girls, you need this! The Collection pe jaake shop karo abhi"
    }
  ],
  "badges": [],
  "notes": "Mirror selfie style outfit check featuring confident woman showcasing embroidered lawn suit with natural first-person commentary in Hinglish, building from full reveal to detail showcase ending with direct call to action"
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
  "seed": 687,
  "positive_prompt": "Keep the subject exactly as photographed - same face, same garment, same colours, same fabric and the same printed branding, unchanged. Change only the surroundings to: Modern stylish bedroom with soft natural light streaming through large windows, minimalist decor with warm neutral tones. The model WEARS the complete outfit, with any dupatta or scarf draped naturally on the body. Show ONLY the person wearing it - absolutely no clothing rack, coat stand, hanger, mannequin or separately-displayed garment anywhere in the frame. CRITICAL: every garment piece keeps its OWN exact colour from the reference - never recolour, tint or harmonise one piece to match another (e.g. if the trousers are black and the dupatta is purple, the trousers stay black and the dupatta stays purple). STRICT: the person must be fully and MODESTLY dressed at all times - absolutely no nudity, no cleavage, no bare shoulders, midriff or legs, and no revealing, tight, sheer or sexy clothing. Keep it decent, elegant and family-friendly. The outfit MUST be an EXACT replica of the one in the reference photo - identical colour on every piece, identical embroidery or print pattern, motif placement, borders, neckline, sleeves, hem and fabric texture. Do NOT redesign, restyle, simplify, recolour, add or remove ANY detail - only the pose, angle or framing may change. Do not invent an unseen back or print. She is taking a mirror selfie and keeps her phone raised in one hand in this shot too - never empty-handed. ABSOLUTE REQUIREMENT - override any other wording: the person wears a high-necked, fully-covering outfit that completely covers the chest, cleavage, shoulders, midriff and legs. NO exposed skin below the collarbone, NO cleavage, NO revealing, low-cut, plunging, strapless, off-shoulder or sheer clothing. If a necklace is worn it rests on a COVERED high neckline. Decent, elegant, family-friendly ONLY. Photorealistic editorial photograph, sharp detail.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/runkarobar-gpu/reelkit/work/reel_202dd60a/product_1.jpg",
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
  "energy_prompt_verbatim": "golden hour glow",
  "full_prompt_sent": "slow push-in. Confident woman in full embroidered green lawn suit standing in front of large mirror, holding phone up for mirror selfie, head-to-toe view showing complete outfit. golden hour glow.",
  "input_still": "/workspace/runkarobar-gpu/reelkit/work/reel_202dd60a/scene_1.png",
  "requested_duration": 7.643,
  "clip_path": "/workspace/runkarobar-gpu/reelkit/work/reel_202dd60a/clip_1.mp4",
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
  "vo_text": "Guys, this embroidered lawn suit se main totally obsessed hun! The Collection ka yeh piece is just perfection",
  "voice_id": "RAPmAZHXSuTrzY9pjpR3",
  "model_id": "eleven_v3",
  "mp3_path": "/workspace/runkarobar-gpu/reelkit/work/reel_202dd60a/audio/scene_1.mp3",
  "measured_duration": 7.643,
  "planned_duration": 6.0
}
```

### Scene 2 — detail / edit_animate / mode=product / engine=video

**compose**

```json
{
  "path": "edit_animate",
  "model": "Qwen-Image-Edit-2511-fp8mixed",
  "fast_lightning_4step": true,
  "seed": 688,
  "positive_prompt": "Keep the subject exactly as photographed - same face, same garment, same colours, same fabric and the same printed branding, unchanged. Change only the surroundings to: Same modern bedroom setting with soft diffused lighting highlighting the fabric texture. The model WEARS the complete outfit, with any dupatta or scarf draped naturally on the body. Show ONLY the person wearing it - absolutely no clothing rack, coat stand, hanger, mannequin or separately-displayed garment anywhere in the frame. CRITICAL: every garment piece keeps its OWN exact colour from the reference - never recolour, tint or harmonise one piece to match another (e.g. if the trousers are black and the dupatta is purple, the trousers stay black and the dupatta stays purple). STRICT: the person must be fully and MODESTLY dressed at all times - absolutely no nudity, no cleavage, no bare shoulders, midriff or legs, and no revealing, tight, sheer or sexy clothing. Keep it decent, elegant and family-friendly. The outfit MUST be an EXACT replica of the one in the reference photo - identical colour on every piece, identical embroidery or print pattern, motif placement, borders, neckline, sleeves, hem and fabric texture. Do NOT redesign, restyle, simplify, recolour, add or remove ANY detail - only the pose, angle or framing may change. Do not invent an unseen back or print. She is taking a mirror selfie and keeps her phone raised in one hand in this shot too - never empty-handed. ABSOLUTE REQUIREMENT - override any other wording: the person wears a high-necked, fully-covering outfit that completely covers the chest, cleavage, shoulders, midriff and legs. NO exposed skin below the collarbone, NO cleavage, NO revealing, low-cut, plunging, strapless, off-shoulder or sheer clothing. If a necklace is worn it rests on a COVERED high neckline. Decent, elegant, family-friendly ONLY. Photorealistic editorial photograph, sharp detail.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/runkarobar-gpu/reelkit/work/reel_202dd60a/product_1.jpg",
  "anchor_used": false,
  "extra_refs": [],
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
  "motion_prompt_verbatim": "gentle orbit",
  "energy_prompt_verbatim": "subtle shimmer",
  "full_prompt_sent": "gentle orbit. Same woman turned to flattering three-quarter angle, phone still raised, showcasing the intricate embroidery work and fabric drape from waist-up. subtle shimmer.",
  "input_still": "/workspace/runkarobar-gpu/reelkit/work/reel_202dd60a/scene_2.png",
  "requested_duration": 7.172,
  "clip_path": "/workspace/runkarobar-gpu/reelkit/work/reel_202dd60a/clip_2.mp4",
  "kenburns": {
    "zoom": "in",
    "start": 1.12,
    "end": 1.25,
    "xDrift": 0.05,
    "yDrift": 0.0,
    "rotateDeg": 3.0
  }
}
```
**voiceover**

```json
{
  "vo_text": "Dekho yeh embroidery work kitni detailed hai, aur lawn fabric ka drape bhi bohot elegant lag raha hai",
  "voice_id": "RAPmAZHXSuTrzY9pjpR3",
  "model_id": "eleven_v3",
  "mp3_path": "/workspace/runkarobar-gpu/reelkit/work/reel_202dd60a/audio/scene_2.mp3",
  "measured_duration": 7.172,
  "planned_duration": 6.0
}
```

### Scene 3 — cta / edit_animate / mode=product / engine=video

**compose**

```json
{
  "path": "edit_animate",
  "model": "Qwen-Image-Edit-2511-fp8mixed",
  "fast_lightning_4step": true,
  "seed": 689,
  "positive_prompt": "Keep the subject exactly as photographed - same face, same garment, same colours, same fabric and the same printed branding, unchanged. Change only the surroundings to: Same bedroom mirror setting with perfect lighting creating an aspirational mood. The model WEARS the complete outfit, with any dupatta or scarf draped naturally on the body. Show ONLY the person wearing it - absolutely no clothing rack, coat stand, hanger, mannequin or separately-displayed garment anywhere in the frame. CRITICAL: every garment piece keeps its OWN exact colour from the reference - never recolour, tint or harmonise one piece to match another (e.g. if the trousers are black and the dupatta is purple, the trousers stay black and the dupatta stays purple). STRICT: the person must be fully and MODESTLY dressed at all times - absolutely no nudity, no cleavage, no bare shoulders, midriff or legs, and no revealing, tight, sheer or sexy clothing. Keep it decent, elegant and family-friendly. The outfit MUST be an EXACT replica of the one in the reference photo - identical colour on every piece, identical embroidery or print pattern, motif placement, borders, neckline, sleeves, hem and fabric texture. Do NOT redesign, restyle, simplify, recolour, add or remove ANY detail - only the pose, angle or framing may change. Do not invent an unseen back or print. She is taking a mirror selfie and keeps her phone raised in one hand in this shot too - never empty-handed. ABSOLUTE REQUIREMENT - override any other wording: the person wears a high-necked, fully-covering outfit that completely covers the chest, cleavage, shoulders, midriff and legs. NO exposed skin below the collarbone, NO cleavage, NO revealing, low-cut, plunging, strapless, off-shoulder or sheer clothing. If a necklace is worn it rests on a COVERED high neckline. Decent, elegant, family-friendly ONLY. Photorealistic editorial photograph, sharp detail.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/runkarobar-gpu/reelkit/work/reel_202dd60a/product_1.jpg",
  "anchor_used": false,
  "extra_refs": [],
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
  "motion_prompt_verbatim": "slow zoom out",
  "energy_prompt_verbatim": "",
  "full_prompt_sent": "slow zoom out. Woman facing camera directly with confident smile, phone raised, full suit visible with focus on the premium quality and overall styling.",
  "input_still": "/workspace/runkarobar-gpu/reelkit/work/reel_202dd60a/scene_3.png",
  "requested_duration": 8.296,
  "clip_path": "/workspace/runkarobar-gpu/reelkit/work/reel_202dd60a/clip_3.mp4",
  "kenburns": {
    "zoom": "out",
    "start": 1.2,
    "end": 1.12,
    "xDrift": 0.0,
    "yDrift": 0.02,
    "rotateDeg": -2.0
  }
}
```
**voiceover**

```json
{
  "vo_text": "Premium quality aur yeh gorgeous embroidery - trust me girls, you need this! The Collection pe jaake shop karo abhi",
  "voice_id": "RAPmAZHXSuTrzY9pjpR3",
  "model_id": "eleven_v3",
  "mp3_path": "/workspace/runkarobar-gpu/reelkit/work/reel_202dd60a/audio/scene_3.mp3",
  "measured_duration": 8.296,
  "planned_duration": 8.0
}
```

## 6. Assemble

```json
{
  "per_scene": [
    {
      "scene": 1,
      "fitted_duration": 7.643,
      "transition_in": "fade",
      "dipped_through_black": false
    },
    {
      "scene": 2,
      "fitted_duration": 7.172,
      "transition_in": "cut",
      "dipped_through_black": false
    },
    {
      "scene": 3,
      "fitted_duration": 8.296,
      "transition_in": "whip",
      "dipped_through_black": true
    }
  ],
  "transition_fallbacks": [
    "scene 3: 'whip' not implemented -> fade"
  ],
  "total_duration": 23.05,
  "master_resolution": "1080x1920",
  "captions_burned": false,
  "fps": 30,
  "outputs": {
    "1080p": "/workspace/runkarobar-gpu/reelkit/work/reel_202dd60a/reel_202dd60a_1080p.mp4"
  }
}
```

## 7. Upload

```json
{
  "reel_1080p_url": "https://staging-storage.runkarobar.com/reels/reel_202dd60a_1080p.mp4",
  "reel_720p_url": "",
  "scene_image_urls": [
    "https://staging-storage.runkarobar.com/images/reel_202dd60a_s1.png",
    "https://staging-storage.runkarobar.com/images/reel_202dd60a_s2.png",
    "https://staging-storage.runkarobar.com/images/reel_202dd60a_s3.png"
  ],
  "log": "NOT PERSISTED"
}
```

## 8. Timings & model load order

```json
{
  "total_wall_clock_sec": 179.44,
  "per_stage": [
    {
      "stage": "brain",
      "seconds": 17.59
    },
    {
      "stage": "voiceover",
      "seconds": 9.72
    },
    {
      "stage": "scene_1",
      "seconds": 46.66
    },
    {
      "stage": "scene_2",
      "seconds": 45.5
    },
    {
      "stage": "scene_3",
      "seconds": 45.24
    },
    {
      "stage": "assemble",
      "seconds": 10.97
    },
    {
      "stage": "upload",
      "seconds": 3.77
    }
  ],
  "model_load_order": [
    {
      "model": "wavespeed:anthropic/claude-sonnet-4",
      "action": "remote",
      "t": 1.66
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 46.9
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 92.43
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 137.65
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
