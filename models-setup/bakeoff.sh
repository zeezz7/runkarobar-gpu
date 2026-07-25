#!/usr/bin/env bash
# =============================================================================
#  Render bake-off: one comparable output per model, timed + VRAM-profiled,
#  uploaded to MinIO.
# =============================================================================
#  Usage:
#     ./bakeoff.sh prep     <ref_image>   # stage ref image + build run workflows
#     ./bakeoff.sh imageA   <ref_image>   # PART A - HiDream-E1.1 product hero
#     ./bakeoff.sh videoB   <hero_image>  # PART B - all video models
#     ./bakeoff.sh guardC   <hero_image>  # PART C - Qwen2.5-VL verdict
#     ./bakeoff.sh all      <ref_image>   # A -> B -> C
#
#  Results accumulate in logs/bakeoff_results.tsv:
#     job \t model \t seconds \t peak_vram_MiB \t local_path \t url
#
#  NOTE ON SCOPE (see REPORT): only LTX-0.9.8, LTX-2.3 and Wan 2.2 are true
#  image->video here. HunyuanVideo I2V is a SEPARATE 25.6 GB model plus a
#  0.65 GB clip_vision encoder (26.27 GB) that does not fit in the free space,
#  and Mochi 1 has no I2V variant at all - it is text-to-video only. Those two
#  therefore run as T2V from a matched prompt and are labelled as such; their
#  rows are comparable for motion/coherence but NOT for product fidelity.
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")"

PY=/venv/main/bin/python
WF=workflows
OUT=logs
RESULTS=$OUT/bakeoff_results.tsv
COMFY_INPUT=/workspace/ComfyUI/input
mkdir -p "$OUT" "$COMFY_INPUT"

# secrets come from /workspace/.env - never hardcoded
set -a; [ -f /workspace/.env ] && . /workspace/.env; set +a
export MINIO_ENDPOINT="${MINIO_ENDPOINT:-staging-storage.runkarobar.com}"
export MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-runkarobar}"
export MINIO_SECRET_KEY="${MINIO_SECRET_KEY:?set it in /workspace/.env}"
export MINIO_BUCKET="${MINIO_BUCKET:-runkarobar}"

[[ -f $RESULTS ]] || printf 'job\tmodel\tseconds\tpeak_vram_MiB\tlocal\turl\n' > "$RESULTS"

# ---------------------------------------------------------------- VRAM sampler
_vram_start() {          # $1 = tag
  ( while true; do
      nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null
      sleep 0.5
    done ) > "$OUT/vram_$1.txt" 2>/dev/null &
  echo $!
}
_vram_peak() {           # $1 = tag
  sort -n "$OUT/vram_$1.txt" 2>/dev/null | tail -1
}

# ------------------------------------------------------------------- run a job
# run_job <tag> <model-label> <workflow.json> <minio-prefix> <upload-basename>
run_job() {
  local tag="$1" model="$2" wf="$3" prefix="$4" newname="${5:-}"
  echo ""
  echo "=============================================================="
  echo ">>> $model   ($wf)"
  echo "=============================================================="
  [[ -f "$wf" ]] || { echo "  !! workflow missing: $wf"; return 1; }

  local sampler; sampler=$(_vram_start "$tag")
  local t0; t0=$(date +%s)

  local rendered
  rendered=$("$PY" run_and_upload.py "$wf" --no-upload 2>>"$OUT/render_$tag.log" | tail -1)
  local rc=$?

  local t1; t1=$(date +%s)
  kill "$sampler" 2>/dev/null; wait "$sampler" 2>/dev/null
  local secs=$(( t1 - t0 ))
  local peak; peak=$(_vram_peak "$tag")

  if [[ $rc -ne 0 || -z "$rendered" || ! -f "$rendered" ]]; then
    echo "  !! FAILED after ${secs}s - see $OUT/render_$tag.log"
    tail -n 12 "$OUT/render_$tag.log" | sed 's/^/     /'
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$tag" "$model" "$secs" "${peak:-?}" "FAILED" "-" >> "$RESULTS"
    return 1
  fi

  echo "  rendered in ${secs}s, peak VRAM ${peak} MiB -> $rendered"

  # optionally rename so the uploaded key is predictable
  local up="$rendered"
  if [[ -n "$newname" ]]; then
    up="$(dirname "$rendered")/$newname"
    cp -f "$rendered" "$up"
  fi

  local url
  url=$("$PY" minio_upload.py "$up" --prefix "$prefix" 2>&1 | tail -1 | awk '{print $1}')
  echo "  uploaded -> $url"
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$tag" "$model" "$secs" "${peak:-?}" "$rendered" "$url" >> "$RESULTS"
}

