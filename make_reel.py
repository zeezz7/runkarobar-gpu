#!/usr/bin/env python3
"""make_reel.py — product image in, finished vertical reel out.

Runs entirely on this GPU box, driving the local ComfyUI through its /prompt API,
then stitches with ffmpeg and uploads to MinIO.

    python make_reel.py product.jpg              # LTX only  (~5 min)
    python make_reel.py product.jpg --hero       # + Wan money shot (~+4 min)

Pipeline
    1. FLUX img2img  -> one clean product hero still (low denoise: keeps branding)
    2. LTX i2v x3    -> three 5 s scene clips (push-in / detail / lifestyle)
    3. Wan i2v x1    -> optional 5 s hero clip, behind --hero (slow, off by default)
    4. ffmpeg        -> 1080x1920 vertical reel, cross-fades + fade in/out, silent
    5. MinIO         -> reels/<timestamp>.mp4, prints the public URL

Config is environment-only; no secrets live in this repo. See reelkit/storage.py.

The 3-scene structure is fixed for now — the VPS "brain" will feed real
storyboards later; swap SCENES for that payload when it does.
"""
from __future__ import annotations

import argparse
import datetime
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from reelkit import imaging, storage, video, workflows  # noqa: E402
from reelkit.comfy import Comfy, ComfyError            # noqa: E402

# --- geometry ---------------------------------------------------------------
# 9:16 throughout. LTX dims must be /32; Wan dims /16; FLUX /16.
HERO_W, HERO_H = 864, 1536      # FLUX still (1.33 MP)
LTX_W, LTX_H = 576, 1024        # LTX render size
WAN_W, WAN_H = 432, 768         # Wan render size (below the 720x480 that hit 32.1 GB)
OUT_W, OUT_H = 1080, 1920       # final reel

LTX_LENGTH, LTX_FPS = 121, 24.0   # 121/24 = 5.04 s   ((n-1)%8==0)
WAN_LENGTH, WAN_FPS = 81, 16.0    # 81/16  = 5.06 s   ((n-1)%4==0)

HERO_PROMPT = (
    "professional commercial product photograph, the product presented cleanly and "
    "centred, crisp studio lighting with soft shadows, seamless gradient backdrop, "
    "sharp focus on the product, glossy highlights, premium advertising still, "
    "high detail, colour-accurate, product label and packaging text unchanged")

# Fixed 3-scene storyboard. Replace with the brain's payload later.
#
# NOTE on `zoom`, measured on this box rather than assumed:
# LTX only keeps a product faithful at high guide strength (1.0). Dropping
# strength to the stock template's 0.15 does produce more measured motion, but
# visual inspection showed it achieves that by letting the product drift out of
# frame and inventing a replacement object — useless for a product ad. So we
# hold strength at 1.0 and get scene-to-scene variety by *framing the hero still
# differently per scene* here, which is deterministic and never risks the
# product's identity.
SCENES = [
    ("push_in", 1.00, 0.50,
     "slow cinematic push-in toward the product, the camera drifts closer "
     "at a steady pace, soft studio light sweeping gently across the "
     "surface, subtle glossy highlights travelling over the packaging, "
     "product stays centred and perfectly in focus, premium commercial "
     "advertising shot, smooth stable motion, shallow depth of field"),
    ("detail", 0.55, 0.62,
     "extreme close product detail, camera glides slowly across the surface, "
     "light rakes over the material picking out fine texture and the edge of "
     "the label, macro clarity, crisp specular highlight travelling slowly, "
     "elegant premium product film, gentle continuous motion"),
    ("lifestyle", 0.78, 0.40,
     "the product sits on a warm natural surface in soft window light, "
     "gentle atmospheric haze drifting through the frame, gradual "
     "camera drift with a shallow depth of field, gauzy bokeh "
     "background, gentle gradual light shift, gentle lifestyle "
     "advertising mood, calm and aspirational, smooth subtle motion"),
]

HERO_CLIP_PROMPT = (
    "hero product shot, dramatic slow reveal, the product rotates almost "
    "imperceptibly as cinematic light sweeps across it, rich reflections and "
    "specular highlights moving over the surface, deep contrast, luxurious "
    "advertising film, ultra-smooth motion, product centred and tack sharp")


