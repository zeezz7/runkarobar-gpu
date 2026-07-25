"""
Stage 4 - ffmpeg assembly.

Takes per-scene clips + per-scene VO and produces the finished reel at two
resolutions.

Rules implemented here (from the brief):
  * audio leads video - each clip is fitted to its VO duration (trim if longer,
    hold the last frame if shorter) so sound and picture never drift.
  * transitionIn: "fade" dips through black for 0.3s (0.15s out of the previous
    scene + 0.15s into the next); "cut" is a hard cut. "whip" and "zoom" are not
    implemented yet and fall back to fade - and that fallback is LOGGED.
  * one continuous VO track built by concatenating scene audio, with real
    silence generated for scenes that have no line, so every scene starts where
    it should.
  * scale, never stretch: fit inside the target and pad.
  * NO MUSIC. Nothing in this file mixes a background track.
"""
import os

import common

FPS = 30
FADE = 0.15          # per side; 2 x 0.15 = 0.3s dip to black
SUPPORTED_TRANSITIONS = {"cut", "fade"}


# ------------------------------------------------------------------ per scene
def fit_clip(src, dst, duration, w, h, fade_in=False, fade_out=False):
    """Normalise one clip: target size (pad, don't stretch), exact duration, fps."""
    have = common.probe_duration(src)
    vf = [
        f"scale={w}:{h}:force_original_aspect_ratio=decrease",
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black",
        f"fps={FPS}",
    ]
    # hold the last frame if the clip is shorter than its voiceover
    if have < duration - 0.02:
        vf.append(f"tpad=stop_mode=clone:stop_duration={duration - have:.3f}")
    if fade_in:
        vf.append(f"fade=t=in:st=0:d={FADE}")
    if fade_out:
        vf.append(f"fade=t=out:st={max(duration - FADE, 0):.3f}:d={FADE}")
    vf.append("format=yuv420p")

    common.run([
        "ffmpeg", "-v", "error", "-y", "-i", src,
        "-vf", ",".join(vf), "-t", f"{duration:.3f}",
        "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-r", str(FPS), dst,
    ])
    return dst


def silence(dst, duration):
    common.run([
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi",
        "-i", f"anullsrc=channel_layout=mono:sample_rate=44100",
        "-t", f"{duration:.3f}", "-c:a", "libmp3lame", "-b:a", "128k", dst,
    ])
    return dst


def pad_audio(src, dst, duration):
    """Force one scene's audio to exactly the scene duration."""
    common.run([
        "ffmpeg", "-v", "error", "-y", "-i", src,
        "-af", f"apad", "-t", f"{duration:.3f}",
        "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", "-ac", "1", dst,
    ])
    return dst


# ------------------------------------------------------------------- captions
def write_srt(scenes, durations, path):
    def ts(t):
        h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")
    lines, t, idx = [], 0.0, 1
    for sc, d in zip(scenes, durations):
        line = (sc.get("vo") or "").strip()
        if line:
            # strip anything that will not render cleanly in a burned-in sub
            line = "".join(ch for ch in line if ch.isprintable())
            lines += [str(idx), f"{ts(t)} --> {ts(t + d)}", line, ""]
            idx += 1
        t += d
    open(path, "w").write("\n".join(lines))
    return path if idx > 1 else None


