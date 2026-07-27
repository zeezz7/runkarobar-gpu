"""
Talking-avatar lip-sync — the one capability with no local model.

Every other stage runs on this box. There is no open lip-sync model installed
(and none in the reelkit working set), so a `lipsync` scene is rendered by a
WaveSpeed avatar model: it takes a presenter STILL and an AUDIO clip and returns
a video of that person speaking it.

That makes this the pipeline's SECOND remote dependency, and a per-scene billed
one, so it is gated hard: `brain.validate()` downgrades `lipsync` to
`edit_animate` unless the template is in `LIPSYNC_TEMPLATES` (ad, testimonial).
No other template can ever trigger a charge here.

All five models share the same {image, audio} contract, so they are swappable by
name — the tenant can trial-and-error for the best sync without a code change.
Model ids ported from StaffHQ's AVATAR_MODEL_IDS.

Both inputs must be PUBLIC URLS: the avatar service fetches them itself, so a
local path cannot be used. We upload to MinIO first.
"""
import os

import common
import costs
import wavespeed

# name -> WaveSpeed model id. Prices are per second of output and are the reason
# this is gated; hunyuan is the cheapest usable one, so it is the default.
AVATAR_MODELS = {
    "hunyuan": "wavespeed-ai/hunyuan-avatar",
    "infinitetalk": "wavespeed-ai/infinitetalk",
    "omnihuman": "bytedance/avatar-omni-human-1.5",
    "kling": "kwaivgi/kling-v2-ai-avatar-standard",
    "wan-speech": "wavespeed-ai/wan-2.2/speech-to-video",
}
DEFAULT_AVATAR = "hunyuan"

# Which models accept a `resolution`, and what they accept. THE DEFAULT IS 480p
# ON ALL OF THEM - leaving it unset silently produced a 480p talking head that
# was then upscaled to 1080x1920, which is exactly as soft as it sounds.
# omnihuman and kling expose no resolution knob at all.
AVATAR_RESOLUTIONS = {
    "hunyuan": ("480p", "720p"),
    "infinitetalk": ("480p", "720p"),
    "wan-speech": ("480p", "720p"),
}
DEFAULT_RESOLUTION = "720p"

# FLAT per-call price from the WaveSpeed catalogue (base_price), confirmed
# against a real dashboard entry: one hunyuan-avatar call billed $0.15.
# This was previously modelled as a per-second rate, which is simply not how
# these are billed.
AVATAR_USD = {"hunyuan": 0.15, "infinitetalk": 0.15, "omnihuman": 0.16,
              "kling": 0.28, "wan-speech": 0.15}


def avatar_model():
    name = (os.environ.get("REELKIT_AVATAR_MODEL") or DEFAULT_AVATAR).strip().lower()
    if name not in AVATAR_MODELS:
        common.log("avatar", f"unknown avatar model {name!r} - using {DEFAULT_AVATAR}")
        name = DEFAULT_AVATAR
    return name


def resolution_for(name):
    opts = AVATAR_RESOLUTIONS.get(name)
    if not opts:
        return None                      # model has no resolution knob
    want = (os.environ.get("REELKIT_AVATAR_RESOLUTION") or DEFAULT_RESOLUTION).lower()
    return want if want in opts else opts[-1]


def lipsync(image_url, audio_url, out_path, item_name="the product",
            model=None, timeout=900):
    """
    Presenter still + audio -> a talking clip. Returns the local path, or None.

    Returning None rather than raising is deliberate: a failed avatar call
    should cost the reel one scene's polish, not the whole render. The caller
    falls back to animating the still normally.
    """
    name = model or avatar_model()
    model_id = AVATAR_MODELS[name]
    common.log("avatar", f"lip-sync via {name} ({model_id})"
                        + (f" @ {resolution_for(name)}" if resolution_for(name) else ""))

    # Avatar services intermittently fail to fetch our input URLs under load
    # ("could not download the input"), which is transient - retry before
    # giving up on the scene.
    last = None
    for attempt in range(1, 4):
        try:
            payload = {
                "image": image_url,
                "audio": audio_url,
                "prompt": (f"A brand presenter speaking to camera, showing the "
                           f"{item_name}, natural expression and gestures."),
            }
            res = resolution_for(name)
            if res:
                payload["resolution"] = res
            out = wavespeed.run(model_id, payload, timeout=timeout)
            if out:
                common.fetch_url(out[0], out_path)
                return out_path
            last = "empty output"
        except Exception as e:
            last = str(e)[:200]
            common.log("avatar", f"attempt {attempt}/3 failed: {last}")
    common.log("avatar", f"lip-sync unavailable ({last}) - falling back to i2v")
    return None


def estimate_usd(seconds=None, model=None):
    """Flat per call - `seconds` is ignored, kept so callers need not change."""
    return AVATAR_USD.get(model or avatar_model(), 0.15)


def note_cost(seconds, model=None):
    """Record the avatar spend on the job's meter."""
    costs.current().avatar(estimate_usd(seconds, model))
