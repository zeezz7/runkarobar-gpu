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

# CONDITIONAL, and this matters. The original clause asserted "keep the brand
# name, logo and label fully legible" unconditionally. On a product that HAS
# printed text (a cosmetic tube) that protects it. On one that does NOT (a
# necklace, a ring, a plain garment) it reads as an instruction to PRODUCE
# branding - and Qwen-Image-Edit duly invented a gold "RRBRIAR 107" logo and a
# row of gibberish price tags on a jewellery reel.
# The wording below is safe either way: preserve text IF it exists, never add
# text that does not.
NO_WATERMARK = (
    " If the product carries printed text, a brand name or a logo, keep it EXACTLY "
    "as it appears in the reference and fully legible. Do NOT add, invent or overlay "
    "ANY text, lettering, numbers, brand name, logo, emblem, watermark, sticker, "
    "price tag, label or caption that is not already physically on the product in "
    "the reference photograph. If the product has no text on it, the render must "
    "have no text anywhere.")

# The piece I did NOT port from StaffHQ, and it cost a reel.
# A seller's phone photo routinely carries marks that are NOT the product: a
# shop watermark, a price sticker, a promo banner, screenshot UI, or - as on the
# ruby-necklace source - a dark script-shaped object lying on the surface behind
# the hand. Because every other guard here says "keep it exactly as
# photographed", the editor faithfully carried that mark into the render and
# stylised it into a handwritten signature in the corner.
# So the instruction has to be TWO-SIDED: erase what is on the PHOTO, keep what
# is on the PRODUCT. Dropping either half breaks something - erase everything
# and a real printed label gets blanked; keep everything and the seller's
# watermark ships in the ad.
ERASE_SOURCE_MARK = (
    " The reference photograph may carry marks that are NOT part of the product - "
    "a shop or seller watermark, a promotional banner or slogan, a price sticker, "
    "phone-screenshot UI, a filename, or stray text and objects lying on the "
    "surface behind it. REMOVE all of those; none of them may appear in the "
    "render, in any corner or edge. But KEEP the product's OWN printed branding "
    "intact. The final frame carries no signature, no handwriting, no artist mark "
    "and no corner text of any kind."
    " Do NOT REPLACE a removed mark with anything else - no substitute badge, "
    "banner, ribbon, sticker or caption may take its place. Where a watermark or "
    "banner was, there must be ONLY the scene itself: plain surface, fabric or "
    "background. Erasing a seller's logo and painting your own marketing badge in "
    "the same corner is exactly the failure this clause exists to prevent.")

# The third place text sneaks in, after the product and the corner: the SCENERY.
# Ask for a boutique interior and the model paints a shop sign on the back wall -
# an invented brand ("EXEUJOUN") in a reel for someone else's product. The two
# clauses above only cover the product and the frame edges, so the set has to be
# named explicitly.
NO_SCENE_TEXT = (
    " The SETTING must also be free of writing: no shop sign, no boutique name, no "
    "brand board, no engraved plaque, no printed box lid, no poster, book, tag or "
    "packaging with lettering, and no writing on any wall, mirror, display case or "
    "surface anywhere in the background. Build the scene from materials, light and "
    "texture alone.")

PRODUCT_LOCK = (
    " The product itself MUST be the exact SAME item as the reference - identical "
    "design, colours, materials, shape, proportions and every detail. Do NOT "
    "redesign, restyle, simplify or substitute it. You may re-angle, zoom, crop, "
    "re-light and place it into the new setting the scene describes - but the "
    "product stays faithful.")

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
    parts.append(ERASE_SOURCE_MARK)
    parts.append(NO_SCENE_TEXT)
    parts.append(HARD_MODESTY)          # last, so it wins
    return "".join(parts)


def product_guards():
    """Guards for a scene with no person in it."""
    return PRODUCT_LOCK + NO_WATERMARK + ERASE_SOURCE_MARK + NO_SCENE_TEXT
