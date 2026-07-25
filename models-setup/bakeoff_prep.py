#!/usr/bin/env python
"""
Build the run-ready bake-off workflows from the validated base workflows.

Two modes:
  --ref  <filename-in-ComfyUI/input>    build PART A (HiDream-E1.1 product hero)
  --hero <filename-in-ComfyUI/input>    build PART B (all video models)

Everything is derived from the saved, schema-validated workflows in workflows/
so the bake-off cannot drift from what was verified.

Normalisation for comparability
-------------------------------
All video jobs target ~5 s. Frame counts are quantised differently per model and
are silently floored if you pass a bad value, so each is set to a legal value:
    Wan 2.2      length 81  @16 fps = 5.06 s   (4n+1)
    LTX-0.9.8    length 121 @24 fps = 5.04 s   (4n+1)
    LTX-2.3      duration 5 s @25 fps          (driven by its own primitives)
    Hunyuan      length 121 @24 fps = 5.04 s   (4n+1)
    Mochi 1      length 121 @24 fps = 5.04 s   (6n+1 -> 121 = 6*20+1)
Resolution is normalised to 832x480 where the model allows it. LTX-2.3 is left
at its native 1280x720 because its two-stage pipeline includes a spatial
upscaler that is tuned to that operating point - noted in the report.
"""
import argparse
import json
import pathlib

HERE = pathlib.Path(__file__).parent
WF = HERE / "workflows"

W, H = 832, 480

# One shared creative brief so every model is asked for the same motion.
MOTION = ("slow smooth cinematic orbit around the product standing upright on a "
          "clean neutral surface, soft studio key light, gentle parallax, subtle "
          "highlight travelling across the packaging, shallow depth of field, "
          "product stays perfectly still and undistorted, photorealistic, 4k")
NEG = ("warped text, garbled letters, distorted packaging, melting product, "
       "extra objects, flicker, jitter, morphing, low quality, blurry, watermark")

# For the two models that cannot do image->video, describe the product in words.
T2V_PROMPT = ("A photorealistic studio product shot of a cosmetic tube standing "
              "upright on a clean neutral surface with a printed label. " + MOTION)


def load(name):
    return json.loads((WF / name).read_text())


def save(doc, name):
    (WF / name).write_text(json.dumps(doc, indent=2) + "\n")
    print(f"  wrote workflows/{name}")


def set_by_class(doc, cls, **kw):
    n = 0
    for node in doc.values():
        if node.get("class_type") == cls:
            for k, v in kw.items():
                if k in node["inputs"] and not isinstance(node["inputs"][k], list):
                    node["inputs"][k] = v
                elif k not in node["inputs"]:
                    node["inputs"][k] = v
            n += 1
    return n


def set_text(doc, positive, negative=None):
    """CLIPTextEncode nodes: longest existing text = positive, other = negative."""
    nodes = [(k, v) for k, v in doc.items() if v.get("class_type") == "CLIPTextEncode"]
    if not nodes:
        return
    nodes.sort(key=lambda kv: len(str(kv[1]["inputs"].get("text", ""))), reverse=True)
    nodes[0][1]["inputs"]["text"] = positive
    if negative is not None and len(nodes) > 1:
        nodes[-1][1]["inputs"]["text"] = negative


def build_partA(ref):
    d = load("hidream_e1_1_edit.api.json")
    set_by_class(d, "LoadImage", image=ref)
    # Instruction-edit models respond to a plain instruction; E1.1 (unlike the
    # older E1) does NOT want the "Editing Instruction:/Target Image
    # Description:" scaffold. The instruction is deliberately conservative -
    # we are testing label survival, so we ask for lighting/background only.
    set_text(
        d,
        "Place this exact product on a clean seamless light grey studio background "
        "with soft professional lighting and a subtle reflection. Keep the product "
        "itself completely unchanged: identical shape, identical colours, and the "
        "printed label, logo and all text must stay perfectly sharp, legible and "
        "unaltered.",
        "changed packaging, altered label, different text, removed logo, blurred text, "
        "distorted product, warped lettering, low quality",
    )
    set_by_class(d, "SaveImage", filename_prefix="hero_hidream")
    save(d, "run_hero_hidream.api.json")


def build_partB(hero):
    # --- LTX-Video 13B 0.9.8 (true i2v) -------------------------------------
    d = load("ltx098_i2v.api.json")
    set_by_class(d, "LoadImage", image=hero)
    set_by_class(d, "LTXVImgToVideo", width=W, height=H, length=121)
    set_text(d, MOTION, NEG)
    set_by_class(d, "SaveVideo", filename_prefix="video/bakeoff_ltx098")
    save(d, "run_ltx098_i2v.api.json")

    # --- LTX-2.3 22B (true i2v, native 1280x720 two-stage) ------------------
    d = load("ltx23_i2v.api.json")
    set_by_class(d, "LoadImage", image=hero)
    set_text(d, MOTION, NEG)
    set_by_class(d, "SaveVideo", filename_prefix="video/bakeoff_ltx23")
    save(d, "run_ltx23_i2v.api.json")

    # --- Wan 2.2 I2V: turbo (LightX2V LoRAs) and baseline -------------------
    # The template drives steps/cfg/step-boundary and the LoRA branch from a
    # single PrimitiveBoolean. True  -> 4 steps, cfg 1.0, boundary 2, LoRAs on.
    # False -> 20 steps, cfg 3.5, boundary 10, LoRAs bypassed.
    for turbo, out in ((True, "run_wan22_turbo.api.json"),
                       (False, "run_wan22_base.api.json")):
        d = load("wan22_i2v_14B.api.json")
        set_by_class(d, "LoadImage", image=hero)
        set_by_class(d, "WanImageToVideo", width=W, height=H)
        set_text(d, MOTION, None)  # keep the template's Chinese negative prompt
        flipped = 0
        for node in d.values():
            if node.get("class_type") == "PrimitiveBoolean":
                node["inputs"]["value"] = turbo
                flipped += 1
        assert flipped == 1, f"expected exactly 1 turbo toggle, found {flipped}"
        set_by_class(d, "SaveVideo",
                     filename_prefix=f"video/bakeoff_wan22_{'turbo' if turbo else 'base'}")
        save(d, out)

    # --- HunyuanVideo (T2V ONLY - no i2v model installed) -------------------
    d = load("hunyuanvideo_t2v.api.json")
    set_by_class(d, "EmptyHunyuanLatentVideo", width=W, height=H, length=121)
    set_text(d, T2V_PROMPT, None)   # cfg-distilled: no negative prompt
    set_by_class(d, "SaveVideo", filename_prefix="video/bakeoff_hunyuan")
    save(d, "run_hunyuan_t2v.api.json")

    # --- Mochi 1 (T2V ONLY - model has no i2v variant) ----------------------
    d = load("mochi1_t2v.api.json")
    set_by_class(d, "EmptyMochiLatentVideo", width=W, height=H, length=121)
    set_text(d, T2V_PROMPT, NEG)
    set_by_class(d, "SaveVideo", filename_prefix="video/bakeoff_mochi")
    save(d, "run_mochi_t2v.api.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", help="filename in ComfyUI/input for PART A")
    ap.add_argument("--hero", help="filename in ComfyUI/input for PART B")
    a = ap.parse_args()
    if a.ref:
        print("building PART A ...")
        build_partA(a.ref)
    if a.hero:
        print("building PART B ...")
        build_partB(a.hero)
    if not (a.ref or a.hero):
        ap.error("need --ref and/or --hero")


if __name__ == "__main__":
    main()
