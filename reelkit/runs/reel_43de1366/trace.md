# Reel run trace — `reel_43de1366`

Run directory: `/workspace/runkarobar-gpu/reelkit/runs/reel_43de1366`

> Items marked **NOT PERSISTED** were never written to disk for this run. They are reported as gaps rather than reconstructed. Runs made after the tracer was wired in capture all of them.


## 1. Request

```json
{
  "product_images": [
    "https://staging-storage.runkarobar.com/videos/uploads/1785161273786-5bbc91472c9e1be3-WhatsApp_Image_2026-07-23_at_9.11.25_PM.jpg"
  ],
  "brief": "20s premium luxury reel for this mint-green CZ necklace and matching earrings set — elegant jewellery showcase, clean hero shots on premium surfaces (velvet box, bust, marble), soft sparkle, warm female Hinglish voiceover. Source is a WhatsApp screenshot: ignore the phone status bar, reply bar, emojis, hand and cloth background — isolate ONLY the jewellery.",
  "config": {
    "lengthSec": 20,
    "resolution": "1080p",
    "aspectRatio": "9:16",
    "language": "hinglish",
    "brandName": "",
    "elevenVoiceId": "",
    "captions": false,
    "template": "showcase",
    "trace": true
  }
}
```

Product files on disk: `product_1.jpg`

Template: `showcase`

## 2. Vision captions

**image 1** (verbatim (persisted by tracer)):

> Stage 0 is a vision model now - no separate captioning pass. Images sent to the brain:
https://staging-storage.runkarobar.com/videos/uploads/1785161273786-5bbc91472c9e1be3-WhatsApp_Image_2026-07-23_at_9.11.25_PM.jpg


## 3. Brain prompt (exact string sent to the LLM)

Attempts until valid JSON: `NOT PERSISTED`

```text
===== SYSTEM =====
You are a senior creative director for short vertical product ads. You reply with a single JSON object and nothing else - no prose, no markdown fence.

===== USER =====
Write the storyboard for a vertical social ad.

BRIEF: 20s premium luxury reel for this mint-green CZ necklace and matching earrings set — elegant jewellery showcase, clean hero shots on premium surfaces (velvet box, bust, marble), soft sparkle, warm female Hinglish voiceover. Source is a WhatsApp screenshot: ignore the phone status bar, reply bar, emojis, hand and cloth background — isolate ONLY the jewellery.
BRAND: the brand
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

STYLE DIRECTIVE (template: showcase):
Clean, minimal, premium product showcase. Let the product be the hero with elegant hero shots and subtle camera moves. Minimal on-screen text. Calm, confident, aspirational tone. No gimmicks. Vary the framing across scenes - a hero, a tight macro on the key detail (texture, stitching, hardware, stones), and a styled lifestyle beat - never three of the same shot. Stage the product on a tasteful real surface with soft depth, never a flat solid-colour wall.
Follow these unless the brief says otherwise:
  - aim for about 3 scenes (stay within 3-5)
  - favour subtle camera movement
  - do not use a hard call to action; let the product speak
  - keep the vo sparse; avoid claim badges and slogans
The brief always outranks this directive. You still choose the scene count, methods, energy, motion and wording yourself.

===== IMAGES =====
https://staging-storage.runkarobar.com/videos/uploads/1785161273786-5bbc91472c9e1be3-WhatsApp_Image_2026-07-23_at_9.11.25_PM.jpg
```

## 4. Storyboard returned

