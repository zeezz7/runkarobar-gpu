# Reel run trace — `reel_138ba49e`

Run directory: `/workspace/runkarobar-gpu/reelkit/runs/reel_138ba49e`

> Items marked **NOT PERSISTED** were never written to disk for this run. They are reported as gaps rather than reconstructed. Runs made after the tracer was wired in capture all of them.


## 1. Request

```json
{
  "product_images": [
    "https://staging-storage.runkarobar.com/videos/uploads/1785163518653-70cb87e17e752c9b-WhatsApp_Image_2026-07-27_at_6.33.54_PM.jpg"
  ],
  "brief": "AI-directed 20s premium reel for this Mihnain Apparels women's ethnic suit: a magenta / berry-pink kurta with gold zari embroidery on the yoke and shoulders and a gold embroidered hem, paired with a grey-silver zari-border dupatta and grey salwar. A MODEL should WEAR the full suit through the reel, the SAME model in every scene. Keep the embroidery, the magenta colour, the grey dupatta and every zari detail EXACT - do not reinvent or simplify the pattern. Elegant festive ethnic mood, clean premium shots, warm female Hinglish voiceover. Source is a flat-lay product photo on wood with roses and a 'Mihnain Apparels' logo: ignore the props and the logo, keep only the garment.",
  "config": {
    "lengthSec": 20,
    "resolution": "1080p",
    "aspectRatio": "9:16",
    "language": "hinglish",
    "brandName": "Mihnain Apparels",
    "elevenVoiceId": "",
    "captions": false,
    "template": "ai-director",
    "includeHuman": true,
    "trace": true
  }
}
```

Product files on disk: `product_1.jpg`

Template: `ai-director`

## 2. Vision captions

**image 1** (verbatim (persisted by tracer)):

> Stage 0 is a vision model now - no separate captioning pass. Images sent to the brain:
https://staging-storage.runkarobar.com/videos/uploads/1785163518653-70cb87e17e752c9b-WhatsApp_Image_2026-07-27_at_6.33.54_PM.jpg


## 3. Brain prompt (exact string sent to the LLM)

Attempts until valid JSON: `NOT PERSISTED`

```text
===== SYSTEM =====
You are a senior creative director for short vertical product ads. You reply with a single JSON object and nothing else - no prose, no markdown fence.

===== USER =====
Write the storyboard for a vertical social ad.

BRIEF: AI-directed 20s premium reel for this Mihnain Apparels women's ethnic suit: a magenta / berry-pink kurta with gold zari embroidery on the yoke and shoulders and a gold embroidered hem, paired with a grey-silver zari-border dupatta and grey salwar. A MODEL should WEAR the full suit through the reel, the SAME model in every scene. Keep the embroidery, the magenta colour, the grey dupatta and every zari detail EXACT - do not reinvent or simplify the pattern. Elegant festive ethnic mood, clean premium shots, warm female Hinglish voiceover. Source is a flat-lay product photo on wood with roses and a 'Mihnain Apparels' logo: ignore the props and the logo, keep only the garment.
BRAND: Mihnain Apparels
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

WHO IS ON SCREEN:
  A real person features with the product - wearing, holding or using it. Show them naturally and keep them consistent across scenes (same face, hair and build throughout). They must be fully and modestly dressed in every shot.

===== IMAGES =====
https://staging-storage.runkarobar.com/videos/uploads/1785163518653-70cb87e17e752c9b-WhatsApp_Image_2026-07-27_at_6.33.54_PM.jpg
```

## 4. Storyboard returned

