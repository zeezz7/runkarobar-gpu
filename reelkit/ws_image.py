"""
WaveSpeed image renderer - bytedance/seedream-v4 (edit + text-to-image).

This REPLACED the local Qwen image models (Qwen-Image-Edit-2511 and
Qwen-Image-2512) for every still the pipeline draws. The 8-step Lightning
edit path was where reels went to die: waxy mannequin humans, invented
lettering stamped on plain fabric, poses locked to image1's composition -
one suit burned two days of retries on exactly those failures. The photo
studio's 4-model bake-off (2026-08-01) picked seedream-v4 for the same job:
faithful garments, photoreal people, true re-posing from references, at
$0.028/image - pocket change next to the Wan GPU minutes.

The GPU box keeps ONLY video work (Wan/Hunyuan I2V), BiRefNet segmentation
and the Qwen2.5-VL OCR *guard* - a reader that never draws a pixel.

WaveSpeed needs reference images as URLs, so local files (product photos,
anchor stills) are uploaded to MinIO first, cached per (path, mtime) so a
product photo uploads once per job, not once per scene.
"""
import os
import subprocess
import sys
import time
import urllib.request

import common
import costs
import wavespeed

EDIT_MODEL = os.environ.get("WS_IMAGE_EDIT_MODEL", "bytedance/seedream-v4/edit")
T2I_MODEL = os.environ.get("WS_IMAGE_T2I_MODEL", "bytedance/seedream-v4")

_ref_cache = {}   # local path -> (mtime, public url)


def _public_url(path):
    """Expose a local reference file via MinIO so WaveSpeed can fetch it."""
    st = os.stat(path)
    hit = _ref_cache.get(path)
    if hit and hit[0] == st.st_mtime:
        return hit[1]
    for var in ("MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY",
                "MINIO_BUCKET"):
        if var not in os.environ:
            raise RuntimeError(f"{var} not set (expected in /workspace/.env)")
    key = f"refs/{int(time.time())}-{os.getpid()}-{os.path.basename(path)}"
    p = subprocess.run(
        [sys.executable, os.path.join(common.REELKIT, "minio_upload.py"),
         path, "--key", key],
        capture_output=True, text=True, env=dict(os.environ))
    if p.returncode != 0:
        raise RuntimeError(f"ref upload failed for {path}: {p.stderr[-300:]}")
    url = p.stdout.strip().split()[0]
    _ref_cache[path] = (st.st_mtime, url)
    return url


def _run(model, payload, out_path, max_polls=80, poll_s=3.0):
    """Submit one render and poll it home. Downloads the first output to
    `out_path` and meters $0.028 on the job's cost. Raises on failure - the
    caller's guard/retry logic decides what a failed still means."""
    rid = None
    for attempt in range(5):
        try:
            res = wavespeed._request(
                "POST", f"{wavespeed.BASE_URL}/api/v3/{model}", payload)
        except wavespeed.WaveSpeedError as e:
            if "429" in str(e) and attempt < 4:     # rate limit: wait it out
                time.sleep(20)
                continue
            raise
        rid = (res.get("data") or {}).get("id")
        if res.get("code") == 200 and rid:
            break
        common.log("ws-image", f"submit retry ({str(res)[:120]})")
        time.sleep(8)
    if not rid:
        raise RuntimeError(f"{model}: submit failed after retries")
    for _ in range(max_polls):
        time.sleep(poll_s)
        st = wavespeed._request(
            "GET", f"{wavespeed.BASE_URL}/api/v3/predictions/{rid}/result")
        d = st.get("data") or {}
        if d.get("status") == "completed":
            outs = d.get("outputs") or []
            if not outs:
                raise RuntimeError(f"{model}: completed with no outputs")
            urllib.request.urlretrieve(outs[0], out_path)
            costs.current().wavespeed("image")
            return out_path
        if d.get("status") in ("failed", "error"):
            raise RuntimeError(f"{model}: {str(d.get('error'))[:200]}")
    raise RuntimeError(f"{model}: timed out after {int(max_polls * poll_s)}s")


def edit(prompt, images, out_path, size):
    """Edit/compose from reference image(s). `images` are local paths or URLs;
    order matters - image 1 is what prompts like "the first image shows..."
    point at. Seedream takes no negative prompt and no seed: every call is a
    fresh roll, which is exactly what a guard retry wants."""
    urls = [(p if str(p).startswith("http") else _public_url(p))
            for p in images if p][:6]
    if not urls:
        raise ValueError("edit() needs at least one reference image")
    common.log("ws-image", f"edit {len(urls)} ref(s) size={size} "
                           f"-> {os.path.basename(out_path)}")
    return _run(EDIT_MODEL, {"prompt": prompt, "images": urls, "size": size},
                out_path)


def generate(prompt, out_path, size):
    """Pure text-to-image (scene backgrounds, atmosphere b-roll)."""
    common.log("ws-image", f"t2i size={size} -> {os.path.basename(out_path)}")
    return _run(T2I_MODEL, {"prompt": prompt, "size": size}, out_path)
