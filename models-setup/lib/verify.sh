#!/usr/bin/env bash
# Re-verify every file recorded in the manifest against its remote size.
# Run standalone:  bash /workspace/models-setup/lib/verify.sh
source "$(dirname "${BASH_SOURCE[0]}")/fetch.sh"

MANIFEST_IN="${1:-/workspace/models-setup/logs/manifest.tsv}"
pass=0; fail=0; missing=0

printf '%-58s %14s %14s  %s\n' FILE LOCAL REMOTE STATUS
printf '%s\n' "--------------------------------------------------------------------------------------------------"

# Unique dest paths, last record wins
awk -F'\t' '$1=="OK"{d[$3]=$5} END{for (k in d) print k "\t" d[k]}' "$MANIFEST_IN" | sort | while IFS=$'\t' read -r dest url; do
  base="$(basename "$dest")"
  if [[ ! -f "$dest" ]]; then
    printf '%-58s %14s %14s  %s\n' "$base" "-" "-" "MISSING"
    continue
  fi
  l="$(stat -c%s "$dest")"
  r="$(remote_size "$url" 2>/dev/null)"
  if [[ -z "$r" ]]; then
    printf '%-58s %14s %14s  %s\n' "$base" "$l" "?" "REMOTE_UNKNOWN"
  elif [[ "$l" == "$r" ]]; then
    printf '%-58s %14s %14s  %s\n' "$base" "$l" "$r" "OK"
  else
    printf '%-58s %14s %14s  %s\n' "$base" "$l" "$r" "MISMATCH"
  fi
done
