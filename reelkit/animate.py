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
# Wan 2.2 i2v quality ceiling - 121 frames = 7.56s at 16fps.
WAN_MAX_FRAMES = 121


# ------------------------------------------------------------------ 2b guard
_TOKEN_CACHE = {}


def unload_guard():
    """
    Free the guard's Qwen2.5-VL.

    validate_image keeps its own module-level instance, which is a SECOND copy of
    the same 16GB model the brain loads for captioning. Holding both alongside a
    34GB brain and ComfyUI's diffusion models overflowed the 95GB card (measured:
    65.6GB in this process alone before ComfyUI's 26.8GB).
    """
    import gc
    import torch
    import validate_image
    validate_image._model = None
    validate_image._proc = None
    gc.collect()
    torch.cuda.empty_cache()
    common.log("guard", "VL model unloaded")


def _label_tokens(path):
    """
    Read label text off an image with the existing Qwen2.5-VL guard.

    Cached per (path, mtime): the source product photo is identical for every
    scene, so re-running the VL model on it once per scene was pure waste. The
    mtime matters — a guard retry OVERWRITES the scene still at the same path,
    and a path-only key returned the FIRST render's tokens for the new image,
    making every retry verdict a lie (observed: identical token list on two
    different renders while the second was actually a different garment).
    """
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        key = (path, 0)
    if key in _TOKEN_CACHE:
        return _TOKEN_CACHE[key]
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
    _TOKEN_CACHE[key] = (toks, v)
    return toks, v


MIN_TOKENS_FOR_GUARD = 3


def guard_composite(composite_path, source_path, min_overlap=0.5):
    """
    Stage 2b. Returns (ok: bool, detail: str).

    Compares label tokens read from the composite against the source product.

    The composite pastes real product pixels, so a mismatch means the product got
    cropped, occluded or badly scaled - not that it was redrawn. But the signal is
    only trustworthy when there is enough text to read: on a garment with one tiny
    embroidered logo the VL model hallucinates a different word each time it looks
    (measured: 'BRETEL' vs 'BALLY' on identical pixels), and a single misread
    scores 0%. Below MIN_TOKENS_FOR_GUARD the OCR signal is too weak to judge, so
    we report it and pass rather than burn a re-composite chasing a phantom.
    """
    src_toks, _ = _label_tokens(source_path)
    out_toks, _ = _label_tokens(composite_path)
    if not src_toks:
        # A blank product must STAY blank. The edit model loves stamping
        # invented brand text on empty surfaces (observed: mirrored gibberish
        # on a pump's blank insoles), and skipping the guard here let it ship.
        # Two-token threshold because a single OCR misread on clean pixels is
        # common (see docstring).
        if len(out_toks) >= 2:
            return False, (f"source has no printed text but the render shows "
                           f"{sorted(out_toks)} - invented lettering")
        return True, "source had no readable label text - guard skipped"
    if len(src_toks) < MIN_TOKENS_FOR_GUARD:
        return True, (f"only {len(src_toks)} token(s) readable on the source "
                      f"({sorted(src_toks)}) - too weak to diff, guard skipped")
    kept = src_toks & out_toks
    ratio = len(kept) / len(src_toks)
    detail = (f"source={sorted(src_toks)} composite={sorted(out_toks)} "
              f"kept={ratio*100:.0f}%")
    return ratio >= min_overlap, detail


