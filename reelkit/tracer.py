"""
Per-run audit trail. LOGGING ONLY - this module never influences rendering.

Every /make-reel call writes a directory of artefacts so any run can be replayed
and explained after the fact:

    runs/<run_id>/
        request.json            the exact request as received (incl. template)
        vision_captions.txt     full VL caption per product image (untruncated)
        brain_prompt.txt        the exact string sent to the LLM, system + user
        storyboard.json         the JSON the brain returned
        scene_<n>_compose.json  positive/negative prompt, seed, model, paths
        scene_<n>_guard.json    OCR-diff verdict, tokens, score, retry count
        scene_<n>_animate.json  engine, verbatim motion + energy prompts, clip
        scene_<n>_vo.json       vo text, voice id, mp3 path, measured duration
        assemble.json           fitted durations, transitions, fallbacks
        result.json             the response returned to the caller
        timings.json            seconds per stage + model load/unload order
        trace.md                human-readable roll-up

Enabled by default; disable per request with config {"trace": false}.
"""
import json
import os
import time

import common

RUNS = os.path.join(common.REELKIT, "runs")


class Tracer:
    def __init__(self, run_id, enabled=True):
        self.run_id = run_id
        self.enabled = enabled
        self.dir = os.path.join(RUNS, run_id)
        self.t0 = time.time()
        self._marks = []
        self._models = []
        if enabled:
            os.makedirs(self.dir, exist_ok=True)

    # ------------------------------------------------------------------ io
    def _w(self, name, text):
        if not self.enabled:
            return
        try:
            # Never overwrite: a retried stage (a regenerated scene still, a
            # second Sonnet direction pass) gets name_2/_3..., so the trace
            # keeps EVERY attempt instead of only the last one.
            path = os.path.join(self.dir, name)
            if os.path.exists(path):
                base, ext = os.path.splitext(name)
                k = 2
                while os.path.exists(os.path.join(self.dir, f"{base}_{k}{ext}")):
                    k += 1
                path = os.path.join(self.dir, f"{base}_{k}{ext}")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as e:                       # never break a render to log
            common.log("trace", f"could not write {name}: {e}")

    def write_json(self, name, obj):
        self._w(name, json.dumps(obj, indent=2, ensure_ascii=False, default=str))

    def write_text(self, name, text):
        self._w(name, text if isinstance(text, str) else str(text))

    # -------------------------------------------------------------- timing
    def mark(self, stage):
        """Record the end of a stage."""
        now = time.time()
        prev = self._marks[-1]["at"] if self._marks else self.t0
        self._marks.append({"stage": stage, "at": now,
                            "seconds": round(now - prev, 2)})
        if self.enabled:
            common.log("trace", f"{stage}: {round(now - prev, 2)}s")

    def model(self, name, action):
        """Record a model load/unload so VRAM order is reconstructable."""
        self._models.append({"model": name, "action": action,
                             "t": round(time.time() - self.t0, 2)})

    def timings(self):
        return {"total_wall_clock_sec": round(time.time() - self.t0, 2),
                "per_stage": [{"stage": m["stage"], "seconds": m["seconds"]}
                              for m in self._marks],
                "model_load_order": self._models}

    # ----------------------------------------------------------- roll-up
    def rollup(self, result=None):
        if not self.enabled:
            return None
        self.write_json("timings.json", self.timings())
        if result is not None:
            self.write_json("result.json", result)
        try:
            import trace_run
            tr = trace_run.build_from_dir(self.dir, self.run_id)
            self.write_text("trace.md", trace_run.to_md(tr))
            self.write_json("trace.json", tr)
        except Exception as e:
            common.log("trace", f"roll-up failed (artefacts still written): {e}")
        return self.dir
