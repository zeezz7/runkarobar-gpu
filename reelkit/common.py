"""
Shared plumbing for the reel pipeline: ComfyUI job submission, ffmpeg/ffprobe
helpers, and job workspace management.

ComfyUI runs as a long-lived supervisor service on 127.0.0.1:18188. Every image
and video stage submits an API-format workflow to it rather than loading models
in-process, which keeps model residency (and therefore speed) under ComfyUI's
control instead of ours.
"""
import json
import os
import shutil
import subprocess
import time
import urllib.request
import uuid

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:18188")
COMFY_INPUT = "/workspace/ComfyUI/input"
COMFY_OUTPUT = "/workspace/ComfyUI/output"
REELKIT = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(REELKIT, "work")
TPL = os.path.join(REELKIT, "workflows")


# --------------------------------------------------------------------- config
def load_env(path="/workspace/.env"):
    """Load KEY=VALUE lines into os.environ without clobbering existing vars."""
    if not os.path.isfile(path):
        return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ------------------------------------------------------------------ job space
def new_job(name_hint="reel"):
    jid = f"{name_hint}_{uuid.uuid4().hex[:8]}"
    d = os.path.join(WORK, jid)
    os.makedirs(d, exist_ok=True)
    return jid, d


def stage_input(src_path, as_name):
    """Copy a file into ComfyUI's input dir so LoadImage can see it."""
    os.makedirs(COMFY_INPUT, exist_ok=True)
    dst = os.path.join(COMFY_INPUT, as_name)
    shutil.copyfile(src_path, dst)
    return as_name


def fetch_url(url, dst):
    """Download a remote asset (product images arrive as URLs)."""
    req = urllib.request.Request(url, headers={"User-Agent": "reelkit/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dst, "wb") as fh:
        shutil.copyfileobj(r, fh)
    return dst


# -------------------------------------------------------------------- comfyui
def _post(path, payload):
    req = urllib.request.Request(
        f"{COMFY}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def _get(path):
    with urllib.request.urlopen(f"{COMFY}{path}", timeout=180) as r:
        return json.loads(r.read())


def comfy_run(workflow, timeout=1800, poll=3):
    """Queue an API-format workflow, block until done, return output file paths."""
    res = _post("/prompt", {"prompt": workflow, "client_id": str(uuid.uuid4())})
    if "prompt_id" not in res:
        raise RuntimeError(f"ComfyUI rejected prompt: {json.dumps(res)[:800]}")
    pid = res["prompt_id"]

    t0 = time.time()
    while time.time() - t0 < timeout:
        hist = _get(f"/history/{pid}")
        if pid in hist:
            entry = hist[pid]
            st = entry.get("status", {})
            if st.get("status_str") == "error":
                msgs = json.dumps(st.get("messages", []))[:1200]
                raise RuntimeError(f"ComfyUI execution error: {msgs}")
            files = []
            for node_out in entry.get("outputs", {}).values():
                for key in ("images", "gifs", "videos"):
                    for item in node_out.get(key, []) or []:
                        if not isinstance(item, dict) or "filename" not in item:
                            continue
                        if item.get("type") not in (None, "output"):
                            continue
                        p = os.path.join(COMFY_OUTPUT, item.get("subfolder", ""),
                                         item["filename"])
                        if os.path.isfile(p):
                            files.append(p)
            if files:
                return sorted(set(files))
            if st.get("completed") or st.get("status_str") == "success":
                return []
        time.sleep(poll)
    raise TimeoutError(f"ComfyUI job {pid} exceeded {timeout}s")


def load_tpl(name):
    return json.loads(open(os.path.join(TPL, name)).read())


def nodes_of(wf, class_type):
    return [(k, v) for k, v in wf.items() if v.get("class_type") == class_type]


def set_class(wf, class_type, **kw):
    """Set literal inputs on every node of a class. Returns how many it touched."""
    n = 0
    for _, node in nodes_of(wf, class_type):
        for k, v in kw.items():
            node["inputs"][k] = v
        n += 1
    return n


def set_prompts(wf, positive, negative=None, cls="CLIPTextEncode", field="text"):
    """Longest existing text = positive slot, shortest = negative slot."""
    nl = nodes_of(wf, cls)
    if not nl:
        return
    nl.sort(key=lambda kv: len(str(kv[1]["inputs"].get(field, ""))), reverse=True)
    nl[0][1]["inputs"][field] = positive
    if negative is not None and len(nl) > 1:
        nl[-1][1]["inputs"][field] = negative


# --------------------------------------------------------------------- ffmpeg
def run(cmd, check=True):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(cmd[:6])}...\n{p.stderr[-1500:]}")
    return p


def probe_duration(path):
    p = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path])
    try:
        return float(p.stdout.strip())
    except ValueError:
        return 0.0


def dims_for(aspect, height):
    """(w,h) for an aspect keyword at a given short/long edge convention."""
    if aspect == "1:1":
        return height, height
    return int(round(height * 9 / 16)), height   # 9:16 default


def log(stage, msg):
    print(f"[{stage}] {msg}", flush=True)
