#!/usr/bin/env bash
# =============================================================================
#  ComfyUI model bake-off set - downloader
# =============================================================================
#  Every source URL below was verified to return HTTP 200 ANONYMOUSLY (no HF
#  token) and its byte size read from the HuggingFace `x-linked-size` header.
#
#  Idempotent: re-running skips any file whose on-disk size already matches the
#  remote size exactly. Safe to re-run after an interruption (partial files
#  resume via curl -C -).
#
#  Usage:
#     ./download_models.sh                # all enabled families
#     ./download_models.sh shared flux    # only the named families
#     MIN_FREE_GB=20 ./download_models.sh # raise the disk floor
#
#  Families: shared flux hidream ltx098 ltx23 wan22 hunyuan mochi qwen
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")"
source lib/fetch.sh

M=/workspace/ComfyUI/models
export MIN_FREE_GB="${MIN_FREE_GB:-12}"
mkdir -p logs && : > "${MANIFEST:-logs/manifest.tsv}"

HF=https://huggingface.co

# -----------------------------------------------------------------------------
# shared - encoders/VAE used by more than one family. Download ONCE.
#   t5xxl_fp8_e4m3fn_scaled : byte-identical across comfyanonymous/flux_text_encoders,
#                             Comfy-Org/HiDream-I1_ComfyUI and
#                             Comfy-Org/mochi_preview_repackaged (SHA256
#                             a498f048...57a verified in all three).
#                             ONE copy serves HiDream + LTX-0.9.8 + Mochi.
#                             NOTE: ComfyUI's LTX-0.9.8 and Mochi templates
#                             default to t5xxl_fp16 (9.79 GB). We deliberately
#                             use the fp8 scaled build instead: it is the same
#                             T5-XXL, is published by Comfy-Org for both models,
#                             and saves 9.79 GB. If LTX prompt adherence ever
#                             looks weak, add t5xxl_fp16 (see f_t5fp16 below)
#                             and switch that workflow's CLIPLoader to it.
#   ae.safetensors          : the FLUX autoencoder, byte-identical across the
#                             Lumina and HiDream repos. Serves FLUX + HiDream.
#   clip_l.safetensors      : FLUX/Hunyuan CLIP-L. NOTE this is NOT the same
#                             file as clip_l_hidream.safetensors.
# -----------------------------------------------------------------------------
f_shared() {
  echo "== shared encoders / VAE =="
  fetch "$HF/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn_scaled.safetensors" \
        "$M/text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors"
  fetch "$HF/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors" \
        "$M/text_encoders/clip_l.safetensors"
  fetch "$HF/Comfy-Org/Lumina_Image_2.0_Repackaged/resolve/main/split_files/vae/ae.safetensors" \
        "$M/vae/ae.safetensors"
}

# OPTIONAL: the fp16 T5-XXL that ComfyUI's LTX-0.9.8 / Mochi templates default
# to. +9.79 GB. Only add this if fp8 prompt adherence proves insufficient.
f_t5fp16() {
  echo "== OPTIONAL t5xxl_fp16 =="
  fetch "$HF/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp16.safetensors" \
        "$M/text_encoders/t5xxl_fp16.safetensors"
}

# -----------------------------------------------------------------------------
# flux - FLUX.1-dev fp8.  NON-COMMERCIAL LICENSE.
#   black-forest-labs/FLUX.1-dev is GATED (401 anon), and so is
#   Comfy-Org/Flux_Dev_ComfyUI_Repackaged (the commonly-cited "ungated mirror" -
#   it is NOT ungated). Kijai/flux-fp8 is open and is a direct fp8_e4m3fn cast
#   of the BFL weights (780 tensors, 100% F8_E4M3, BFL key layout).
# -----------------------------------------------------------------------------
f_flux() {
  echo "== FLUX.1-dev fp8 =="
  fetch "$HF/Kijai/flux-fp8/resolve/main/flux1-dev-fp8-e4m3fn.safetensors" \
        "$M/diffusion_models/flux1-dev-fp8-e4m3fn.safetensors"
}

