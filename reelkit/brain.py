"""
Stage 0 - the brain: turns (product images + brief + config) into a storyboard.

Model: Qwen2.5-32B-Instruct (fp8-dynamic, compressed-tensors). This is a TEXT
instruct model and is deliberately NOT the Qwen2.5-VL-7B vision guard - that 7B
model does OCR-diff only and must never write storyboards.

The brain still needs to SEE the product, so we caption each product image with
the VL model first and feed those captions in as text. That keeps one vision
model on the box doing both jobs it is good at, without letting it direct.

Design rules from the brief that are enforced here:
  * strict JSON out, validated against a schema, up to 3 retries on malformed
    output;
  * scene count scales with length (~1 scene per 4-6s) and total durationSec
    must land within +/-1s of config.lengthSec;
  * `energy` is FREE TEXT chosen by the model. There are no keyword lists, no
    per-product branches and no hardcoded effects anywhere in this pipeline -
    the executor renders whatever the brain writes.
  * the model is unloaded before image/video models are loaded (VRAM).
"""
import gc
import json
import os
import re

import common

BRAIN_DIR = os.environ.get(
    "BRAIN_DIR", "/workspace/models/brain/Qwen2.5-32B-Instruct-FP8-dynamic")
VL_DIR = os.environ.get(
    "QWEN_VL_DIR", "/workspace/models/qwen2.5-vl/Qwen2.5-VL-7B-Instruct")

_model = _tok = None

GOALS = {"reveal", "showcase", "detail", "wear", "lifestyle", "cta"}
METHODS = {"compose_animate", "generate_animate"}
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
PRODUCT (what the supplied photographs actually show):
{captions}

Return EXACTLY this JSON shape:
{{
  "concept": "<one-line creative concept>",
  "voice": "<voice direction, e.g. 'male energetic Hinglish'>",
  "scenes": [
    {{
      "n": 1,
      "goal": "reveal|showcase|detail|wear|lifestyle|cta",
      "method": "compose_animate|generate_animate",
      "mode": "product|scene",
      "visual": "<the on-screen shot description>",
      "motion": "<camera move, e.g. 'slow push-in', 'orbit', 'crane down'>",
      "energy": "<a visual effect such as 'water splash' or 'rising steam', or empty string for clean>",
      "transitionIn": "cut|fade|whip|zoom",
      "durationSec": 4,
      "kenburns": {{"zoom": "in", "start": 1.0, "end": 1.12, "xDrift": 0.0, "yDrift": -0.05}},
      "vo": "<the spoken line for this scene, in {language}>"
    }}
  ],
  "notes": "<director rationale>"
}}

HARD REQUIREMENTS
- {nmin} to {nmax} scenes. The scene durationSec values MUST sum to {length} (+/-1).
- Use "compose_animate" + mode "product" whenever the real product is on screen:
  its true photographed pixels get composited in, so the label stays perfect.
- Use "generate_animate" + mode "scene" only for shots WITHOUT the product
  (pure atmosphere, texture plates, lifestyle b-roll).
- At least one scene must be compose_animate. The final scene should be the cta.
- "vo" must be written in {language} and be speakable in roughly its durationSec.
- "energy" is your free choice per scene - describe the effect in plain words, or
  leave it "" for a clean shot. Do not repeat the same energy in every scene.
- "motion" should vary between scenes; name a concrete camera move.
- "kenburns" gives the EXACT numbers for the camera move on product scenes, so the
  renderer applies them directly instead of guessing from your words:
    zoom   "in" or "out"
    start  starting zoom factor, 1.0 = no zoom (range 0.9-1.6)
    end    ending zoom factor   (range 0.9-1.6; use end<start for a pull-out)
    xDrift horizontal pan across the whole shot, fraction of width  (-0.2 to 0.2)
    yDrift vertical pan across the whole shot, fraction of height   (-0.2 to 0.2)
  Make these match your "motion" wording and vary them per scene. Keep moves
  gentle (a 0.08-0.20 zoom change reads well over 3-5 seconds).
- "vo" lines must be long enough to actually SPEAK for their durationSec at a
  natural ad pace - roughly 2.5 words per second. A 4 second scene needs about
  10 words, not 4.
