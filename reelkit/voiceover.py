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
import costs

TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"

# Highest-fidelity output first; the API 403s anything above your plan, so we
# walk down. Measured on this account 2026-07-27:
#   pcm_44100      -> 403, Pro tier and above
#   mp3_44100_192  -> 403, Creator tier and above
#   mp3_44100_128  -> 200  (what we actually get)
# Upgrading the ElevenLabs plan is the ONLY way to improve the source audio -
# everything downstream of here is already lossless (see assemble.py).
OUTPUT_FORMATS = ("pcm_44100", "mp3_44100_192", "mp3_44100_128")

# eleven_v3 is the current top-quality model (74 languages) and is a clear step
# up on the multilingual_v2 this used to pin - noticeably better prosody and
# code-switching, which is what Hinglish copy actually needs. Read at CALL time,
# not import time: common.load_env() usually runs after this module is imported,
# so a module-level read would miss /workspace/.env.
DEFAULT_MODEL_ID = "eleven_v3"

# Hinglish reads slow and flat at 1.0 - 1.1x gives it the pace an actual reel
# has, and shortens every slot, which is also what stops clips being stretched.
# Applied with ffmpeg atempo, NOT the API's voice_settings.speed: v3 accepts
# that field with HTTP 200 and then ignores it (measured - speed=1.1 came back
# LONGER than speed=1.0, i.e. it was just generation variance).
DEFAULT_SPEED = {"hinglish": 1.1, "hi": 1.1, "ur": 1.1, "en": 1.0}


def speed_for(language):
    env = os.environ.get("REELKIT_VO_SPEED")
    if env:
        try:
            return max(0.5, min(2.0, float(env)))
        except ValueError:
            pass
    return DEFAULT_SPEED.get((language or "en").lower(), 1.0)


def model_id():
    return os.environ.get("ELEVEN_MODEL_ID") or DEFAULT_MODEL_ID

# Sane defaults per language when config.elevenVoiceId is empty.
# FEMALE by default. This used to point every language at Charlie, a deep male
# voice, which is wrong for most of what this pipeline advertises (fashion,
# beauty, apparel) and was the main reason the voiceover read badly.
# "Zara" is a standard-accent young female social-media read - it carries
# Hinglish code-switching far more naturally than the American voices, which
# lean hard into an English accent mid-sentence.
ZARA_SOCIAL = "RAPmAZHXSuTrzY9pjpR3"   # young, social-media creator, standard
BELLA_PRO = "hpp4J3VqNfWAUOO0d1Us"     # professional/bright, for straight VO
DEFAULT_VOICES = {
    "en":       BELLA_PRO,
    "hi":       ZARA_SOCIAL,
    "hinglish": ZARA_SOCIAL,
    "ur":       ZARA_SOCIAL,
}


# Templates that are inherently fronted by a woman (outfit-check, ad) force a
# female voice, mirroring StaffHQ. Explicit config.elevenVoiceId always wins.
FEMALE_VOICES = {"en": BELLA_PRO, "hi": ZARA_SOCIAL,
                 "hinglish": ZARA_SOCIAL, "ur": ZARA_SOCIAL}


def female_voice(language=None):
    return FEMALE_VOICES.get((language or "en").lower(), FEMALE_VOICES["en"])


def pick_voice(config):
    vid = (config.get("elevenVoiceId") or "").strip()
    if vid:
        return vid
    return DEFAULT_VOICES.get((config.get("language") or "en").lower(),
                              DEFAULT_VOICES["en"])


