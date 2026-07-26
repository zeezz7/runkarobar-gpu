# reelkit

Self-contained vertical-reel generator. One HTTP call in, one finished reel URL out.
Every stage runs on the GPU box: brain → scene images → video → voiceover → stitch →
upload.

```
POST /make-reel   ->  {reel_1080p_url, scene_image_urls, storyboard, durationSec}
GET  /health      ->  {"ok": true}
```

## Rebuilding the box from scratch

The box is disposable; this repo is the recipe. Model weights are NOT committed.

```bash
# 1. models (~110 GB, byte-verified against the remote on every run)
cd models-setup && ./download_models.sh          # all families
./download_models.sh brain qwenimage wan22       # or just what reelkit needs

# 2. secrets
cp .env.example /workspace/.env && chmod 600 /workspace/.env   # then fill it in

# 3. python deps beyond the base image
/venv/main/bin/uv pip install -r reelkit/requirements.txt

# 4. serve
cd reelkit && python server.py                   # :8189
```

`ComfyUI` must be running on `127.0.0.1:18188` (supervisor service on the Vast image).

## Stages

| Stage | File | What it does |
|---|---|---|
| 0 | `brain.py` | Qwen2.5-14B-Instruct-FP8 writes a schema-validated storyboard. Sees the product through Qwen2.5-VL captions. Unloaded before the image models load. |
| 1 | `compose.py` | `edit_animate` (Qwen-Image-Edit, default) re-images the world around the real photo. `compose_animate` segments with BiRefNet and composites the real pixels for a provably exact label. `generate_animate` for product-free b-roll. |
| 2 | `animate.py` | Wan 2.2 I2V + LightX2V, or HunyuanVideo I2V — same `i2v()` signature, chosen with `REELKIT_VIDEO_MODEL`. |
| 2b | `animate.guard_composite` | OCR-diff: label tokens on the render vs the source photo. |
| 3 | `voiceover.py` | ElevenLabs TTS. Real durations drive the cut. **Voiceover only — never music.** |
| 4 | `assemble.py` | Fit to VO, fade/cut, continuous VO track, optional burned captions, 1080p. |
| 5 | `make_reel.py` | Orchestrates 0–4, uploads, returns the result JSON. |
| 6 | `server.py` | FastAPI. |

## Templates

Templates are **brain prompt presets; the render pipeline is template-agnostic.**
A template only appends a style directive to the prompt and some soft defaults —
the storyboard schema and every downstream stage are unchanged.

| `config.template` | Direction |
|---|---|
| `ai-director` *(default)* | No directive at all — identical to pre-template behaviour |
| `showcase` | Calm, minimal, premium; product is the hero; no hard CTA |
| `ad` | High-energy direct response; hook in 2s; strong CTA |
| `unboxing` | Anticipation first, reveal as the payoff |
| `outfit-check` | Aspirational try-on; person wearing it in a real setting |
| `testimonial` | UGC talking-head. **No avatar/lipsync stage is wired** — falls back to a person-to-camera shot through the normal i2v path, and says so in the log. |

Unknown values fall back to `ai-director` with a warning rather than erroring.

## Tracing

Every run writes a full audit trail to `runs/<run_id>/` (disable with
`config.trace = false`):

```
request.json  vision_captions.txt  brain_prompt.txt  storyboard.json
scene_<n>_{compose,guard,animate,vo}.json
assemble.json  result.json  timings.json  trace.md  trace.json
```

`brain_prompt.txt` is the exact string sent to the LLM. `trace_run.py <run_id>`
rebuilds a trace for older runs, marking anything that was never saved as
**NOT PERSISTED** rather than guessing it.

The text traces are committed; the media they reference is not — reels live on MinIO.

## Hard rules

- **No music.** Voiceover or silence.
- **No hardcoded product behaviour.** No keyword lists, no `if isFaceWash`. The brain
  decides `energy`, `motion`, `kenburns` numbers and method; the executor renders
  whatever it is given.
- **Claims.** The VO may only state benefits printed on the packaging. This is a
  prompt-level rule, so it reduces risk rather than guaranteeing compliance — check
  copy before anything ships.
- **Secrets** live in `/workspace/.env`, never in source.

## Known limits

- A 15s reel takes **~7–8 min**: three Wan clips at ~65s each is the floor, plus
  ~1 min of brain. Not 3 min without cutting scenes or clip length.
- Wan renders natively at 480×832 and is upscaled to 1080p. HunyuanVideo I2V is
  720×1280 native — a smaller upscale — but slower and has no distilled fast path.
- `whip` and `zoom` transitions fall back to a fade (logged).
- The OCR guard needs ≥3 readable tokens; on a small embroidered logo it skips rather
  than guess, so apparel fidelity is not machine-verified.
- **HunyuanVideo's licence excludes the EU, UK and South Korea.** Wan 2.2 is
  Apache-2.0 with no such limit.