```json
{
  "concept": "Premium mint-green CZ jewellery set showcase with elegant luxury presentation",
  "voice": "warm female Hinglish",
  "scenes": [
    {
      "n": 1,
      "goal": "reveal",
      "method": "edit_animate",
      "mode": "product",
      "visual": "Mint-green CZ necklace and earrings set displayed in open black velvet jewellery box",
      "background": "plush black velvet interior, soft warm golden light from above, subtle shadows, luxurious texture",
      "motion": "slow push-in",
      "energy": "gentle sparkle on stones",
      "transitionIn": "fade",
      "durationSec": 6.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "in",
        "start": 1.0,
        "end": 1.15,
        "xDrift": 0.0,
        "yDrift": 0.0,
        "rotateDeg": 0.0
      },
      "vo": "Yeh hai asli elegance - mint green CZ ka premium set"
    },
    {
      "n": 2,
      "goal": "detail",
      "method": "edit_animate",
      "mode": "product",
      "visual": "Extreme close-up of the mint-green CZ stones and crystal details in the necklace pendant",
      "background": "smooth white marble surface, soft diffused lighting, clean minimalist setting",
      "motion": "gentle orbit",
      "energy": "prismatic light reflections",
      "transitionIn": "cut",
      "durationSec": 5.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "in",
        "start": 1.12,
        "end": 1.2,
        "xDrift": 0.1,
        "yDrift": 0.0,
        "rotateDeg": 3.0
      },
      "vo": "Har stone mein chamak, har detail mein perfection"
    },
    {
      "n": 3,
      "goal": "showcase",
      "method": "edit_animate",
      "mode": "product",
      "visual": "Complete necklace and earrings set arranged on elegant jewellery display bust",
      "background": "cream silk fabric backdrop, warm ambient lighting, sophisticated display surface",
      "motion": "slow crane down",
      "energy": "",
      "transitionIn": "fade",
      "durationSec": 5.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "out",
        "start": 1.2,
        "end": 1.12,
        "xDrift": 0.0,
        "yDrift": 0.1,
        "rotateDeg": -2.0
      },
      "vo": "Luxury jewellery jo banaye aapko special"
    },
    {
      "n": 4,
      "goal": "cta",
      "method": "edit_animate",
      "mode": "product",
      "visual": "Final hero shot of the complete mint-green CZ set against premium backdrop",
      "background": "soft grey velvet surface, elegant mood lighting, refined luxury setting",
      "motion": "subtle tilt",
      "energy": "soft golden glow",
      "transitionIn": "fade",
      "durationSec": 4.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "in",
        "start": 1.12,
        "end": 1.12,
        "xDrift": 0.0,
        "yDrift": -0.05,
        "rotateDeg": 1.5
      },
      "vo": "Ab baniye fashion queen"
    }
  ],
  "badges": [],
  "notes": "Premium showcase focusing on the mint-green CZ stones with varied angles - velvet box reveal, macro detail shot, bust display, and final hero. Each scene uses different surfaces and lighting to maintain luxury feel while highlighting the jewellery's elegance."
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
  "seed": 330,
  "positive_prompt": "Keep the subject exactly as photographed - same face, same garment, same colours, same fabric and the same printed branding, unchanged. Change only the surroundings to: plush black velvet interior, soft warm golden light from above, subtle shadows, luxurious texture. The product itself MUST be the exact SAME item as the reference - identical design, colours, materials, shape AND all of its OWN printed branding: keep the real brand name, logo and label text exactly as they are and fully legible. Do NOT invent, restyle, swap or blank out any logo, emblem, label or text, and NEVER turn it into a generic unbranded version. You may re-angle, zoom, crop, re-light and place it into the new setting the scene describes - but the product and its branding stay faithful. Keep the product - INCLUDING its own printed brand name, logo and label - exactly as the reference and fully legible; do not add any new overlaid text, watermark or logo of your own, and do not blank or replace the product's real branding. Photorealistic editorial photograph, sharp detail.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/runkarobar-gpu/reelkit/work/reel_43de1366/product_1.jpg",
  "anchor_used": false,
  "extra_refs": [],
  "shows_person": false
}
```
**guard**

```json
{
  "scene": 1,
  "pass": true,
  "detail": "only 1 token(s) readable on the source (['910']) - too weak to diff, guard skipped",
  "retries": 0
}
```
**animate**