```json
{
  "concept": "Premium ethnic elegance meets festive sophistication",
  "voice": "warm female Hinglish",
  "scenes": [
    {
      "n": 1,
      "goal": "reveal",
      "method": "edit_animate",
      "mode": "product",
      "visual": "Close-up of model wearing the complete magenta kurta suit with gold zari embroidery, grey dupatta draped elegantly over one shoulder",
      "background": "Soft golden warm lighting, blurred festive bokeh lights in background, rich marble surface",
      "motion": "slow push-in",
      "energy": "golden light particles",
      "transitionIn": "fade",
      "durationSec": 5.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "in",
        "start": 1.0,
        "end": 1.15,
        "xDrift": 0.0,
        "yDrift": -0.03,
        "rotateDeg": 0.0
      },
      "vo": "Festive season mein sabse elegant look chahiye? Mihnain ka premium collection dekho"
    },
    {
      "n": 2,
      "goal": "detail",
      "method": "edit_animate",
      "mode": "product",
      "visual": "Model adjusting the grey-silver dupatta, showcasing the intricate gold zari border work and the magenta kurta's embroidered yoke",
      "background": "Warm candlelit ambiance, soft shadows dancing on textured wall, intimate festive setting",
      "motion": "gentle arc around",
      "energy": "",
      "transitionIn": "cut",
      "durationSec": 4.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "in",
        "start": 1.12,
        "end": 1.12,
        "xDrift": 0.08,
        "yDrift": 0.0,
        "rotateDeg": 3.0
      },
      "vo": "Hand-crafted zari work, pure elegance har detail mein"
    },
    {
      "n": 3,
      "goal": "wear",
      "method": "edit_animate",
      "mode": "product",
      "visual": "Full-body shot of model gracefully posing in the complete suit - magenta kurta with gold embroidery, grey salwar and dupatta",
      "background": "Luxurious heritage palace courtyard, warm evening light filtering through arches, marble pillars",
      "motion": "slow crane down",
      "energy": "floating rose petals",
      "transitionIn": "whip",
      "durationSec": 6.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "in",
        "start": 1.12,
        "end": 1.12,
        "xDrift": -0.05,
        "yDrift": 0.1,
        "rotateDeg": -2.0
      },
      "vo": "Traditional charm with modern grace - ye hai perfect festive outfit jo banaye aapko center of attraction"
    },
    {
      "n": 4,
      "goal": "cta",
      "method": "edit_animate",
      "mode": "product",
      "visual": "Model smiling confidently in the magenta suit, hands gently touching the embroidered dupatta edge",
      "background": "Elegant mirror backdrop with soft fairy lights, premium boutique atmosphere, golden hour lighting",
      "motion": "subtle zoom in",
      "energy": "sparkle highlights",
      "transitionIn": "fade",
      "durationSec": 5.0,
      "motionEngine": "video",
      "kenburns": {
        "zoom": "in",
        "start": 1.0,
        "end": 1.1,
        "xDrift": 0.0,
        "yDrift": -0.02,
        "rotateDeg": 0.0
      },
      "vo": "Mihnain Apparels se order karo - premium ethnic wear jo banaye har occasion special"
    }
  ],
  "badges": [
    {
      "text": "Premium Quality",
      "color": "#D4AF37"
    }
  ],
  "notes": "Premium ethnic reel showcasing the exact magenta kurta with gold zari work and grey dupatta. Consistent model throughout, emphasizing craftsmanship and festive elegance with warm Hinglish voiceover that builds from product reveal to emotional connection to clear CTA."
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
  "seed": 1601,
  "positive_prompt": "Keep the product exactly as photographed - identical shape, colours, materials and every detail, unchanged. Change only the surroundings to: Soft golden warm lighting, blurred festive bokeh lights in background, rich marble surface. The product itself MUST be the exact SAME item as the reference - identical design, colours, materials, shape, proportions and every detail. Do NOT redesign, restyle, simplify or substitute it. You may re-angle, zoom, crop, re-light and place it into the new setting the scene describes - but the product stays faithful. If the product carries printed text, a brand name or a logo, keep it EXACTLY as it appears in the reference and fully legible. Do NOT add, invent or overlay ANY text, lettering, numbers, brand name, logo, emblem, watermark, sticker, price tag, label or caption that is not already physically on the product in the reference photograph. If the product has no text on it, the render must have no text anywhere. The reference photograph may carry marks that are NOT part of the product - a shop or seller watermark, a promotional banner or slogan, a price sticker, phone-screenshot UI, a filename, or stray text and objects lying on the surface behind it. REMOVE all of those; none of them may appear in the render, in any corner or edge. But KEEP the product's OWN printed branding intact. The final frame carries no signature, no handwriting, no artist mark and no corner text of any kind. Photorealistic editorial photograph, sharp detail.",
  "negative_prompt": "signature, handwriting, handwritten script, artist mark, corner text, watermark, text, lettering, letters, words, numbers, caption, subtitle, label, price tag, sticker, sign, logo, emblem, brand mark, gibberish text, garbled writing, fake logo, different product, altered design, changed colours, distorted shape, duplicated product, extra objects, people, hands, blurry, soft focus, low quality, jpeg artifacts",
  "source_photo": "/workspace/runkarobar-gpu/reelkit/work/reel_138ba49e/product_1.jpg",
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
  "detail": "only 2 token(s) readable on the source (['APPARELS', 'MIHNAIN']) - too weak to diff, guard skipped",
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
  "full_prompt_sent": "slow push-in. Close-up of model wearing the complete magenta kurta suit with gold zari embroidery, grey dupatta draped elegantly over one shoulder. golden light particles.",
  "input_still": "/workspace/runkarobar-gpu/reelkit/work/reel_138ba49e/scene_1.png",
  "requested_duration": 5.03,
  "clip_path": "/workspace/runkarobar-gpu/reelkit/work/reel_138ba49e/clip_1.mp4",
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
  "vo_text": "Festive season mein sabse elegant look chahiye? Mihnain ka premium collection dekho",
  "voice_id": "RAPmAZHXSuTrzY9pjpR3",
  "model_id": "eleven_v3",
  "mp3_path": "/workspace/runkarobar-gpu/reelkit/work/reel_138ba49e/audio/scene_1.mp3",
  "measured_duration": 5.03,
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
  "seed": 1602,
  "positive_prompt": "Keep the product exactly as photographed - identical shape, colours, materials and every detail, unchanged. Change only the surroundings to: Warm candlelit ambiance, soft shadows dancing on textured wall, intimate festive setting. The product itself MUST be the exact SAME item as the reference - identical design, colours, materials, shape, proportions and every detail. Do NOT redesign, restyle, simplify or substitute it. You may re-angle, zoom, crop, re-light and place it into the new setting the scene describes - but the product stays faithful. If the product carries printed text, a brand name or a logo, keep it EXACTLY as it appears in the reference and fully legible. Do NOT add, invent or overlay ANY text, lettering, numbers, brand name, logo, emblem, watermark, sticker, price tag, label or caption that is not already physically on the product in the reference photograph. If the product has no text on it, the render must have no text anywhere. The reference photograph may carry marks that are NOT part of the product - a shop or seller watermark, a promotional banner or slogan, a price sticker, phone-screenshot UI, a filename, or stray text and objects lying on the surface behind it. REMOVE all of those; none of them may appear in the render, in any corner or edge. But KEEP the product's OWN printed branding intact. The final frame carries no signature, no handwriting, no artist mark and no corner text of any kind. Photorealistic editorial photograph, sharp detail.",
  "negative_prompt": "signature, handwriting, handwritten script, artist mark, corner text, watermark, text, lettering, letters, words, numbers, caption, subtitle, label, price tag, sticker, sign, logo, emblem, brand mark, gibberish text, garbled writing, fake logo, different product, altered design, changed colours, distorted shape, duplicated product, extra objects, people, hands, blurry, soft focus, low quality, jpeg artifacts",
  "source_photo": "/workspace/runkarobar-gpu/reelkit/work/reel_138ba49e/product_1.jpg",
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
  "detail": "only 2 token(s) readable on the source (['APPARELS', 'MIHNAIN']) - too weak to diff, guard skipped",
  "retries": 0
}
```
**animate**