# --------------------------------------------------------------- ken burns
DEFAULT_KB = {"zoom": "in", "start": 1.0, "end": 1.12, "xDrift": 0.0,
              "yDrift": 0.0, "rotateDeg": 0.0}


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
    chain = [f"scale={w*2}:{h*2}:force_original_aspect_ratio=decrease",
             f"pad={w*2}:{h*2}:(ow-iw)/2:(oh-ih)/2:color=black",
             f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={FPS}"]
    # zoompan can only scale and translate. Rotation is a separate filter, which
    # is why a storyboard asking for "orbit" used to render as a plain push-in.
    rot = float(kb.get("rotateDeg", 0.0) or 0.0)
    if abs(rot) > 0.05:
        rad = rot * 3.141592653589793 / 180.0
        chain.append(f"rotate=a='{rad}*(t/{duration:.3f})':c=none:"
                     f"ow=iw:oh=ih:bilinear=1")
    chain.append("format=yuv420p")
    vf = ",".join(chain)
    common.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", image_path,
                "-vf", vf, "-t", f"{duration:.3f}", "-c:v", "libx264",
                "-preset", "medium", "-crf", "18", "-r", str(FPS), out_path])
    return out_path


# ------------------------------------------------------------------ video i2v
# Which image-to-video model animates a still. Both are driven through the same
# i2v(image, prompt, ...) signature, so nothing downstream changes.
#   wan     - Wan 2.2 14B + LightX2V, 4 steps, native 480x832  (~65s / 5s clip)
#   hunyuan - HunyuanVideo I2V 720p bf16, native 720x1280      (2.25x the pixels)
VIDEO_MODEL = os.environ.get("REELKIT_VIDEO_MODEL", "wan").lower()
HY_FPS = 24


def hunyuan_i2v(image_path, prompt, out_path, job_tag, duration=5.0,
                width=720, height=1280, steps=20):
    """
    HunyuanVideo I2V 720p. Native 720x1280 vertical - 2.25x the pixels of Wan's
    480x832, so the 1080p master is a much smaller upscale.

    Notes that differ from Wan and matter here:
      * the model is bf16 only (no fp8 build), loaded with weight_dtype
        fp8_e4m3fn so it casts at load instead of eating 25.6GB of VRAM;
      * I2V needs a clip_vision encoder that the T2V variant does not;
      * frame count must be 4n+1.
    """
    name = f"rk_hy_{job_tag}.png"
    common.stage_input(image_path, name)
    length = max(int(round(duration * HY_FPS / 4)) * 4 + 1, 25)

    wf = common.load_tpl("tpl_hunyuan_i2v.api.json")
    common.set_class(wf, "LoadImage", image=name)
    common.set_class(wf, "HunyuanImageToVideo", width=width, height=height,
                     length=length, batch_size=1)
    common.set_class(wf, "TextEncodeHunyuanVideo_ImageToVideo", prompt=prompt,
                     image_interleave=2)
    common.set_class(wf, "BasicScheduler", steps=steps, scheduler="simple", denoise=1.0)
    common.set_class(wf, "RandomNoise", noise_seed=abs(hash(job_tag)) % 10**8)
    common.set_class(wf, "CreateVideo", fps=HY_FPS, bit_depth=8)
    common.set_class(wf, "SaveVideo", filename_prefix=f"video/rk_{job_tag}")
    outs = common.comfy_run(wf, timeout=3600)
    if not outs:
        raise RuntimeError("hunyuan i2v produced no video")
    return outs[0]


def video_i2v(image_path, prompt, out_path, job_tag, duration=5.0, end_image=None,
              hd=False):
    """Dispatch to whichever i2v model is selected. Same signature either way.

    `end_image` (directed motion) and `hd` (720p + ESRGAN) are Wan-only:
    HunyuanVideo has neither path, so they are ignored there.
    """
    if VIDEO_MODEL == "hunyuan":
        common.log("animate", f"i2v engine: HunyuanVideo 720p ({duration:.1f}s)")
        return hunyuan_i2v(image_path, prompt, out_path, job_tag, duration)
    common.log("animate", f"i2v engine: Wan 2.2 {'720x1280+ESRGAN' if hd else '480x832'}"
                          f" ({duration:.1f}s)" + (" [FLF2V start->end]" if end_image else ""))
    return wan_i2v(image_path, prompt, out_path, job_tag, duration, end_image, hd=hd)


