#!/usr/bin/env bash
# Waits for the video bake-off to finish, then runs the E1.1 denoise sweep
# (PART A retry) and the PART C vision-guard check.
set -uo pipefail
cd "$(dirname "$0")"
# secrets come from /workspace/.env - never hardcoded
set -a; [ -f /workspace/.env ] && . /workspace/.env; set +a
export MINIO_ENDPOINT=staging-storage.runkarobar.com MINIO_ACCESS_KEY=runkarobar \
       MINIO_SECRET_KEY="${MINIO_SECRET_KEY:?set it in /workspace/.env}" MINIO_BUCKET=runkarobar
PY=/venv/main/bin/python

while pgrep -f 'bakeoff.sh videoB' >/dev/null; do sleep 10; done
echo "=== PART B finished; starting E1.1 denoise sweep ==="
for dn in 0p45 0p6 0p75; do
  wf=workflows/run_hero_e11_dn${dn}.api.json
  [ -f "$wf" ] || continue
  echo ">>> denoise ${dn}"
  out=$($PY run_and_upload.py "$wf" --no-upload 2>>logs/sweep.log | tail -1)
  if [ -n "$out" ] && [ -f "$out" ]; then
    cp -f "$out" "$(dirname "$out")/hero_e11_${dn}.png"
    url=$($PY minio_upload.py "$(dirname "$out")/hero_e11_${dn}.png" --prefix images 2>&1 | tail -1 | awk '{print $1}')
    echo "  $out -> $url"
    printf 'sweep_%s\tHiDream-E1.1 denoise %s\t-\t-\t%s\t%s\n' "$dn" "$dn" "$out" "$url" >> logs/bakeoff_results.tsv
  else
    echo "  FAILED denoise ${dn}"
  fi
done
echo "=== PART C: vision guard ==="
./bakeoff.sh guardC /workspace/ComfyUI/output/hero_hidream.png
echo "=== ALL DONE ==="
