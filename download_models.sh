#!/usr/bin/env bash
# Model downloads for this ComfyUI instance (Vast.ai RTX 5090, 32 GB VRAM).
#
# Idempotent: every fetch uses `wget -c` and each file is size-verified against
# the HuggingFace `x-linked-size` header, so re-running skips completed files.
#
# Usage:  bash /workspace/download_models.sh [ltx|flux|wan|all]
set -uo pipefail

COMFY=/workspace/ComfyUI
MODELS="$COMFY/models"

# fetch <url> <target-relative-to-models> <expected-bytes>
fetch() {
  local url="$1" rel="$2" want="$3" dst="$MODELS/$2"
  mkdir -p "$(dirname "$dst")"
  if [[ -f "$dst" ]] && [[ "$(stat -c %s "$dst")" == "$want" ]]; then
    echo "  [have] $rel"
    return 0
  fi
  echo "  [get ] $rel  ($(numfmt --to=iec "$want"))"
  wget -c -q --show-progress -O "$dst" "$url" || { echo "  FAILED: $rel"; return 1; }
  local got; got="$(stat -c %s "$dst")"
  if [[ "$got" != "$want" ]]; then
    echo "  SIZE MISMATCH for $rel: got $got, expected $want" >&2
    return 1
  fi
  echo "  [ok  ] $rel"
}

need_space() {  # need_space <bytes>
  local avail; avail="$(df --output=avail -B1 / | tail -1)"
  if (( avail < $1 )); then
    echo "Not enough free space: need $(numfmt --to=iec "$1"), have $(numfmt --to=iec "$avail")" >&2
    exit 1
  fi
  echo "Disk OK: $(numfmt --to=iec "$avail") free"
}

# ---------------------------------------------------------------- LTX-Video --
# LTXV 13B 0.9.8 dev, fp8. VAE is bundled INSIDE the checkpoint (vae.* keys),
# so there is no separate VAE file. Loads with core CheckpointLoaderSimple —
# no custom nodes needed (ComfyUI core ships comfy/ldm/lightricks + nodes_lt.py).
ltx() {
  echo "== LTX-Video 13B 0.9.8 fp8 =="
  need_space 22000000000
  fetch "https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltxv-13b-0.9.8-dev-fp8.safetensors" \
        "checkpoints/ltxv-13b-0.9.8-dev-fp8.safetensors" 15694279916
  # T5-XXL fp8 — SHARED with FLUX (identical xet hash 31868d1b…a77a13e8).
  fetch "https://huggingface.co/Comfy-Org/mochi_preview_repackaged/resolve/main/split_files/text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors" \
        "text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors" 5157348688
}

# --------------------------------------------------------------------- FLUX --
# FLUX.1-dev, fp8, SPLIT loader (UNETLoader + DualCLIPLoader + VAELoader).
# Split rather than the 17.2 GB all-in-one checkpoint specifically so the T5
# already fetched by ltx() is reused instead of duplicated -> 12.5 GB not 17.2 GB.
#
# NOTE: black-forest-labs/FLUX.1-dev is GATED (401 without an HF token).
# The fp8 UNet below comes from Kijai/flux-fp8, the standard ungated community
# fp8 repackage — Comfy-Org/flux1-dev publishes no split fp8 UNet, only bf16.
# FLUX.1-dev is licensed NON-COMMERCIAL.
flux() {
  echo "== FLUX.1-dev fp8 =="
  need_space 14000000000
  fetch "https://huggingface.co/Kijai/flux-fp8/resolve/main/flux1-dev-fp8-e4m3fn.safetensors" \
        "diffusion_models/flux1-dev-fp8-e4m3fn.safetensors" 11901525888
  fetch "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors" \
        "text_encoders/clip_l.safetensors" 246144152
  fetch "https://huggingface.co/Comfy-Org/Lumina_Image_2.0_Repackaged/resolve/main/split_files/vae/ae.safetensors" \
        "vae/ae.safetensors" 335304388
  # T5-XXL: intentionally NOT downloaded here — ltx() already placed the
  # byte-identical file at text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors.
  if [[ ! -f "$MODELS/text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors" ]]; then
    echo "  T5 missing — pulling it (normally shared with LTX)"
    fetch "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn_scaled.safetensors" \
          "text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors" 5157348688
  else
    echo "  [have] text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors (shared with LTX)"
  fi
}

# ----------------------------------------------------------------- Wan 2.2 --
# Wan 2.2 I2V 14B: a TWO-EXPERT model. The high-noise and low-noise files are
# both required — they are not alternatives. Sampling runs high-noise for steps
# 0-10, then hands the leftover-noise latent to low-noise for steps 10-end.
#
# VAE is wan_2.1_vae.safetensors (NOT wan2.2_vae.safetensors — that one is for
# the 5B ti2v model only). Text encoder is UMT5, which is a DIFFERENT model from
# the T5-XXL used by LTX/FLUX and cannot be shared.
wan() {
  echo "== Wan 2.2 I2V 14B fp8 =="
  need_space 38000000000
  local base="https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files"
  fetch "$base/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors" \
        "diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors" 14294742832
  fetch "$base/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors" \
        "diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors" 14294742832
  fetch "$base/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" \
        "text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" 6735906897
  fetch "$base/vae/wan_2.1_vae.safetensors" \
        "vae/wan_2.1_vae.safetensors" 253815318
}

case "${1:-all}" in
  ltx)  ltx ;;
  flux) flux ;;
  wan)  wan ;;
  all)  ltx; flux; wan ;;
  *)    echo "usage: $0 [ltx|flux|wan|all]"; exit 1 ;;
esac
echo "Done."
