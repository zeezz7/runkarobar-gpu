"""
Natural sound-effects (foley) track for a reel - OPT-IN only.

Policy (hard rule): this is FOLEY, never music. No melody, no instruments, no
beat, no song. Every prompt sent to ElevenLabs is wrapped with an explicit
"no music" instruction, and the brain is separately told to author only
diegetic real-world sounds. See make_reel's soundEffects flag; when it is off
this module is never called and the reel is voiceover-only, exactly as before.

ElevenLabs Sound Generation: POST /v1/sound-generation, text -> mp3. We size
each effect to its scene duration (their API caps a single generation at 22s,
which is far longer than any scene). The clips are mixed UNDER the voiceover at
a low, ducked volume in assemble.py so speech always stays on top.
"""
import os

import common

SFX_URL = "https://api.elevenlabs.io/v1/sound-generation"

# Prepended to every effect so the model cannot wander into musical territory.
NO_MUSIC = ("natural real-world foley sound effect only, diegetic, "
            "absolutely no music, no melody, no instruments, no beat, no song: ")

# ElevenLabs caps one generation at 22s; scenes are a few seconds, so this is
# only a safety clamp.
MAX_SFX_SECONDS = 22.0
MIN_SFX_SECONDS = 0.5


def sound_effect(text, out_path, duration, api_key=None, timeout=120):
    """Generate one foley clip for `text`, ~`duration` seconds. Returns path.

    Returns None (silent scene) on empty text or any API failure - SFX is a
    non-essential garnish and must never break a reel.
    """
    text = (text or "").strip()
    if not text:
        return None

    import urllib.error
    import urllib.request
    import json as _json

    api_key = api_key or os.environ.get("ELEVEN_API_KEY")
    if not api_key:
        common.log("sfx", "ELEVEN_API_KEY not set - skipping sound effects")
        return None

    dur = max(MIN_SFX_SECONDS, min(float(duration), MAX_SFX_SECONDS))
    body = _json.dumps({
        "text": NO_MUSIC + text,
        "duration_seconds": round(dur, 2),
        # keep it faithful to the (foley) prompt rather than "creative"
        "prompt_influence": 0.6,
    }).encode()
    req = urllib.request.Request(
        SFX_URL, data=body, method="POST",
        headers={"xi-api-key": api_key, "Content-Type": "application/json",
                 "Accept": "audio/mpeg"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, \
                open(out_path, "wb") as fh:
            fh.write(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        common.log("sfx", f"ElevenLabs HTTP {e.code}: {detail} - scene left silent")
        return None
    except Exception as e:
        common.log("sfx", f"sfx failed ({e}) - scene left silent")
        return None
    common.log("sfx", f"'{text[:40]}' -> {dur:.1f}s")
    return out_path


def scene_sfx(storyboard, config, job_dir, durations):
    """Generate a foley clip per scene. Returns a list parallel to scenes:
        [{"n": int, "audio": path|None, "duration": float}, ...]

    `durations` is the authoritative per-scene length (from the VO tracks) so
    each effect matches the scene it plays under.
    """
    sfx_dir = os.path.join(job_dir, "sfx")
    os.makedirs(sfx_dir, exist_ok=True)
    out = []
    for sc, d in zip(storyboard["scenes"], durations):
        n = sc["n"]
        path = os.path.join(sfx_dir, f"scene_{n}.mp3")
        clip = sound_effect(sc.get("sfx"), path, d)
        out.append({"n": n, "audio": clip, "duration": float(d)})
    return out
