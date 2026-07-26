#!/usr/bin/env python
"""
Assemble a human-readable trace for a reel run from whatever was persisted.

This is the RETROACTIVE reconstructor: it reads the run folder plus the server
and ComfyUI logs. Anything that was never written to disk is reported as
"NOT PERSISTED" rather than reconstructed - a guessed prompt in an audit trail is
worse than an honest gap.

For runs made after tracer.py was wired in, everything below is captured at the
moment it happens and this script simply formats it.

    python trace_run.py [run_id]        # defaults to the newest run
"""
import json
import os
import re
import subprocess
import sys

import common

WORK = common.WORK
SERVER_LOG = os.path.join(WORK, "server.log")
COMFY_LOG = "/var/log/portal/comfyui.log"
MISSING = "NOT PERSISTED"


def _read(p, default=None):
    try:
        return open(p, encoding="utf-8", errors="replace").read()
    except OSError:
        return default


def _json(p, default=None):
    t = _read(p)
    try:
        return json.loads(t) if t else default
    except json.JSONDecodeError:
        return default


def _dur(p):
    return round(common.probe_duration(p), 3) if os.path.isfile(p) else None


def _dims(p):
    if not os.path.isfile(p):
        return None
    r = common.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=width,height", "-of", "csv=p=0", p],
                   check=False)
    return r.stdout.strip() or None


def newest_run():
    runs = [d for d in os.listdir(WORK)
            if d.startswith("reel_") and os.path.isdir(os.path.join(WORK, d))
            and os.path.isfile(os.path.join(WORK, d, "result.json"))]
    if not runs:
        raise SystemExit("no completed runs found")
    return max(runs, key=lambda d: os.path.getmtime(os.path.join(WORK, d)))


def log_slice(run_id):
    """The server-log lines belonging to this run (from its [job] line onward)."""
    txt = _read(SERVER_LOG, "") or ""
    lines = [l for l in txt.splitlines() if re.match(r"^\[(job|brain|vo|compose|"
                                                     r"guard|animate|assemble|upload)\]", l)]
    start = next((i for i, l in enumerate(lines) if run_id in l), None)
    if start is None:
        return []
    out = []
    for l in lines[start:]:
        if l.startswith("[job] reel_") and run_id not in l and out:
            break
        out.append(l)
    return out


def build_from_dir(d, run_id):
    """Build a trace from a runs/<id> directory written by tracer.py."""
    return _build(d, run_id, os.path.join(WORK, run_id))


def build(run_id):
    """Retroactive build from a work/<id> directory (pre-tracer runs)."""
    return _build(os.path.join(WORK, run_id), run_id, os.path.join(WORK, run_id))