def log(step: str, msg: str) -> None:
    print(f"[{step:<9}] {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a vertical product reel.")
    ap.add_argument("image", type=Path, help="product photo (jpg/png)")
    ap.add_argument("--hero", action="store_true",
                    help="also render a Wan 2.2 money shot (~4 min extra)")
    ap.add_argument("--seed", type=int, default=None, help="base seed (default random)")
    ap.add_argument("--out", type=Path, default=None, help="local output mp4 path")
    ap.add_argument("--no-upload", action="store_true", help="skip the MinIO upload")
    ap.add_argument("--comfy", default="http://127.0.0.1:18188", help="ComfyUI base URL")
    args = ap.parse_args()

    if not args.image.is_file():
        log("fatal", f"input image not found: {args.image}")
        return 2

    seed = args.seed if args.seed is not None else random.randint(1, 2**31)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = args.out or Path(f"/workspace/reels_out/reel-{stamp}.mp4")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    timings: list[tuple[str, float]] = []
    t_start = time.time()
    comfy = Comfy(args.comfy)

    # Fail fast on config/connectivity before spending GPU minutes.
    cfg = None
    if not args.no_upload:
        try:
            cfg = storage.Config.from_env()
            layout = storage.detect_layout(cfg)
            log("preflight", f"MinIO {cfg.endpoint} bucket={cfg.bucket} layout={layout}")
        except storage.StorageError as e:
            log("fatal", f"storage preflight failed: {e}")
            return 2
    try:
        stats = comfy.health()
        log("preflight", f"ComfyUI {stats['system']['comfyui_version']} ok  seed={seed}")
    except ComfyError as e:
        log("fatal", str(e))
        return 2

    try:
        # -- 1. product hero still (FLUX img2img) ----------------------------
        t = time.time()
        src_name = comfy.stage_input(args.image)
        hero_paths = comfy.run(
            workflows.flux_product_hero(src_name, HERO_PROMPT, width=HERO_W,
                                        height=HERO_H, seed=seed),
            label="flux-hero")
        hero = hero_paths[0]
        timings.append(("flux hero", time.time() - t))
        log("flux", f"hero still -> {hero.name}  ({timings[-1][1]:.0f}s)")

        # stage the hero back into input/ so the video models can load it
        hero_name = comfy.stage_input(hero)

        # -- 2. scene clips (LTX) --------------------------------------------
        clips: list[Path] = []
        for i, (name, zoom, anchor, prompt) in enumerate(SCENES):
            t = time.time()
            framed = imaging.reframe(hero, out_path.parent / f"frame_{i}_{name}.png",
                                     zoom=zoom, anchor=anchor,
                                     out_w=LTX_W, out_h=LTX_H)
            framed_name = comfy.stage_input(framed)
            out = comfy.run(
                workflows.ltx_image_to_video(framed_name, prompt, width=LTX_W,
                                             height=LTX_H, length=LTX_LENGTH,
                                             fps=LTX_FPS, seed=seed + 100 + i,
                                             prefix=f"reel/scene_{i}_{name}"),
                label=f"ltx-{name}")
            clips.append(out[0])
            timings.append((f"ltx {name}", time.time() - t))
            d = video.probe(out[0])
            log("ltx", f"scene {i+1}/3 {name:<9} zoom={zoom:.2f} -> {out[0].name} "
                       f"{d['width']}x{d['height']} {d['duration']:.2f}s "
                       f"({timings[-1][1]:.0f}s)")

        # -- 3. optional Wan money shot --------------------------------------
        if args.hero:
            t = time.time()
            out = comfy.run(
                workflows.wan_image_to_video(hero_name, HERO_CLIP_PROMPT, width=WAN_W,
                                             height=WAN_H, length=WAN_LENGTH,
                                             fps=WAN_FPS, seed=seed + 999),
                label="wan-hero", timeout=3600)
            clips.append(out[0])
            timings.append(("wan hero", time.time() - t))
            d = video.probe(out[0])
            log("wan", f"money shot -> {out[0].name} {d['width']}x{d['height']} "
                       f"{d['duration']:.2f}s ({timings[-1][1]:.0f}s)")

        # -- 4. stitch --------------------------------------------------------
        t = time.time()
        meta = video.stitch(clips, out_path, width=OUT_W, height=OUT_H)
        timings.append(("stitch", time.time() - t))
        log("stitch", f"{out_path} {meta['width']}x{meta['height']} "
                      f"{meta['duration']:.2f}s from {len(clips)} clips "
                      f"({timings[-1][1]:.0f}s)")

        # -- 5. upload --------------------------------------------------------
        url = None
        if not args.no_upload:
            t = time.time()
            key = f"reels/{out_path.name}"
            url = storage.upload(out_path, key, cfg)
            timings.append(("upload", time.time() - t))
            ok, code, size = storage.verify_public(url)
            log("upload", f"{url} ({timings[-1][1]:.0f}s)")
            log("verify", f"anonymous HEAD -> {code}, {size/1e6:.2f} MB, "
                          f"{'OK' if ok else 'NOT PUBLICLY READABLE'}")
            if not ok:
                log("fatal", "uploaded object is not publicly readable")
                return 1

    except (ComfyError, video.VideoError, storage.StorageError) as e:
        log("fatal", str(e))
        return 1

    total = time.time() - t_start
    print("\n--- timings ---")
    for name, secs in timings:
        print(f"  {name:<12} {secs:7.1f}s")
    print(f"  {'TOTAL':<12} {total:7.1f}s")
    if url:
        print(f"\nREEL URL: {url}")
    else:
        print(f"\nREEL: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
