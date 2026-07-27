"""
Prompt guards — the clauses that encode each template's recipe.

Ported from StaffHQ's video-studio.service.ts, where they lived as loose module
constants consumed by hardcoded per-template branches. Here they are data: the
brain folds them into a template's persona, and compose.py appends the person /
product ones generically. Nothing in this file knows what the product IS — that
is the whole point, and adding an `if is_face_wash` here would break it.

Each constant exists because a specific failure was observed:

  COLOR_LOCK        one garment piece got "harmonised" to another (a black
                    shalwar drifting purple to match the dupatta)
  WEAR_GUARD        the catalog's display prop came along - a dupatta on a
                    stand, a coat hanger - into a lifestyle scene
  MODESTY_GUARD     applies to EVERY person scene, all templates
  HARD_MODESTY      appended LAST so it beats revealing wording that slipped
                    into an AI-written visual
  SAME_MODEL        the anchor clause - the reason one person carries a reel
  MIRROR_PHONE      she turned and was suddenly empty-handed mid-selfie
  PRESENTER_FACE    lip-sync needs an unobstructed mouth to drive
  PRODUCT_LOCK      lock identity while PERMITTING re-framing (the opposite of
                    COLOR_LOCK, which locks the frame too)
  SCENE_LEAD        without it the editor just re-outputs the reference photo
                    and every "new" scene looks like the flat catalog shot
"""
import re

COLOR_LOCK = (
    " CRITICAL: every garment piece keeps its OWN exact colour from the reference "
    "- never recolour, tint or harmonise one piece to match another (e.g. if the "
    "trousers are black and the dupatta is purple, the trousers stay black and the "
    "dupatta stays purple).")

WEAR_GUARD = (
    " The model WEARS the complete outfit, with any dupatta or scarf draped "
    "naturally on the body. Show ONLY the person wearing it - absolutely no "
    "clothing rack, coat stand, hanger, mannequin or separately-displayed garment "
    "anywhere in the frame.")

MODESTY_GUARD = (
    " STRICT: the person must be fully and MODESTLY dressed at all times - "
    "absolutely no nudity, no cleavage, no bare shoulders, midriff or legs, and no "
    "revealing, tight, sheer or sexy clothing. Keep it decent, elegant and "
    "family-friendly.")

HARD_MODESTY = (
    " ABSOLUTE REQUIREMENT - override any other wording: the person wears a "
    "high-necked, fully-covering outfit that completely covers the chest, "
    "cleavage, shoulders, midriff and legs. NO exposed skin below the collarbone, "
    "NO cleavage, NO revealing, low-cut, plunging, strapless, off-shoulder or "
    "sheer clothing. If a necklace is worn it rests on a COVERED high neckline. "
    "Decent, elegant, family-friendly ONLY.")

# Words that push an AI-written `visual` toward nudity. Neutralised before the
# scene is composed - cheaper and more reliable than rejecting the render after.
REVEALING_TERMS = re.compile(
    r"d[eé]collet[ae]ge|cleavage|low[-\s]?cut|plunging|strapless|"
    r"off[-\s]?shoulder|bare (chest|shoulders?|skin|midriff|back)|midriff|"
    r"topless|nude|naked|lingerie|bikini|sheer|see[-\s]?through|revealing|"
    r"exposed (chest|skin|d[eé]collet)", re.I)

SAME_MODEL = (
    " Use the SAME person as in the FIRST reference image - identical face, hair, "
    "skin tone and body - only the pose, angle or framing changes.")

MIRROR_PHONE = (
    " She is taking a mirror selfie and keeps her phone raised in one hand in this "
    "shot too - never empty-handed.")

MIRROR_PRODUCT_GUARD = (
    " The outfit MUST be an EXACT replica of the one in the reference photo - "
    "identical colour on every piece, identical embroidery or print pattern, motif "
    "placement, borders, neckline, sleeves, hem and fabric texture. Do NOT "
    "redesign, restyle, simplify, recolour, add or remove ANY detail - only the "
    "pose, angle or framing may change. Do not invent an unseen back or print.")

PRESENTER_FACE = (
    " The presenter faces the camera directly with a clear, well-lit, UNOBSTRUCTED "
    "front view of the whole face (both eyes and the mouth fully visible) - the "
    "product must not cover the face - a natural, confident expression ready to "
    "speak to the viewer.")

NO_WATERMARK = (
    " Keep the product - INCLUDING its own printed brand name, logo and label - "
    "exactly as the reference and fully legible; do not add any new overlaid text, "
    "watermark or logo of your own, and do not blank or replace the product's real "
    "branding.")

PRODUCT_LOCK = (
    " The product itself MUST be the exact SAME item as the reference - identical "
    "design, colours, materials, shape AND all of its OWN printed branding: keep "
    "the real brand name, logo and label text exactly as they are and fully "
    "legible. Do NOT invent, restyle, swap or blank out any logo, emblem, label or "
    "text, and NEVER turn it into a generic unbranded version. You may re-angle, "
    "zoom, crop, re-light and place it into the new setting the scene describes - "
    "but the product and its branding stay faithful.")

SCENE_LEAD = (
    "Create a NEW, original cinematic advertising shot as described below - freshly "
    "framed, lit, angled and composed for this specific moment. Do NOT simply "
    "reproduce, lightly edit or re-output the reference photo; build a genuinely "
    "new scene. ")


def desexualise(text):
    """Strip revealing wording from an AI-written visual before it is rendered."""
    if not text:
        return text
    return REVEALING_TERMS.sub("modestly dressed", text)


def person_guards(template_defaults=None, is_followon=False):
    """
    Assemble the guard clauses for a scene that contains a PERSON.

    Modesty applies to every template. The rest are switched on by the
    template's own defaults, so this stays a preset lookup and never a
    per-product branch.
    """
    d = template_defaults or {}
    parts = [WEAR_GUARD, COLOR_LOCK, MODESTY_GUARD]
    if d.get("mirrorSelfie"):
        parts.append(MIRROR_PRODUCT_GUARD)
        parts.append(MIRROR_PHONE)
    if d.get("presenterFace"):
        parts.append(PRESENTER_FACE)
    if is_followon and d.get("anchorModel"):
        parts.append(SAME_MODEL)
    parts.append(HARD_MODESTY)          # last, so it wins
    return "".join(parts)


def product_guards():
    """Guards for a scene with no person in it."""
    return PRODUCT_LOCK + NO_WATERMARK