```json
{
  "engine": "wan",
  "path": "video_i2v",
  "motion_prompt_verbatim": "slow push-in",
  "energy_prompt_verbatim": "gentle sparkle on stones",
  "full_prompt_sent": "slow push-in. Mint-green CZ necklace and earrings set displayed in open black velvet jewellery box. gentle sparkle on stones.",
  "input_still": "/workspace/runkarobar-gpu/reelkit/work/reel_43de1366/scene_1.png",
  "requested_duration": 6.0,
  "clip_path": "/workspace/runkarobar-gpu/reelkit/work/reel_43de1366/clip_1.mp4",
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
  "vo_text": "Yeh hai asli elegance - mint green CZ ka premium set",
  "voice_id": "RAPmAZHXSuTrzY9pjpR3",
  "model_id": "eleven_v3",
  "mp3_path": "/workspace/runkarobar-gpu/reelkit/work/reel_43de1366/audio/scene_1.mp3",
  "measured_duration": 6.0,
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
  "seed": 331,
  "positive_prompt": "Keep the subject exactly as photographed - same face, same garment, same colours, same fabric and the same printed branding, unchanged. Change only the surroundings to: smooth white marble surface, soft diffused lighting, clean minimalist setting. The product itself MUST be the exact SAME item as the reference - identical design, colours, materials, shape AND all of its OWN printed branding: keep the real brand name, logo and label text exactly as they are and fully legible. Do NOT invent, restyle, swap or blank out any logo, emblem, label or text, and NEVER turn it into a generic unbranded version. You may re-angle, zoom, crop, re-light and place it into the new setting the scene describes - but the product and its branding stay faithful. Keep the product - INCLUDING its own printed brand name, logo and label - exactly as the reference and fully legible; do not add any new overlaid text, watermark or logo of your own, and do not blank or replace the product's real branding. Photorealistic editorial photograph, sharp detail.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/runkarobar-gpu/reelkit/work/reel_43de1366/product_1.jpg",
  "anchor_used": false,
  "extra_refs": [],
  "shows_person": false
}
```
**guard**

```json
{
  "scene": 2,
  "pass": true,
  "detail": "only 1 token(s) readable on the source (['910']) - too weak to diff, guard skipped",
  "retries": 0
}
```
**animate**

```json
{
  "engine": "wan",
  "path": "video_i2v",
  "motion_prompt_verbatim": "gentle orbit",
  "energy_prompt_verbatim": "prismatic light reflections",
  "full_prompt_sent": "gentle orbit. Extreme close-up of the mint-green CZ stones and crystal details in the necklace pendant. prismatic light reflections.",
  "input_still": "/workspace/runkarobar-gpu/reelkit/work/reel_43de1366/scene_2.png",
  "requested_duration": 5.0,
  "clip_path": "/workspace/runkarobar-gpu/reelkit/work/reel_43de1366/clip_2.mp4",
  "kenburns": {
    "zoom": "in",
    "start": 1.12,
    "end": 1.2,
    "xDrift": 0.1,
    "yDrift": 0.0,
    "rotateDeg": 3.0
  }
}
```
**voiceover**

```json
{
  "vo_text": "Har stone mein chamak, har detail mein perfection",
  "voice_id": "RAPmAZHXSuTrzY9pjpR3",
  "model_id": "eleven_v3",
  "mp3_path": "/workspace/runkarobar-gpu/reelkit/work/reel_43de1366/audio/scene_2.mp3",
  "measured_duration": 5.0,
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
  "seed": 332,
  "positive_prompt": "Keep the subject exactly as photographed - same face, same garment, same colours, same fabric and the same printed branding, unchanged. Change only the surroundings to: cream silk fabric backdrop, warm ambient lighting, sophisticated display surface. The product itself MUST be the exact SAME item as the reference - identical design, colours, materials, shape AND all of its OWN printed branding: keep the real brand name, logo and label text exactly as they are and fully legible. Do NOT invent, restyle, swap or blank out any logo, emblem, label or text, and NEVER turn it into a generic unbranded version. You may re-angle, zoom, crop, re-light and place it into the new setting the scene describes - but the product and its branding stay faithful. Keep the product - INCLUDING its own printed brand name, logo and label - exactly as the reference and fully legible; do not add any new overlaid text, watermark or logo of your own, and do not blank or replace the product's real branding. Photorealistic editorial photograph, sharp detail.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/runkarobar-gpu/reelkit/work/reel_43de1366/product_1.jpg",
  "anchor_used": false,
  "extra_refs": [],
  "shows_person": false
}
```
**guard**

