"""
Lip-sync — LOCAL ONLY. There is currently no local model, so this is disabled.

HARD RULE FOR THIS PIPELINE: every pixel is generated on this box. Images come
from Qwen-Image / Qwen-Image-Edit, video from Wan 2.2 (or HunyuanVideo I2V), all
on the local GPU. The ONLY remote calls in the whole pipeline are:

    * the Stage 0 storyboard brain  - text/vision LLM, generates no pixels
    * ElevenLabs TTS                - audio, generates no pixels

This module used to call WaveSpeed's hosted avatar models
(wavespeed-ai/hunyuan-avatar and friends) to lip-sync a presenter. That is a
REMOTE VIDEO GENERATOR and it violates the rule, so it is gone - not disabled
behind a flag, removed. Do not reintroduce it.

WHAT THIS MEANS TODAY
A scene whose method is "lipsync" cannot be truly lip-synced. `lipsync()`
returns None, and make_reel falls back to animating the presenter still with Wan
i2v: the person moves and gestures naturally, but their mouth does not track the
voiceover.

HOW TO GET REAL LIP-SYNC BACK, ON-BOX
Install a local lip-sync model into ComfyUI and implement `lipsync()` against it.
Realistic candidates, all of which run on this GPU:

    LatentSync (ByteDance)  diffusion-based, best current open quality
    MuseTalk                real-time class, 30fps+, lighter
    Sonic / EchoMimic       portrait animation driven by audio
    Wav2Lip                 oldest and weakest, but tiny and reliable

All take (face image or video + audio) -> a talking clip, which is exactly the
signature below, so only the body of `lipsync()` needs writing.
"""
import common

# Kept so brain.py's gate still resolves; no model is reachable from here.
LIPSYNC_AVAILABLE = False


def lipsync(image_url, audio_url, out_path, item_name="the product",
            model=None, timeout=900):
    """
    Not implemented locally. Returns None so the caller falls back to i2v.

    Signature is deliberately unchanged from the removed remote version, so
    wiring a local model in later touches only this function.
    """
    common.log("avatar",
               "lip-sync is LOCAL-ONLY and no local model is installed - "
               "rendering the presenter with Wan i2v instead (mouth will not "
               "track the voiceover). See avatar.py for how to add one.")
    return None


def estimate_usd(seconds=None, model=None):
    """Local rendering has no per-call price; GPU time is metered separately."""
    return 0.0


def note_cost(seconds, model=None):
    """No-op: nothing remote is billed here any more."""
    return None
