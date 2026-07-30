#!/usr/bin/env bash
# =============================================================================
#  Populate the RunPod Network Volume - RUN ONCE, EVER.
# =============================================================================
#  Run this on a TEMPORARY pod that has the volume mounted at /runpod-volume.
#  When it finishes, destroy that pod: the volume persists and every serverless
#  worker mounts it read-only-ish at cold start, so the ~150 GB is downloaded
#  once rather than baked into an image or pulled per worker.
#
#  Reuses the same fetch helper as download_models.sh, so the guarantees carry
#  over: idempotent (a file whose size already matches remote is skipped), byte
#  -verified against HuggingFace's x-linked-size header, resumable, and it
#  refuses to start a download that would take free space below the floor.
#
#  The layout below is not arbitrary - it is EXACTLY what the Dockerfile's
#  extra_model_paths.yaml (base_path /runpod-volume/ComfyUI/) and QWEN_VL_DIR
#  expect. Change one and you must change the other.
#
#  DELIBERATELY NOT DOWNLOADED:
#    * brain weights   - the storyboard brain is a remote WaveSpeed call.
#                        Qwen2.5-14B/32B are not installed anywhere.
#    * Wan 2.2 S2V     - no talking-avatar, no lip-sync in any template. Person
#                        scenes render through Wan 2.2 I2V like everything else.
#
#  Usage:
#      VOL=/runpod-volume bash volume_setup.sh
#      VOL=/runpod-volume bash volume_setup.sh --verify-only
# =============================================================================
set -uo pipefail

VOL="${VOL:-/runpod-volume}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# lib/fetch.sh lives with the downloader; this script is shipped beside reelkit,
# so accept either location.
FETCH=""
for c in "$HERE/../models-setup/lib/fetch.sh" "$HERE/lib/fetch.sh" \
         "/workspace/models-setup/lib/fetch.sh"; do
  [[ -f "$c" ]] && { FETCH="$c"; break; }
done
if [[ -z "$FETCH" ]]; then
  echo "!! cannot find lib/fetch.sh (looked beside this script and in models-setup/)" >&2
  exit 1
fi

export MIN_FREE_GB="${MIN_FREE_GB:-20}"
export MANIFEST="${MANIFEST:-$VOL/.reelkit_manifest.tsv}"
mkdir -p "$(dirname "$MANIFEST")"
# shellcheck source=/dev/null
source "$FETCH"

M="$VOL/ComfyUI/models"          # everything ComfyUI loads
X="$VOL/models"                  # transformers checkpoints, outside ComfyUI
HF=https://huggingface.co

VERIFY_ONLY=0
[[ "${1:-}" == "--verify-only" ]] && VERIFY_ONLY=1

echo "== reelkit volume setup"
echo "   volume : $VOL"
echo "   floor  : ${MIN_FREE_GB} GiB free"
if [[ ! -d "$VOL" ]]; then
  echo "!! $VOL does not exist - is the Network Volume mounted?" >&2
  exit 1
fi

# --- the exact layout the Dockerfile expects --------------------------------
mkdir -p \
  "$M/diffusion_models" "$M/text_encoders" "$M/clip_vision" "$M/vae" \
  "$M/loras" "$M/upscale_models" "$M/background_removal" "$M/checkpoints" \
  "$X/qwen2.5-vl"