def tts(text, out_path, voice_id, api_key=None, timeout=120, speed=1.0):
    """Synthesise one line. Returns (path, duration_seconds)."""
    import urllib.error
    import urllib.request
    import json as _json

    api_key = api_key or os.environ.get("ELEVEN_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVEN_API_KEY not set (expected in /workspace/.env)")

    mid = model_id()
    # v3 quantises stability to 0.0 / 0.5 / 1.0 (creative / natural / robust) and
    # ignores `style`; sending the v2 values gets you a 422 or silently odd
    # delivery. 0.5 is the natural read an ad wants.
    if mid.startswith("eleven_v3"):
        # similarity_boost high: stay close to the reference voice rather than
        # drifting, which is what makes a read sound synthetic.
        settings = {"stability": 0.5, "similarity_boost": 0.9,
                    "use_speaker_boost": True}
    else:
        settings = {"stability": 0.4, "similarity_boost": 0.75,
                    "style": 0.35, "use_speaker_boost": True}
    costs.current().eleven(text)
    body = _json.dumps({
        "text": text, "model_id": mid, "voice_settings": settings,
    }).encode()

    last = None
    for fmt in OUTPUT_FORMATS:
        req = urllib.request.Request(
            TTS_URL.format(voice=voice_id) + f"?output_format={fmt}",
            data=body, method="POST",
            headers={"xi-api-key": api_key, "Content-Type": "application/json",
                     "Accept": "audio/mpeg"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r, \
                    open(out_path, "wb") as fh:
                fh.write(r.read())
            if fmt != OUTPUT_FORMATS[-1]:
                common.log("vo", f"output_format={fmt}")
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:400]
            # 403 = this format is above the plan; try the next one down.
            if e.code == 403 and "output_format" in detail:
                last = detail
                continue
            raise RuntimeError(f"ElevenLabs HTTP {e.code}: {detail}")
    else:
        raise RuntimeError(f"ElevenLabs refused every output format: {last}")

    # atempo preserves pitch; chain it if ever asked for >2.0.
    if speed and abs(speed - 1.0) > 0.01:
        sped = out_path + ".spd.mp3"
        common.run(["ffmpeg", "-v", "error", "-y", "-i", out_path,
                    "-filter:a", f"atempo={speed:.3f}",
                    "-c:a", "libmp3lame", "-b:a", "192k", sped])
        os.replace(sped, out_path)

    dur = common.probe_duration(out_path)
    if dur <= 0:
        raise RuntimeError(f"TTS produced unplayable audio: {out_path}")
    return out_path, dur


MIN_SCENE = 1.6          # never cut a shot shorter than this
TAIL_PAD = 0.25          # breathing room after a line so cuts do not clip it


def rebalance(tracks, target, tol=1.0):
    """
    Fit the scene slots to the REQUESTED reel length after real speech is known.

    Two faults this fixes, both measured on a live run:
      * a line longer than its planned slot pushed the reel to 16.17s against a
        requested 15s - the +/-1s guarantee was only ever checked on the
        storyboard, never on the delivered file;
      * a 4.83s line sat in a 7.0s slot, leaving 2.17s of dead air.

    Speech is never truncated: each slot's floor is its own audio length plus a
    short tail. Slack is taken from (or given to) the scenes that have it.
    """
    floors = [max((t["speech"] or 0) + TAIL_PAD, MIN_SCENE) for t in tracks]
    total = sum(t["duration"] for t in tracks)
    if abs(total - target) <= tol:
        return tracks

    if total > target:                      # shrink, but never below the speech
        excess = total - target
        slack = [t["duration"] - f for t, f in zip(tracks, floors)]
        avail = sum(s for s in slack if s > 0)
        if avail > 0:
            take = min(excess, avail)
            for t, f, sl in zip(tracks, floors, slack):
                if sl > 0:
                    t["duration"] = round(t["duration"] - take * (sl / avail), 3)
    else:                                   # stretch the shortest shots
        add = (target - total) / len(tracks)
        for t in tracks:
            t["duration"] = round(t["duration"] + add, 3)

    for t, f in zip(tracks, floors):        # never go under the floor
        t["duration"] = round(max(t["duration"], f), 3)
    common.log("vo", f"rebalanced to {sum(t['duration'] for t in tracks):.2f}s "
                     f"(target {target}s)")
    return tracks


def voice_scenes(storyboard, config, job_dir):
    """
    Synthesise VO for every scene that has one.

    Returns a list parallel to storyboard['scenes']:
        {"n":1, "audio": "/path/scene_1.mp3" | None, "duration": float}
    `duration` is the authoritative clip length for that scene.
    """
    voice_id = pick_voice(config)
    spd = speed_for(config.get("language"))
    if abs(spd - 1.0) > 0.01:
        common.log("vo", f"speaking at {spd}x")
    audio_dir = os.path.join(job_dir, "audio")
    os.makedirs(audio_dir, exist_ok=True)

    out = []
    for sc in storyboard["scenes"]:
        n = sc["n"]
        line = (sc.get("vo") or "").strip()
        planned = float(sc.get("durationSec") or 4)
        if not line:
            common.log("vo", f"scene {n}: silent (no vo) -> {planned:.2f}s")
            out.append({"n": n, "audio": None, "duration": planned, "speech": 0.0})
            continue
        path = os.path.join(audio_dir, f"scene_{n}.mp3")
        _, dur = tts(line, path, voice_id, speed=spd)
        # a hair of air after the line so cuts do not clip the last word
        # audio leads video ONLY when the line is longer than planned; a short
        # line keeps its planned slot (padded with silence in assemble) so the
        # finished reel still matches config.lengthSec.
        speech = dur
        dur = round(max(dur + TAIL_PAD, planned), 3)
        common.log("vo", f"scene {n}: slot {dur:.2f}s (speech {speech:.2f}s, "
                         f"planned {planned:.2f}s) \"{line[:44]}\"")
        out.append({"n": n, "audio": path, "duration": dur, "speech": speech})

    target = float(config.get("lengthSec") or sum(t["duration"] for t in out))
    return rebalance(out, target)


if __name__ == "__main__":
    import sys
    common.load_env()
    text = sys.argv[1] if len(sys.argv) > 1 else "Fresh skin, every single day."
    p, d = tts(text, "/tmp/vo_unit_test.mp3", DEFAULT_VOICES["en"])
    print(f"OK  {p}  {d:.2f}s  {os.path.getsize(p)} bytes")
