#!/usr/bin/env bash
# Prove the COMFY_INPUT path mismatch: run the real compose.edit_scene with
# (A) common.py's default staging dir  vs  (B) ComfyUI's actual input dir.
# POST-only (no GPU execution) - we only want ComfyUI's /prompt validation.
set -u
SRC=/root/gpu-src
[ -d "$SRC" ] || git clone --depth 1 -q https://github.com/zeezz7/runkarobar-gpu.git "$SRC"
cd "$SRC" && git pull -q 2>/dev/null || true
COMFY_URL=http://127.0.0.1:8188 python3 - <<'PY'
import os, sys, json, urllib.request, urllib.error
sys.path.insert(0, "/root/gpu-src/reelkit")
import common
from PIL import Image
Image.new("RGB", (768, 768), (180, 160, 140)).save("/root/prod.png")
import compose

def probe(wf, timeout=1800, poll=3):
    body = json.dumps({"prompt": wf, "client_id": "diag"}).encode()
    req = urllib.request.Request(common.COMFY + "/prompt", data=body,
                                headers={"Content-Type": "application/json"}, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=60)
        print("  -> ACCEPTED:", r.read().decode()[:160])
        return ["ok"]
    except urllib.error.HTTPError as e:
        print("  -> HTTP", e.code, "body:", e.read().decode("utf-8", "replace")[:1500])
        return []
common.comfy_run = probe

print("ComfyUI real input dir on this pod: /root/ComfyUI/input")
print("=== A) common.COMFY_INPUT =", common.COMFY_INPUT, "(the buggy default) ===")
try: compose.edit_scene("/root/prod.png", "luxury studio scene, dramatic light", "diag_a")
except Exception as e: print("  raised:", str(e)[:200])

print("=== B) common.COMFY_INPUT = /root/ComfyUI/input (ComfyUI's real dir) ===")
common.COMFY_INPUT = "/root/ComfyUI/input"
try: compose.edit_scene("/root/prod.png", "luxury studio scene, dramatic light", "diag_b")
except Exception as e: print("  raised:", str(e)[:200])
PY
