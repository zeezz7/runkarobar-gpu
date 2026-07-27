"""
Per-job cost accounting, for the `cost_usd` field in the Result JSON.

Three things cost money on a reel and they are billed in completely different
units, so each is tracked where it is actually spent rather than guessed at the
end:

    WaveSpeed   per CALL      - wavespeed.chat() knows which endpoint it hit
    ElevenLabs  per CHARACTER - voiceover.tts() knows the text it sent
    the GPU     per SECOND    - make_reel times the render

Rates are read from the environment, never hardcoded, because all three change
with the plan you are on and the machine you rent. Defaults are the list prices
observed on 2026-07-27; override in /workspace/.env:

    COST_GPU_USD_PER_HOUR     what Vast bills for this instance
    COST_ELEVEN_USD_PER_1K    your ElevenLabs per-1000-character rate
    (WaveSpeed per-call prices come from its own model catalogue)

`cost_usd` is therefore an ESTIMATE and is labelled as one - it is meant for
attributing spend across jobs, not for invoicing.
"""
import os
import threading
import time

# WaveSpeed catalogue prices (GET /api/v3/models, base_price).
WAVESPEED_PRICES = {"vision": 0.05, "text": 0.01}


def _f(name, default):
    try:
        return float(os.environ.get(name) or default)
    except ValueError:
        return default


class Meter:
    """Accumulates one job's spend. Thread-safe: uploads/TTS run in pools."""

    def __init__(self):
        self._lock = threading.Lock()
        self.wavespeed_usd = 0.0
        self.wavespeed_calls = 0
        self.eleven_chars = 0
        self.gpu_seconds = 0.0
        self._t0 = time.time()

    def wavespeed(self, kind):
        with self._lock:
            self.wavespeed_usd += WAVESPEED_PRICES.get(kind, 0.0)
            self.wavespeed_calls += 1

    def eleven(self, text):
        with self._lock:
            self.eleven_chars += len(text or "")

    def stop_clock(self):
        """Wall-clock is the honest proxy: the box is rented by the hour."""
        with self._lock:
            self.gpu_seconds = round(time.time() - self._t0, 1)

    def summary(self):
        gpu_rate = _f("COST_GPU_USD_PER_HOUR", 1.10)
        eleven_rate = _f("COST_ELEVEN_USD_PER_1K", 0.30)
        gpu = self.gpu_seconds / 3600.0 * gpu_rate
        eleven = self.eleven_chars / 1000.0 * eleven_rate
        total = gpu + eleven + self.wavespeed_usd
        return {
            "total_usd": round(total, 4),
            "gpu_usd": round(gpu, 4),
            "gpu_seconds": self.gpu_seconds,
            "wavespeed_usd": round(self.wavespeed_usd, 4),
            "wavespeed_calls": self.wavespeed_calls,
            "elevenlabs_usd": round(eleven, 4),
            "elevenlabs_chars": self.eleven_chars,
            "rates": {"gpu_usd_per_hour": gpu_rate,
                      "eleven_usd_per_1k_chars": eleven_rate},
            "note": "estimate - rates are configurable, see costs.py",
        }


# One meter per job. The server holds a GPU lock so only one job runs at a time;
# reset() at the start of each keeps them from accumulating into each other.
_current = Meter()


def reset():
    global _current
    _current = Meter()
    return _current


def current():
    return _current
