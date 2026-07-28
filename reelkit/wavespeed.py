"""
WaveSpeed any-llm client — the remote backend for Stage 0 (the storyboard brain).

Why this exists
---------------
Stage 0 used to load a local Qwen2.5-Instruct checkpoint (14B active, 32B kept),
which cost ~16 GB of VRAM and minutes of load+generate time on every reel, and
had to be explicitly unloaded before the image models could fit. That whole path
is gone: the brain is now one HTTP call.

The API shape (verified live against api.wavespeed.ai on 2026-07-27)
--------------------------------------------------------------------
It is a JOB API, not an OpenAI-compatible chat API. Two steps:

    POST /api/v3/wavespeed-ai/any-llm/vision   {"prompt":..., "images":[url,...]}
      -> {"code":200, "data":{"id":"<hex>", "urls":{"get": "<poll url>"}}}
    GET  /api/v3/predictions/<id>/result
      -> {"data":{"status":"created|processing|completed|failed",
                  "outputs":["<the model's text>"], "error":""}}

`outputs` is a LIST OF STRINGS, and the whole reply is `outputs[0]` — there is no
`choices[0].message.content` here. Do not swap in the OpenAI SDK.

Two traps worth knowing
-----------------------
* `images` takes **URLs only** (max 16). There is no base64 / multipart path, so
  a local file has to be reachable over HTTP before the brain can see it.
* Insufficient balance fails at SUBMIT with HTTP 200 + `{"code":400,"message":
  "Insufficient credits..."}` and no `data.id`. The HTTP status is 200, so
  checking only the status code silently looks like success.
"""
import json
import os
import time
import urllib.error
import urllib.request

import common
import costs

BASE_URL = os.environ.get("WAVESPEED_BASE_URL", "https://api.wavespeed.ai").rstrip("/")

# The catalogue advertises this enum for both any-llm endpoints (see
# GET /api/v3/models). It is what the service documents as supported; the
# backend is an OpenRouter passthrough, so an unlisted id MAY work — but it is
# not promised, and an unlisted id is the first thing to suspect on a 400.
CATALOGUE = (
    "google/gemini-2.5-flash", "google/gemini-2.5-pro",
    "google/gemini-3-flash-preview", "openai/gpt-4o", "openai/gpt-4.1",
    "openai/gpt-5-chat", "meta-llama/llama-4-scout",
)

VISION_PATH = "/api/v3/wavespeed-ai/any-llm/vision"   # $0.05/call
TEXT_PATH = "/api/v3/wavespeed-ai/any-llm"            # $0.01/call


class WaveSpeedError(RuntimeError):
    pass


def _key():
    k = os.environ.get("WAVESPEED_API_KEY", "").strip()
    if not k:
        raise WaveSpeedError(
            "WAVESPEED_API_KEY is not set. Put it in /workspace/.env (mode 600).")
    return k


def _request(method, url, payload=None, timeout=120):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": f"Bearer {_key()}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:600]
        raise WaveSpeedError(f"{method} {url} -> HTTP {e.code}: {body}") from None


def balance():
    """Account balance in USD. Cheap, and the first thing to check on a failure."""
    return float(_request("GET", f"{BASE_URL}/api/v3/balance")["data"]["balance"])


