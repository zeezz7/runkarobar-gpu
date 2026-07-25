#!/usr/bin/env python
"""
Queue an API-format workflow on the local ComfyUI, wait for it, then upload the
resulting file(s) to MinIO and print the public URL(s).

Credentials come from the environment, never from this file:
    MINIO_ENDPOINT   host only, no scheme  (the SDK requires this)
    MINIO_ACCESS_KEY
    MINIO_SECRET_KEY
    MINIO_BUCKET

Usage:
    python run_and_upload.py workflows/hidream_i1_full_uhd.api.json
    python run_and_upload.py wf.json --no-upload      # render only
    python run_and_upload.py --upload-only out.png    # upload an existing file
"""
import argparse
import json
import mimetypes
import os
import sys
import time
import urllib.request
import uuid

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:18188")
OUTPUT_ROOT = "/workspace/ComfyUI/output"


def _post(path, payload):
    req = urllib.request.Request(
        f"{COMFY}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def _get(path):
    with urllib.request.urlopen(f"{COMFY}{path}", timeout=120) as r:
        return json.loads(r.read())


def queue(workflow_path):
    wf = json.loads(open(workflow_path).read())
    cid = str(uuid.uuid4())
    res = _post("/prompt", {"prompt": wf, "client_id": cid})
    if "prompt_id" not in res:
        raise SystemExit(f"ComfyUI rejected the prompt:\n{json.dumps(res, indent=2)}")
    return res["prompt_id"]


def wait(prompt_id, timeout=5400, poll=5):
    """Block until the prompt leaves the queue, then return its history entry."""
    start = time.time()
    last_note = 0
    while time.time() - start < timeout:
        hist = _get(f"/history/{prompt_id}")
        if prompt_id in hist:
            entry = hist[prompt_id]
            status = entry.get("status", {})
            if status.get("completed") or status.get("status_str") == "success":
                return entry
            if status.get("status_str") == "error":
                for m in status.get("messages", []):
                    print(json.dumps(m)[:2000], file=sys.stderr)
                raise SystemExit("workflow failed - see messages above")
            return entry
        el = int(time.time() - start)
        if el - last_note >= 30:
            q = _get("/queue")
            print(f"  ... {el}s elapsed "
                  f"(running={len(q.get('queue_running', []))}, "
                  f"pending={len(q.get('queue_pending', []))})", file=sys.stderr)
            last_note = el
        time.sleep(poll)
    raise SystemExit(f"timed out after {timeout}s")


def outputs_of(entry):
    files = []
    for node_out in entry.get("outputs", {}).values():
        for key in ("images", "gifs", "videos", "audio"):
            for item in node_out.get(key, []) or []:
                if not isinstance(item, dict) or "filename" not in item:
                    continue
                if item.get("type") not in (None, "output"):
                    continue
                p = os.path.join(OUTPUT_ROOT, item.get("subfolder", ""), item["filename"])
                if os.path.isfile(p):
                    files.append(p)
    return sorted(set(files))


def upload(paths, prefix="bakeoff"):
    from minio import Minio
    endpoint = os.environ["MINIO_ENDPOINT"].replace("https://", "").replace("http://", "").rstrip("/")
    bucket = os.environ["MINIO_BUCKET"]
    client = Minio(
        endpoint,
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=True,
    )
    if not client.bucket_exists(bucket):
        raise SystemExit(f"bucket {bucket!r} does not exist on {endpoint}")

    urls = []
    for p in paths:
        key = f"{prefix}/{os.path.basename(p)}"
        ctype = mimetypes.guess_type(p)[0] or "application/octet-stream"
        client.fput_object(bucket, key, p, content_type=ctype)
        urls.append((p, f"https://{endpoint}/{bucket}/{key}", os.path.getsize(p)))
    return urls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="workflow .api.json, or a file when --upload-only")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--upload-only", action="store_true")
    ap.add_argument("--prefix", default="bakeoff")
    args = ap.parse_args()

    if args.upload_only:
        files = [args.target]
    else:
        print(f"queueing {args.target}", file=sys.stderr)
        pid = queue(args.target)
        print(f"prompt_id={pid}", file=sys.stderr)
        entry = wait(pid)
        files = outputs_of(entry)
        if not files:
            raise SystemExit("workflow completed but produced no output files")
        for f in files:
            print(f"rendered {f} ({os.path.getsize(f)/1e6:.2f} MB)", file=sys.stderr)

    if args.no_upload:
        for f in files:
            print(f)
        return 0

    for path, url, size in upload(files, args.prefix):
        print(f"{url}   ({size/1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