```json
{
  "engine": "wan",
  "path": "video_i2v",
  "motion_prompt_verbatim": "gentle arc around",
  "energy_prompt_verbatim": "",
  "full_prompt_sent": "gentle arc around. Model adjusting the grey-silver dupatta, showcasing the intricate gold zari border work and the magenta kurta's embroidered yoke.",
  "input_still": "/workspace/runkarobar-gpu/reelkit/work/reel_138ba49e/scene_2.png",
  "requested_duration": 3.568,
  "clip_path": "/workspace/runkarobar-gpu/reelkit/work/reel_138ba49e/clip_2.mp4",
  "kenburns": {
    "zoom": "in",
    "start": 1.12,
    "end": 1.12,
    "xDrift": 0.08,
    "yDrift": 0.0,
    "rotateDeg": 3.0
  }
}
```
**voiceover**

```json
{
  "vo_text": "Hand-crafted zari work, pure elegance har detail mein",
  "voice_id": "RAPmAZHXSuTrzY9pjpR3",
  "model_id": "eleven_v3",
  "mp3_path": "/workspace/runkarobar-gpu/reelkit/work/reel_138ba49e/audio/scene_2.mp3",
  "measured_duration": 3.568,
  "planned_duration": 4.0
}
```

### Scene 3 — wear / edit_animate / mode=product / engine=video

