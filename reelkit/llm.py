"""
LLM provider switch for the brain + QA calls.

Two providers, one function:

    anthropic  - DIRECT Claude API (default whenever ANTHROPIC_API_KEY is set).
                 Serves claude-sonnet-4-6 (newer than the Sonnet 4.0 WaveSpeed
                 proxied) at ~half the per-reel cost of WaveSpeed's flat
                 $0.05/vision-call gateway fee, and without the submit->poll
                 round trip (~15s saved per call).
    wavespeed  - the original any-llm gateway; kept as the fallback so a
                 missing/broken Anthropic key can never kill reels.

Selection: BRAIN_PROVIDER env ('anthropic' | 'wavespeed'). Unset -> anthropic
if ANTHROPIC_API_KEY is present, else wavespeed. Model for the anthropic path
comes from ANTHROPIC_MODEL (default claude-sonnet-4-6); the wavespeed path
keeps using WAVESPEED_BRAIN_MODEL via brain.brain_model().

The call contract matches wavespeed.chat(): images are PUBLIC URLS, the reply
is the model's raw text, errors raise. Callers keep their own retry loops.
"""
import os

import common
import costs
import wavespeed


def provider():
    p = (os.environ.get("BRAIN_PROVIDER") or "").strip().lower()
    if p in ("anthropic", "wavespeed"):
        return p
    return "anthropic" if os.environ.get("ANTHROPIC_API_KEY", "").strip() else "wavespeed"


def _anthropic_chat(prompt, system, images, temperature, max_tokens,
                    model=None):
    # Imported lazily so the wavespeed path never needs the SDK installed.
    import anthropic

    # A caller-supplied claude-* model wins (the photo director/QA run Haiku
    # while the reel brain runs Sonnet); WaveSpeed-style ids ("anthropic/...")
    # are that gateway's namespace and fall through to the env default.
    if not (model and model.startswith("claude-")):
        model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6").strip()
    client = anthropic.Anthropic()          # reads ANTHROPIC_API_KEY
    content = [{"type": "image", "source": {"type": "url", "url": u}}
               for u in (images or [])]
    content.append({"type": "text", "text": prompt})
    resp = client.messages.create(
        model=model,
        max_tokens=int(max_tokens or 1600),
        system=system or "",
        temperature=temperature if temperature is not None else 0.7,
        messages=[{"role": "user", "content": content}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"anthropic refused the request ({resp.stop_reason})")
    text = "".join(b.text for b in resp.content if b.type == "text")
    usd = costs.current().anthropic(resp.usage.input_tokens,
                                    resp.usage.output_tokens)
    common.log("llm", f"anthropic {model}: {resp.usage.input_tokens} in / "
                      f"{resp.usage.output_tokens} out (~${usd:.4f}, "
                      f"{len(images or [])} image(s))")
    return text


def chat(prompt, system=None, images=None, model=None, temperature=None,
         max_tokens=1400):
    """Drop-in replacement for wavespeed.chat with a provider switch."""
    if provider() == "anthropic":
        try:
            return _anthropic_chat(prompt, system, images, temperature,
                                   max_tokens, model=model)
        except Exception as e:
            # A dead key/model must degrade to the gateway, not kill the reel.
            common.log("llm", f"anthropic call failed ({e}) - falling back "
                              f"to wavespeed for this call")
    return wavespeed.chat(prompt, system=system, images=images, model=model,
                          temperature=temperature, max_tokens=max_tokens)