def _build(d, run_id, media_dir):
    res = _json(os.path.join(d, "result.json"), {}) or {}
    sb = _json(os.path.join(d, "storyboard.json"), {}) or {}
    # media (stills/clips/audio) always live in the work dir
    md = media_dir if os.path.isdir(media_dir) else d
    lines = log_slice(run_id)
    joined = "\n".join(lines)

    t = {"run_id": run_id, "run_dir": d}

    # 1 request -------------------------------------------------------------
    persisted_req = _json(os.path.join(d, "request.json"))
    t["request"] = persisted_req or MISSING
    products = sorted(f for f in os.listdir(md) if f.startswith("product_")) if os.path.isdir(md) else []
    t["product_files_on_disk"] = products

    # 2 vision --------------------------------------------------------------
    vc = _read(os.path.join(d, "vision_captions.txt"))
    if vc:
        t_caps = [{"note": "verbatim (persisted by tracer)", "text": c.strip()}
                  for c in vc.split("\n---\n") if c.strip()]
    else:
        t_caps = None
    caps = [l.split("caption: ", 1)[1] for l in lines if "] caption: " in l]
    t["vision_captions"] = t_caps or ([{"note": "TRUNCATED to 110 chars by the logger",
                                        "text": c} for c in caps] if caps else MISSING)

    # 3 brain prompt --------------------------------------------------------
    bp = _read(os.path.join(d, "brain_prompt.txt"))
    t["brain_prompt"] = bp or MISSING
    tpl = re.search(r"\[brain\] template '([^']+)'", joined)
    t["template"] = tpl.group(1) if tpl else (
        (persisted_req or {}).get("config", {}).get("template", MISSING))
    at = re.search(r"storyboard ok on attempt (\d+)", joined)
    t["brain_attempts"] = int(at.group(1)) if at else MISSING

    # 4 storyboard ----------------------------------------------------------
    t["storyboard"] = sb or MISSING

    # 5 per scene -----------------------------------------------------------
    scenes = []
    for sc in sb.get("scenes", []):
        n = sc["n"]
        cj = _json(os.path.join(d, f"scene_{n}_compose.json"))
        gj = _json(os.path.join(d, f"scene_{n}_guard.json"))
        aj = _json(os.path.join(d, f"scene_{n}_animate.json"))
        vj = _json(os.path.join(d, f"scene_{n}_vo.json"))
        still = os.path.join(md, f"scene_{n}.png")
        clip = os.path.join(md, f"clip_{n}.mp4")
        mp3 = os.path.join(md, "audio", f"scene_{n}.mp3")

        gline = [l for l in lines if f"[guard] scene {n}:" in l]
        aline = [l for l in lines if f"[animate] scene {n}:" in l]
        vline = [l for l in lines if f"[vo] scene {n}:" in l]

        scenes.append({
            "n": n, "method": sc.get("method"), "mode": sc.get("mode"),
            "goal": sc.get("goal"), "motionEngine": sc.get("motionEngine"),
            "compose": cj or {
                "positive_prompt": MISSING, "negative_prompt": MISSING,
                "seed": MISSING, "model": MISSING, "mask_result": MISSING,
                "still_path": still if os.path.isfile(still) else MISSING,
                "still_size": _dims(still) or MISSING,
                "note": "compose inputs were not written to disk for this run"},
            "guard": gj or ({"log_lines": gline} if gline else MISSING),
            "animate": aj or {
                "log_lines": aline or MISSING,
                "clip_path": clip if os.path.isfile(clip) else MISSING,
                "clip_duration": _dur(clip), "clip_size": _dims(clip),
                "motion_prompt": MISSING, "energy_prompt": MISSING,
                "note": "verbatim motion/energy prompt sent to the video model "
                        "was not written to disk for this run"},
            "voiceover": vj or {
                "vo_text": sc.get("vo"), "voice_id": MISSING,
                "mp3_path": mp3 if os.path.isfile(mp3) else MISSING,
                "measured_duration": _dur(mp3),
                "log_line": vline[0] if vline else MISSING},
        })
    t["scenes"] = scenes

    # 6 assemble ------------------------------------------------------------
    aj_file = _json(os.path.join(d, "assemble.json"))
    fits = re.findall(r"\[assemble\] scene (\d+): ([\d.]+)s (fade-in|cut)", joined)
    fallbacks = [l for l in lines if "not implemented - falling back" in l]
    t["assemble"] = aj_file or {
        "per_scene": [{"scene": int(a), "fitted_duration": float(b),
                       "transition_in": c} for a, b, c in fits] or MISSING,
        "transition_fallbacks": fallbacks or [],
        "total_duration": res.get("durationSec", MISSING),
        "master_1080p_size": _dims(os.path.join(md, f"{run_id}_1080p.mp4")),
    }

    # 7 upload --------------------------------------------------------------
    t["upload"] = {
        "reel_1080p_url": res.get("reel_1080p_url", MISSING),
        "reel_720p_url": res.get("reel_720p_url", MISSING),
        "scene_image_urls": res.get("scene_image_urls", MISSING),
        "log": [l for l in lines if l.startswith("[upload]")] or MISSING,
    }

    # 8 timings -------------------------------------------------------------
    tj = _json(os.path.join(d, "timings.json"))
    comfy = _read(COMFY_LOG, "") or ""
    prompt_times = re.findall(r"Prompt executed in ([\d.]+) seconds", comfy)[-12:]
    t["timings"] = tj or {
        "total_wall_clock_sec": res.get("_elapsedSec", MISSING),
        "per_stage": MISSING,
        "note": "per-stage timings were not recorded for this run; the ComfyUI "
                "prompt durations below are the last 12 on the box and are not "
                "attributable to specific scenes with certainty",
        "recent_comfy_prompt_seconds": [float(x) for x in prompt_times],
        "model_load_order": MISSING,
    }
    t["guard_summary"] = res.get("_guard", MISSING)
    return t


