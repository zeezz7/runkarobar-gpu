"""
Stage 0 - the brain: turns (product images + brief + config) into a storyboard.

Model: REMOTE. A single WaveSpeed any-llm/vision call (see wavespeed.py) does
the whole job - it looks at the product photographs and writes the storyboard in
one shot. Pick the model with WAVESPEED_BRAIN_MODEL.

This used to be a local Qwen2.5-Instruct checkpoint (14B active, 32B kept) fed
by Qwen2.5-VL captions. That path is DELETED, deliberately:
  * it cost ~16 GB of VRAM that had to be explicitly freed before the image
    models could load, and two production OOMs came from getting that wrong;
  * load + caption + generate ran into minutes; the remote call is seconds;
  * neither Qwen2.5-14B nor Qwen2.5-32B is installed on the box any more.
Do NOT reintroduce a local brain. The 7B Qwen2.5-VL that remains on disk is the
Stage 2b guard (validate_image.py) - it does OCR-diff only, costs no API spend,
and must never write storyboards.

Because the brain is now a vision model, the separate captioning pass is gone
too: the photographs go straight to it. That is one billed call per reel.

Design rules from the brief that are enforced here:
  * strict JSON out, validated against a schema, up to 3 retries on malformed
    output (a retry is another billed call - see storyboard());
  * scene count scales with length (~1 scene per 4-6s) and total durationSec
    must land within +/-1s of config.lengthSec;
  * `energy` is FREE TEXT chosen by the model. There are no keyword lists, no
    per-product branches and no hardcoded effects anywhere in this pipeline -
    the executor renders whatever the brain writes.
"""
import json
import os
import re

import common
import wavespeed

# The remote brain. Overridable so the model can be changed without a code edit.
# Read at CALL time, not import time: common.load_env() often runs after this
# module is imported, so a module-level read would miss /workspace/.env.
DEFAULT_BRAIN_MODEL = "anthropic/claude-sonnet-4"


def brain_model():
    return os.environ.get("WAVESPEED_BRAIN_MODEL") or DEFAULT_BRAIN_MODEL


VL_DIR = os.environ.get(
    "QWEN_VL_DIR", "/workspace/models/qwen2.5-vl/Qwen2.5-VL-7B-Instruct")

GOALS = {"reveal", "showcase", "detail", "wear", "lifestyle", "cta"}
# goals whose whole point is showing the real product
PRODUCT_GOALS = {"reveal", "showcase", "detail", "wear", "cta"}
# "lipsync" is still a valid storyboard value, but NOTHING can render it on this
# box today: the remote avatar service was removed (all pixels are generated
# locally - see avatar.py) and no local lip-sync model is installed. Any lipsync
# scene is therefore downgraded to edit_animate in validate(), which renders a
# real person shot through Wan i2v - they just do not mouth the words.
# Re-enable by adding a template here ONCE avatar.lipsync() works locally.
METHODS = {"compose_animate", "generate_animate", "edit_animate", "lipsync"}
LIPSYNC_TEMPLATES = set()
MODES = {"product", "scene"}
TRANSITIONS = {"cut", "fade", "whip", "zoom"}

SYSTEM = (
    "You are a senior creative director for short vertical product ads. "
    "You reply with a single JSON object and nothing else - no prose, no markdown fence."
)

