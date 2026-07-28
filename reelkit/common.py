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
import urllib.error
import urllib.request
import uuid

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:18188")
# WHERE COMFYUI READS/WRITES. These MUST match the ComfyUI process's own input/
# output dirs, because stage_input() copies product images into COMFY_INPUT and
# comfy_run() reads results back from COMFY_OUTPUT. The default is the old box
# layout (/workspace/ComfyUI). On RunPod serverless ComfyUI runs from
# /opt/ComfyUI, so the Dockerfile sets COMFY_INPUT=/opt/ComfyUI/input and
# COMFY_OUTPUT=/opt/ComfyUI/output. Getting this wrong makes LoadImage fail
# validation with "Invalid image file" (HTTP 400) even though everything is
# staged correctly - just in a directory ComfyUI never looks in.
COMFY_INPUT = os.environ.get("COMFY_INPUT", "/workspace/ComfyUI/input")
COMFY_OUTPUT = os.environ.get("COMFY_OUTPUT", "/workspace/ComfyUI/output")
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
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        # ComfyUI signals a bad workflow with HTTP 400 and a JSON body
        # {"error": ..., "node_errors": {...}} that names the exact node +
        # input that failed (e.g. a lora_name/ckpt_name not on disk). urlopen
        # raises before we can read it, so a plain "HTTP Error 400" is useless.
        # Recover the body: if it is the JSON rejection, hand it back so
        # comfy_run() surfaces node_errors; otherwise raise it verbatim.
        body = e.read().decode("utf-8", "replace")
        try:
            return json.loads(body)
        except ValueError:
            raise RuntimeError(
                f"ComfyUI POST {path} -> HTTP {e.code}: {body[:1200]}") from None


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


def _resolve_cond_roles(wf, cls):
    """
    Work out which text-encode node feeds the sampler's POSITIVE input and which
    feeds NEGATIVE, by walking the graph backwards from the sampler.

    This used to be guessed from string length ("longest = positive"), which is
    unsafe: Wan's template ships a 137-character Chinese negative prompt, so any
    motion prompt shorter than that would have been written into the NEGATIVE
    slot - telling the model to avoid the very thing we asked for.
    """
    targets = {}
    for _, node in wf.items():
        if node.get("class_type") in ("KSampler", "KSamplerAdvanced", "SamplerCustom",
                                      "SamplerCustomAdvanced", "CFGGuider"):
            for role in ("positive", "negative"):
                link = node["inputs"].get(role)
                if isinstance(link, list) and link:
                    targets.setdefault(role, link[0])
    if not targets:
        return {}

    def walk(nid, depth=0):
        """Follow links back until we hit a node of the wanted class."""
        if depth > 8 or nid not in wf:
            return None
        if wf[nid].get("class_type") == cls:
            return nid
        for v in wf[nid]["inputs"].values():
            if isinstance(v, list) and v and isinstance(v[0], str):
                got = walk(v[0], depth + 1)
                if got:
                    return got
        return None

    roles = {}
    for role, start in targets.items():
        got = walk(start)
        if got:
            roles[role] = got
    # positive and negative must not resolve to the same node
    if roles.get("positive") and roles.get("positive") == roles.get("negative"):
        roles.pop("negative", None)
    return roles


def set_prompts(wf, positive, negative=None, cls="CLIPTextEncode", field="text"):
    """Write the positive (and optionally negative) prompt into the right nodes."""
    roles = _resolve_cond_roles(wf, cls)
    if roles.get("positive"):
        wf[roles["positive"]]["inputs"][field] = positive
        if negative is not None and roles.get("negative"):
            wf[roles["negative"]]["inputs"][field] = negative
        return roles
    # fallback for graphs we cannot trace (single text node, or an unusual sampler)
    nl = nodes_of(wf, cls)
    if not nl:
        return {}
    nl.sort(key=lambda kv: len(str(kv[1]["inputs"].get(field, ""))), reverse=True)
    nl[0][1]["inputs"][field] = positive
    if negative is not None and len(nl) > 1:
        nl[-1][1]["inputs"][field] = negative
    log("prompt", f"WARNING: could not trace {cls} roles - fell back to length heuristic")
    return {}


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
