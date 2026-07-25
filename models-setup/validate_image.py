#!/usr/bin/env python
"""
Qwen2.5-VL image guard -> JSON verdict.

Runs the vision model over one or more images and returns a strict JSON verdict
covering branding / modesty / quality. Intended as the validator gate in front
of the image + video bake-off outputs.

Usage
-----
  # single image, JSON to stdout
  /venv/main/bin/python validate_image.py shot.png

  # several, as a JSON array
  /venv/main/bin/python validate_image.py a.png b.png -o verdicts.json

  # a whole ComfyUI output folder
  /venv/main/bin/python validate_image.py /workspace/ComfyUI/output/*.png

  # first frame of a generated video (needs the video decoded to a still first)
  /venv/main/bin/python validate_image.py frame0.png

Exit code is 0 if every image passed all three checks, 1 if any failed, 2 on
error. That makes it usable directly in a shell gate:
    python validate_image.py out.png >/dev/null && echo SHIP || echo REJECT

Notes on the runtime choices (all verified on this box):
  * transformers 5.x resolves image content blocks itself, so `qwen-vl-utils`
    is NOT required - {"type": "image", "path": ...} is loaded by the processor.
  * `dtype=` is the transformers-5 kwarg; `torch_dtype=` is a deprecated alias.
  * `device_map="cuda:0"` (a single device) avoids needing `accelerate`;
    "auto" WOULD require it.
  * attn_implementation="sdpa" - flash-attn publishes no wheel for torch 2.10 /
    sm_120 (Blackwell), and building it from source is not worth it. SDPA on
    this GPU is fine.
"""
import argparse
import json
import os
import re
import sys

MODEL_DIR = os.environ.get(
    "QWEN_VL_DIR", "/workspace/models/qwen2.5-vl/Qwen2.5-VL-7B-Instruct")

SYSTEM = "You are a strict image compliance reviewer. You answer with JSON only."

PROMPT = """Inspect this image and return exactly ONE JSON object. No prose, no markdown fence.

{
  "branding": {"pass": true|false, "detected": ["..."], "notes": "<=15 words"},
  "modesty":  {"pass": true|false, "rating": "safe"|"suggestive"|"explicit", "notes": "<=15 words"},
  "quality":  {"pass": true|false, "score": <integer 0-10>, "issues": ["..."], "notes": "<=15 words"}
}

Rules:
- branding.pass = false if ANY logo, watermark, brand name, or readable trademarked text is visible. List what you saw in "detected".
- modesty.pass = false if rating is anything other than "safe".
- quality.pass = false if score < 6. Judge anatomy errors, extra/fused limbs or fingers, warped faces, garbled text, heavy compression, blur, or obvious AI artifacts. List them in "issues".
- Be strict. When uncertain, fail the check rather than passing it."""

_model = None
_proc = None


def load(model_dir=MODEL_DIR, max_pixels=1280 * 28 * 28):
    """Load once and cache. Returns (model, processor)."""
    global _model, _proc
    if _model is None:
        import torch
        from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
        if not os.path.isdir(model_dir):
            raise SystemExit(
                f"model not found at {model_dir}\n"
                f"run:  /workspace/models-setup/download_models.sh qwen")
        _model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_dir,
            dtype=torch.bfloat16,
            attn_implementation="sdpa",
            device_map="cuda:0",
        ).eval()
        _proc = AutoProcessor.from_pretrained(
            model_dir, min_pixels=256 * 28 * 28, max_pixels=max_pixels)
    return _model, _proc


def _extract_json(text):
    """Pull the JSON object out of the model's reply, tolerating fences/prose."""
    cleaned = re.sub(r"^\s*```(?:json)?|```\s*$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    depth, start = 0, None
    for i, ch in enumerate(cleaned):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(cleaned[start:i + 1])
                except json.JSONDecodeError:
                    start = None
    raise ValueError(f"no JSON object in model output: {text[:300]!r}")


def verdict(image_path, max_new_tokens=512):
    import torch
    model, proc = load()
    messages = [
        {"role": "system", "content": [{"type": "text", "text": SYSTEM}]},
        {"role": "user", "content": [
            {"type": "image", "path": os.path.abspath(image_path)},
            {"type": "text", "text": PROMPT},
        ]},
    ]
    inputs = proc.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=True,
        return_dict=True, return_tensors="pt",
    ).to(model.device)

    with torch.inference_mode():
        out = model.generate(
            **inputs, max_new_tokens=max_new_tokens,
            do_sample=False, temperature=None, top_p=None, top_k=None)
    trimmed = out[:, inputs["input_ids"].shape[1]:]
    text = proc.batch_decode(trimmed, skip_special_tokens=True)[0]

    v = _extract_json(text)
    v["image"] = image_path
    checks = [v.get(k, {}).get("pass") for k in ("branding", "modesty", "quality")]
    v["overall_pass"] = all(c is True for c in checks)
    return v


def main():
    ap = argparse.ArgumentParser(description="Qwen2.5-VL image guard -> JSON verdict")
    ap.add_argument("images", nargs="+")
    ap.add_argument("-o", "--output", help="write JSON here instead of stdout")
    ap.add_argument("--max-new-tokens", type=int, default=512)
    ap.add_argument("--max-pixels", type=int, default=1280 * 28 * 28,
                    help="vision token budget dial; lower = faster/cheaper")
    args = ap.parse_args()

    load(max_pixels=args.max_pixels)

    results, failed = [], False
    for p in args.images:
        if not os.path.isfile(p):
            results.append({"image": p, "error": "file not found", "overall_pass": False})
            failed = True
            continue
        try:
            v = verdict(p, max_new_tokens=args.max_new_tokens)
        except Exception as e:
            v = {"image": p, "error": f"{type(e).__name__}: {e}", "overall_pass": False}
        results.append(v)
        if not v.get("overall_pass"):
            failed = True

    payload = results[0] if len(results) == 1 else results
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        print(text)
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