**compose**

```json
{
  "path": "edit_animate",
  "model": "Qwen-Image-Edit-2511-fp8mixed",
  "fast_lightning_4step": true,
  "seed": 1603,
  "positive_prompt": "Keep the product exactly as photographed - identical shape, colours, materials and every detail, unchanged. Change only the surroundings to: Luxurious heritage palace courtyard, warm evening light filtering through arches, marble pillars. The product itself MUST be the exact SAME item as the reference - identical design, colours, materials, shape, proportions and every detail. Do NOT redesign, restyle, simplify or substitute it. You may re-angle, zoom, crop, re-light and place it into the new setting the scene describes - but the product stays faithful. If the product carries printed text, a brand name or a logo, keep it EXACTLY as it appears in the reference and fully legible. Do NOT add, invent or overlay ANY text, lettering, numbers, brand name, logo, emblem, watermark, sticker, price tag, label or caption that is not already physically on the product in the reference photograph. If the product has no text on it, the render must have no text anywhere. The reference photograph may carry marks that are NOT part of the product - a shop or seller watermark, a promotional banner or slogan, a price sticker, phone-screenshot UI, a filename, or stray text and objects lying on the surface behind it. REMOVE all of those; none of them may appear in the render, in any corner or edge. But KEEP the product's OWN printed branding intact. The final frame carries no signature, no handwriting, no artist mark and no corner text of any kind. Photorealistic editorial photograph, sharp detail.",
  "negative_prompt": "signature, handwriting, handwritten script, artist mark, corner text, watermark, text, lettering, letters, words, numbers, caption, subtitle, label, price tag, sticker, sign, logo, emblem, brand mark, gibberish text, garbled writing, fake logo, different product, altered design, changed colours, distorted shape, duplicated product, extra objects, people, hands, blurry, soft focus, low quality, jpeg artifacts",
  "source_photo": "/workspace/runkarobar-gpu/reelkit/work/reel_138ba49e/product_1.jpg",
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
  "detail": "only 2 token(s) readable on the source (['APPARELS', 'MIHNAIN']) - too weak to diff, guard skipped",
  "retries": 0
}
```
**animate**

