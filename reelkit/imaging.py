"""Per-scene framing.

LTX keeps a product faithful only at high guide strength (see the note in
make_reel.py), and high strength means little camera movement. So the visual
variety between scenes comes from *framing the hero still differently* per
scene rather than from asking the video model to move more.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image


def reframe(src: Path, dst: Path, *, zoom: float = 1.0, anchor: float = 0.5,
            out_w: int | None = None, out_h: int | None = None) -> Path:
    """Centre-crop `src` to `zoom` of its area, then resize to (out_w, out_h).

    zoom=1.0 is the full frame; zoom=0.6 is a tighter 60% crop (a push-in).
    `anchor` is the vertical centre of the crop, 0.0 top .. 1.0 bottom — product
    stills usually want a slightly high anchor so the crop favours the product
    rather than the table.
    """
    if not 0.05 <= zoom <= 1.0:
        raise ValueError(f"zoom must be in (0.05, 1.0], got {zoom}")
    img = Image.open(src).convert("RGB")
    w, h = img.size
    cw, ch = int(w * zoom), int(h * zoom)
    left = max(0, min(w - cw, (w - cw) // 2))
    top = max(0, min(h - ch, int((h - ch) * anchor)))
    img = img.crop((left, top, left + cw, top + ch))
    if out_w and out_h:
        img = img.resize((out_w, out_h), Image.LANCZOS)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, quality=95)
    return dst