```json
{
  "scene": 3,
  "pass": true,
  "detail": "only 1 token(s) readable on the source (['910']) - too weak to diff, guard skipped",
  "retries": 0
}
```
**animate**

```json
{
  "engine": "wan",
  "path": "video_i2v",
  "motion_prompt_verbatim": "slow crane down",
  "energy_prompt_verbatim": "",
  "full_prompt_sent": "slow crane down. Complete necklace and earrings set arranged on elegant jewellery display bust.",
  "input_still": "/workspace/runkarobar-gpu/reelkit/work/reel_43de1366/scene_3.png",
  "requested_duration": 5.0,
  "clip_path": "/workspace/runkarobar-gpu/reelkit/work/reel_43de1366/clip_3.mp4",
  "kenburns": {
    "zoom": "out",
    "start": 1.2,
    "end": 1.12,
    "xDrift": 0.0,
    "yDrift": 0.1,
    "rotateDeg": -2.0
  }
}
```
**voiceover**

```json
{
  "vo_text": "Luxury jewellery jo banaye aapko special",
  "voice_id": "RAPmAZHXSuTrzY9pjpR3",
  "model_id": "eleven_v3",
  "mp3_path": "/workspace/runkarobar-gpu/reelkit/work/reel_43de1366/audio/scene_3.mp3",
  "measured_duration": 5.0,
  "planned_duration": 5.0
}
```

### Scene 4 — cta / edit_animate / mode=product / engine=video

**compose**

```json
{
  "path": "edit_animate",
  "model": "Qwen-Image-Edit-2511-fp8mixed",
  "fast_lightning_4step": true,
  "seed": 333,
  "positive_prompt": "Keep the subject exactly as photographed - same face, same garment, same colours, same fabric and the same printed branding, unchanged. Change only the surroundings to: soft grey velvet surface, elegant mood lighting, refined luxury setting. The product itself MUST be the exact SAME item as the reference - identical design, colours, materials, shape AND all of its OWN printed branding: keep the real brand name, logo and label text exactly as they are and fully legible. Do NOT invent, restyle, swap or blank out any logo, emblem, label or text, and NEVER turn it into a generic unbranded version. You may re-angle, zoom, crop, re-light and place it into the new setting the scene describes - but the product and its branding stay faithful. Keep the product - INCLUDING its own printed brand name, logo and label - exactly as the reference and fully legible; do not add any new overlaid text, watermark or logo of your own, and do not blank or replace the product's real branding. Photorealistic editorial photograph, sharp detail.",
  "negative_prompt": "changed clothing, different garment, altered colours, warped fabric, distorted face, extra limbs, deformed hands, blurry, low quality, jpeg artifacts, watermark",
  "source_photo": "/workspace/runkarobar-gpu/reelkit/work/reel_43de1366/product_1.jpg",
  "anchor_used": false,
  "extra_refs": [],
  "shows_person": false
}
```
**guard**

```json
{
  "scene": 4,
  "pass": true,
  "detail": "only 1 token(s) readable on the source (['910']) - too weak to diff, guard skipped",
  "retries": 0
}
```
**animate**