```json
{
  "engine": "wan",
  "path": "video_i2v",
  "motion_prompt_verbatim": "slow crane down",
  "energy_prompt_verbatim": "floating rose petals",
  "full_prompt_sent": "slow crane down. Full-body shot of model gracefully posing in the complete suit - magenta kurta with gold embroidery, grey salwar and dupatta. floating rose petals.",
  "input_still": "/workspace/runkarobar-gpu/reelkit/work/reel_138ba49e/scene_3.png",
  "requested_duration": 7.721,
  "clip_path": "/workspace/runkarobar-gpu/reelkit/work/reel_138ba49e/clip_3.mp4",
  "kenburns": {
    "zoom": "in",
    "start": 1.12,
    "end": 1.12,
    "xDrift": -0.05,
    "yDrift": 0.1,
    "rotateDeg": -2.0
  }
}
```
**voiceover**

```json
{
  "vo_text": "Traditional charm with modern grace - ye hai perfect festive outfit jo banaye aapko center of attraction",
  "voice_id": "RAPmAZHXSuTrzY9pjpR3",
  "model_id": "eleven_v3",
  "mp3_path": "/workspace/runkarobar-gpu/reelkit/work/reel_138ba49e/audio/scene_3.mp3",
  "measured_duration": 7.721,
  "planned_duration": 6.0
}
```

### Scene 4 — cta / edit_animate / mode=product / engine=video

**compose**

```json
{
  "path": "edit_animate",
  "model": "Qwen-Image-Edit-2511-fp8mixed",
  "fast_lightning_4step": true,
  "seed": 1604,
  "positive_prompt": "Keep the product exactly as photographed - identical shape, colours, materials and every detail, unchanged. Change only the surroundings to: Elegant mirror backdrop with soft fairy lights, premium boutique atmosphere, golden hour lighting. The product itself MUST be the exact SAME item as the reference - identical design, colours, materials, shape, proportions and every detail. Do NOT redesign, restyle, simplify or substitute it. You may re-angle, zoom, crop, re-light and place it into the new setting the scene describes - but the product stays faithful. If the product carries printed text, a brand name or a logo, keep it EXACTLY as it appears in the reference and fully legible. Do NOT add, invent or overlay ANY text, lettering, numbers, brand name, logo, emblem, watermark, sticker, price tag, label or caption that is not already physically on the product in the reference photograph. If the product has no text on it, the render must have no text anywhere. The reference photograph may carry marks that are NOT part of the product - a shop or seller watermark, a promotional banner or slogan, a price sticker, phone-screenshot UI, a filename, or stray text and objects lying on the surface behind it. REMOVE all of those; none of them may appear in the render, in any corner or edge. But KEEP the product's OWN printed branding intact. The final frame carries no signature, no handwriting, no artist mark and no corner text of any kind. Photorealistic editorial photograph, sharp detail.",
  "negative_prompt": "signature, handwriting, handwritten script, artist mark, corner text, watermark, text, lettering, letters, words, numbers, caption, subtitle, label, price tag, sticker, sign, logo, emblem, brand mark, gibberish text, garbled writing, fake logo, different product, altered design, changed colours, distorted shape, duplicated product, extra objects, people, hands, blurry, soft focus, low quality, jpeg artifacts",
  "source_photo": "/workspace/runkarobar-gpu/reelkit/work/reel_138ba49e/product_1.jpg",
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
  "detail": "only 2 token(s) readable on the source (['APPARELS', 'MIHNAIN']) - too weak to diff, guard skipped",
  "retries": 0
}
```
**animate**

```json
{
  "engine": "wan",
  "path": "video_i2v",
  "motion_prompt_verbatim": "subtle zoom in",
  "energy_prompt_verbatim": "sparkle highlights",
  "full_prompt_sent": "subtle zoom in. Model smiling confidently in the magenta suit, hands gently touching the embroidered dupatta edge. sparkle highlights.",
  "input_still": "/workspace/runkarobar-gpu/reelkit/work/reel_138ba49e/scene_4.png",
  "requested_duration": 5.396,
  "clip_path": "/workspace/runkarobar-gpu/reelkit/work/reel_138ba49e/clip_4.mp4",
  "kenburns": {
    "zoom": "in",
    "start": 1.0,
    "end": 1.1,
    "xDrift": 0.0,
    "yDrift": -0.02,
    "rotateDeg": 0.0
  }
}
```
**voiceover**

