#!/usr/bin/env python
"""
Retarget the ComfyUI-converted official templates onto the exact model files
this box actually downloaded, and set a per-model output prefix.

Re-runnable: it is a pure find/replace over model filenames, so running it twice
is a no-op.

Why each rewrite is needed:
  * hidream_e1_1  - the official template ships the bf16 edit model and casts it
                    at load with weight_dtype="fp8_e4m3fn_fast". We downloaded a
                    real fp8 build instead (half the disk), so point at it and
                    drop the cast back to "default".
  * hunyuanvideo  - Comfy-Org publishes HunyuanVideo in bf16 only (25.6 GB). We
                    use Kijai's genuine fp8_e4m3fn build (13.2 GB). It is a plain
                    (unscaled) cast, so it must load with weight_dtype="default".
  * ltx098        - the shipped LTXV templates target the OLD 2B 0.9/0.9.5
                    checkpoints. Retarget to the 13B 0.9.8 fp8 checkpoint. All
                    sampler settings (30 steps, max_shift 2.05, base_shift 0.95,
                    stretch, terminal 0.1, cfg 3) already match the documented
                    0.9.8 recipe, so they are left alone.
  * t5xxl         - we deduped to ONE shared t5xxl (the fp8 scaled build) rather
                    than also carrying the 9.79 GB fp16 copy.
"""
import json, pathlib, sys

HERE = pathlib.Path(__file__).parent

# filename -> filename, applied to every string input in the graph
RENAMES = {
    "hidream_e1_1_edit.api.json": {
        "hidream_e1_1_bf16.safetensors": "hidream_e1_1_fp8.safetensors",
    },
    "hunyuanvideo_t2v.api.json": {
        "hunyuan_video_t2v_720p_bf16.safetensors":
            "hunyuan_video_720_cfgdistill_fp8_e4m3fn.safetensors",
    },
    "ltx098_t2v.api.json": {
        "ltx-video-2b-v0.9.safetensors": "ltxv-13b-0.9.8-dev-fp8.safetensors",
        "t5xxl_fp16.safetensors": "t5xxl_fp8_e4m3fn_scaled.safetensors",
    },
    "ltx098_i2v.api.json": {
        "ltx-video-2b-v0.9.5.safetensors": "ltxv-13b-0.9.8-dev-fp8.safetensors",
        "t5xxl_fp16.safetensors": "t5xxl_fp8_e4m3fn_scaled.safetensors",
    },
}

# node class -> {input: value} forced after renaming
FORCE = {
    "hidream_e1_1_edit.api.json": [("UNETLoader", "weight_dtype", "default")],
    "hunyuanvideo_t2v.api.json":  [("UNETLoader", "weight_dtype", "default")],
}

# The official templates reference input images that ship only with ComfyUI's
# hosted template gallery, not with the pip package (verified: no image assets in
# comfyui_workflow_templates_json, and the raw GitHub paths 404). Point them at
# ComfyUI's bundled input/example.png (768x768 RGB) so every workflow is valid
# and runnable as-is. To use your own: drop it in /workspace/ComfyUI/input/ and
# change the LoadImage "image" field to its filename.
DEFAULT_IMAGE = "example.png"
IMAGE_NODES = {
    "hidream_e1_1_edit.api.json",
    "ltx098_i2v.api.json",
    "ltx23_i2v.api.json",
    "wan22_i2v_14B.api.json",
}

PREFIX = {
    "hidream_i1_full_t2i.api.json": "hidream_i1_full",
    "hidream_e1_1_edit.api.json":   "hidream_e1_1_edit",
    "ltx098_t2v.api.json":          "video/ltx098_t2v",
    "ltx098_i2v.api.json":          "video/ltx098_i2v",
    "ltx23_t2v.api.json":           "video/ltx23_t2v",
    "ltx23_i2v.api.json":           "video/ltx23_i2v",
    "wan22_i2v_14B.api.json":       "video/wan22_i2v",
    "hunyuanvideo_t2v.api.json":    "video/hunyuanvideo_t2v",
    "mochi1_t2v.api.json":          "video/mochi1_t2v",
}

changed = 0
for path in sorted(HERE.glob("*.api.json")):
    name = path.name
    doc = json.loads(path.read_text())
    before = json.dumps(doc, sort_keys=True)

    ren = RENAMES.get(name, {})
    for node in doc.values():
        for k, v in list(node.get("inputs", {}).items()):
            if isinstance(v, str) and v in ren:
                node["inputs"][k] = ren[v]

    for cls, inp, val in FORCE.get(name, []):
        for node in doc.values():
            if node.get("class_type") == cls:
                node["inputs"][inp] = val

    if name in IMAGE_NODES:
        for node in doc.values():
            if node.get("class_type") == "LoadImage":
                node["inputs"]["image"] = DEFAULT_IMAGE

    if name in PREFIX:
        for node in doc.values():
            if "filename_prefix" in node.get("inputs", {}):
                node["inputs"]["filename_prefix"] = PREFIX[name]

    after = json.dumps(doc, sort_keys=True)
    if before != after:
        path.write_text(json.dumps(doc, indent=2) + "\n")
        print(f"patched  {name}")
        changed += 1
    else:
        print(f"unchanged {name}")
print(f"\n{changed} file(s) modified")
