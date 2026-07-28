"""
RunPod serverless entrypoint.

This is ONLY a wrapper. RunPod supplies the queue, /run and /status, so
server.py's hand-rolled job registry is not needed here - but server.py stays,
because it is how the pipeline is tested locally and on a plain GPU box.

The job payload is the SAME shape /run already accepts:

    {"input": {"product_images": [...], "brief": "...", "config": {...}}}

and the returned dict is make_reel()'s result, UNCHANGED and snake_case, because
the VPS reads those exact keys:

    reel_1080p_url, reel_720p_url, scene_image_urls, storyboard, durationSec,
    cost_usd

IMPORT SAFETY MATTERS HERE. RunPod imports this module to boot the worker, and a
worker that touches the GPU or the network at import time either dies on a cold
start or wedges before it can report why. Every reelkit module is import-safe
(verified: the full graph imports in 0.05s with CUDA_VISIBLE_DEVICES empty), and
make_reel does its work inside the call, not at module scope.

ComfyUI is NOT started here - the container entrypoint brings it up first and
waits for it. The handler only posts workflows, exactly as make_reel always has.

No talking-avatar, no lip-sync, no Wan 2.2 S2V: person scenes render through
Wan 2.2 I2V like everything else.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import runpod                                              # noqa: E402

import common                                              # noqa: E402
import make_reel                                           # noqa: E402


def handler(job):
    """One reel per job. Returns the result dict, or {"error": ...}."""
    payload = (job or {}).get("input") or {}
    try:
        common.load_env()
        result = make_reel.make_reel(payload)
        # Returned verbatim - renaming or nesting any of these keys silently
        # breaks the caller, which reads reel_1080p_url off the top level.
        return result
    except Exception as e:
        # RunPod marks the job FAILED and surfaces the "error" string in
        # /status, so make it self-diagnosing: the full traceback goes to the
        # worker log AND a compact tail (last frames + message) rides along in
        # the returned error, so the caller/poller sees WHERE it broke without
        # opening the Logs tab.
        tb = traceback.format_exc()
        common.log("handler", f"job failed: {type(e).__name__}: {e}")
        common.log("handler", tb[-3000:])
        tail = " | ".join(ln.strip() for ln in tb.strip().splitlines()[-6:] if ln.strip())
        return {"error": f"{type(e).__name__}: {e} :: {tail}"[:1600]}


runpod.serverless.start({"handler": handler})