TEMPLATE = """Write the storyboard for a vertical social ad.

BRIEF: {brief}
BRAND: {brand}
LANGUAGE: {language}
TOTAL LENGTH: {length} seconds
PRODUCT: study the attached photograph(s). Read every word printed on the
packaging and treat that text as the only source of truth about the product -
the voiceover may claim nothing that is not printed there.

Return EXACTLY this JSON shape:
{{
  "concept": "<one-line creative concept>",
  "voice": "<voice direction, e.g. 'male energetic Hinglish'>",
  "scenes": [
    {{
      "n": 1,
      "goal": "reveal|showcase|detail|wear|lifestyle|cta",
      "method": "edit_animate|compose_animate|generate_animate|lipsync",
      "mode": "product|scene",
      "visual": "<the on-screen shot - the START frame of the scene>",
      "visualEnd": "<the END frame: SAME model/product/outfit, only pose/angle/framing changed (a clear motion delta). Also the next scene's start. Empty if not using directed motion.>",
      "background": "<ONLY the setting/environment for this shot - the place, surface, light and mood. Never mention the product, clothing or any person.>",
      "motion": "<camera move, e.g. 'slow push-in', 'orbit', 'crane down'>",
      "sfx": "<SHORT natural foley for this scene, e.g. 'soft fabric movement', 'water droplet splash', 'gentle shimmer'. Diegetic ONLY - NO music/melody/instruments/beat. Empty for silent.>",
      "energy": "<a visual effect such as 'water splash' or 'rising steam', or empty string for clean>",
      "transitionIn": "cut|fade|whip|zoom",
      "durationSec": 4,
      "motionEngine": "video",
      "kenburns": {{"zoom": "in", "start": 1.0, "end": 1.12, "xDrift": 0.0, "yDrift": -0.05, "rotateDeg": 0.0}},
      "vo": "<the spoken line for this scene, in {language}>"
    }}
  ],
  "badges": [{{"text": "<short on-screen badge, max 16 chars>", "color": "#RRGGBB"}}],
  "notes": "<director rationale>"
}}

HARD REQUIREMENTS
- {nmin} to {nmax} scenes. The scene durationSec values MUST sum to {length} (+/-1).
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
- "vo" must be written in {language} and MUST fit its durationSec when spoken.
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
  written in {language}. If {language} is "hinglish", write natural spoken Hinglish -
  Hindi sentence structure in Latin script, mixing in the English words an Indian ad
  would actually use (e.g. "Subah ki freshness, har din - deep clean, aloe vera ke
  saath"). Do NOT fall back to plain English. If {language} is "hi" or "ur", write in
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
Return only the JSON object."""



# ---------------------------------------------------------------- templates
# A template is a CREATIVE-DIRECTION PRESET, not a pipeline. It only appends a
# style directive to the prompt this module already builds, plus soft defaults
# the brain is asked to honour. The storyboard JSON schema is unchanged and the
# renderer (compose -> animate -> guard -> VO -> assemble -> upload) never sees
# the template at all.
#
#   "ai-director" (the default) injects nothing, so its output is identical to
#   the behaviour before templates existed.
#   Every `defaults` key is consumed generically by the executor - compose.py
#   reads anchorModel/mirrorSelfie/presenterFace to pick guard clauses,
#   animate.py reads preferMethod to decide whether a scene is lip-synced, and
#   make_reel reads lengthSec/forceFemaleVoice/wantsBadges. Nothing branches on
#   what the product is.
TEMPLATES = {
    "ai-director": {
        "persona": "",
        "defaults": {},
    },
    "showcase": {
        "persona": (
            "Clean, minimal, premium product showcase. Let the product be the hero "
            "with elegant hero shots and subtle camera moves. Minimal on-screen text. "
            "Calm, confident, aspirational tone. No gimmicks. Vary the framing across "
            "scenes - a hero, a tight macro on the key detail (texture, stitching, "
            "hardware, stones), and a styled lifestyle beat - never three of the same "
            "shot. Stage the product on a tasteful real surface with soft depth, "
            "never a flat solid-colour wall."),
        "defaults": {"sceneBias": 3, "wantsBadges": False, "wantsCta": False,
                     "motionStyle": "subtle", "lengthSec": 15},
    },
    "ad": {
        "persona": (
            "High-energy direct-response ad fronted by a brand presenter. Hook the "
            "viewer in the first 2 seconds, state one clear benefit, and end on a "
            "strong call to action. Punchy, bold, fast. "
            "Scene 1 is the PRESENTER: a friendly, confident female presenter facing "
            "camera, holding or wearing the product, addressing the viewer - use "
            "method 'edit_animate' with mode 'scene', and write its vo as the words "
            "she is saying. The remaining scenes are product beats that sell the "
            "benefit, with energy where it genuinely fits the product. "
            "Also propose 2-3 short on-screen badges in the storyboard's 'badges' "
            "array - a price, an offer or a one-word benefit (e.g. '₹499', 'FREE "
            "SHIPPING', 'LIMITED'). Keep each under 16 characters."),
        "defaults": {"sceneBias": 4, "wantsBadges": True, "wantsCta": True,
                     "motionStyle": "dynamic", "lengthSec": 20,
                     "forceFemaleVoice": True, "presenterFace": True,
                     "anchorModel": True},
    },
    "unboxing": {
        "persona": (
            "Anticipation-first reveal. Open on the closed packaging or box with the "
            "product still hidden, build a moment of suspense, then reveal the product "
            "as the payoff hero shot. Tactile and satisfying - hands opening a lid, a "
            "sleeve sliding off, tissue parting. The reveal scene must be the "
            "sharpest, most premium frame in the reel."),
        "defaults": {"sceneBias": 4, "revealFirst": True, "wantsCta": True,
                     "motionStyle": "reveal", "lengthSec": 20},
    },
    "outfit-check": {
        "persona": (
            "A first-person 'outfit check' mirror-selfie reel, the way it is actually "
            "posted: ONE confident woman standing in front of a large full-length "
            "mirror in a tastefully styled modern room, holding her phone up to take "
            "the mirror photo, wearing the exact outfit, visible head-to-toe. "
            "The SAME woman carries every scene - she never changes. Each scene is a "
            "fresh beat: establish the full look, then turn to a flattering "
            "three-quarter angle, then a closer waist-up framing on the fabric and "
            "detailing, ending on a confident look to camera. She keeps the phone "
            "raised in every shot. "
            "Write the vo as casual, trendy FIRST-PERSON lines - 'obsessed with this "
            "fit', 'the drape on this is unreal' - like a real girl showing off her "
            "outfit, NOT an ad read. The last line is a call to action to shop. "
            "She is TALKING to camera while she films - write each vo as the exact "
            "words she says, and keep every line short enough to say comfortably "
            "within the scene's durationSec."),
        "defaults": {"sceneBias": 3, "preferMode": "scene", "wantsCta": True,
                     "motionStyle": "dynamic", "lengthSec": 30,
                     "forceFemaleVoice": True, "anchorModel": True,
                     "mirrorSelfie": True, "presenterFace": True},
    },
    "testimonial": {
        "persona": (
            "Authentic UGC testimonial. ONE real-feeling person talks straight to "
            "camera about the product like a friend's recommendation - warm, honest, "
            "specific, a little imperfect. Not a polished ad read. "
            "EVERY scene is that person talking to camera: use method 'edit_animate' "
            "with mode 'scene', and write each vo as the exact words they say. The "
            "same person throughout. Cut away only if a scene genuinely needs to show "
            "the product detail they are describing."),
        "defaults": {"sceneBias": 3, "wantsCta": True, "lengthSec": 20,
                     "presenterFace": True, "anchorModel": True},
    },
}
DEFAULT_TEMPLATE = "ai-director"


