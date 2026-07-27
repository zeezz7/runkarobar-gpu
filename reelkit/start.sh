#!/usr/bin/env bash
# Container entrypoint: bring ComfyUI up FIRST, then hand over to the handler.
#
# Ordering is the whole point. RunPod will route a job the moment the worker
# reports ready, and make_reel posts its very first workflow within seconds - so
# if ComfyUI is still loading, that job dies on a connection refused and the
# caller sees a failure that looks like a pipeline bug.
set -euo pipefail

COMFY_PORT="${COMFY_PORT:-8188}"
COMFY_HOST="${COMFY_HOST:-127.0.0.1}"
BOOT_TIMEOUT="${COMFY_BOOT_TIMEOUT:-600}"

log() { echo "[start] $*"; }

# --- sanity: is the volume actually mounted? --------------------------------
# A missing volume is the single most likely deployment mistake, and without
# this check it surfaces much later as "model not found" inside a render.
if [[ ! -d /runpod-volume/ComfyUI/models/diffusion_models ]]; then
  log "WARNING: /runpod-volume/ComfyUI/models/diffusion_models is missing."
  log "         The Network Volume is not mounted, or volume_setup.sh never ran."
  log "         ComfyUI will start but every render will fail to find its models."
else
  n=$(find /runpod-volume/ComfyUI/models -name '*.safetensors' 2>/dev/null | wc -l)
  log "volume mounted: ${n} safetensors visible"
fi

# --- ComfyUI in the background ----------------------------------------------
log "starting ComfyUI on ${COMFY_HOST}:${COMFY_PORT}"
python /opt/ComfyUI/main.py \
    --listen "${COMFY_HOST}" \
    --port "${COMFY_PORT}" \
    --disable-auto-launch \
    --disable-metadata \
    >/tmp/comfyui.log 2>&1 &
COMFY_PID=$!

# --- block until it actually answers ----------------------------------------
log "waiting for ComfyUI to answer /system_stats (timeout ${BOOT_TIMEOUT}s)"
deadline=$((SECONDS + BOOT_TIMEOUT))
until curl -sf "http://${COMFY_HOST}:${COMFY_PORT}/system_stats" >/dev/null 2>&1; do
  if ! kill -0 "${COMFY_PID}" 2>/dev/null; then
    log "ComfyUI died during startup. Last 40 lines:"
    tail -40 /tmp/comfyui.log
    exit 1
  fi
  if (( SECONDS > deadline )); then
    log "ComfyUI did not come up within ${BOOT_TIMEOUT}s. Last 40 lines:"
    tail -40 /tmp/comfyui.log
    exit 1
  fi
  sleep 2
done
log "ComfyUI is up (pid ${COMFY_PID})"

# --- hand over ---------------------------------------------------------------
# exec so the handler becomes PID 1's child and signals reach it directly.
cd /opt/reelkit
log "starting the RunPod handler"
exec python handler.py