# -----------------------------------------------------------------------------
# hidream - HiDream-I1-FULL fp8 (txt2img, the high-end variant) + E1.1 fp8. MIT.
#   All three I1 fp8 variants (full/dev/fast) are byte-identical in size
#   (17,105,946,040) - Full costs nothing extra over Dev. Full is the
#   non-distilled, highest-quality variant: cfg 5.0, 50 steps, uni_pc/simple,
#   and it is the ONLY I1 variant where negative prompts actually work
#   (dev/fast are guidance-distilled and ignore them).
#   E1.1 has NO official fp8 - Comfy-Org ships only bf16 (34.21 GB). The
#   boricuapab repack is the only fp8 build and halves it to 17.11 GB.
#   clip_l_hidream / clip_g_hidream are LONG-CLIP variants - they are NOT the
#   FLUX clip_l/clip_g and must not be substituted.
# -----------------------------------------------------------------------------
f_hidream() {
  echo "== HiDream-I1-Full fp8 + E1.1 fp8 =="
  local B=$HF/Comfy-Org/HiDream-I1_ComfyUI/resolve/main/split_files
  fetch "$B/diffusion_models/hidream_i1_full_fp8.safetensors" \
        "$M/diffusion_models/hidream_i1_full_fp8.safetensors"
  fetch "$B/text_encoders/clip_l_hidream.safetensors" "$M/text_encoders/clip_l_hidream.safetensors"
  fetch "$B/text_encoders/clip_g_hidream.safetensors" "$M/text_encoders/clip_g_hidream.safetensors"
  fetch "$B/text_encoders/llama_3.1_8b_instruct_fp8_scaled.safetensors" \
        "$M/text_encoders/llama_3.1_8b_instruct_fp8_scaled.safetensors"
  fetch "$HF/boricuapab/hidream_e1_1_full_bf16-fp8/resolve/main/hidream_e1_1_bf16-fp8.safetensors" \
        "$M/diffusion_models/hidream_e1_1_fp8.safetensors"
}

# -----------------------------------------------------------------------------
# wan22 - Wan 2.2 I2V 14B fp8. Apache-2.0.
#   TWO experts (high_noise + low_noise) - BOTH required, chained as two
#   KSamplerAdvanced passes.
#   TRAP: the VAE is wan_2.1_vae.safetensors (253,815,318 B). The 2.2 VAE is
#   for the 5B TI2V model ONLY (48-ch vs 16-ch latent) and will not work here.
#   The LightX2V 4-step LoRAs are optional but are wired in by ComfyUI's own
#   template turbo toggle (~536s -> ~85s on a 4090D at 640x640).
# -----------------------------------------------------------------------------
f_wan22() {
  echo "== Wan 2.2 I2V 14B fp8 =="
  local B=$HF/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files
  fetch "$B/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors" \
        "$M/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"
  fetch "$B/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors" \
        "$M/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"
  fetch "$B/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" \
        "$M/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
  fetch "$B/vae/wan_2.1_vae.safetensors" "$M/vae/wan_2.1_vae.safetensors"
  fetch "$B/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors" \
        "$M/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors"
  fetch "$B/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors" \
        "$M/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors"
}

# -----------------------------------------------------------------------------
# ltx098 - LTX-Video 13B 0.9.8 fp8. Lightricks OpenRAIL-style license.
# -----------------------------------------------------------------------------
f_ltx098() {
  echo "== LTX-Video 13B 0.9.8 fp8 =="
  fetch "$HF/Lightricks/LTX-Video/resolve/main/ltxv-13b-0.9.8-dev-fp8.safetensors" \
        "$M/checkpoints/ltxv-13b-0.9.8-dev-fp8.safetensors"
}

# -----------------------------------------------------------------------------
# ltx23 - LTX-2.3 22B fp8. Uses a GEMMA-3-12B text encoder (not T5), so it
#   shares nothing with the other families.
#   The single checkpoint serves three loaders: CheckpointLoaderSimple,
#   LTXVAudioVAELoader, and LTXAVTextEncoderLoader(ckpt_name).
#   LOCAL inference only - do NOT use the bundled api_ltxv_*.json templates or
#   the LtxvApiTextToVideo / LtxvApiImageToVideo nodes; those bill a PAID cloud
#   service. URLs below come from ComfyUI's own local (non-API) template.
# -----------------------------------------------------------------------------
f_ltx23() {
  echo "== LTX-2.3 22B fp8 =="
  fetch "$HF/Lightricks/LTX-2.3-fp8/resolve/main/ltx-2.3-22b-dev-fp8.safetensors" \
        "$M/checkpoints/ltx-2.3-22b-dev-fp8.safetensors"
  fetch "$HF/Comfy-Org/ltx-2/resolve/main/split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors" \
        "$M/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors"
  fetch "$HF/Lightricks/LTX-2.3/resolve/main/ltx-2.3-spatial-upscaler-x2-1.1.safetensors" \
        "$M/latent_upscale_models/ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
  fetch "$HF/Comfy-Org/ltx-2.3/resolve/main/split_files/loras/ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors" \
        "$M/loras/ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors"
  fetch "$HF/Comfy-Org/ltx-2/resolve/main/split_files/loras/gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors" \
        "$M/loras/gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors"
}

