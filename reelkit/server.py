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

from fastapi import FastAPI, HTTPException
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


class ReelRequest(BaseModel):
    product_images: list[str] = Field(..., min_length=1)
    brief: str
    config: Config = Config()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/make-reel")
def make_reel_endpoint(req: ReelRequest):
    payload = {"product_images": req.product_images,
               "brief": req.brief,
               "config": req.config.model_dump()}
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