```json
{
  "engine": "wan",
  "path": "video_i2v",
  "motion_prompt_verbatim": "subtle tilt",
  "energy_prompt_verbatim": "soft golden glow",
  "full_prompt_sent": "subtle tilt. Final hero shot of the complete mint-green CZ set against premium backdrop. soft golden glow.",
  "input_still": "/workspace/runkarobar-gpu/reelkit/work/reel_43de1366/scene_4.png",
  "requested_duration": 4.0,
  "clip_path": "/workspace/runkarobar-gpu/reelkit/work/reel_43de1366/clip_4.mp4",
  "kenburns": {
    "zoom": "in",
    "start": 1.12,
    "end": 1.12,
    "xDrift": 0.0,
    "yDrift": -0.05,
    "rotateDeg": 1.5
  }
}
```
**voiceover**

```json
{
  "vo_text": "Ab baniye fashion queen",
  "voice_id": "RAPmAZHXSuTrzY9pjpR3",
  "model_id": "eleven_v3",
  "mp3_path": "/workspace/runkarobar-gpu/reelkit/work/reel_43de1366/audio/scene_4.mp3",
  "measured_duration": 4.0,
  "planned_duration": 4.0
}
```

## 6. Assemble

```json
{
  "per_scene": [
    {
      "scene": 1,
      "fitted_duration": 6.0,
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
    },
    {
      "scene": 4,
      "fitted_duration": 4.0,
      "transition_in": "fade",
      "dipped_through_black": true
    }
  ],
  "transition_fallbacks": [],
  "total_duration": 19.98,
  "master_resolution": "1080x1920",
  "captions_burned": false,
  "fps": 30,
  "outputs": {
    "1080p": "/workspace/runkarobar-gpu/reelkit/work/reel_43de1366/reel_43de1366_1080p.mp4"
  }
}
```

## 7. Upload

```json
{
  "reel_1080p_url": "https://staging-storage.runkarobar.com/reels/reel_43de1366_1080p.mp4",
  "reel_720p_url": "",
  "scene_image_urls": [
    "https://staging-storage.runkarobar.com/images/reel_43de1366_s1.png",
    "https://staging-storage.runkarobar.com/images/reel_43de1366_s2.png",
    "https://staging-storage.runkarobar.com/images/reel_43de1366_s3.png",
    "https://staging-storage.runkarobar.com/images/reel_43de1366_s4.png"
  ],
  "log": "NOT PERSISTED"
}
```

## 8. Timings & model load order

```json
{
  "total_wall_clock_sec": 637.85,
  "per_stage": [
    {
      "stage": "brain",
      "seconds": 19.67
    },
    {
      "stage": "voiceover",
      "seconds": 7.77
    },
    {
      "stage": "scene_1",
      "seconds": 52.91
    },
    {
      "stage": "scene_2",
      "seconds": 46.06
    },
    {
      "stage": "scene_3",
      "seconds": 45.79
    },
    {
      "stage": "scene_4",
      "seconds": 42.95
    },
    {
      "stage": "assemble",
      "seconds": 11.6
    },
    {
      "stage": "upload",
      "seconds": 411.11
    }
  ],
  "model_load_order": [
    {
      "model": "wavespeed:anthropic/claude-sonnet-4",
      "action": "remote",
      "t": 1.64
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 47.29
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 99.36
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 145.1
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 191.1
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
    "detail": "only 1 token(s) readable on the source (['910']) - too weak to diff, guard skipped"
  },
  {
    "scene": 2,
    "ok": true,
    "detail": "only 1 token(s) readable on the source (['910']) - too weak to diff, guard skipped"
  },
  {
    "scene": 3,
    "ok": true,
    "detail": "only 1 token(s) readable on the source (['910']) - too weak to diff, guard skipped"
  },
  {
    "scene": 4,
    "ok": true,
    "detail": "only 1 token(s) readable on the source (['910']) - too weak to diff, guard skipped"
  }
]
```
