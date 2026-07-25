"""Minimal ComfyUI /prompt API client.

Submits an API-format graph, blocks until it finishes, and resolves the produced
files to absolute paths on disk.
"""
from __future__ import annotations

import json
import shutil
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

DEFAULT_HOST = "http://127.0.0.1:18188"
COMFY_ROOT = Path("/workspace/ComfyUI")


class ComfyError(RuntimeError):
    pass


class Comfy:
    def __init__(self, host: str = DEFAULT_HOST, root: Path = COMFY_ROOT):
        self.host = host.rstrip("/")
        self.root = Path(root)

    # -- infra ---------------------------------------------------------------
    def health(self) -> dict:
        try:
            with urllib.request.urlopen(f"{self.host}/api/system_stats", timeout=15) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            raise ComfyError(f"ComfyUI unreachable at {self.host}: {e}") from e

    def stage_input(self, src: Path) -> str:
        """Copy a file into ComfyUI's input/ dir so LoadImage can see it."""
        src = Path(src).expanduser().resolve()
        if not src.is_file():
            raise ComfyError(f"input image not found: {src}")
        dst_dir = self.root / "input"
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / f"reel_{uuid.uuid4().hex[:10]}{src.suffix.lower()}"
        shutil.copyfile(src, dst)
        return dst.name

    # -- execution -----------------------------------------------------------
    def run(self, graph: dict, *, timeout: int = 3600, poll: float = 3.0,
            label: str = "job", on_tick=None) -> list[Path]:
        """Queue a graph, wait for it, return absolute paths of produced files."""
        payload = json.dumps({"prompt": graph, "client_id": str(uuid.uuid4())}).encode()
        req = urllib.request.Request(
            f"{self.host}/prompt", data=payload,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                prompt_id = json.load(r)["prompt_id"]
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:2000]
            raise ComfyError(f"{label}: graph rejected by ComfyUI:\n{detail}") from e

        t0 = time.time()
        while True:
            if time.time() - t0 > timeout:
                raise ComfyError(f"{label}: timed out after {timeout}s")
            time.sleep(poll)
            with urllib.request.urlopen(f"{self.host}/history/{prompt_id}", timeout=30) as r:
                hist = json.load(r)
            if prompt_id not in hist:
                if on_tick:
                    on_tick(time.time() - t0)
                continue
            entry = hist[prompt_id]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                msgs = json.dumps(status.get("messages", []), indent=1)[:3000]
                raise ComfyError(f"{label}: execution failed:\n{msgs}")
            return self._collect(entry.get("outputs", {}), label)

    def _collect(self, outputs: dict, label: str) -> list[Path]:
        paths: list[Path] = []
        for node_out in outputs.values():
            for key in ("images", "gifs", "videos"):
                for item in node_out.get(key, []) or []:
                    if not isinstance(item, dict) or "filename" not in item:
                        continue
                    p = (self.root / item.get("type", "output")
                         / item.get("subfolder", "") / item["filename"])
                    if p.is_file():
                        paths.append(p)
        if not paths:
            raise ComfyError(f"{label}: completed but produced no output files")
        return paths