# ------------------------------------------------------------------- wan i2v
def wan_i2v(image_path, prompt, out_path, job_tag, duration=5.0, end_image=None,
            hd=False):
    """Wan 2.2 I2V + LightX2V 4-step. Returns the raw clip path.

    When `end_image` is given, wire it into WanImageToVideo's optional
    `end_image` input so Wan morphs from the start still to the end still
    (first-last-frame to video) instead of inventing motion from one frame.
    """
    name = f"rk_wan_{job_tag}.png"
    common.stage_input(image_path, name)
    # 4n+1, and CAPPED: Wan 2.2 i2v is trained around 81 frames; past ~121 the
    # motion starts looping and drifting, so a longer slot is better filled by
    # a slight slow-down in assemble than by asking Wan for frames it cannot do.
    length = max(int(round(duration * WAN_FPS / 4)) * 4 + 1, 33)
    length = min(length, WAN_MAX_FRAMES)

    end_name = None
    if end_image:
        end_name = f"rk_wanend_{job_tag}.png"
        common.stage_input(end_image, end_name)

    # FLF2V (end_image) and HD (720p + ESRGAN) are the two "spicy" paths, and both
    # depend on the running ComfyUI having the right node features. If either is
    # unsupported the /prompt call errors and would kill the whole reel - so we try
    # the rich graph, and on ANY failure fall back to plain 480x832 I2V so the reel
    # ALWAYS renders. This is the directed-motion "was failed" fix.
    try:
        wf = _build_wan_wf(name, prompt, length, job_tag, end_name=end_name, hd=hd)
        outs = common.comfy_run(wf, timeout=2400)
        if not outs:
            raise RuntimeError("wan i2v produced no video")
        return outs[0]
    except Exception as e:
        if not (end_name or hd):
            raise
        common.log("animate", f"wan rich path failed ({str(e)[:140]}) - "
                              f"falling back to plain 480x832 I2V")
        wf = _build_wan_wf(name, prompt, length, job_tag, end_name=None, hd=False)
        outs = common.comfy_run(wf, timeout=2400)
        if not outs:
            raise RuntimeError("wan i2v produced no video (fallback)")
        return outs[0]


# HD upscaler. 720p -> 1080p only needs 1.5x, so a 2x ESRGAN produces the
# IDENTICAL final 1080p frames as the old 4x-UltraSharp for ~1/4 the compute
# (4x rendered 2880x5120 per frame - 81 times per clip - then threw 3/4 of it
# away in the downscale; measured as the bulk of the 145-186s/scene HD cost).
# The model is fetched onto the network volume on first use; a fetch failure
# falls back to the 4x model that is already there.
X2_UPSCALER = "RealESRGAN_x2plus.pth"
X2_UPSCALER_URL = ("https://github.com/xinntao/Real-ESRGAN/releases/download/"
                   "v0.2.1/RealESRGAN_x2plus.pth")
_UPSCALE_DIR = "/runpod-volume/ComfyUI/models/upscale_models"


def _hd_upscaler():
    p = os.path.join(_UPSCALE_DIR, X2_UPSCALER)
    if os.path.isfile(p):
        return X2_UPSCALER
    try:
        os.makedirs(_UPSCALE_DIR, exist_ok=True)
        common.fetch_url(X2_UPSCALER_URL, p + ".part")
        os.replace(p + ".part", p)
        common.log("animate", f"fetched {X2_UPSCALER} onto the volume")
        return X2_UPSCALER
    except Exception as e:
        common.log("animate", f"{X2_UPSCALER} fetch failed ({e}) - "
                              f"falling back to 4x-UltraSharp")
        return "4x-UltraSharp.pth"


