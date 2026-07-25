#!/usr/bin/env bash
# Bootstrap this box's ComfyUI generation stack.
#
# Assumes ComfyUI is already installed (the Vast.ai ComfyUI image provides it at
# $COMFY). This script does the two things that are NOT in the base image:
#   1. downloads the model weights  (download_models.sh)
#   2. installs the API-format workflows into ComfyUI's user workflow dir
#
# Usage:  bash setup.sh [ltx|flux|wan|all]
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMFY="${COMFY:-/workspace/ComfyUI}"
WHICH="${1:-all}"

echo "== preflight =="
[[ -d "$COMFY" ]] || { echo "ComfyUI not found at $COMFY (set COMFY=...)" >&2; exit 1; }
echo "  ComfyUI:   $COMFY"
echo "  free disk: $(df -h "$COMFY" | tail -1 | awk '{print $4}')"
if command -v nvidia-smi >/dev/null; then
  echo "  GPU:       $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader)"
else
  echo "  GPU:       nvidia-smi not found — CPU only?" >&2
fi

echo "== models =="
bash "$REPO/download_models.sh" "$WHICH"

echo "== workflows =="
dst="$COMFY/user/default/workflows"
mkdir -p "$dst"
cp -v "$REPO"/workflows/*.json "$dst"/

echo
echo "Done. Restart ComfyUI to pick up new models:  supervisorctl restart comfyui"
echo "See MODELS.md for per-model settings, VRAM ceilings and known traps."