if (( VERIFY_ONLY == 0 )); then

  # --- Qwen-Image: t2i backdrops + the default edit scene builder -----------
  echo; echo "== Qwen-Image-2512 + Qwen-Image-Edit-2511"
  QB=$HF/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files
  QE=$HF/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files
  fetch "$QB/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" \
        "$M/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"
  fetch "$QB/vae/qwen_image_vae.safetensors" "$M/vae/qwen_image_vae.safetensors"
  fetch "$QB/diffusion_models/qwen_image_2512_fp8_e4m3fn.safetensors" \
        "$M/diffusion_models/qwen_image_2512_fp8_e4m3fn.safetensors"
  fetch "$QE/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors" \
        "$M/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors"
  fetch "$HF/lightx2v/Qwen-Image-2512-Lightning/resolve/main/Qwen-Image-2512-Lightning-4steps-V1.0-bf16.safetensors" \
        "$M/loras/Qwen-Image-2512-Lightning-4steps.safetensors"
  fetch "$HF/lightx2v/Qwen-Image-Edit-2511-Lightning/resolve/main/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors" \
        "$M/loras/Qwen-Image-Edit-2511-Lightning-4steps.safetensors"
  # 8-step Lightning LoRAs — the pipeline DEFAULT (see compose.py). A clear quality
  # step up from 4-step for a few extra seconds; still ~12-25x faster than base.
  fetch "$HF/lightx2v/Qwen-Image-2512-Lightning/resolve/main/Qwen-Image-2512-Lightning-8steps-V1.0-bf16.safetensors" \
        "$M/loras/Qwen-Image-2512-Lightning-8steps.safetensors"
  fetch "$HF/lightx2v/Qwen-Image-Edit-2511-Lightning/resolve/main/Qwen-Image-Edit-2511-Lightning-8steps-V1.0-bf16.safetensors" \
        "$M/loras/Qwen-Image-Edit-2511-Lightning-8steps.safetensors"
  fetch "$QE/loras/Qwen-Image-Edit-2509-White_to_Scene.safetensors" \
        "$M/loras/Qwen-Image-Edit-2509-White_to_Scene.safetensors"

  # --- Wan 2.2 I2V: the ONLY video engine every template uses ---------------
  #  TRAP: the VAE is wan_2.1_vae (253,815,318 B). wan2.2_vae is for the 5B
  #  TI2V model only - 48-channel vs 16-channel latent - and will not work.
  echo; echo "== Wan 2.2 I2V 14B + LightX2V"
  WB=$HF/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files
  fetch "$WB/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors" \
        "$M/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"
  fetch "$WB/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors" \
        "$M/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"
  fetch "$WB/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" \
        "$M/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
  fetch "$WB/vae/wan_2.1_vae.safetensors" "$M/vae/wan_2.1_vae.safetensors"
  fetch "$WB/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors" \
        "$M/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors"
  fetch "$WB/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors" \
        "$M/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors"

  # --- HunyuanVideo I2V: REMOVED ------------------------------------------
  #  The pipeline always uses Wan (REELKIT_VIDEO_MODEL defaults to "wan"), so
  #  HunyuanVideo's ~36GB (model + llava text encoders + clip_l + vae) was dead
  #  weight on the volume. Dropped to fit a smaller drive and populate faster.
  #  animate.hunyuan_i2v still exists but is only reachable with
  #  REELKIT_VIDEO_MODEL=hunyuan - do NOT set that unless you re-add these files.
  echo; echo "== HunyuanVideo: SKIPPED (Wan-only pipeline, saves ~36GB)"

  # --- segmentation + upscaler ----------------------------------------------
  echo; echo "== BiRefNet + 4x-UltraSharp"
  fetch "$HF/Comfy-Org/BiRefNet/resolve/main/background_removal/birefnet.safetensors" \
        "$M/background_removal/birefnet.safetensors"
  fetch "$HF/uwg/upscaler/resolve/main/ESRGAN/4x-UltraSharp.pth" \
        "$M/upscale_models/4x-UltraSharp.pth"
  # 2x model for the HD path: 720p->1080p only needs 1.5x, and the 2x pass is
  # ~4x cheaper than 4x-then-downscale for the same final frames. animate.py
  # also lazy-fetches this on first HD render if it is missing.
  fetch "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth" \
        "$M/upscale_models/RealESRGAN_x2plus.pth"

  # --- Qwen2.5-VL: the Stage 2b OCR guard (transformers, not ComfyUI) -------
  #  NOTE: --exclude must be REPEATED per pattern. Passing several patterns to
  #  one flag makes the CLI treat the extras as positional FILENAMES, download
  #  nothing, and still exit 0 - a silent false success.
  echo; echo "== Qwen2.5-VL-7B-Instruct (OCR guard)"
  # The guard is a multi-file transformers model, so it comes via the HuggingFace
  # CLI, not a single-file fetch. A bare pod may not have it - install on demand
  # (this runs on the populate pod only; the endpoint just READS the result).
  if ! command -v hf >/dev/null 2>&1 && ! command -v huggingface-cli >/dev/null 2>&1; then
    echo "  hf CLI missing - installing huggingface_hub[cli]"
    pip install -q -U "huggingface_hub[cli]" 2>/dev/null \
      || pip3 install -q -U "huggingface_hub[cli]" 2>/dev/null \
      || echo "  !! could not install the HuggingFace CLI"
  fi
  HFCLI=hf; command -v hf >/dev/null 2>&1 || HFCLI=huggingface-cli
  "$HFCLI" download Qwen/Qwen2.5-VL-7B-Instruct \
      --local-dir "$X/qwen2.5-vl/Qwen2.5-VL-7B-Instruct" \
      --exclude "*.pth" --exclude "*.bin" --exclude "original/*" \
      --max-workers 8 || echo "  !! qwen guard download failed"