def to_md(t):
    L = []
    A = L.append
    A(f"# Reel run trace — `{t['run_id']}`\n")
    A(f"Run directory: `{t['run_dir']}`\n")
    A("> Items marked **NOT PERSISTED** were never written to disk for this run. "
      "They are reported as gaps rather than reconstructed. Runs made after the "
      "tracer was wired in capture all of them.\n")

    A("\n## 1. Request\n")
    r = t["request"]
    A(f"```json\n{json.dumps(r, indent=2, ensure_ascii=False) if r != MISSING else MISSING}\n```")
    A(f"\nProduct files on disk: `{', '.join(t['product_files_on_disk']) or 'none'}`")
    A(f"\nTemplate: `{t['template']}`")

    A("\n## 2. Vision captions\n")
    v = t["vision_captions"]
    if v == MISSING:
        A(MISSING)
    else:
        for i, c in enumerate(v, 1):
            A(f"**image {i}** ({c['note']}):\n\n> {c['text']}\n")

    A("\n## 3. Brain prompt (exact string sent to the LLM)\n")
    A(f"Attempts until valid JSON: `{t['brain_attempts']}`\n")
    if t["brain_prompt"] == MISSING:
        A(f"**{MISSING}** — the assembled prompt string was not saved for this run.")
    else:
        A("```text\n" + t["brain_prompt"] + "\n```")

    A("\n## 4. Storyboard returned\n")
    A(f"```json\n{json.dumps(t['storyboard'], indent=2, ensure_ascii=False)}\n```")

    A("\n## 5. Per scene\n")
    for s in t["scenes"]:
        A(f"\n### Scene {s['n']} — {s['goal']} / {s['method']} / mode={s['mode']} "
          f"/ engine={s['motionEngine']}\n")
        for sect in ("compose", "guard", "animate", "voiceover"):
            A(f"**{sect}**\n")
            A(f"```json\n{json.dumps(s[sect], indent=2, ensure_ascii=False)}\n```")

    A("\n## 6. Assemble\n")
    A(f"```json\n{json.dumps(t['assemble'], indent=2, ensure_ascii=False)}\n```")

    A("\n## 7. Upload\n")
    A(f"```json\n{json.dumps(t['upload'], indent=2, ensure_ascii=False)}\n```")

    A("\n## 8. Timings & model load order\n")
    A(f"```json\n{json.dumps(t['timings'], indent=2, ensure_ascii=False)}\n```")

    A("\n## Guard summary\n")
    A(f"```json\n{json.dumps(t['guard_summary'], indent=2, ensure_ascii=False)}\n```")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    rid = sys.argv[1] if len(sys.argv) > 1 else newest_run()
    tr = build(rid)
    d = tr["run_dir"]
    json.dump(tr, open(os.path.join(d, "trace.json"), "w"), indent=2, ensure_ascii=False)
    open(os.path.join(d, "trace.md"), "w").write(to_md(tr))
    print(os.path.join(d, "trace.md"))
    print(os.path.join(d, "trace.json"))