# ------------------------------------------------------------------- assemble
def assemble(scene_clips, vo_tracks, storyboard, job_dir, name, aspect="9:16",
             captions=True):
    """
    scene_clips : [path,...] in scene order
    vo_tracks   : [{"n","audio","duration"},...] from voiceover.voice_scenes
    Returns {"1080p": path, "720p": path, "durationSec": float}
    """
    scenes = storyboard["scenes"]
    tmp = os.path.join(job_dir, "assemble")
    os.makedirs(tmp, exist_ok=True)

    durations = [float(v["duration"]) for v in vo_tracks]

    # which scenes dip through black
    fades = []
    for i, sc in enumerate(scenes):
        t = (sc.get("transitionIn") or "cut").lower()
        if t not in SUPPORTED_TRANSITIONS:
            common.log("assemble",
                       f"scene {sc['n']}: transition '{t}' not implemented - "
                       f"falling back to fade")
            t = "fade"
        fades.append(t == "fade" and i > 0)   # first scene never fades in

    # ---- normalise clips at master resolution (1080 tall) -------------------
    mw, mh = common.dims_for(aspect, 1920) if aspect != "1:1" else (1080, 1080)
    parts = []
    for i, (clip, dur) in enumerate(zip(scene_clips, durations)):
        out = os.path.join(tmp, f"part_{i + 1}.mp4")
        fit_clip(clip, out, dur, mw, mh,
                 fade_in=fades[i],
                 fade_out=(i + 1 < len(fades) and fades[i + 1]))
        parts.append(out)
        common.log("assemble", f"scene {i + 1}: {dur:.2f}s "
                               f"{'fade-in' if fades[i] else 'cut'}")

    # ---- concat video ------------------------------------------------------
    lst = os.path.join(tmp, "concat.txt")
    with open(lst, "w") as fh:
        for p in parts:
            fh.write(f"file '{p}'\n")
    silent_master = os.path.join(tmp, "video_silent.mp4")
    common.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                "-i", lst, "-c", "copy", silent_master])

    # ---- one continuous VO track ------------------------------------------
    aparts = []
    for v, d in zip(vo_tracks, durations):
        a = os.path.join(tmp, f"a_{v['n']}.mp3")
        aparts.append(pad_audio(v["audio"], a, d) if v.get("audio")
                      else silence(a, d))
    alst = os.path.join(tmp, "aconcat.txt")
    with open(alst, "w") as fh:
        for p in aparts:
            fh.write(f"file '{p}'\n")
    vo_track = os.path.join(tmp, "vo.mp3")
    common.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                "-i", alst, "-c", "copy", vo_track])

    master = os.path.join(tmp, "master.mp4")
    common.run(["ffmpeg", "-v", "error", "-y", "-i", silent_master, "-i", vo_track,
                "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", master])

    # ---- captions ----------------------------------------------------------
    srt = write_srt(scenes, durations, os.path.join(tmp, "subs.srt")) if captions else None
    total = common.probe_duration(master)

    # ---- final encodes -----------------------------------------------------
    outs = {}
    for label, tall in (("1080p", 1920), ("720p", 1280)):
        w, h = (tall, tall) if aspect == "1:1" else common.dims_for(aspect, tall)
        if aspect == "1:1":
            w = h = 1080 if label == "1080p" else 720
        dst = os.path.join(job_dir, f"{name}_{label}.mp4")
        vf = [f"scale={w}:{h}:force_original_aspect_ratio=decrease",
              f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"]
        if srt:
            style = ("FontName=DejaVu Sans,Fontsize=16,PrimaryColour=&H00FFFFFF,"
                     "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,"
                     "Alignment=2,MarginV=90")
            vf.append(f"subtitles={srt}:force_style='{style}'")
        vf.append("format=yuv420p")
        common.run(["ffmpeg", "-v", "error", "-y", "-i", master,
                    "-vf", ",".join(vf),
                    "-c:v", "libx264", "-profile:v", "high", "-preset", "medium",
                    "-crf", "21" if label == "1080p" else "23",
                    "-maxrate", "6M" if label == "1080p" else "2M",
                    "-bufsize", "12M" if label == "1080p" else "4M",
                    "-c:a", "aac", "-b:a", "160k",
                    "-movflags", "+faststart", "-r", str(FPS), dst])
        outs[label] = dst
        common.log("assemble", f"{label}: {dst} ({os.path.getsize(dst)/1e6:.1f} MB)")

    outs["durationSec"] = round(total, 2)
    return outs
