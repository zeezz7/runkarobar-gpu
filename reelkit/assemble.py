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


# Every intermediate is LOSSLESS PCM. This chain used to re-encode the voiceover
# to mp3 128k mono here, then to AAC for the master, then to AAC AGAIN for the
# final encode - four lossy generations stacked on top of ElevenLabs' own mp3,
# each one adding swirl to sibilants. Now there is exactly ONE lossy step, the
# final AAC.
A_RATE, A_CH = 48000, 2
# -16 LUFS / -1.5 dBTP is the loudness social platforms normalise to; hitting it
# here means they leave the audio alone instead of pulling it around.
LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"


def silence(dst, duration):
    common.run([
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi",
        "-i", f"anullsrc=channel_layout=stereo:sample_rate={A_RATE}",
        "-t", f"{duration:.3f}", "-c:a", "pcm_s16le", dst,
    ])
    return dst


def pad_audio(src, dst, duration):
    """Force one scene's audio to exactly the scene duration (lossless)."""
    common.run([
        "ffmpeg", "-v", "error", "-y", "-i", src,
        "-af", f"{LOUDNORM},aresample={A_RATE},apad",
        "-t", f"{duration:.3f}",
        "-c:a", "pcm_s16le", "-ar", str(A_RATE), "-ac", str(A_CH), dst,
    ])
    return dst


# ------------------------------------------------------------------- captions
def _hex_to_ass(hex_colour, fallback="&H001C6BE8&"):
    """
    #RRGGBB -> ASS &HBBGGRR&. ASS is BGR, not RGB - swapping the bytes is the
    whole trick, and getting it wrong silently gives you the complementary
    colour rather than an error.
    """
    h = (hex_colour or "").strip().lstrip("#")
    if len(h) != 6:
        return fallback
    try:
        r, g, b = h[0:2], h[2:4], h[4:6]
        return f"&H00{b}{g}{r}".upper() + "&"
    except Exception:
        return fallback


