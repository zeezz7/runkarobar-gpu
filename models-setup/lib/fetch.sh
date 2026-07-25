#!/usr/bin/env bash
# Shared download helper for the ComfyUI model bake-off set.
#
# Design goals:
#   * idempotent      - re-running skips any file whose local size already
#                       matches the remote size exactly (byte check).
#   * size-verified   - remote size comes from HuggingFace's `x-linked-size`
#                       header (the true LFS object size); plain
#                       `content-length` is used as a fallback for non-LFS or
#                       non-HF hosts.
#   * disk-safe       - refuses to start a download that would push free space
#                       below MIN_FREE_GB, and aborts cleanly mid-flight if the
#                       disk runs low.
#   * resumable       - partial files land in <dest>.part and are resumed with
#                       curl -C -.
#
# Usage:  fetch <url> <dest_abs_path> [friendly_name]

set -uo pipefail

# Working headroom to preserve on the filesystem holding the models.
MIN_FREE_GB="${MIN_FREE_GB:-12}"
MANIFEST="${MANIFEST:-/workspace/models-setup/logs/manifest.tsv}"

_bytes_free() {
  # Free bytes on the filesystem holding $1
  df -PB1 "$(dirname "$1")" | awk 'NR==2{print $4}'
}

_human() {
  awk -v b="$1" 'BEGIN{
    if (b >= 1073741824) printf "%.2f GiB", b/1073741824;
    else if (b >= 1048576) printf "%.1f MiB", b/1048576;
    else printf "%d B", b
  }'
}

# Echo the authoritative remote size in bytes, or empty string if unknown.
remote_size() {
  local url="$1" hdrs
  hdrs="$(curl -sIL --retry 3 --retry-delay 2 --max-time 60 "$url" 2>/dev/null)" || return 1
  local code
  code="$(printf '%s' "$hdrs" | awk 'toupper($1) ~ /^HTTP/ {c=$2} END{print c}')"
  if [[ "$code" != "200" ]]; then
    echo "HTTP_${code:-000}" >&2
    return 1
  fi
  # x-linked-size is HF's true LFS object size; content-length on the final hop
  # is the CDN body length. Prefer x-linked-size when present.
  local xls cl
  xls="$(printf '%s' "$hdrs" | tr -d '\r' | awk 'BEGIN{IGNORECASE=1}/^x-linked-size:/{print $2}' | tail -1)"
  cl="$(printf '%s' "$hdrs" | tr -d '\r' | awk 'BEGIN{IGNORECASE=1}/^content-length:/{print $2}' | tail -1)"
  if [[ -n "$xls" ]]; then echo "$xls"; elif [[ -n "$cl" ]]; then echo "$cl"; else echo ""; fi
}

fetch() {
  local url="$1" dest="$2" name="${3:-$(basename "$2")}"
  local dir; dir="$(dirname "$dest")"
  mkdir -p "$dir"

  local rsize
  rsize="$(remote_size "$url")" || {
    echo "  !! HEAD failed / non-200 for ${name}" >&2
    echo -e "FAIL\t${name}\t${dest}\t0\t${url}\thead_failed" >> "$MANIFEST"
    return 1
  }

  if [[ -z "$rsize" ]]; then
    echo "  ?? remote size unknown for ${name} - downloading unverified" >&2
    rsize=0
  fi

  # ---- idempotent skip -----------------------------------------------------
  if [[ -f "$dest" ]]; then
    local lsize; lsize="$(stat -c%s "$dest")"
    if [[ "$rsize" != "0" && "$lsize" == "$rsize" ]]; then
      echo "  == ${name} already complete ($(_human "$lsize"))"
      echo -e "OK\t${name}\t${dest}\t${lsize}\t${url}\tskipped_verified" >> "$MANIFEST"
      return 0
    fi
    echo "  ~~ ${name} size mismatch (local ${lsize} vs remote ${rsize}) - refetching"
    mv -f "$dest" "${dest}.part"
  fi

  # ---- disk safety gate ----------------------------------------------------
  local have need free_after
  have=0
  [[ -f "${dest}.part" ]] && have="$(stat -c%s "${dest}.part")"
  need=$(( rsize - have ))
  (( need < 0 )) && need=0
  local avail; avail="$(_bytes_free "$dest")"
  free_after=$(( avail - need ))
  local min_bytes=$(( MIN_FREE_GB * 1073741824 ))

  if (( rsize > 0 && free_after < min_bytes )); then
    echo "  XX ABORT ${name}: needs $(_human "$need"), only $(_human "$avail") free;" >&2
    echo "     would leave $(_human "$free_after") < ${MIN_FREE_GB} GiB floor. Skipping." >&2
    echo -e "SKIP\t${name}\t${dest}\t0\t${url}\tdisk_floor" >> "$MANIFEST"
    return 2
  fi

  echo "  -> ${name}  ($(_human "$rsize"))"
  # --fail so 4xx/5xx do not get written to disk as an HTML error page.
  if ! curl -sSL --fail --retry 5 --retry-delay 5 --retry-connrefused \
        -C - -o "${dest}.part" "$url"; then
    echo "  !! download failed: ${name}" >&2
    echo -e "FAIL\t${name}\t${dest}\t0\t${url}\tcurl_error" >> "$MANIFEST"
    return 1
  fi

  # ---- post-download byte verification ------------------------------------
  local got; got="$(stat -c%s "${dest}.part")"
  if [[ "$rsize" != "0" && "$got" != "$rsize" ]]; then
    echo "  !! SIZE MISMATCH ${name}: got ${got}, expected ${rsize} - leaving .part" >&2
    echo -e "FAIL\t${name}\t${dest}\t${got}\t${url}\tsize_mismatch_expected_${rsize}" >> "$MANIFEST"
    return 1
  fi
  mv -f "${dest}.part" "$dest"
  echo "  ok ${name}  $(_human "$got")"
  echo -e "OK\t${name}\t${dest}\t${got}\t${url}\tdownloaded" >> "$MANIFEST"
  return 0
}

# Guard used between families: bail out of a script if the disk is already low.
disk_guard() {
  local path="${1:-/workspace}"
  local avail; avail="$(df -PB1 "$path" | awk 'NR==2{print $4}')"
  local min_bytes=$(( MIN_FREE_GB * 1073741824 ))
  if (( avail < min_bytes )); then
    echo "XX DISK GUARD: only $(_human "$avail") free (floor ${MIN_FREE_GB} GiB). Stopping." >&2
    return 1
  fi
  echo "-- disk ok: $(_human "$avail") free"
  return 0
}