def resolve_template(name):
    """Unknown or missing -> the default. Never raises."""
    key = (name or DEFAULT_TEMPLATE).strip().lower()
    if key not in TEMPLATES:
        common.log("brain", f"unknown template {name!r} - falling back to "
                            f"'{DEFAULT_TEMPLATE}'")
        key = DEFAULT_TEMPLATE
    return key, TEMPLATES[key]


# StaffHQ's "What's in the video" radio. FALSE IS THE DEFAULT and means product
# only - no people, no hands, no model anywhere. True means a real person
# features with the product (wears / holds / uses it).
#
# This is a PRESET INPUT, exactly like the template: it changes what the brain is
# asked for, and the executor renders whatever comes back. There is no
# per-product branch anywhere.
PEOPLE_RULE_OFF = (
    "\n\nWHO IS ON SCREEN - HARD RULE, overrides the style directive above:\n"
    "  This reel is PRODUCT ONLY. NO people, NO model, NO hands, NO fingers, NO "
    "arms, NO reflections of a person, NO silhouettes - nobody appears in ANY "
    "scene. Do not describe anyone wearing, holding, touching, opening or using "
    "the product. If the supplied photograph contains a person, your scenes must "
    "re-stage the product WITHOUT them - on a surface, a stand, a mannequin-free "
    "display, or floating in a lit set.\n"
    "  Every scene's mode must be \"product\", and \"visual\" must describe the "
    "product and its setting only.")
PEOPLE_RULE_ON = (
    "\n\nWHO IS ON SCREEN:\n"
    "  The SAME real person wears/holds the product ON-BODY in EVERY scene, from "
    "the VERY FIRST frame (same face, hair, build throughout). Never open on an "
    "empty/flat garment and have a person appear later, and never let them vanish. "
    "Fully and modestly dressed in every shot.")


def people_directive(include_human):
    return PEOPLE_RULE_ON if include_human else PEOPLE_RULE_OFF


