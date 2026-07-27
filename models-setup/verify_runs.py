#!/usr/bin/env python
"""
Step 4 verification: prove every installed model actually RUNS, not just that
its bytes landed on disk.

One real generation per model, driven through reelkit's own functions (not a
hand-built graph) so this exercises the exact code path production uses. Peak
VRAM is sampled from nvidia-smi at 250 ms while each job runs, with ComfyUI's
VRAM freed beforehand so each number is that model's own peak and not a
leftover from the previous test.

  /venv/main/bin/python verify_runs.py               # all tests
  /venv/main/bin/python verify_runs.py wan hunyuan   # named tests only

Results are appended to logs/verify_runs.json.
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request

sys.path.insert(0, "/workspace/reelkit")
import common                                             # noqa: E402

OUT_DIR = "/workspace/models-setup/logs"
RESULTS = os.path.join(OUT_DIR, "verify_runs.json")
WORK = "/workspace/models-setup/logs/verify_work"


# --------------------------------------------------------------- VRAM sampler
def gpu_used_mib():
    p = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True)
    try:
        return int(p.stdout.strip().splitlines()[0])
    except Exception:
        return -1


class PeakSampler(threading.Thread):
    """Poll GPU memory in the background; expose the max seen."""

    def __init__(self, interval=0.25):
        super().__init__(daemon=True)
        # NB: not self._stop - that name shadows Thread._stop(), which join()
        # calls internally, and blows up with "'Event' object is not callable".
        self.interval, self.peak, self._done = interval, 0, threading.Event()

    def run(self):
        while not self._done.is_set():
            v = gpu_used_mib()
            if v > self.peak:
                self.peak = v
            self._done.wait(self.interval)

    def stop(self):
        self._done.set()
        self.join(timeout=5)
        return self.peak


def free_comfy_vram():
    """Unload every model ComfyUI holds so the next peak is measured clean."""
    req = urllib.request.Request(
        f"{common.COMFY}/free",
        data=json.dumps({"unload_models": True, "free_memory": True}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=120).read()
    except Exception as e:
        print(f"  (warn: /free failed: {e})")
    # ComfyUI frees asynchronously; wait for the card to actually settle.
    for _ in range(40):
        time.sleep(1)
        if gpu_used_mib() < 4000:
            break
    print(f"  baseline VRAM after free: {gpu_used_mib()} MiB")


# ------------------------------------------------------------------- the tests
PRODUCT_PROMPT = (
    "product photograph of a matte white cosmetic tube standing upright on a wet "
    "slate stone, the words PURE GLOW printed in clean bold sans-serif on the "
    "tube, soft studio light, shallow depth of field, water droplets, "
    "photorealistic, high detail"
)
MOTION_PROMPT = (
    "slow cinematic push-in on the product, gentle drifting steam, subtle "
    "highlights sliding across the surface, camera moves smoothly"
)


def t_t2i_qwen(state):
    """Qwen-Image-2512 fp8 -> text-to-image. Produces the still everything else uses."""
    import compose
    p = compose.generate_scene(PRODUCT_PROMPT, 1024, 1024, "vrfy_t2i", seed=7)
    state["still"] = p
    return p


def t_qwen_edit(state):
    """Qwen-Image-Edit-2511 fp8mixed -> instruction edit of that still."""
    import compose
    src = state.get("still") or state["fallback_still"]
    return compose.edit_scene(
        src, "place the product on a sunlit marble bathroom counter beside a "
             "folded linen towel, keep the product and its label exactly as they are",
        "vrfy_edit", seed=7)


def t_birefnet(state):
    """BiRefNet segmentation through the live tpl_mask graph."""
    import compose
    os.makedirs(WORK, exist_ok=True)
    src = state.get("still") or state["fallback_still"]
    cut, cov = compose.segment(src, WORK, "vrfy")
    print(f"  coverage {cov*100:.1f}% of frame")
    return cut


def t_wan(state):
    """Wan 2.2 I2V 14B fp8 + LightX2V. 4n+1 frames enforced inside wan_i2v()."""
    import animate
    os.makedirs(WORK, exist_ok=True)
    src = state.get("still") or state["fallback_still"]
    return animate.wan_i2v(src, MOTION_PROMPT,
                           os.path.join(WORK, "vrfy_wan.mp4"), "vrfy_wan",
                           duration=3.0)


def t_hunyuan(state):
    """HunyuanVideo I2V 720p bf16. Slower: 20 steps, no distilled path."""
    import animate
    os.makedirs(WORK, exist_ok=True)
    src = state.get("still") or state["fallback_still"]
    return animate.hunyuan_i2v(src, MOTION_PROMPT,
                               os.path.join(WORK, "vrfy_hy.mp4"), "vrfy_hy",
                               duration=3.0)


TESTS = [
    ("t2i_qwen", "Qwen-Image-2512 fp8", t_t2i_qwen),
    ("qwen_edit", "Qwen-Image-Edit-2511 fp8mixed", t_qwen_edit),
    ("birefnet", "BiRefNet", t_birefnet),
    ("wan", "Wan 2.2 I2V 14B fp8 + LightX2V", t_wan),
    ("hunyuan", "HunyuanVideo I2V 720p bf16", t_hunyuan),
]


def main():
    wanted = set(sys.argv[1:])
    os.makedirs(OUT_DIR, exist_ok=True)
    common.load_env()
    state = {"fallback_still": "/workspace/ComfyUI/input/example.png"}

    results = []
    if os.path.isfile(RESULTS):
        results = json.load(open(RESULTS))

    for key, label, fn in TESTS:
        if wanted and key not in wanted:
            continue
        print(f"\n{'='*78}\n== {label}  [{key}]\n{'='*78}")
        free_comfy_vram()
        base = gpu_used_mib()
        s = PeakSampler()
        s.start()
        t0 = time.time()
        rec = {"key": key, "model": label, "baseline_mib": base}
        try:
            out = fn(state)
            rec["ok"] = True
            rec["output"] = out
            rec["output_bytes"] = os.path.getsize(out) if out and os.path.isfile(out) else 0
        except Exception as e:
            rec["ok"] = False
            rec["error"] = f"{type(e).__name__}: {e}"[:2000]
        finally:
            rec["peak_mib"] = s.stop()
            rec["seconds"] = round(time.time() - t0, 1)

        rec["peak_gib"] = round(rec["peak_mib"] / 1024, 1)
        status = "OK " if rec["ok"] else "FAIL"
        print(f"\n  [{status}] {label}: peak {rec['peak_gib']} GiB "
              f"({rec['peak_mib']} MiB), {rec['seconds']}s")
        if rec["ok"]:
            print(f"         -> {rec['output']} ({rec['output_bytes']} bytes)")
        else:
            print(f"         !! {rec['error'][:600]}")

        results = [r for r in results if r["key"] != key] + [rec]
        json.dump(results, open(RESULTS, "w"), indent=2)

    print(f"\n{'='*78}\nSUMMARY  (card total 97,887 MiB / 95.6 GiB)")
    print(f"{'MODEL':<38} {'RAN':<5} {'PEAK VRAM':>12} {'SECS':>7}")
    print("-" * 78)
    for r in sorted(results, key=lambda r: [k for k, _, _ in TESTS].index(r["key"])
                    if r["key"] in [k for k, _, _ in TESTS] else 99):
        print(f"{r['model']:<38} {'yes' if r['ok'] else 'NO':<5} "
              f"{r['peak_gib']:>8} GiB {r['seconds']:>7}")
    print(f"\nfull results: {RESULTS}")
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