Return only the JSON object."""


# ------------------------------------------------------------------- captions
def caption_products(image_paths, max_new_tokens=120):
    """Describe each product photo with the VL model so the brain can 'see'."""
    import torch
    from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

    if not os.path.isdir(VL_DIR):
        return [f"(image {i+1}: no vision model available)"
                for i in range(len(image_paths))]

    m = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        VL_DIR, dtype=torch.bfloat16, attn_implementation="sdpa",
        device_map="cuda:0").eval()
    proc = AutoProcessor.from_pretrained(VL_DIR, min_pixels=256*28*28,
                                         max_pixels=1280*28*28)
    caps = []
    for p in image_paths:
        msgs = [{"role": "user", "content": [
            {"type": "image", "path": os.path.abspath(p)},
            {"type": "text", "text":
             "Describe this product in one sentence: what it is, its exact brand "
             "and product name as printed, its colours, shape and packaging. "
             "Be literal and specific."}]}]
        inp = proc.apply_chat_template(msgs, add_generation_prompt=True,
                                       tokenize=True, return_dict=True,
                                       return_tensors="pt").to(m.device)
        with torch.inference_mode():
            out = m.generate(**inp, max_new_tokens=max_new_tokens, do_sample=False,
                             temperature=None, top_p=None, top_k=None)
        txt = proc.batch_decode(out[:, inp["input_ids"].shape[1]:],
                                skip_special_tokens=True)[0].strip()
        caps.append(txt)
        common.log("brain", f"caption: {txt[:110]}")
    del m, proc
    gc.collect()
    torch.cuda.empty_cache()
    return caps


# ---------------------------------------------------------------------- model
def load_brain():
    global _model, _tok
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    if _model is None:
        if not os.path.isdir(BRAIN_DIR):
            raise RuntimeError(f"brain model not found at {BRAIN_DIR}")
        common.log("brain", f"loading {os.path.basename(BRAIN_DIR)}")
        _tok = AutoTokenizer.from_pretrained(BRAIN_DIR)
        _model = AutoModelForCausalLM.from_pretrained(
            BRAIN_DIR, dtype="auto", device_map="cuda:0").eval()
    return _model, _tok


def unload_brain():
    """Free VRAM before the image/video models load."""
    global _model, _tok
    import torch
    _model = _tok = None
    gc.collect()
    torch.cuda.empty_cache()
    common.log("brain", "unloaded")


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
    if abs(end - start) < 0.005:                     # no movement -> use zoom hint
        end = start - 0.10 if str(kb.get("zoom", "in")).lower() == "out" else start + 0.12
        end = max(0.9, min(1.6, end))
    return {"zoom": "out" if end < start else "in",
            "start": round(start, 4), "end": round(end, 4),
            "xDrift": round(num("xDrift", -0.2, 0.2, 0.0), 4),
            "yDrift": round(num("yDrift", -0.2, 0.2, 0.0), 4)}


def validate(sb, length):
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
        for k in ("goal", "method", "mode", "visual", "motion",
                  "transitionIn", "durationSec", "vo"):
            if k not in sc:
                raise ValueError(f"scene {i} missing '{k}'")
        sc["n"] = i
        sc.setdefault("energy", "")
        if sc["method"] not in METHODS:
            raise ValueError(f"scene {i} method must be one of {sorted(METHODS)}")
        if sc["mode"] not in MODES:
            raise ValueError(f"scene {i} mode must be one of {sorted(MODES)}")
        if sc["goal"] not in GOALS:
            raise ValueError(f"scene {i} goal must be one of {sorted(GOALS)}")
        if sc["transitionIn"] not in TRANSITIONS:
            raise ValueError(f"scene {i} transitionIn must be one of {sorted(TRANSITIONS)}")
        try:
            sc["durationSec"] = float(sc["durationSec"])
        except (TypeError, ValueError):
            raise ValueError(f"scene {i} durationSec must be a number")
        total += sc["durationSec"]
        sc["kenburns"] = _clean_kenburns(sc.get("kenburns"))
    if abs(total - length) > 1.0:
        raise ValueError(
            f"scene durations sum to {total:.1f}s but must sum to {length}s (+/-1)")
    if not any(s["method"] == "compose_animate" for s in scenes):
        raise ValueError("at least one scene must use method 'compose_animate'")
    sb.setdefault("notes", "")
    return sb


# ------------------------------------------------------------------- generate
def storyboard(brief, config, product_images, retries=3):
    length = float(config.get("lengthSec") or 20)
    nmin = max(2, int(round(length / 6)))
    nmax = max(nmin, int(round(length / 4)))
    caps = caption_products(product_images)
    captions = "\n".join(f"  - image {i+1}: {c}" for i, c in enumerate(caps))

    prompt = TEMPLATE.format(
        brief=brief, brand=config.get("brandName") or "the brand",
        language=config.get("language") or "en", length=int(length),
        captions=captions, nmin=nmin, nmax=nmax)

    model, tok = load_brain()
    import torch
    last_err = None
    for attempt in range(1, retries + 1):
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt}]
        if last_err:
            msgs.append({"role": "user", "content":
                         f"Your previous answer was rejected: {last_err}. "
                         f"Return corrected JSON only."})
        text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inp = tok([text], return_tensors="pt").to(model.device)
        with torch.inference_mode():
            out = model.generate(**inp, max_new_tokens=1600, do_sample=True,
                                 temperature=0.85, top_p=0.9)
        raw = tok.decode(out[0][inp["input_ids"].shape[1]:], skip_special_tokens=True)
        try:
            sb = validate(_extract_json(raw), length)
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
    imgs = sys.argv[1:] or ["/workspace/bakeoff/ref/nivea_ref.jpg"]
    sb = storyboard("15s energetic ad for Nivea Men face wash, fresh gym vibe, male VO",
                    {"lengthSec": 15, "language": "en", "brandName": "Nivea Men"}, imgs)
    print(json.dumps(sb, indent=2, ensure_ascii=False))
    unload_brain()