DIRECTED_MOTION_RULE = (
    "\n\nDIRECTED MOTION: each scene morphs from 'visual' (first frame) to "
    "'visualEnd' (last frame), and a scene's 'visualEnd' is the NEXT scene's first "
    "frame. So: (1) SAME cast in both - if a person is in 'visual' the same person "
    "is in 'visualEnd'; if 'visual' is product-only, 'visualEnd' is too. A person "
    "must never appear or vanish between them. (2) 'visualEnd' must be a CLEARLY "
    "different pose/angle/framing (front->3/4 turn, wide->macro detail) - not a "
    "near-identical frame. (3) Match each 'visualEnd' to the next scene's 'visual', "
    "and make every scene a distinct shot (vary distance and angle).")


def _template_directive(key, spec, nmin, nmax):
    """Render the style directive block appended to the existing prompt."""
    persona = (spec.get("persona") or "").strip()
    if not persona and not spec.get("defaults"):
        return ""                       # ai-director: inject nothing at all

    lines = [f"\n\nSTYLE DIRECTIVE (template: {key}):", persona]
    d = spec.get("defaults") or {}
    guidance = []
    if d.get("sceneBias"):
        guidance.append(f"aim for about {d['sceneBias']} scenes (stay within "
                        f"{nmin}-{nmax})")
    if d.get("motionStyle"):
        guidance.append(f"favour {d['motionStyle']} camera movement")
    if d.get("wantsCta") is True:
        guidance.append("end on an explicit call to action in the final scene's vo")
    if d.get("wantsCta") is False:
        guidance.append("do not use a hard call to action; let the product speak")
    if d.get("wantsBadges") is True:
        guidance.append("you may work a short benefit claim into the vo lines")
    if d.get("wantsBadges") is False:
        guidance.append("keep the vo sparse; avoid claim badges and slogans")
    if d.get("revealFirst"):
        guidance.append("scene 1 must build anticipation before the product is fully "
                        "revealed; the reveal is the payoff")
    if d.get("preferMode") == "scene":
        guidance.append("favour scenes with a person using or wearing the product "
                        "over isolated packshots")
    if d.get("preferMethod") == "lipsync":
        guidance.append("write the vo as first-person speech from a person on camera, "
                        "as if they are speaking the line themselves")
    if guidance:
        lines.append("Follow these unless the brief says otherwise:")
        lines += [f"  - {g}" for g in guidance]
    lines.append("The brief always outranks this directive. You still choose the "
                 "scene count, methods, energy, motion and wording yourself.")
    return "\n".join(lines)


# ------------------------------------------------------------- product images
def product_image_urls(product_images, image_urls=None):
    """
    Resolve what the remote brain will actually be shown.

    any-llm/vision takes URLs only - there is no base64 path - so a purely local
    file cannot be sent. make_reel already has the caller's original URLs, so it
    passes them straight through; the local copies it downloaded are only for
    the renderers. A local-only run therefore has nothing to show the brain, and
    that is worth saying out loud rather than silently writing a storyboard for
    a product the model never saw.
    """
    urls = [u for u in (image_urls or []) if str(u).startswith(("http://", "https://"))]
    if urls:
        return urls[:16]
    local = [p for p in (product_images or [])
             if not str(p).startswith(("http://", "https://"))]
    if local:
        common.log("brain", f"WARNING: {len(local)} product image(s) are local files "
                            f"with no public URL - the brain will write BLIND. Pass "
                            f"image_urls, or host them, for a product-aware storyboard.")
    return []


def unload_brain():
    """
    No-op. Kept so existing callers do not break.

    There is no local brain to unload any more - Stage 0 is a remote call and
    holds zero VRAM. This used to free ~16 GB before the image models loaded.
    """
    common.log("brain", "no local brain to unload (remote WaveSpeed brain)")


