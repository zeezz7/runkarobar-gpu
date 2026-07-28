#!/usr/bin/env bash
# =============================================================================
#  diag_comfy.sh - reproduce the ComfyUI /prompt validation on a POD
# =============================================================================
#  Run on a temp pod that has the reelkit Network Volume mounted at /workspace.
#  Stands up ComfyUI 0.28.0 pointed at the volume's models (exactly replicating
#  the serverless image's extra_model_paths auto-load), then:
#    1. confirms extra_model_paths is loaded (are the volume LoRAs visible?)
#    2. confirms the edit workflow's node classes exist
#    3. POSTs the real tpl_qwen_edit.api.json and prints ComfyUI's exact
#       response - the node_errors body that a bare "HTTP 400" hides.
#
#  Usage:
#    curl -sSL https://raw.githubusercontent.com/zeezz7/runkarobar-gpu/main/reelkit/diag_comfy.sh | bash
# =============================================================================
set -u
CM=/root/ComfyUI
SRC=/root/gpu-src
COMFY=http://127.0.0.1:8188
COMFYUI_COMMIT=700821e1364eaab0e8f21c538a2131719fec57bf

# 1. ComfyUI 0.28.0 --------------------------------------------------------
if [ ! -f "$CM/main.py" ]; then
  git clone --filter=blob:none https://github.com/comfyanonymous/ComfyUI.git "$CM"
fi
cd "$CM" || exit 1
git checkout -q "$COMFYUI_COMMIT" 2>/dev/null || true
echo ">> installing ComfyUI requirements (quiet)..."
pip install --break-system-packages -q -r requirements.txt

# 2. point ComfyUI at the volume's models (pod mount = /workspace) ----------
cat > "$CM/extra_model_paths.yaml" <<'YAML'
reelkit:
    base_path: /workspace/ComfyUI/
    checkpoints: models/checkpoints
    diffusion_models: models/diffusion_models
    text_encoders: models/text_encoders
    clip_vision: models/clip_vision
    vae: models/vae
    loras: models/loras
    upscale_models: models/upscale_models
    background_removal: models/background_removal
YAML

# 3. start ComfyUI (if not already up) -------------------------------------
if ! curl -sf "$COMFY/system_stats" >/dev/null 2>&1; then
  echo ">> starting ComfyUI..."
  ( python main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch \
      >/root/comfy.log 2>&1 & )
  for i in $(seq 1 120); do
    curl -sf "$COMFY/system_stats" >/dev/null 2>&1 && break
    sleep 2
  done
fi
if ! curl -sf "$COMFY/system_stats" >/dev/null 2>&1; then
  echo "!! ComfyUI FAILED TO START. Last 30 log lines:"
  tail -30 /root/comfy.log
  exit 1
fi
echo ">> ComfyUI UP"

# 4. is extra_model_paths loaded? (does ComfyUI see the volume LoRAs?) ------
echo "=============================================================="
echo "=== 1) extra_model_paths loaded? (LoRAs ComfyUI can see) ==="
curl -s "$COMFY/object_info/LoraLoaderModelOnly" | python3 -c "
import sys, json
d = json.load(sys.stdin)
l = d['LoraLoaderModelOnly']['input']['required']['lora_name'][0]
print('lora count:', len(l))
print('8-step edit LoRA present:', any('Edit-2511-Lightning-8steps' in x for x in l))
for x in l: print('   ', x)
"

# 5. do the edit workflow's node classes exist? ----------------------------
echo "=============================================================="
echo "=== 2) edit-workflow node classes exist? (200 = yes) ==="
for n in TextEncodeQwenImageEditPlus FluxKontextImageScale LoraLoaderModelOnly \
         UNETLoader VAELoader CLIPLoader KSampler VAEDecode VAEEncode LoadImage; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$COMFY/object_info/$n")
  echo "$code $n"
done

# 6. POST the real edit workflow, print ComfyUI's exact validation result --
echo "=============================================================="
echo "=== 3) POST tpl_qwen_edit.api.json -> /prompt (the REAL error) ==="
if [ ! -d "$SRC" ]; then
  git clone --depth 1 -q https://github.com/zeezz7/runkarobar-gpu.git "$SRC"
fi
python3 - "$CM" "$SRC" "$COMFY" <<'PY'
import json, os, sys, urllib.request, urllib.error
from PIL import Image
CM, SRC, COMFY = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(os.path.join(CM, "input"), exist_ok=True)
Image.new("RGB", (768, 768), (200, 180, 160)).save(os.path.join(CM, "input", "diag.png"))
wf = json.load(open(os.path.join(SRC, "reelkit", "workflows", "tpl_qwen_edit.api.json")))
for k, v in wf.items():
    ct = v.get("class_type", "")
    ins = v.setdefault("inputs", {})
    if ct == "LoadImage":            ins["image"] = "diag.png"
    if ct == "LoraLoaderModelOnly":  ins["lora_name"] = "Qwen-Image-Edit-2511-Lightning-8steps.safetensors"
    if ct == "PrimitiveBoolean":     ins["value"] = True
body = json.dumps({"prompt": wf, "client_id": "diag"}).encode()
req = urllib.request.Request(COMFY + "/prompt", data=body,
                            headers={"Content-Type": "application/json"}, method="POST")
try:
    r = urllib.request.urlopen(req, timeout=60)
    print("ACCEPTED (no validation error):", r.read().decode()[:400])
except urllib.error.HTTPError as e:
    print("HTTP", e.code, "- ComfyUI validation body:")
    print(e.read().decode("utf-8", "replace")[:4000])
PY
echo "=============================================================="
echo ">> done."