# -----------------------------------------------------------------------------
# hunyuan - HunyuanVideo t2v 720p fp8. Tencent Community License (restricted).
#   Comfy-Org/HunyuanVideo_repackaged ships ONLY bf16 (25.64 GB); the fp8 build
#   lives on Kijai/HunyuanVideo_comfy at 13.19 GB. The cfgdistill build is the
#   standard t2v model (it is guidance-distilled -> use cfg 1.0).
# -----------------------------------------------------------------------------
f_hunyuan() {
  echo "== HunyuanVideo t2v 720p fp8 =="
  fetch "$HF/Kijai/HunyuanVideo_comfy/resolve/main/hunyuan_video_720_cfgdistill_fp8_e4m3fn.safetensors" \
        "$M/diffusion_models/hunyuan_video_720_cfgdistill_fp8_e4m3fn.safetensors"
  fetch "$HF/Comfy-Org/HunyuanVideo_repackaged/resolve/main/split_files/text_encoders/llava_llama3_fp8_scaled.safetensors" \
        "$M/text_encoders/llava_llama3_fp8_scaled.safetensors"
  fetch "$HF/Comfy-Org/HunyuanVideo_repackaged/resolve/main/split_files/vae/hunyuan_video_vae_bf16.safetensors" \
        "$M/vae/hunyuan_video_vae_bf16.safetensors"
}

# -----------------------------------------------------------------------------
# mochi - Mochi 1 preview fp8. Apache-2.0. Uses the shared t5xxl.
# -----------------------------------------------------------------------------
f_mochi() {
  echo "== Mochi 1 preview fp8 =="
  local B=$HF/Comfy-Org/mochi_preview_repackaged/resolve/main/split_files
  fetch "$B/diffusion_models/mochi_preview_fp8_scaled.safetensors" \
        "$M/diffusion_models/mochi_preview_fp8_scaled.safetensors"
  fetch "$B/vae/mochi_vae.safetensors" "$M/vae/mochi_vae.safetensors"
}

