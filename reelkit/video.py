"""ffmpeg stitching: normalise clips to vertical and cross-fade them together."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


class VideoError(RuntimeError):
    pass


def _run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise VideoError(f"{cmd[0]} failed ({proc.returncode}):\n{proc.stderr[-2500:]}")
    return proc.stdout


def probe(path: Path) -> dict:
    out = _run(["ffprobe", "-v", "error", "-print_format", "json",
                "-show_format", "-show_streams", str(path)])
    info = json.loads(out)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if v is None:
        raise VideoError(f"no video stream in {path}")
    return {"duration": float(info["format"]["duration"]),
            "width": int(v["width"]), "height": int(v["height"]),
            "nb_frames": int(v.get("nb_frames") or 0)}


def stitch(clips: list[Path], out_path: Path, *, width: int = 1080, height: int = 1920,
           fps: int = 30, xfade: float = 0.5, fade_io: float = 0.5) -> dict:
    """Concatenate clips into one vertical reel with cross-fades and fade in/out.

    Each clip is scaled to cover width x height and centre-cropped, so mixed
    source resolutions (LTX 9:16 and Wan 9:16) compose cleanly. Silent by
    design — no audio track is produced.
    """
    if not clips:
        raise VideoError("no clips to stitch")
    for c in clips:
        if not Path(c).is_file():
            raise VideoError(f"clip missing: {c}")

    durs = [probe(Path(c))["duration"] for c in clips]
    n = len(clips)
    # a cross-fade cannot be longer than the shorter of the two clips it joins
    xf = min(xfade, min(durs) / 2) if n > 1 else 0.0

    parts = []
    for i in range(n):
        parts.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={fps},format=yuv420p[v{i}]")

    if n == 1:
        chain, last, total = "", "v0", durs[0]
    else:
        acc = durs[0]
        last = "v0"
        links = []
        for i in range(1, n):
            offset = acc - xf
            tag = f"x{i}"
            links.append(f"[{last}][v{i}]xfade=transition=fade:duration={xf:.3f}:"
                         f"offset={offset:.3f}[{tag}]")
            acc = acc + durs[i] - xf
            last = tag
        chain = ";" + ";".join(links)
        total = acc

    fi = min(fade_io, total / 4)
    filt = (";".join(parts) + chain +
            f";[{last}]fade=t=in:st=0:d={fi:.3f},"
            f"fade=t=out:st={max(total - fi, 0):.3f}:d={fi:.3f}[out]")

    cmd = ["ffmpeg", "-y", "-v", "error"]
    for c in clips:
        cmd += ["-i", str(c)]
    cmd += ["-filter_complex", filt, "-map", "[out]",
            "-an",                      # silent: VO/music comes later
            "-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_path)]
    _run(cmd)

    if not Path(out_path).is_file() or Path(out_path).stat().st_size == 0:
        raise VideoError(f"stitch produced no output at {out_path}")
    return probe(Path(out_path))
