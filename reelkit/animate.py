"""
Stage 2 - motion, and Stage 2b - the label guard.

Two ways a scene becomes video:

  mode == "product"   Ken-Burns (ffmpeg zoompan) over the SHARP composite.
                      The product pixels are only ever translated and scaled, so
                      the printed label cannot warp. If the brain asked for an
                      `energy`, that effect is generated separately ON PURE BLACK
                      and screen-blended over the still - black contributes
                      nothing to a screen blend, so the product stays untouched.

  mode == "scene"     Wan 2.2 I2V + LightX2V. Real generative motion, used only
                      where the product is not the subject.

Stage 2b runs before any compose_animate scene is animated: the OCR-diff guard
(validate_image.py, used as-is) reads the label off the composite and off the
source product photo and compares them. A mismatch means the product got cropped,
occluded or badly scaled - so we re-composite at a different scale/placement
rather than shipping a broken label.

Nothing here branches on what the product IS. `energy` and `motion` are free text
from the brain and are passed through to the renderer verbatim.
"""
import os

from PIL import Image

import common

FPS = 30
WAN_FPS = 16


# ------------------------------------------------------------------ 2b guard
def _label_tokens(path):
    """Read label text off an image with the existing Qwen2.5-VL guard."""
    import validate_image
    v = validate_image.verdict(path)
    det = (v.get("branding") or {}).get("detected") or []
    if isinstance(det, str):
        det = [det]
    toks = set()
    for d in det:
        for w in str(d).replace("/", " ").split():
            w = "".join(c for c in w if c.isalnum()).upper()
            if len(w) >= 3:
                toks.add(w)
    return toks, v


def guard_composite(composite_path, source_path, min_overlap=0.5):
    """
    Stage 2b. Returns (ok: bool, detail: str).
    Compares label tokens read from the composite against the source product.
    """
    src_toks, _ = _label_tokens(source_path)
    out_toks, _ = _label_tokens(composite_path)
    if not src_toks:
        return True, "source had no readable label text - guard skipped"
    kept = src_toks & out_toks
    ratio = len(kept) / len(src_toks)
    detail = (f"source={sorted(src_toks)} composite={sorted(out_toks)} "
              f"kept={ratio*100:.0f}%")
    return ratio >= min_overlap, detail


# --------------------------------------------------------------- ken burns
DEFAULT_KB = {"zoom": "in", "start": 1.0, "end": 1.12, "xDrift": 0.0, "yDrift": 0.0}


def ken_burns(image_path, out_path, duration, w, h, kb=None):
    """
    Slow camera move over a sharp still.

    `kb` is the brain's optional structured `kenburns` block - already validated
    and clamped in brain._clean_kenburns - so these are machine-usable numbers
    fed straight into zoompan. No text is interpreted here. Absent -> gentle
    default push-in.

    Only translation and scaling are applied, so the printed label cannot warp.
    """
    kb = kb or DEFAULT_KB
    frames = max(int(duration * FPS), 2)
    s, e = float(kb["start"]), float(kb["end"])
    xd, yd = float(kb.get("xDrift", 0.0)), float(kb.get("yDrift", 0.0))
    prog = f"(on/{frames})"                     # 0 -> 1 across the clip
    z = f"{s}+({e}-{s})*{prog}"
    # centre, plus the requested drift as a fraction of the source dimensions
    x = f"iw/2-(iw/zoom/2)+({xd})*iw*{prog}"
    y = f"ih/2-(ih/zoom/2)+({yd})*ih*{prog}"
    # oversample first so the pan is smooth rather than stepped
    vf = (f"scale={w*2}:{h*2}:force_original_aspect_ratio=decrease,"
          f"pad={w*2}:{h*2}:(ow-iw)/2:(oh-ih)/2:color=black,"
          f"zoompan=z='{z}':x='{x}':y='{y}':"
          f"d={frames}:s={w}x{h}:fps={FPS},"
          f"format=yuv420p")
    common.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", image_path,
                "-vf", vf, "-t", f"{duration:.3f}", "-c:v", "libx264",
                "-preset", "medium", "-crf", "18", "-r", str(FPS), out_path])
    return out_path


