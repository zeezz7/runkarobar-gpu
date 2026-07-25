#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
# secrets come from /workspace/.env - never hardcoded
set -a; [ -f /workspace/.env ] && . /workspace/.env; set +a
export MINIO_ENDPOINT=staging-storage.runkarobar.com MINIO_ACCESS_KEY=runkarobar \
       MINIO_SECRET_KEY="${MINIO_SECRET_KEY:?set it in /workspace/.env}" MINIO_BUCKET=runkarobar
PY=/venv/main/bin/python; V=/workspace/ComfyUI/output/video

echo "=== STAGE 1: four scene images (Qwen-Image-Edit-2511, 40 steps) ==="
for i in 1 2 3 4; do
  out=$($PY run_and_upload.py workflows/run_nv${i}_img.api.json --no-upload 2>/dev/null | tail -1)
  [ -f "$out" ] || { echo "  img$i FAILED"; continue; }
  cp -f "$out" /workspace/ComfyUI/input/nv${i}.png
  cp -f "$out" /workspace/ComfyUI/output/nivea_scene${i}.png
  echo "  img$i ok -> $(basename $out)"
done

echo "=== STAGE 2: four Wan 2.2 clips ==="
for i in 1 2 3 4; do
  out=$($PY run_and_upload.py workflows/run_nv${i}_vid.api.json --no-upload 2>/dev/null | tail -1)
  [ -f "$out" ] && echo "  clip$i ok -> $(basename $out)" || echo "  clip$i FAILED"
done

echo "=== STAGE 3: concat + encode ==="
cd "$V"; : > nvconcat.txt
for i in 1 2 3 4; do echo "file '$V/nv${i}_clip_00001_.mp4'" >> nvconcat.txt; done
ffmpeg -loglevel error -y -f concat -safe 0 -i nvconcat.txt -c copy nivea_master.mp4
ffmpeg -loglevel error -y -i nivea_master.mp4 -vf "scale=1080:1920:flags=lanczos,format=yuv420p" \
  -c:v libx264 -profile:v high -preset medium -crf 21 -maxrate 6M -bufsize 12M -movflags +faststart -r 30 nivea_reel_1080p.mp4
ffmpeg -loglevel error -y -i nivea_master.mp4 -vf "scale=720:1280:flags=lanczos,format=yuv420p" \
  -c:v libx264 -profile:v high -preset medium -crf 23 -maxrate 2M -bufsize 4M -movflags +faststart -r 30 nivea_reel_720p.mp4
ls -la nivea_reel_*.mp4 | awk '{printf "  %-26s %6.1f MB\n",$9,$5/1e6}'

echo "=== STAGE 4: upload ==="
cd /workspace/models-setup
for i in 1 2 3 4; do $PY minio_upload.py /workspace/ComfyUI/output/nivea_scene${i}.png --prefix images 2>&1 | tail -1; done
for f in nivea_reel_720p nivea_reel_1080p; do $PY minio_upload.py "$V/${f}.mp4" --prefix reels 2>&1 | tail -1; done
echo "NIVEA_REEL_DONE"