# ------------------------------------------------------------------ validate
def _extract_json(text):
    t = re.sub(r"^\s*```(?:json)?|```\s*$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    depth = start = None
    depth = 0
    for i, ch in enumerate(t):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(t[start:i + 1])
                except json.JSONDecodeError:
                    start = None
    raise ValueError("no JSON object in model output")


def _clean_kenburns(kb):
    """
    Optional per-scene camera numbers. The brain hands us machine-usable values
    so the executor never has to interpret prose. Malformed or out-of-range
    values are dropped (-> None) rather than failing the whole storyboard; the
    renderer then falls back to its gentle default push-in.
    """
    if not isinstance(kb, dict):
        return None
    def num(key, lo, hi, default):
        try:
            v = float(kb.get(key, default))
        except (TypeError, ValueError):
            return default
        return max(lo, min(hi, v))
    start = num("start", 0.9, 1.6, 1.0)
    end = num("end", 0.9, 1.6, 1.12)
    rot = num("rotateDeg", -12.0, 12.0, 0.0)
    if abs(end - start) < 0.005:                     # no movement -> use zoom hint
        end = start - 0.10 if str(kb.get("zoom", "in")).lower() == "out" else start + 0.12
        end = max(0.9, min(1.6, end))
    # a rotated frame exposes black corners unless we overscan a little
    if abs(rot) > 0.2:
        start = max(start, 1.12)
        end = max(end, 1.12)
    return {"zoom": "out" if end < start else "in",
            "start": round(start, 4), "end": round(end, 4),
            "xDrift": round(num("xDrift", -0.2, 0.2, 0.0), 4),
            "yDrift": round(num("yDrift", -0.2, 0.2, 0.0), 4),
            "rotateDeg": round(rot, 3)}


def validate(sb, length, template=None, include_human=True):
    """Raise ValueError with a specific reason the model can act on."""
    if not isinstance(sb, dict):
        raise ValueError("top level is not an object")
    for k in ("concept", "voice", "scenes"):
        if k not in sb:
            raise ValueError(f"missing key '{k}'")
    scenes = sb["scenes"]
    if not isinstance(scenes, list) or not 2 <= len(scenes) <= 8:
        raise ValueError("'scenes' must be a list of 2-8 scenes")
    total = 0.0
    for i, sc in enumerate(scenes, 1):
        sc.setdefault("background", "")
        for k in ("goal", "method", "mode", "visual", "motion",
                  "transitionIn", "durationSec", "vo"):
            if k not in sc:
                raise ValueError(f"scene {i} missing '{k}'")
        sc["n"] = i
        sc.setdefault("energy", "")
        # Optional fields for directed-motion (visualEnd) and sound effects (sfx).
        # Absent on older brain output / when the feature is off -> harmless
        # empty string, and the renderer falls back to classic single-still I2V
        # and a silent track respectively.
        sc.setdefault("visualEnd", "")
        sc.setdefault("sfx", "")
        if sc["method"] not in METHODS:
            raise ValueError(f"scene {i} method must be one of {sorted(METHODS)}")
        if sc["mode"] not in MODES:
            raise ValueError(f"scene {i} mode must be one of {sorted(MODES)}")
        if sc["goal"] not in GOALS:
            raise ValueError(f"scene {i} goal must be one of {sorted(GOALS)}")
        # generate_animate never involves the real product, so a scene that is
        # meant to SHOW the product cannot use it - otherwise the ad renders a
        # different item than the one being sold (observed: scene 1 of a Snitch
        # reel showed an entirely invented polo).
        if sc["method"] == "generate_animate":
            if sc["goal"] in PRODUCT_GOALS:
                raise ValueError(
                    f"scene {i} has goal '{sc['goal']}' which shows the product, so it "
                    f"cannot use generate_animate - use edit_animate instead")
            if sc["mode"] == "product":
                raise ValueError(
                    f"scene {i} is mode 'product' so it cannot use generate_animate - "
                    f"use edit_animate instead")
        if sc["transitionIn"] not in TRANSITIONS:
            raise ValueError(f"scene {i} transitionIn must be one of {sorted(TRANSITIONS)}")
        try:
            sc["durationSec"] = float(sc["durationSec"])
        except (TypeError, ValueError):
            raise ValueError(f"scene {i} durationSec must be a number")
        total += sc["durationSec"]
        sc["kenburns"] = _clean_kenburns(sc.get("kenburns"))
        eng = str(sc.get("motionEngine", "video")).lower()
        sc["motionEngine"] = eng if eng in ("kenburns", "video") else "video"
    if abs(total - length) > 1.0:
        raise ValueError(
            f"scene durations sum to {total:.1f}s but must sum to {length}s (+/-1)")
    # A reel of zooming stills looks cheap. Wan i2v is what makes a shot read as
    # footage, so cap the still-image engine at a single scene.
    kb_scenes = [s for s in scenes if s.get("motionEngine") == "kenburns"]
    if kb_scenes:
        raise ValueError(
            f"scenes {[s['n'] for s in kb_scenes]} use motionEngine 'kenburns'. "
            f"Every scene must be a real animated shot - set motionEngine to 'video'")
    if not any(s["method"] in ("compose_animate", "edit_animate", "lipsync")
               for s in scenes):
        raise ValueError("at least one scene must use 'edit_animate' or "
                         "'compose_animate' so the real product appears")
    # lipsync is billed per scene by a remote avatar model, so it is allowed ONLY
    # where the template asked for it. A brain that volunteers it anywhere else
    # gets the scene downgraded rather than the whole storyboard rejected - the
    # shot is still renderable, just without the talking head.
    if template not in LIPSYNC_TEMPLATES:
        for sc in scenes:
            if sc["method"] == "lipsync":
                common.log("brain", f"scene {sc['n']}: lipsync is not enabled for "
                                    f"template {template!r} - rendering as edit_animate")
                sc["method"] = "edit_animate"

    # Badges are on-screen text chips (assemble.py burns them). Clamp hard: they
    # are drawn at a fixed size, so a long string runs off frame.
    badges = sb.get("badges")
    clean_badges = []
    if isinstance(badges, list):
        for b in badges[:6]:
            if not isinstance(b, dict):
                continue
            text = str(b.get("text") or "").strip()[:16]
            if not text:
                continue
            colour = str(b.get("color") or "").strip()
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", colour):
                colour = ""
            clean_badges.append({"text": text, "color": colour})
    sb["badges"] = clean_badges

    # Enforce the people rule rather than trusting the prompt: a "just the
    # product" reel that renders a hand is the single most visible way to get
    # this wrong, and the brain gets a specific complaint it can act on.
    if not include_human:
        bad = [s_["n"] for s_ in scenes if s_.get("mode") == "scene"]
        if bad:
            raise ValueError(
                f"scenes {bad} use mode 'scene' but this reel is PRODUCT ONLY "
                f"(includeHuman is false) - every scene must be mode 'product' "
                f"with nobody on screen")
        # Person indicators only. "face" and "neck" are deliberately NOT blanket
        # matches: they collide with product words (a FACE wash, a bottle NECK),
        # so "face" is flagged only when it is NOT a product phrase, and "neck"
        # is dropped. The real human-free enforcement is downstream anyway (the
        # ghost-mannequin edit removes any person, and the Sonnet gate checks the
        # rendered stills), so this text check just catches the obvious cases.
        human = re.compile(
            r"\bface(?!\s*(?:wash|cream|cleanser|cleansing|scrub|mask|serum|gel|"
            r"foam|wipe|care|moistur|oil|pack|lotion|toner|cloth))\b"
            r"|\b(model|person|people|someone|somebody|human|woman|women|girl|"
            r"boy|man|guy|lady|hand|hands|finger|fingers|palm|palms|arm|arms|"
            r"wrist|shoulder|torso|chest|wearing|worn by|holding|held by|holds|"
            r"wears|she|he|her|his|him)\b", re.I)
        for s_ in scenes:
            hit = human.search(f"{s_.get('visual','')} {s_.get('background','')}")
            if hit:
                raise ValueError(
                    f"scene {s_['n']} mentions '{hit.group(0)}' but this reel is "
                    f"PRODUCT ONLY (includeHuman is false) - rewrite it with no "
                    f"person, hands or body parts anywhere")

    sb.setdefault("notes", "")
    return sb


def direct_from_stills(still_urls, sb, config, include_human, product_urls=None,
                       tracer=None):
    """
    The gate AND the director, in one WaveSpeed vision call, AFTER the stills
    exist. Looks at the ACTUAL generated images (not the pre-render plan) and per
    scene returns:
      pass/issue - QA: product intact + human-free when required, and
      motion     - a camera/motion prompt GROUNDED in that real image, and
      vo         - the spoken line, tuned to what's shown while keeping the
                   storyboard's story and any exact call to action.

    Grounding motion + VO in the real pixels is what lifts video quality: the old
    flow wrote motion blind, against a plan the image often didn't match. NEVER
    raises - on any error it falls back to the storyboard's own motion + vo so
    the reel still renders.
    """
    urls = [u for u in (still_urls or []) if u]
    refs = [u for u in (product_urls or []) if u][:1]
    scenes = (sb or {}).get("scenes", [])
    if not urls:
        return []
    human_rule = (
        "There must be NO person/model/face/hands/arms/body - PRODUCT ONLY (a "
        "ghost-mannequin / hollow-garment / flat product shot is correct); a "
        "person appearing is WRONG."
        if not include_human else
        "The SAME real person MUST be present WEARING the product ON-BODY in this "
        "still - NOT a flat, empty or floating garment, and NOT the bare product "
        "alone. pass=false if there is no visible person, if the garment is shown "
        "unworn/flat, or if the person's face or build changes from the other "
        "stills (they must look like the same individual across every scene).")
    length = int(float(config.get("lengthSec") or 20))
    per = max(2, length // max(1, len(urls)))
    draft = "\n".join(f'  scene {s.get("n")}: planned VO "{s.get("vo", "")}"'
                      for s in scenes)
    # Show Sonnet the ORIGINAL product as image 1 so it COMPARES, not guesses.
    # Without it, an all-grey outfit passed when the real product is a magenta
    # kurti (the grey dupatta looked "close enough" from the text alone).
    if refs:
        intro = (f"IMAGE 1 is the REFERENCE PRODUCT - the exact item that MUST "
                 f"appear in every scene. IMAGES 2-{len(urls) + 1} are the "
                 f"generated scene stills, IN ORDER.\n")
        qa = ("the SAME product as IMAGE 1 - same garment type and the SAME "
              "colours (e.g. if the reference is a magenta kurti, an all-grey "
              "outfit or a different dress or a suit is WRONG), same embroidery, "
              "prints and design; no warping or gibberish text")
    else:
        intro = f"Below are the {len(urls)} generated scene stills IN ORDER.\n"
        qa = ("the product intact - correct shape, colours, logos and text; no "
              "warping or gibberish")
    prompt = (
        f"You are QA + director for a {length}s {config.get('language', 'en')} "
        f"product video for {config.get('brandName') or 'the brand'}. "
        f"Concept: {(sb or {}).get('concept', '')}.\n"
        f"{intro}The writer's planned voiceover:\n{draft}\n\n"
        f"For EACH generated scene still, IN ORDER, return:\n"
        f"1. pass/issue - QA. pass=true ONLY if the still shows {qa}; and: "
        f"{human_rule} If the product differs from the reference in any obvious "
        f"way, set pass=false with a short issue.\n"
        f"2. motion - ONE short camera/motion instruction for an image-to-video "
        f"model, grounded in THIS image (its surface, props, light). Premium and "
        f"subtle: a camera move plus any natural motion truly present (droplets, "
        f"steam, reflections). Never invent people or objects not in the image.\n"
        f"3. vo - the spoken line for this scene, ~{per}s of speech. The lines "
        f"together tell ONE story and MUST keep the planned message and any exact "
        f"call to action; the last scene closes it.\n"
        f"Return ONLY a JSON array, ONE object per generated scene (do NOT include "
        f"the reference image), in order:\n"
        f'[{{"scene":1,"pass":true,"issue":"","motion":"...","vo":"..."}}]')
    try:
        raw = wavespeed.chat(prompt, system="You output ONLY strict JSON.",
                             images=refs + urls, model=brain_model(),
                             temperature=0.3, max_tokens=1400)
        data = _extract_json(raw)
        if isinstance(data, dict):
            data = data.get("scenes") or data.get("results") or [data]
        out = []
        for i, item in enumerate(data if isinstance(data, list) else [], 1):
            if not isinstance(item, dict):
                continue
            out.append({"scene": item.get("scene", i),
                        "pass": bool(item.get("pass", True)),
                        "issue": str(item.get("issue") or "")[:120],
                        "motion": str(item.get("motion") or "").strip()[:300],
                        "vo": str(item.get("vo") or "").strip()[:300]})
        if tracer:
            tracer.write_json("sonnet_direction.json",
                              {"prompt": prompt, "raw": raw, "directions": out})
        if out:
            return out
    except Exception as e:
        common.log("validate",
                   f"Sonnet direction failed (non-fatal, using plan): {e}")
    # Fallback: keep the storyboard's own motion + vo, pass everything.
    return [{"scene": s.get("n", i + 1), "pass": True, "issue": "",
             "motion": s.get("motion", ""), "vo": s.get("vo", "")}
            for i, s in enumerate(scenes)]


# ------------------------------------------------------------------- generate
def storyboard(brief, config, product_images, retries=3, tracer=None,
               image_urls=None):
    """
    One WaveSpeed any-llm/vision call per reel (~$0.05).

    `retries` only fires when the returned JSON fails validate(), and each retry
    is another billed call - so the happy path costs exactly one. The retry
    re-sends the images along with the specific complaint, because dropping them
    would make the correction blind to the product.
    """
    length = float(config.get("lengthSec") or 20)
    nmin = max(2, int(round(length / 6)))
    nmax = max(nmin, int(round(length / 4)))
    model = brain_model()
    urls = product_image_urls(product_images, image_urls)
    if tracer:
        tracer.write_text("vision_captions.txt",
                          "Stage 0 is a vision model now - no separate captioning "
                          "pass. Images sent to the brain:\n" + "\n".join(urls))

    tpl_key, tpl_spec = resolve_template(config.get("template"))

    prompt = TEMPLATE.format(
        brief=brief, brand=config.get("brandName") or "the brand",
        language=config.get("language") or "en", length=int(length),
        nmin=nmin, nmax=nmax)
    # Purely additive: ai-director appends nothing, so its prompt - and therefore
    # its output - is byte-identical to the pre-template behaviour.
    directive = _template_directive(tpl_key, tpl_spec, nmin, nmax)
    prompt += directive
    # Appended AFTER the template directive so it wins: a template persona may
    # describe a model in a mirror, but "just the product" must still mean
    # nobody on screen.
    include_human = bool(config.get("includeHuman", False))
    prompt += people_directive(include_human)
    if bool(config.get("directedMotion", False)):
        prompt += DIRECTED_MOTION_RULE
    # SAFETY CLAMP: WaveSpeed hard-caps the prompt at 10000 chars and 400s the
    # whole call if exceeded (a rich directed-motion + style prompt, or a very long
    # user brief, can approach it). Clamp with margin so a reel can never die on
    # prompt length - worst case we drop the tail, the brain still runs.
    MAX_PROMPT = 9800
    if len(prompt) > MAX_PROMPT:
        common.log("brain", f"prompt {len(prompt)} chars > {MAX_PROMPT} - clamping "
                            f"(WaveSpeed caps at 10000)")
        prompt = prompt[:MAX_PROMPT]
    common.log("brain", f"includeHuman={include_human} - "
                        + ("a person features with the product"
                           if include_human else "PRODUCT ONLY, nobody on screen"))
    common.log("brain", f"template '{tpl_key}'"
                        + (f" (+{len(directive)} chars of style directive)"
                           if directive else " (no directive - default behaviour)"))
    if tpl_spec.get("defaults", {}).get("presenterFace"):
        common.log("brain", f"template '{tpl_key}' fronts a presenter; every shot "
                            f"renders locally (Wan i2v) - no lip-sync model is "
                            f"installed, so mouths will not track the voiceover")

    if tracer:
        tracer.write_text("brain_prompt.txt",
                          f"===== SYSTEM =====\n{SYSTEM}\n\n===== USER =====\n{prompt}\n"
                          f"\n===== IMAGES =====\n" + "\n".join(urls))
        tracer.model(f"wavespeed:{model}", "remote")

    common.log("brain", f"remote brain {model} via WaveSpeed"
                        f"{f' + {len(urls)} image(s)' if urls else ' (no images)'}")
    last_err = None
    for attempt in range(1, retries + 1):
        ask = prompt
        if last_err:
            ask += (f"\n\nYour previous answer was rejected: {last_err}\n"
                    f"Return corrected JSON only.")
        raw = wavespeed.chat(ask, system=SYSTEM, images=urls, model=model,
                             temperature=0.85, max_tokens=1600)
        try:
            sb = validate(_extract_json(raw), length, template=tpl_key,
                          include_human=include_human)
            common.log("brain", f"storyboard ok on attempt {attempt}: "
                                f"{len(sb['scenes'])} scenes, "
                                f"{sum(s['durationSec'] for s in sb['scenes']):.0f}s")
            return sb
        except ValueError as e:
            last_err = str(e)
            common.log("brain", f"attempt {attempt} rejected: {last_err}")
    raise RuntimeError(f"brain failed to produce valid storyboard: {last_err}")


if __name__ == "__main__":
    import sys
    common.load_env()
    # Args are product image URLs - the remote brain can only be shown URLs.
    imgs = sys.argv[1:]
    sb = storyboard("15s energetic ad for Nivea Men face wash, fresh gym vibe, male VO",
                    {"lengthSec": 15, "language": "en", "brandName": "Nivea Men"},
                    imgs, image_urls=imgs)
    print(json.dumps(sb, indent=2, ensure_ascii=False))