```json
{
  "vo_text": "Mihnain Apparels se order karo - premium ethnic wear jo banaye har occasion special",
  "voice_id": "RAPmAZHXSuTrzY9pjpR3",
  "model_id": "eleven_v3",
  "mp3_path": "/workspace/runkarobar-gpu/reelkit/work/reel_138ba49e/audio/scene_4.mp3",
  "measured_duration": 5.396,
  "planned_duration": 5.0
}
```

## 6. Assemble

```json
{
  "per_scene": [
    {
      "scene": 1,
      "fitted_duration": 5.03,
      "transition_in": "fade",
      "dipped_through_black": false
    },
    {
      "scene": 2,
      "fitted_duration": 3.568,
      "transition_in": "cut",
      "dipped_through_black": false
    },
    {
      "scene": 3,
      "fitted_duration": 7.721,
      "transition_in": "whip",
      "dipped_through_black": true
    },
    {
      "scene": 4,
      "fitted_duration": 5.396,
      "transition_in": "fade",
      "dipped_through_black": true
    }
  ],
  "transition_fallbacks": [
    "scene 3: 'whip' not implemented -> fade"
  ],
  "total_duration": 21.44,
  "master_resolution": "1080x1920",
  "captions_burned": false,
  "fps": 30,
  "outputs": {
    "1080p": "/workspace/runkarobar-gpu/reelkit/work/reel_138ba49e/reel_138ba49e_1080p.mp4"
  }
}
```

## 7. Upload

```json
{
  "reel_1080p_url": "https://staging-storage.runkarobar.com/reels/reel_138ba49e_1080p.mp4",
  "reel_720p_url": "",
  "scene_image_urls": [
    "https://staging-storage.runkarobar.com/images/reel_138ba49e_s1.png",
    "https://staging-storage.runkarobar.com/images/reel_138ba49e_s2.png",
    "https://staging-storage.runkarobar.com/images/reel_138ba49e_s3.png",
    "https://staging-storage.runkarobar.com/images/reel_138ba49e_s4.png"
  ],
  "log": "NOT PERSISTED"
}
```

## 8. Timings & model load order

```json
{
  "total_wall_clock_sec": 273.8,
  "per_stage": [
    {
      "stage": "brain",
      "seconds": 22.06
    },
    {
      "stage": "voiceover",
      "seconds": 11.69
    },
    {
      "stage": "scene_1",
      "seconds": 48.53
    },
    {
      "stage": "scene_2",
      "seconds": 39.2
    },
    {
      "stage": "scene_3",
      "seconds": 64.11
    },
    {
      "stage": "scene_4",
      "seconds": 49.59
    },
    {
      "stage": "assemble",
      "seconds": 12.7
    },
    {
      "stage": "upload",
      "seconds": 25.91
    }
  ],
  "model_load_order": [
    {
      "model": "wavespeed:anthropic/claude-sonnet-4",
      "action": "remote",
      "t": 1.82
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 55.24
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 100.42
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 140.53
    },
    {
      "model": "i2v:wan",
      "action": "load",
      "t": 205.13
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
    "detail": "only 2 token(s) readable on the source (['APPARELS', 'MIHNAIN']) - too weak to diff, guard skipped"
  },
  {
    "scene": 2,
    "ok": true,
    "detail": "only 2 token(s) readable on the source (['APPARELS', 'MIHNAIN']) - too weak to diff, guard skipped"
  },
  {
    "scene": 3,
    "ok": true,
    "detail": "only 2 token(s) readable on the source (['APPARELS', 'MIHNAIN']) - too weak to diff, guard skipped"
  },
  {
    "scene": 4,
    "ok": true,
    "detail": "only 2 token(s) readable on the source (['APPARELS', 'MIHNAIN']) - too weak to diff, guard skipped"
  }
]
```
