#!/usr/bin/env python
"""
Verify downloaded .safetensors files without loading any weights.

Reads only the header (first 8 bytes = little-endian header length, then that
many bytes of JSON) and checks:
  * the file really is safetensors (an HTML error page or a truncated download
    fails here even when the byte count happens to look right)
  * the largest declared tensor offset does not exceed the file size
  * reports the dtype mix, so you can confirm an "fp8" file is actually F8_E4M3

Usage:
  /venv/main/bin/python lib/inspect_safetensors.py [path-or-dir ...]
Defaults to scanning the ComfyUI models tree.
"""
import json
import os
import struct
import sys
from collections import Counter

DEFAULT_ROOTS = ["/workspace/ComfyUI/models"]


def inspect(path):
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        raw = fh.read(8)
        if len(raw) < 8:
            return "TOO_SMALL", {}, size
        (hlen,) = struct.unpack("<Q", raw)
        if hlen <= 0 or hlen > size or hlen > 200_000_000:
            return "BAD_HEADER_LEN", {}, size
        head = fh.read(hlen)
    try:
        meta = json.loads(head)
    except Exception:
        return "HEADER_NOT_JSON", {}, size

    dtypes = Counter()
    max_end = 0
    for name, info in meta.items():
        if name == "__metadata__":
            continue
        if not isinstance(info, dict) or "dtype" not in info:
            return "BAD_ENTRY", {}, size
        dtypes[info["dtype"]] += 1
        offs = info.get("data_offsets")
        if isinstance(offs, list) and len(offs) == 2:
            max_end = max(max_end, offs[1])

    if 8 + hlen + max_end > size:
        return "TRUNCATED", dtypes, size
    return "OK", dtypes, size


def main():
    roots = sys.argv[1:] or DEFAULT_ROOTS
    files = []
    for r in roots:
        if os.path.isfile(r):
            files.append(r)
        else:
            for dirpath, _, names in os.walk(r):
                files += [os.path.join(dirpath, n) for n in sorted(names)
                          if n.endswith(".safetensors")]
    files = sorted(set(files))

    bad = 0
    print(f"{'STATUS':<15} {'GB':>7}  {'TENSORS':>7}  FILE / dtypes")
    print("-" * 100)
    for f in files:
        status, dtypes, size = inspect(f)
        n = sum(dtypes.values())
        mix = ", ".join(f"{k}:{v}" for k, v in dtypes.most_common(4))
        rel = os.path.relpath(f, "/workspace/ComfyUI/models") if f.startswith(
            "/workspace/ComfyUI/models") else f
        print(f"{status:<15} {size/1e9:7.2f}  {n:>7}  {rel}")
        if mix:
            print(f"{'':<15} {'':>7}  {'':>7}    {mix}")
        if status != "OK":
            bad += 1
    print("-" * 100)
    print(f"{len(files)} file(s), {bad} bad")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