# ------------------------------------------------------------------------ prep
cmd_prep() {
  local ref="$1"
  [[ -f "$ref" ]] || { echo "reference image not found: $ref"; exit 1; }
  cp -f "$ref" "$COMFY_INPUT/product_ref$(echo "$ref" | sed 's/.*\(\.[^.]*\)$/\1/')"
  "$PY" bakeoff_prep.py --ref "$(basename "$COMFY_INPUT"/product_ref.*)"
}

# --------------------------------------------------------------------- PART A
cmd_imageA() {
  run_job hero "HiDream-E1.1 (edit)" "$WF/run_hero_hidream.api.json" images hero_hidream.png
}

# --------------------------------------------------------------------- PART B
cmd_videoB() {
  # Stage PART A's hero into ComfyUI/input so the i2v models consume the exact
  # same frame, then regenerate the video workflows against it.
  local hero="${1:-/workspace/ComfyUI/output/hero_hidream.png}"
  if [[ ! -f "$hero" ]]; then
    hero=$(ls -t /workspace/ComfyUI/output/hero_hidream*.png 2>/dev/null | head -1)
  fi
  [[ -f "$hero" ]] || { echo "!! no hero image found - run './bakeoff.sh imageA' first"; return 1; }
  cp -f "$hero" "$COMFY_INPUT/bakeoff_hero.png"
  echo "staged hero -> $COMFY_INPUT/bakeoff_hero.png  ($(basename "$hero"))"
  "$PY" bakeoff_prep.py --hero bakeoff_hero.png || return 1

  run_job ltx098   "LTX-Video 13B 0.9.8 (i2v)"      "$WF/run_ltx098_i2v.api.json"   reels bakeoff_ltx098.mp4
  run_job ltx23    "LTX-2.3 22B (i2v)"              "$WF/run_ltx23_i2v.api.json"    reels bakeoff_ltx23.mp4
  run_job wanturbo "Wan 2.2 I2V +LightX2V (4-step)" "$WF/run_wan22_turbo.api.json"  reels bakeoff_wan22_turbo.mp4
  run_job wanbase  "Wan 2.2 I2V baseline (20-step)" "$WF/run_wan22_base.api.json"   reels bakeoff_wan22_base.mp4
  run_job hunyuan  "HunyuanVideo 720p (T2V only)"   "$WF/run_hunyuan_t2v.api.json"  reels bakeoff_hunyuan.mp4
  run_job mochi    "Mochi 1 (T2V only)"             "$WF/run_mochi_t2v.api.json"    reels bakeoff_mochi.mp4
}

# --------------------------------------------------------------------- PART C
cmd_guardC() {
  local hero="$1"
  echo ""
  echo "=== PART C: Qwen2.5-VL-7B guard on $hero ==="
  local sampler; sampler=$(_vram_start guard)
  local t0; t0=$(date +%s)
  "$PY" validate_image.py "$hero" -o "$OUT/guard_hero.json" 2>"$OUT/guard_hero.log"
  local rc=$?
  local t1; t1=$(date +%s)
  kill "$sampler" 2>/dev/null; wait "$sampler" 2>/dev/null
  echo "guard exit=$rc in $((t1-t0))s, peak VRAM $(_vram_peak guard) MiB"
  cat "$OUT/guard_hero.json" 2>/dev/null
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' guard "Qwen2.5-VL-7B" "$((t1-t0))" "$(_vram_peak guard)" "$OUT/guard_hero.json" "-" >> "$RESULTS"
}

# ------------------------------------------------------------------------ main
case "${1:-}" in
  prep)   cmd_prep "$2" ;;
  imageA) cmd_imageA ;;
  videoB) cmd_videoB ;;
  guardC) cmd_guardC "$2" ;;
  all)    cmd_prep "$2"; cmd_imageA; cmd_videoB
          cmd_guardC "$(ls -t /workspace/ComfyUI/output/hero_hidream.png 2>/dev/null | head -1)" ;;
  *) sed -n '2,22p' "$0"; exit 1 ;;
esac

echo ""
echo "=== results so far ==="
column -t -s$'\t' "$RESULTS"