def chat(prompt, system=None, images=None, model=None, temperature=0.85,
         max_tokens=1600, timeout=300, poll=2.0):
    """
    One completion. Returns the model's text.

    `images` is a list of http(s) URLs; when present the vision endpoint is used
    (5x the price of the text one), otherwise the text endpoint.
    """
    # Default is a NON-thinking model on purpose. google/gemini-2.5-pro (the old
    # default) is a thinking model: WaveSpeed's any-llm passthrough ignores
    # reasoning:False, so it spends the whole max_tokens budget on hidden
    # reasoning and the visible JSON comes back truncated (~199 chars, no closing
    # brace) -> _extract_json fails on every retry. claude-sonnet-4 emits the
    # storyboard JSON directly and validates first try. Override per-endpoint
    # with WAVESPEED_BRAIN_MODEL if needed.
    model = model or os.environ.get("WAVESPEED_BRAIN_MODEL", "anthropic/claude-sonnet-4")
    images = [u for u in (images or []) if u]
    path, price = (VISION_PATH, 0.05) if images else (TEXT_PATH, 0.01)

    payload = {"model": model, "prompt": prompt, "temperature": temperature,
               "max_tokens": max_tokens, "reasoning": False}
    if system:
        payload["system_prompt"] = system
    if images:
        if len(images) > 16:
            raise WaveSpeedError(f"any-llm/vision accepts at most 16 images, got {len(images)}")
        payload["images"] = images

    res = _request("POST", f"{BASE_URL}{path}", payload)
    # NB: a submit failure arrives as HTTP 200 with code != 200 and no data.id.
    if res.get("code") != 200 or not (res.get("data") or {}).get("id"):
        msg = res.get("message", json.dumps(res)[:400])
        hint = ""
        if "credit" in msg.lower():
            hint = (f" — account balance is exhausted; a {path.rsplit('/',1)[-1]} "
                    f"call costs ${price:.2f}. Top up at wavespeed.ai.")
        elif model not in CATALOGUE:
            hint = (f" — '{model}' is not in the advertised catalogue "
                    f"({', '.join(CATALOGUE)}). Set WAVESPEED_BRAIN_MODEL to one of those.")
        raise WaveSpeedError(f"submit rejected: {msg}{hint}")

    costs.current().wavespeed("vision" if images else "text")
    jid = res["data"]["id"]
    get_url = (res["data"].get("urls") or {}).get(
        "get", f"{BASE_URL}/api/v3/predictions/{jid}/result")
    common.log("wavespeed", f"{model} job {jid[:12]} submitted (~${price:.2f})")

    t0 = time.time()
    while time.time() - t0 < timeout:
        d = _request("GET", get_url).get("data") or {}
        st = d.get("status")
        if st == "completed":
            outs = d.get("outputs") or []
            if not outs or not str(outs[0]).strip():
                raise WaveSpeedError(f"job {jid} completed with empty outputs")
            ms = (d.get("timings") or {}).get("inference")
            common.log("wavespeed", f"job {jid[:12]} completed"
                                    + (f" in {ms/1000:.1f}s" if ms else ""))
            return str(outs[0])
        if st == "failed":
            raise WaveSpeedError(f"job {jid} failed: {d.get('error') or 'no reason given'}")
        time.sleep(poll)
    raise WaveSpeedError(f"job {jid} exceeded {timeout}s (last status {st!r})")


def run(model_id, payload, timeout=900, poll=3.0):
    """
    Submit ANY WaveSpeed model and return its output URLs.

    `chat()` is the any-llm special case; this is the general one (avatar
    lip-sync uses it). Same submit-then-poll contract, same failure modes -
    notably an exhausted balance arriving as HTTP 200 with code 400.
    """
    res = _request("POST", f"{BASE_URL}/api/v3/{model_id}", payload)
    if res.get("code") != 200 or not (res.get("data") or {}).get("id"):
        msg = res.get("message", json.dumps(res)[:300])
        raise WaveSpeedError(f"{model_id} submit rejected: {msg}")
    jid = res["data"]["id"]
    get_url = (res["data"].get("urls") or {}).get(
        "get", f"{BASE_URL}/api/v3/predictions/{jid}/result")
    common.log("wavespeed", f"{model_id} job {jid[:12]} submitted")

    t0 = time.time()
    while time.time() - t0 < timeout:
        d = _request("GET", get_url).get("data") or {}
        st = d.get("status")
        if st == "completed":
            outs = [u for u in (d.get("outputs") or []) if u]
            if not outs:
                raise WaveSpeedError(f"job {jid} completed with no outputs")
            return outs
        if st == "failed":
            raise WaveSpeedError(f"job {jid} failed: {d.get('error') or 'no reason'}")
        time.sleep(poll)
    raise WaveSpeedError(f"job {jid} exceeded {timeout}s (last status {st!r})")


if __name__ == "__main__":
    common.load_env()
    print(f"balance: ${balance():.4f}")
    print(chat("Reply with exactly: OK", max_tokens=8, temperature=0))