# ------------------------------------------------------------------- wan i2v
def wan_i2v(image_path, prompt, out_path, job_tag, duration=5.0):
    """Wan 2.2 I2V + LightX2V 4-step. Returns the raw clip path."""
    name = f"rk_wan_{job_tag}.png"
    common.stage_input(image_path, name)
    length = max(int(round(duration * WAN_FPS / 4)) * 4 + 1, 33)   # 4n+1

    wf = common.load_tpl("tpl_wan_i2v.api.json")
    common.set_class(wf, "LoadImage", image=name)
    common.set_class(wf, "WanImageToVideo", width=480, height=832)
    common.set_class(wf, "PrimitiveBoolean", value=True)           # turbo path
    common.set_class(wf, "SaveVideo", filename_prefix=f"video/rk_{job_tag}")
    common.set_prompts(wf, prompt, None)                            # keep template negative
    for _, node in common.nodes_of(wf, "ComfyMathExpression"):
        pass
    outs = common.comfy_run(wf, timeout=2400)
    if not outs:
        raise RuntimeError("wan i2v produced no video")
    return outs[0]


def energy_plate(energy_text, out_path, job_tag, duration, w, h):
    """Generate the brain's requested effect on pure black, for screen-blending."""
    black = os.path.join(os.path.dirname(out_path), f"black_{job_tag}.png")
    Image.new("RGB", (480, 832), (0, 0, 0)).save(black)
    prompt = (f"{energy_text}, isolated on a pure black background, "
              f"bright glowing particles and motion against pure black, "
              f"nothing else in frame")
    clip = wan_i2v(black, prompt, out_path, f"{job_tag}_fx", duration)
    return clip


def screen_blend(base_clip, fx_clip, out_path, duration):
    """Overlay the effect with a screen blend - black pixels vanish."""
    common.run([
        "ffmpeg", "-v", "error", "-y", "-i", base_clip, "-i", fx_clip,
        "-filter_complex",
        "[1:v]scale=iw:ih[fx];[0:v][fx]scale2ref=w=iw:h=ih[fx2][base];"
        "[base][fx2]blend=all_mode=screen:all_opacity=0.85,format=yuv420p[v]",
        "-map", "[v]", "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-r", str(FPS),
        out_path])
    return out_path


# ------------------------------------------------------------------ per scene
def animate_scene(scene, still_path, source_product, job_dir, w, h, duration,
                  guard_log=None):
    """
    Turn one scene's still into a clip of `duration` seconds.
    Returns (clip_path, guard_verdict_or_None).
    """
    n = scene["n"]
    tag = f"{os.path.basename(job_dir)}_s{n}"
    out = os.path.join(job_dir, f"clip_{n}.mp4")
    verdict = None

    if scene["method"] == "compose_animate" and source_product:
        ok, detail = guard_composite(still_path, source_product)
        verdict = {"scene": n, "ok": ok, "detail": detail}
        common.log("guard", f"scene {n}: {'PASS' if ok else 'FAIL'} - {detail}")
        if guard_log is not None:
            guard_log.append(verdict)

    if scene.get("mode") == "product":
        kb = scene.get("kenburns")
        base = ken_burns(still_path, os.path.join(job_dir, f"kb_{n}.mp4"),
                         duration, w, h, kb=kb)
        common.log("animate", f"scene {n}: kenburns "
                              f"{'brain '+str(kb) if kb else 'default push-in'}")
        energy = (scene.get("energy") or "").strip()
        if energy:
            common.log("animate", f"scene {n}: energy plate '{energy[:40]}'")
            fx = energy_plate(energy, os.path.join(job_dir, f"fx_{n}.mp4"),
                              tag, duration, w, h)
            return screen_blend(base, fx, out, duration), verdict
        os.replace(base, out)
        common.log("animate", f"scene {n}: ken-burns {duration:.2f}s")
        return out, verdict

    motion = scene.get("motion") or "slow cinematic camera move"
    energy = (scene.get("energy") or "").strip()
    prompt = f"{motion}. {scene['visual']}." + (f" {energy}." if energy else "")
    common.log("animate", f"scene {n}: wan i2v '{motion[:40]}'")
    clip = wan_i2v(still_path, prompt, out, tag, duration)
    os.replace(clip, out) if clip != out else None
    return out, verdict
