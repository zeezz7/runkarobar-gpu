"""
Stage 6 - the API wrapper.

One endpoint in, one finished reel out. The calling server sends the brief and
shows the returned URL; everything else happens on this box.

    POST /make-reel   -> runs the whole pipeline, returns the Result JSON
    GET  /health      -> {"ok": true}

The reel job is long (minutes) and runs synchronously, one per request, which is
what the brief asked for and what maps cleanly onto RunPod serverless later -
the handler there just calls make_reel(request) the same way.
"""
import os
import threading
import traceback
import uuid

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

import common
import make_reel as pipeline

PORT = int(os.environ.get("REELKIT_PORT", "8189"))
app = FastAPI(title="reelkit", version="1.0")

# ComfyUI serialises GPU work anyway; this makes the constraint explicit so two
# concurrent requests cannot interleave model loads and thrash VRAM.
_gpu_lock = threading.Lock()


class Config(BaseModel):
    lengthSec: int = 20
    resolution: str = "1080p"
    aspectRatio: str = "9:16"
    language: str = "en"
    brandName: str = ""
    elevenVoiceId: str = ""
    captions: bool = True
    # Creative-direction preset. Unknown values fall back to "ai-director"
    # (warned, not rejected). See brain.TEMPLATES.
    template: str = "ai-director"
    # "What's in the video": False (default) = product only, nobody on screen.
    includeHuman: bool = False


class ReelRequest(BaseModel):
    product_images: list[str] = Field(..., min_length=1)
    brief: str
    config: Config = Config()


# ── async job API (the "runpod" contract the VPS speaks) ────────────────────
# A reel takes minutes, and any HTTP proxy in front of us gives up long before
# that - a Cloudflare quick tunnel 524s at ~100s. So the caller submits, gets an
# id immediately, and polls. The render itself is the SAME pipeline under the
# SAME GPU lock; this is only a wrapper.
_jobs = {}
_jobs_lock = threading.Lock()
BEARER = (os.environ.get("REELKIT_BEARER") or "").strip()


def _auth(authorization):
    """Optional bearer. Unset (the current staging setup) means open."""
    if not BEARER:
        return
    if authorization != f"Bearer {BEARER}":
        raise HTTPException(status_code=401, detail="bad or missing bearer token")


def _set(job_id, **fields):
    with _jobs_lock:
        _jobs.setdefault(job_id, {}).update(fields)


def _render_job(job_id, payload):
    # IN_QUEUE until the GPU is actually ours - two concurrent /run calls must
    # show the second one queued rather than pretending it is rendering.
    _set(job_id, status="IN_QUEUE")
    with _gpu_lock:
        _set(job_id, status="IN_PROGRESS")
        try:
            out = pipeline.make_reel(payload)
            _set(job_id, status="COMPLETED", output=out)
            common.log("api", f"job {job_id} COMPLETED")
        except Exception as e:
            common.log("api", f"job {job_id} FAILED: {type(e).__name__}: {e}")
            common.log("api", traceback.format_exc()[-1200:])
            _set(job_id, status="FAILED", error=f"{type(e).__name__}: {e}")


class RunBody(BaseModel):
    """The VPS wraps the request in {"input": {...}}."""
    input: ReelRequest


@app.post("/run")
def run(body: RunBody, authorization: str = Header(default=None)):
    """Submit a render. Returns {"id": ...} immediately - never blocks."""
    _auth(authorization)
    job_id = uuid.uuid4().hex
    payload = {"product_images": body.input.product_images,
               "brief": body.input.brief,
               "config": body.input.config.model_dump(exclude_unset=True)}
    _set(job_id, status="IN_QUEUE")
    threading.Thread(target=_render_job, args=(job_id, payload),
                     daemon=True).start()
    common.log("api", f"job {job_id} submitted ({payload['config'].get('template')})")
    return {"id": job_id}


@app.get("/status/{job_id}")
def status(job_id: str, authorization: str = Header(default=None)):
    _auth(authorization)
    with _jobs_lock:
        job = dict(_jobs.get(job_id) or {})
    if not job:
        raise HTTPException(status_code=404, detail="unknown job id")
    res = {"status": job.get("status", "IN_QUEUE")}
    # output ONLY on COMPLETED, error ONLY on FAILED - the caller branches on
    # exactly that.
    if res["status"] == "COMPLETED":
        res["output"] = job.get("output")
    elif res["status"] == "FAILED":
        res["error"] = job.get("error") or "render failed"
    return res


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/make-reel")
def make_reel_endpoint(req: ReelRequest):
    payload = {"product_images": req.product_images,
               "brief": req.brief,
               # exclude_unset is load-bearing: pydantic materialises every
               # Config default, so a plain model_dump() makes "the caller said
               # nothing" indistinguishable from "the caller said 20" - and the
               # per-template default length could then never apply. Only pass on
               # what was actually sent; make_reel.DEFAULT_CONFIG fills the rest.
               "config": req.config.model_dump(exclude_unset=True)}
    with _gpu_lock:
        try:
            return pipeline.make_reel(payload)
        except Exception as e:
            common.log("api", f"job failed: {type(e).__name__}: {e}")
            raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    import uvicorn
    common.load_env()
    print(f"[reelkit] listening on 0.0.0.0:{PORT}  "
          f"(POST /make-reel, GET /health)", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