# -----------------------------------------------------------------------------
# qwen - Qwen2.5-VL vision guard. Apache-2.0. NOT a ComfyUI model - it lives
#   outside models/ and is driven by validate_image.py.
# -----------------------------------------------------------------------------
f_qwen() {
  echo "== Qwen2.5-VL vision guard =="
  QWEN_REPO="${QWEN_REPO:-Qwen/Qwen2.5-VL-7B-Instruct}"
  local dest="/workspace/models/qwen2.5-vl/${QWEN_REPO##*/}"
  # NOTE: --exclude must be REPEATED per pattern. Passing
  #   --exclude "*.pth" "*.bin" "original/*"
  # makes the CLI treat the extra strings as positional FILENAMES, warn
  # "Ignoring --exclude since filenames have being explicitly set", download
  # nothing, and still EXIT 0 - a silent false success.
  /venv/main/bin/hf download "$QWEN_REPO" \
      --local-dir "$dest" \
      --exclude "*.pth" --exclude "*.bin" --exclude "original/*" \
      --max-workers 8 || { echo "  !! qwen download failed"; return 1; }

  # hf exits 0 too readily, so assert the weights are actually there.
  local idx="$dest/model.safetensors.index.json"
  if [[ ! -f "$idx" ]]; then
    echo "  !! qwen: no model.safetensors.index.json at $dest"; return 1
  fi
  local missing=0 shard
  while read -r shard; do
    [[ -f "$dest/$shard" ]] || { echo "  !! qwen: missing shard $shard"; missing=1; }
  done < <(/venv/main/bin/python -c "
import json,sys
print('\n'.join(sorted(set(json.load(open(sys.argv[1]))['weight_map'].values()))))" "$idx")
  (( missing )) && return 1
  local bytes; bytes=$(du -sb "$dest" | cut -f1)
  if (( bytes < 10000000000 )); then
    echo "  !! qwen: only $((bytes/1000000)) MB on disk - incomplete"; return 1
  fi
  echo "  ok qwen ($QWEN_REPO, $((bytes/1000000000)) GB, all shards present)"
}

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# extras - models added during the bake-off, not part of the original set.
#   4x-UltraSharp   : ESRGAN upscaler used by the UHD image workflow.
#   birefnet        : segmentation for MASKED COMPOSITING - the only reliable way
#                     to change a background while keeping a product/garment
#                     pixel-exact. Loaded by ComfyUI's native
#                     LoadBackgroundRemovalModel / RemoveBackground nodes.
# -----------------------------------------------------------------------------
f_extras() {
  echo "== extras (upscaler + BiRefNet segmentation) =="
  fetch "$HF/uwg/upscaler/resolve/main/ESRGAN/4x-UltraSharp.pth" \
        "$M/upscale_models/4x-UltraSharp.pth"
  fetch "$HF/Comfy-Org/BiRefNet/resolve/main/background_removal/birefnet.safetensors" \
        "$M/background_removal/birefnet.safetensors"
}

# -----------------------------------------------------------------------------
# qwenimage - Qwen-Image-Edit-2511 (instruction editing) + Qwen-Image-2512
#   (text-to-image). Apache-2.0, ungated. Replaces HiDream on this box.
#   * 2511 is the CURRENT edit revision (supersedes 2509). Its release notes
#     cite reduced image drift and better character/identity consistency -
#     exactly the product-fidelity problem HiDream-E1.1 failed.
#   * There is NO plain fp8_e4m3fn build of 2511; the fp8 pick is "fp8mixed",
#     which keeps sensitive layers at higher precision (bf16 is 38.1 GiB).
#   * The 2512 BASE model is required for plain text-to-image (backgrounds for
#     the masked-composite workflows). The Edit model has no empty-latent path -
#     its KSampler latent always comes from VAEEncode of an input image.
#   * qwen_2.5_vl_7b_fp8_scaled is SHARED by every Qwen-Image variant - one copy.
#     NOTE: this is the ComfyUI-format text encoder, NOT the same thing as the
#     transformers checkpoint in /workspace/models/qwen2.5-vl used by the guard.
#   * CLIPLoader type must be "qwen_image"; model chain needs
#     ModelSamplingAuraFlow(shift=3.1) -> CFGNorm.
# -----------------------------------------------------------------------------
f_qwenimage() {
  echo "== Qwen-Image-Edit-2511 + Qwen-Image-2512 =="
  local E=$HF/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files
  local B=$HF/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files
  # shared encoder + vae first (cheap, needed by everything)
  fetch "$B/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" \
        "$M/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"
  fetch "$B/vae/qwen_image_vae.safetensors" "$M/vae/qwen_image_vae.safetensors"
  # the edit model - the main event
  fetch "$E/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors" \
        "$M/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors"
  # base t2i - replaces HiDream as the background generator
  fetch "$B/diffusion_models/qwen_image_2512_fp8_e4m3fn.safetensors" \
        "$M/diffusion_models/qwen_image_2512_fp8_e4m3fn.safetensors"
  # 4-step Lightning LoRAs (optional, ~10x faster; costs prompt adherence)
  fetch "$HF/lightx2v/Qwen-Image-Edit-2511-Lightning/resolve/main/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors" \
        "$M/loras/Qwen-Image-Edit-2511-Lightning-4steps.safetensors"
  fetch "$HF/lightx2v/Qwen-Image-2512-Lightning/resolve/main/Qwen-Image-2512-Lightning-4steps-V1.0-bf16.safetensors" \
        "$M/loras/Qwen-Image-2512-Lightning-4steps.safetensors"
  # product-into-scene helper LoRA (trained on 2509; 2511 compat untested)
  fetch "$E/loras/Qwen-Image-Edit-2509-White_to_Scene.safetensors" \
        "$M/loras/Qwen-Image-Edit-2509-White_to_Scene.safetensors"
}


# -----------------------------------------------------------------------------
# brain - Qwen2.5-32B-Instruct fp8 (compressed-tensors). Stage 0 of the reel
#   pipeline: writes the storyboard. NOT a ComfyUI model - lives outside
#   ComfyUI/models and is loaded by reelkit/brain.py via transformers.
#   fp8 is chosen over AWQ/GPTQ int4 because those kernels have no sm_120
#   (Blackwell) support, while fp8 is native on this GPU.
# -----------------------------------------------------------------------------
f_brain() {
  echo "== Qwen2.5-32B-Instruct-FP8-dynamic (reel pipeline brain) =="
  local dest="/workspace/models/brain/Qwen2.5-32B-Instruct-FP8-dynamic"
  /venv/main/bin/hf download RedHatAI/Qwen2.5-32B-Instruct-FP8-dynamic \
      --local-dir "$dest" --exclude "*.pth" --exclude "original/*" --max-workers 8 \
    || { echo "  !! brain download failed"; return 1; }
  local idx="$dest/model.safetensors.index.json"
  [[ -f "$idx" ]] || { echo "  !! missing index at $dest"; return 1; }
  local missing=0 shard
  while read -r shard; do
    [[ -f "$dest/$shard" ]] || { echo "  !! missing shard $shard"; missing=1; }
  done < <(/venv/main/bin/python -c "
import json,sys
print('\n'.join(sorted(set(json.load(open(sys.argv[1]))['weight_map'].values()))))" "$idx")
  (( missing )) && return 1
  echo "  ok brain ($(du -sh "$dest" | cut -f1), all shards present)"
}
# -----------------------------------------------------------------------------
# hunyuani2v - HunyuanVideo I2V 720p. Replaces LTX-2.3 (deleted) as the
#   higher-resolution video path. NOTE the model is bf16 only (no fp8 build) and
#   I2V additionally needs a clip_vision encoder that T2V does not.
#   Licence: Tencent Hunyuan Community - EXCLUDES the EU, UK and South Korea.
# -----------------------------------------------------------------------------
f_hunyuani2v() {
  echo "== HunyuanVideo I2V 720p =="
  local B=$HF/Comfy-Org/HunyuanVideo_repackaged/resolve/main/split_files
  fetch "$B/diffusion_models/hunyuan_video_image_to_video_720p_bf16.safetensors" \
        "$M/diffusion_models/hunyuan_video_image_to_video_720p_bf16.safetensors"
  fetch "$B/text_encoders/llava_llama3_fp8_scaled.safetensors" \
        "$M/text_encoders/llava_llama3_fp8_scaled.safetensors"
  fetch "$B/text_encoders/clip_l.safetensors" "$M/text_encoders/clip_l.safetensors"
  fetch "$B/clip_vision/llava_llama3_vision.safetensors" \
        "$M/clip_vision/llava_llama3_vision.safetensors"
  fetch "$B/vae/hunyuan_video_vae_bf16.safetensors" "$M/vae/hunyuan_video_vae_bf16.safetensors"
}

# -----------------------------------------------------------------------------
# wan22s2v - Wan 2.2 S2V 14B, audio-driven video (real lip-sync), ON-BOX.
#   Apache-2.0, same licence and family as the I2V model already installed.
#   This replaces the remote talking-avatar service that was removed: every
#   pixel is generated locally, which is a hard rule for this pipeline.
#   Needs an audio encoder (wav2vec2) that the I2V path does not - the node
#   chain is AudioEncoderLoader -> AudioEncoderEncode -> WanSoundImageToVideo.
#   fp8_scaled (16.4 GB) over bf16 (32.6 GB): same trade as every other model
#   here, and it leaves room on the card beside the image models.
# -----------------------------------------------------------------------------
f_wan22s2v() {
  echo "== Wan 2.2 S2V 14B (local lip-sync) =="
  local B=$HF/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files
  fetch "$B/diffusion_models/wan2.2_s2v_14B_fp8_scaled.safetensors" \
        "$M/diffusion_models/wan2.2_s2v_14B_fp8_scaled.safetensors"
  fetch "$B/audio_encoders/wav2vec2_large_english_fp16.safetensors" \
        "$M/audio_encoders/wav2vec2_large_english_fp16.safetensors"
}

# The DEFAULT set is the live reelkit working set (2026-07-27), nothing more.
# Deliberately NOT default, and why:
#   flux      non-commercial licence.
#   hidream   lost the image bake-off to Qwen-Image-Edit ("MEN" -> "NEN").
#   ltx098 ltx23 mochi   lost the video bake-off; deleted from the box.
#   hunyuan   that is HunyuanVideo *T2V*, deleted. The live one is hunyuani2v.
#   shared    t5xxl_fp8 / clip_l / ae are orphaned now - every live model
#             bundles its own encoders (hunyuani2v fetches its own clip_l).
#   brain     the storyboard brain moved to WaveSpeed (remote); no local
#             Qwen2.5-Instruct is installed. Saves ~50 GB of disk and VRAM.
# Any of them is one argument away:  ./download_models.sh hidream ltx23
FAMILIES=("$@")
if [[ ${#FAMILIES[@]} -eq 0 ]]; then
  FAMILIES=(qwenimage wan22 hunyuani2v qwen extras)
fi
for fam in "${FAMILIES[@]}"; do
  disk_guard /workspace || { echo "Stopping before '${fam}' - disk floor reached."; exit 1; }
  "f_${fam}"
done
disk_guard /workspace
echo "== done. manifest: ${MANIFEST:-logs/manifest.tsv}"