def write_badges_ass(badges, total, path, w, h):
    """
    IG-story badges: big white text on a solid colour block, popping in and out,
    spread evenly across the reel.

    Ported from StaffHQ's ffmpeg.assembler.ts. Pure libass, so it costs nothing
    and adds no dependency. Two details carried over deliberately:
      * BorderStyle=3 with a fat Outline is what makes the solid box - there is
        no "background box" property in ASS;
      * anchored to the LOWER third (alignment 2) with a generous MarginV so a
        badge never lands on a talking presenter's face, and sits above where
        the caption line would go.
    """
    badges = [b for b in (badges or []) if (b.get("text") or "").strip()][:6]
    if not badges or total <= 0:
        return None
    fs = max(int(h / 17), 48)              # ~112px at 1080x1920
    margin_h = int(w * 0.065)
    margin_v = int(h * 0.22)               # clear of captions and the very bottom

    def ts(t):
        hh = int(t // 3600); mm = int(t % 3600 // 60); ss = t % 60
        return f"{hh:d}:{mm:02d}:{ss:05.2f}"

    styles = []
    for i, b in enumerate(badges):
        c = _hex_to_ass(b.get("color"))
        styles.append(
            f"Style: Badge{i},DejaVu Sans,{fs},&H00FFFFFF,&H00FFFFFF,{c},{c},"
            f"-1,0,0,0,100,100,0,0,3,20,0,2,{margin_h},{margin_h},{margin_v},1")

    head = ("[Script Info]\n"
            "ScriptType: v4.00+\n"
            f"PlayResX: {w}\nPlayResY: {h}\n"
            "WrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\n"
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
            "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,"
            "ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,"
            "MarginR,MarginV,Encoding\n"
            + "\n".join(styles) + "\n\n[Events]\n"
            "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n")

    seg = total / len(badges)
    gap = min(0.5, seg * 0.15)
    events = []
    for i, b in enumerate(badges):
        start = i * seg + gap
        stop = min((i + 1) * seg - gap, start + 3.5)
        if stop <= start:
            continue
        text = "".join(ch for ch in b["text"].strip() if ch.isprintable())
        # fade in/out + a small pop: 72% -> 100% over 220ms.
        fx = r"{\fad(220,220)\fscx72\fscy72\t(0,220,\fscx100\fscy100)}"
        events.append(
            f"Dialogue: 0,{ts(start)},{ts(stop)},Badge{i},,0,0,0,,{fx}{text}")
    if not events:
        return None
    open(path, "w").write(head + "\n".join(events) + "\n")
    common.log("assemble", f"{len(events)} badge(s) burned")
    return path


def write_ass(scenes, durations, path, w, h):
    """
    Burned-in captions as a real ASS file.

    We write ASS directly instead of SRT + `force_style`, because ASS Fontsize is
    interpreted relative to PlayResY - and when that is not declared libass
    assumes 288, so a nominal size renders ~6.7x too large at 1080x1920. Passing
    `original_size=` to the subtitles filter did NOT reliably fix it (measured:
    captions still ~200px tall and covering the product). Declaring PlayResX/Y
    here makes Fontsize mean actual pixels.
    """
    fs = max(int(h / 42), 20)           # ~46px at 1080x1920
    margin_v = int(h * 0.10)            # keep clear of the platform UI
    margin_h = int(w * 0.08)

    def ts(t):
        hh = int(t // 3600); mm = int(t % 3600 // 60); ss = t % 60
        return f"{hh:d}:{mm:02d}:{ss:05.2f}"

    def wrap(line, max_chars=34):
        words, out, cur = line.split(), [], ""
        for word in words:
            if cur and len(cur) + 1 + len(word) > max_chars:
                out.append(cur); cur = word
            else:
                cur = f"{cur} {word}".strip()
        if cur:
            out.append(cur)
        return "\\N".join(out[:3])      # never more than three lines

    head = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {w}\nPlayResY: {h}\n"
        "WrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,"
        "BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,"
        "BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
        f"Style: Cap,DejaVu Sans,{fs},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,3,2,2,{margin_h},{margin_h},{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n")

    events, t, n = [], 0.0, 0
    for sc, d in zip(scenes, durations):
        line = (sc.get("vo") or "").strip()
        if line:
            line = "".join(ch for ch in line if ch.isprintable())
            events.append(f"Dialogue: 0,{ts(t)},{ts(t + d)},Cap,,0,0,0,,{wrap(line)}")
            n += 1
        t += d
    open(path, "w").write(head + "\n".join(events) + "\n")
    return path if n else None


# ------------------------------------------------------------------- assemble
def assemble(scene_clips, vo_tracks, storyboard, job_dir, name, aspect="9:16",
             captions=True, tracer=None):
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
        a = os.path.join(tmp, f"a_{v['n']}.wav")
        aparts.append(pad_audio(v["audio"], a, d) if v.get("audio")
                      else silence(a, d))
    alst = os.path.join(tmp, "aconcat.txt")
    with open(alst, "w") as fh:
        for p in aparts:
            fh.write(f"file '{p}'\n")
    vo_track = os.path.join(tmp, "vo.wav")
    common.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                "-i", alst, "-c", "copy", vo_track])

    master = os.path.join(tmp, "master.mp4")
    common.run(["ffmpeg", "-v", "error", "-y", "-i", silent_master, "-i", vo_track,
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-ar", str(A_RATE), "-ac", str(A_CH), "-shortest", master])

    # ---- captions ----------------------------------------------------------
    total = common.probe_duration(master)

    # ---- final encodes -----------------------------------------------------
    # 1080p only - the 720p rung was dropped at the caller's request.
    outs = {}
    for label, tall in (("1080p", 1920),):
        w, h = (tall, tall) if aspect == "1:1" else common.dims_for(aspect, tall)
        if aspect == "1:1":
            w = h = 1080 if label == "1080p" else 720
        dst = os.path.join(job_dir, f"{name}_{label}.mp4")
        vf = [f"scale={w}:{h}:force_original_aspect_ratio=decrease",
              f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"]
        ass = (write_ass(scenes, durations, os.path.join(tmp, f"subs_{label}.ass"), w, h)
               if captions else None)
        if ass:
            vf.append(f"ass={ass}")
        # Badges are a SEPARATE ass pass from captions: they use their own styles
        # and must render even when captions are off (the `ad` template wants
        # badges without subtitles).
        badge_ass = write_badges_ass(
            storyboard.get("badges"), sum(durations),
            os.path.join(tmp, f"badges_{label}.ass"), w, h)
        if badge_ass:
            vf.append(f"ass={badge_ass}")
        vf.append("format=yuv420p")
        common.run(["ffmpeg", "-v", "error", "-y", "-i", master,
                    "-vf", ",".join(vf),
                    "-c:v", "libx264", "-profile:v", "high", "-preset", "medium",
                    "-crf", "21" if label == "1080p" else "23",
                    "-maxrate", "6M" if label == "1080p" else "2M",
                    "-bufsize", "12M" if label == "1080p" else "4M",
                    # stream-copy the audio: it is already the 192k AAC written
                    # for the master, and re-encoding it here was a second,
                    # pointless lossy generation.
                    "-c:a", "copy",
                    "-movflags", "+faststart", "-r", str(FPS), dst])
        outs[label] = dst
        common.log("assemble", f"{label}: {dst} ({os.path.getsize(dst)/1e6:.1f} MB)")

    outs["durationSec"] = round(total, 2)
    if tracer:
        tracer.write_json("assemble.json", {
            "per_scene": [{"scene": sc["n"], "fitted_duration": d,
                           "transition_in": sc.get("transitionIn"),
                           "dipped_through_black": f}
                          for sc, d, f in zip(scenes, durations, fades)],
            "transition_fallbacks": [
                f"scene {sc['n']}: '{sc.get('transitionIn')}' not implemented -> fade"
                for sc in scenes
                if (sc.get("transitionIn") or "cut").lower() not in SUPPORTED_TRANSITIONS],
            "total_duration": round(total, 2),
            "master_resolution": f"{mw}x{mh}",
            "captions_burned": bool(captions), "fps": FPS,
            "outputs": {k: v for k, v in outs.items() if k != "durationSec"}})
    return outs