def preload_video_model(job_dir):
    """
    Force the Wan weights onto the GPU with a minimal throwaway render (black
    frame, a few frames, 480p) so the multi-GB network-volume load overlaps
    remote work (the ElevenLabs voiceover) instead of delaying scene 1.
    Best-effort: any failure just means scene 1 pays the load as before.
    """
    try:
        black = os.path.join(job_dir, "wan_warmup.png")
        Image.new("RGB", (480, 832), (0, 0, 0)).save(black)
        out = os.path.join(job_dir, "wan_warmup.mp4")
        wan_i2v(black, "static frame, no motion", out, "warmup", duration=0.25)
        common.log("animate", "Wan preloaded (warmup clip rendered)")
    except Exception as e:
        common.log("animate", f"Wan preload failed (non-fatal): {e}")


def _build_wan_wf(name, prompt, length, job_tag, end_name=None, hd=False):
    """Build the Wan I2V workflow. hd -> generate at 720x1280 and inject an
    ESRGAN upscale (native ComfyUI nodes) between the VAEDecode frames and
    CreateVideo, then scale to exactly 1080x1920 - one GPU pass, no per-frame
    round-trips. end_name -> wire the optional FLF2V end_image."""
    wf = common.load_tpl("tpl_wan_i2v.api.json")
    common.set_class(wf, "LoadImage", image=name)
    gw, gh = (720, 1280) if hd else (480, 832)
    # `length` was computed and then NEVER PASSED before - so every clip came out
    # at the template's default 81 frames no matter what was asked for.
    common.set_class(wf, "WanImageToVideo", width=gw, height=gh, length=length)
    common.set_class(wf, "PrimitiveBoolean", value=True)           # turbo path
    common.set_class(wf, "SaveVideo", filename_prefix=f"video/rk_{job_tag}")
    common.set_prompts(wf, prompt, None)                            # keep template negative
    if end_name:
        # Second image loader wired into WanImageToVideo's optional end_image
        # slot. Fixed ids ("rk_*") cannot collide with the template's numeric ids.
        wf["rk_endimg"] = {"class_type": "LoadImage", "inputs": {"image": end_name}}
        for _, node in common.nodes_of(wf, "WanImageToVideo"):
            node["inputs"]["end_image"] = ["rk_endimg", 0]
    if hd:
        # Inject ESRGAN upscale between the decoded frames and CreateVideo:
        #   VAEDecode -> ImageUpscaleWithModel(4x) -> ImageScale(1080x1920) -> CreateVideo
        for _, cnode in common.nodes_of(wf, "CreateVideo"):
            src = cnode["inputs"].get("images")
            if not src:
                break
            wf["rk_upmodel"] = {"class_type": "UpscaleModelLoader",
                                "inputs": {"model_name": _hd_upscaler()}}
            wf["rk_upscale"] = {"class_type": "ImageUpscaleWithModel",
                                "inputs": {"upscale_model": ["rk_upmodel", 0],
                                           "image": src}}
            wf["rk_downscale"] = {"class_type": "ImageScale",
                                  "inputs": {"image": ["rk_upscale", 0],
                                             "upscale_method": "lanczos",
                                             "width": 1080, "height": 1920,
                                             "crop": "disabled"}}
            cnode["inputs"]["images"] = ["rk_downscale", 0]
            break
    return wf


def energy_plate(energy_text, out_path, job_tag, duration, w, h):
    """Generate the brain's requested effect on pure black, for screen-blending."""
    black = os.path.join(os.path.dirname(out_path), f"black_{job_tag}.png")
    Image.new("RGB", (480, 832), (0, 0, 0)).save(black)
    prompt = (f"{energy_text}, isolated on a pure black background, "
              f"bright glowing particles and motion against pure black, "
              f"nothing else in frame")
    clip = video_i2v(black, prompt, out_path, f"{job_tag}_fx", duration)
    return clip


MAX_PLATE_LUMA = 0.14      # calibrated: pure black 0.063, usable fx plate 0.077,
                           # a lit Wan scene 0.235 (that one tinted a whole reel)
FX_OPACITY = 0.35


