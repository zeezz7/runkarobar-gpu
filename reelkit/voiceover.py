"""
Stage 3 - voiceover via ElevenLabs.

HARD RULE from the brief: audio is VOICEOVER ONLY. This module never generates,
mixes or downloads music, and assemble.py never adds a background track.

Audio leads video: each scene's real VO duration (measured with ffprobe, not
estimated) becomes that scene's clip length. Scenes with an empty `vo` stay
silent and keep their planned durationSec.
"""
import os

import common

TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"
MODEL_ID = os.environ.get("ELEVEN_MODEL_ID", "eleven_multilingual_v2")

# Sane defaults per language when config.elevenVoiceId is empty.
# eleven_multilingual_v2 handles hi/ur/hinglish on these English-native voices.
DEFAULT_VOICES = {
    "en":       "IKne3meq5aSn9XLyUdCD",  # Charlie - deep, confident, energetic male
    "hi":       "IKne3meq5aSn9XLyUdCD",
    "hinglish": "IKne3meq5aSn9XLyUdCD",
    "ur":       "IKne3meq5aSn9XLyUdCD",
}


def pick_voice(config):
    vid = (config.get("elevenVoiceId") or "").strip()
    if vid:
        return vid
    return DEFAULT_VOICES.get((config.get("language") or "en").lower(),
                              DEFAULT_VOICES["en"])


def tts(text, out_path, voice_id, api_key=None, timeout=120):
    """Synthesise one line. Returns (path, duration_seconds)."""
    import urllib.error
    import urllib.request
    import json as _json

    api_key = api_key or os.environ.get("ELEVEN_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVEN_API_KEY not set (expected in /workspace/.env)")

    body = _json.dumps({
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": {"stability": 0.4, "similarity_boost": 0.75,
                           "style": 0.35, "use_speaker_boost": True},
    }).encode()
    req = urllib.request.Request(
        TTS_URL.format(voice=voice_id), data=body, method="POST",
        headers={"xi-api-key": api_key, "Content-Type": "application/json",
                 "Accept": "audio/mpeg"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, open(out_path, "wb") as fh:
            fh.write(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        raise RuntimeError(f"ElevenLabs HTTP {e.code}: {detail}")

    dur = common.probe_duration(out_path)
    if dur <= 0:
        raise RuntimeError(f"TTS produced unplayable audio: {out_path}")
    return out_path, dur


def voice_scenes(storyboard, config, job_dir):
    """
    Synthesise VO for every scene that has one.

    Returns a list parallel to storyboard['scenes']:
        {"n":1, "audio": "/path/scene_1.mp3" | None, "duration": float}
    `duration` is the authoritative clip length for that scene.
    """
    voice_id = pick_voice(config)
    audio_dir = os.path.join(job_dir, "audio")
    os.makedirs(audio_dir, exist_ok=True)

    out = []
    for sc in storyboard["scenes"]:
        n = sc["n"]
        line = (sc.get("vo") or "").strip()
        planned = float(sc.get("durationSec") or 4)
        if not line:
            common.log("vo", f"scene {n}: silent (no vo) -> {planned:.2f}s")
            out.append({"n": n, "audio": None, "duration": planned})
            continue
        path = os.path.join(audio_dir, f"scene_{n}.mp3")
        _, dur = tts(line, path, voice_id)
        # a hair of air after the line so cuts do not clip the last word
        # audio leads video ONLY when the line is longer than planned; a short
        # line keeps its planned slot (padded with silence in assemble) so the
        # finished reel still matches config.lengthSec.
        dur = round(max(dur + 0.25, planned), 3)
        common.log("vo", f"scene {n}: {dur:.2f}s (planned {planned:.2f}s) \"{line[:48]}\"")
        out.append({"n": n, "audio": path, "duration": dur})
    return out


if __name__ == "__main__":
    import sys
    common.load_env()
    text = sys.argv[1] if len(sys.argv) > 1 else "Fresh skin, every single day."
    p, d = tts(text, "/tmp/vo_unit_test.mp3", DEFAULT_VOICES["en"])
    print(f"OK  {p}  {d:.2f}s  {os.path.getsize(p)} bytes")