fi

# --- verify ------------------------------------------------------------------
echo; echo "== verifying"
if [[ -f "$MANIFEST" ]]; then
  bash "$(dirname "$FETCH")/verify.sh" "$MANIFEST" 2>/dev/null | tail -30
fi

PY=$(command -v python3 || command -v python)
INSPECT=""
for c in "$HERE/../models-setup/lib/inspect_safetensors.py" \
         "/workspace/models-setup/lib/inspect_safetensors.py"; do
  [[ -f "$c" ]] && { INSPECT="$c"; break; }
done
if [[ -n "$INSPECT" ]]; then
  echo; echo "-- safetensors headers (real tensor data, not an HTML error page)"
  "$PY" "$INSPECT" "$M" 2>/dev/null | tail -6
fi

# --- layout check: does this match what the Dockerfile will look for? -------
echo; echo "== layout check (must match extra_model_paths.yaml + QWEN_VL_DIR)"
ok=1
# NB: the status word is computed BEFORE printf, not inside a $( ) - a
# subshell cannot set `ok`, so an "EMPTY" line used to be reported while the
# script still declared READY at the end.
# -L follows symlinks, so a volume assembled with links verifies the same as
# one with real directories.
check_dir() {                      # <label> <path> <find-args...>
  local label="$1" path="$2"; shift 2
  local n; n=$(find -L "$path" -type f "$@" 2>/dev/null | wc -l)
  local status=OK
  (( n > 0 )) || { status=EMPTY; ok=0; }
  printf '   %-34s %3s file(s)  %s\n' "$label" "$n" "$status"
}

# clip_vision is intentionally empty now (only HunyuanVideo used it, removed).
for d in diffusion_models text_encoders vae loras upscale_models \
         background_removal; do
  check_dir "ComfyUI/models/$d" "$M/$d" \( -name '*.safetensors' -o -name '*.pth' \)
done
check_dir "models/qwen2.5-vl" "$X/qwen2.5-vl" -name '*.safetensors' 

echo; echo "== size on the volume"
du -shL "$M" "$X" 2>/dev/null | sed 's/^/   /'
echo -n "   TOTAL: "; du -sh "$VOL" 2>/dev/null | cut -f1
echo "   free : $(df -h "$VOL" | awk 'NR==2{print $4}')"

echo
if (( ok )); then
  echo "== READY. Destroy this temp pod - the volume persists."
  echo "   Serverless workers mount it at /runpod-volume and find models via"
  echo "   extra_model_paths.yaml (base_path /runpod-volume/ComfyUI/)."
else
  echo "!! INCOMPLETE - one or more folders are empty. Re-run; it will skip"
  echo "   whatever already verified and only fetch what is missing."
  exit 1
fi