def plate_luma(clip):
    """
    Mean luma 0-1, measured with ffprobe/signalstats.

    Wan frequently ignores "on pure black" and renders a lit, coloured scene.
    Screen-blending that over the shot tints the whole frame (observed: an entire
    reel came out magenta), so the plate is measured before it is trusted.
    """
    p = common.run(["ffprobe", "-v", "error", "-f", "lavfi",
                    "-i", f"movie={clip},signalstats",
                    "-show_entries", "frame_tags=lavfi.signalstats.YAVG",
                    "-of", "csv=p=0"], check=False)
    vals = [float(v) for v in p.stdout.split() if v.replace(".", "", 1).isdigit()]
    return (sum(vals) / len(vals) / 255.0) if vals else 1.0


def screen_blend(base_clip, fx_clip, out_path, duration):
    """
    Screen the effect over the still. Blacks contribute nothing to a screen
    blend, so we first crush the plate's low end to true black and keep the
    opacity modest - otherwise a bright plate tints the entire frame.
    """
    common.run([
        "ffmpeg", "-v", "error", "-y", "-i", base_clip, "-i", fx_clip,
        "-filter_complex",
        # crush lows to real black so only the bright effect survives
        "[1:v]lutrgb=r=\'clip((val-70)*1.6,0,255)\':"
        "g=\'clip((val-70)*1.6,0,255)\':b=\'clip((val-70)*1.6,0,255)\'[fxk];"
        "[0:v][fxk]scale2ref=w=iw:h=ih[base][fx2];"
        f"[base][fx2]blend=all_mode=screen:all_opacity={FX_OPACITY},format=yuv420p[v]",
        "-map", "[v]", "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-r", str(FPS),
        out_path])
    return out_path


# ------------------------------------------------------------------ per scene
def animate_scene(scene, still_path, source_product, job_dir, w, h, duration,
                  guard_log=None, tracer=None, end_still=None, hd=False):
    """
    Turn one scene's still into a clip of `duration` seconds.
    Returns (clip_path, guard_verdict_or_None).

    `end_still`: when set (directed-motion mode), Wan morphs from `still_path`
    to `end_still` (first-last-frame) instead of hallucinating the motion.
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

    # Ken-Burns is retained only for an explicit opt-in; every storyboard now
    # asks for real motion, because a reel of zooming stills reads as a slideshow.
    engine = (scene.get("motionEngine") or "video").lower()
    if scene.get("mode") == "product" and engine == "kenburns":
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
            luma = plate_luma(fx)
            if luma > MAX_PLATE_LUMA:
                common.log("animate", f"scene {n}: plate mean luma {luma:.2f} > "
                                      f"{MAX_PLATE_LUMA} - NOT black enough, "
                                      f"skipping overlay to protect colour")
            else:
                common.log("animate", f"scene {n}: blending plate (luma {luma:.2f})")
                os.replace(screen_blend(base, fx, out + ".fx.mp4", duration), out)
                return out, verdict
        os.replace(base, out)
        common.log("animate", f"scene {n}: ken-burns {duration:.2f}s")
        return out, verdict

    motion = scene.get("motion") or "slow cinematic camera move"
    energy = (scene.get("energy") or "").strip()
    prompt = f"{motion}. {scene['visual']}." + (f" {energy}." if energy else "")
    if tracer:
        tracer.write_json(f"scene_{n}_animate.json", {
            "engine": VIDEO_MODEL, "path": "video_i2v",
            "motion_prompt_verbatim": motion, "energy_prompt_verbatim": energy,
            "full_prompt_sent": prompt, "input_still": still_path,
            "requested_duration": duration, "clip_path": out,
            "directed_motion": bool(end_still), "end_still": end_still,
            "kenburns": scene.get("kenburns")})
        tracer.model(f"i2v:{VIDEO_MODEL}", "load")
    common.log("animate", f"scene {n}: i2v '{motion[:40]}'"
                          + (" [directed start->end]" if end_still else ""))
    clip = video_i2v(still_path, prompt, out, tag, duration, end_image=end_still, hd=hd)
    os.replace(clip, out) if clip != out else None
    return out, verdict
