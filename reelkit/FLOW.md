# reelkit — end-to-end flow

How a product photo becomes a finished vertical reel on this box, why each stage is
shaped the way it is, and what is still wrong. Written for someone picking this up
cold.

---

## 0. The one-paragraph version

You POST a product image URL and a one-line brief. A **remote** vision LLM (WaveSpeed
any-llm/vision) looks at the product photo and writes a storyboard. For each scene, a
local image model re-imagines the world around the real product photo; a local vision
model checks the label survived; a local video model animates the still; ElevenLabs
speaks the line. ffmpeg fits every clip to its voiceover, stitches them, and uploads a
1080×1920 MP4.

The pipeline is **hybrid**: only the brain is remote. Everything that touches pixels
runs on this box.

---

## 1. How this box got here

It started as a **model bake-off**, not a pipeline. Eight models were installed and
compared on the same product:

| Model | Verdict |
|---|---|
| **Wan 2.2 I2V + LightX2V** | **Winner.** Real camera motion, 70s/clip, 5.6× faster than its own 20-step baseline with no quality loss. |
| LTX-2.3 22B | Best text stability, near-static motion, 97.2 GB VRAM — 654 MiB from OOM. Deleted later. |
| LTX-Video 0.9.8 | Weakest i2v: cropped, drifted, label mush. Deleted. |
| HunyuanVideo (T2V) | Beautiful light, invented a different product, barely moved. Deleted, later replaced by its I2V sibling. |
| Mochi 1 | Blank unbranded tube, soft, minimal motion. Deleted. |
| HiDream-I1-Full | Excellent text-to-image. Deleted to make room for the brain. |
| HiDream-E1.1 | **Failed the make-or-break test.** Turned "MEN" into "NEN"; higher resolution made it worse; lower denoise produced pure noise. |
| Qwen-Image-Edit-2511 | Replaced HiDream. Renders six lines of small print legibly through a full scene re-render. |

The decisive finding: **a diffusion edit re-renders everything it touches.** That is
why the pipeline has three different ways to make a scene image, and why a vision
model checks the label afterwards.

---

## 2. Request → response

```
POST /make-reel
{
  "product_images": ["https://.../product.jpg"],
  "brief": "15s premium haircare reel ... warm female Hinglish voiceover",
  "config": {
    "lengthSec": 15, "aspectRatio": "9:16", "language": "hinglish",
    "brandName": "Dove", "elevenVoiceId": "", "captions": false,
    "template": "showcase", "trace": true
  }
}
        ↓
{
  "reel_1080p_url": "https://staging-storage.runkarobar.com/reels/<id>_1080p.mp4",
  "reel_720p_url": "",                       // 1080p-only; key kept for compatibility
  "scene_image_urls": [...],
  "storyboard": { ... },
  "durationSec": 15.0
}
```

`server.py` holds a GPU lock, so one reel renders at a time. That is deliberate:
ComfyUI serialises GPU work anyway, and two concurrent jobs thrash VRAM.

---

## 3. The pipeline, stage by stage

```
request
   │
   ├─ fetch product images ─────────────────────────────► work/<id>/product_N.jpg
   │
STAGE 0  brain.py            REMOTE - one WaveSpeed any-llm/vision call (~$0.05)
   │   the product PHOTOS go straight to the model (no captioning pass)
   │   it writes the storyboard              ← template directive appended
   │   validate → retry up to 3× on a specific complaint (each retry is billed)
   │   holds ZERO VRAM - nothing to unload
   │                                                    ► storyboard.json
STAGE 3  voiceover.py    (runs BEFORE the visuals — audio leads video)
   │   ElevenLabs TTS per scene, real duration via ffprobe
   │   rebalance slots to the requested length          ► audio/scene_N.mp3
   │
   └─ per scene ──────────────────────────────────────────────────────┐
        STAGE 1  compose.py    build the still                        │
           edit_animate      Qwen-Image-Edit-2511 re-images the world │
           compose_animate   BiRefNet cutout + Qwen-Image backdrop    │
           generate_animate  pure generation, no product              │
                                                    ► scene_N.png     │
        STAGE 2b animate.guard_composite                              │
           Qwen2.5-VL reads label tokens off render and source        │
           <50% overlap → re-composite (reuses the backdrop)          │
           unload the guard's VL model                                │
        STAGE 2  animate.py    still → clip                           │
           video_i2v() → Wan 2.2  |  HunyuanVideo I2V                 │
           optional energy plate, luma-checked, screen-blended        │
                                                    ► clip_N.mp4      │
        free ComfyUI VRAM before the next scene ──────────────────────┘
   │
STAGE 4  assemble.py
   │   fit each clip to its VO slot (trim, or hold last frame)
   │   fade (0.15s each side) or hard cut per transitionIn
   │   one continuous VO track; optional burned ASS captions
   │                                                    ► <id>_1080p.mp4
STAGE 5  upload  (parallel, ~5s)                        ► MinIO URLs
STAGE 6  trace   runs/<id>/ — 21 artefacts + trace.md
```

---

## 4. What each stage actually decides

### Stage 0 — the brain (remote)

A single WaveSpeed `any-llm/vision` call. It sees the product photographs directly,
so the old Qwen2.5-VL captioning pass is gone. Select the model with
`WAVESPEED_BRAIN_MODEL`; `reelkit/wavespeed.py` has the API details and the three
traps (URL-only images, credit failures arriving as HTTP 200, and the advertised
model catalogue).

**No local brain is installed.** Qwen2.5-14B and Qwen2.5-32B were deliberately not
downloaded — that frees ~50 GB of disk and the ~16 GB of VRAM the brain used to
hold. Do not reintroduce them.

Writes a JSON storyboard. Per scene it chooses `goal`, `method`, `mode`, `visual`,
`background`, `motion`, `energy`, `transitionIn`, `durationSec`, `motionEngine`,
`kenburns` numbers, and the `vo` line.

Machine-enforced rules (a violation is fed back and the brain retries):

- scene durations sum to `lengthSec` ±1
- at least one scene shows the real product
- `generate_animate` is banned from product-showing goals and from `mode: product`
- no scene may use `motionEngine: kenburns`
- `kenburns` values are clamped; rotation lifts zoom to 1.12 so corners can't show

Prompt-level rules (guidance, not guarantees):

- the VO may only claim what is **printed on the packaging**
- language is restated *after* the claims block so it isn't drowned out
- `background` describes a close product surface, never a room

**Templates** are prompt presets only — `TEMPLATES[name]` supplies a `persona` string
and soft `defaults`, appended as a `STYLE DIRECTIVE` section. `ai-director` appends
zero characters, so default behaviour is unchanged. The renderer never sees the
template.

### Stage 1 — three ways to make a still

| Method | When | Product fidelity |
|---|---|---|
| `edit_animate` **(default)** | product in context: worn, held, staged | re-rendered, but Qwen-Image-Edit held 11/11 Nivea tokens and 8/8 Dove tokens |
| `compose_animate` | isolated product, label must be provably exact | **pixel-exact** — real pixels pasted, harmonised with PIL only |
| `generate_animate` | no product on screen | n/a |

`compose_animate` never lets a sampler touch the product. Harmonisation is a colour
pull plus a drawn contact shadow — arithmetic, not inference.

### Stage 2b — the guard

Reads label tokens off the render and the source with Qwen2.5-VL and compares sets.
Skips when the source yields fewer than 3 readable tokens: on a small embroidered
logo the model hallucinated a different word each look ("BRETEL" vs "BALLY" on
identical pixels), and one misread scored 0%.

### Stage 2 — motion

`video_i2v()` dispatches to Wan 2.2 (480×832 native, 4-step LightX2V, ~65 s) or
HunyuanVideo I2V (720×1280 native, 20 steps, slower), selected by
`REELKIT_VIDEO_MODEL`. Same signature, so nothing else changes.

Ken-Burns still exists in the code but is unreachable from a valid storyboard —
a reel of zooming stills reads as a slideshow.

### Stage 3 — voiceover

Runs **before** the visuals so audio can drive the cut. A slot is
`max(speech + 0.25, planned)`, then all slots are rebalanced to the requested length,
each floored at its own audio so a line is never clipped.

**Voiceover only. Nothing in this codebase mixes music.**

---

## 5. Models on the box

| Model | Role | Size | Peak VRAM (measured) |
|---|---|---:|---:|
| WaveSpeed any-llm/vision | brain (**remote**) | — | none |
| Qwen2.5-VL-7B-Instruct | OCR guard only | 16.6 GB | ~18 GiB |
| Qwen-Image-2512 fp8 | text-to-image | 20.4 GB | 28.5 GiB |
| Qwen-Image-Edit-2511 fp8mixed | instruction editing | 20.5 GB | 28.9 GiB |
| Wan 2.2 I2V 14B fp8 + LightX2V | video (default) | 38.0 GB | 38.3 GiB |
| HunyuanVideo I2V 720p bf16 | video (alternative) | 36.1 GB | 61.3 GiB |
| BiRefNet | segmentation | 0.44 GB | 2.4 GiB |
| 4x-UltraSharp | upscaling | 0.07 GB | — |

Peak VRAM measured 2026-07-27 on a 95.6 GiB RTX PRO 6000 SE — see MODELS.md §10.
**Nothing came close to OOM**: the worst case left ~34 GiB spare. The two historical
OOMs both involved the local brain sitting resident beside the diffusion models;
with the brain remote that failure mode no longer exists. The guard's VL model is
still freed after each use and ComfyUI is still told to free between scenes.

---

## 6. Bugs found by looking at output, not logs

Every one of these passed the automated checks:

| Symptom | Cause |
|---|---|
| Entire reel magenta | Wan ignored "on pure black" and rendered a lit scene; screen-blended at 0.85 opacity |
| Captions burying the product | ASS `Fontsize` is relative to `PlayResY`, default **288** → 16 rendered ~107 px. `original_size=` did **not** fix it; explicit ASS did |
| Everything soft | Ken-Burns rendered at 480×832 then upscaled to 1080p, discarding a sharp still |
| Two overlapping faces | compositing a model shot segments the whole person onto a scene containing a person |
| Wrong product entirely | `generate_animate` renders from nothing — it invented a different polo |
| Backdrops containing the product | prompt asked for "close-up of the tube … empty scene with no product" |
| Backdrop was a room with a toilet | `background` described a bathroom instead of a surface |
| "orbit" rendered as a zoom | `kenburns` vocabulary had no rotation; 7 of 8 scenes were identical push-ins |
| Motion prompt could land in the negative slot | positive was picked by **string length**; Wan's Chinese negative is 137 chars |
| Reel 16.17 s against 15 s requested | ±1 s was enforced on the storyboard, never the output |
| Face wash "eliminates pimples and acne" | nothing constrained VO claims to the packaging |
| Guard failed on identical pixels | one hallucinated token scored 0% |
| Two OOMs | brain held resident beside a duplicate VL model; then ComfyUI stacked 80.5 GB |

---

## 7. Timing (measured, 15 s / 3 scenes)

| Stage | Time |
|---|---:|
| Brain (captions + load + generate) | ~60–90 s |
| Scene image, 4-step Lightning | **9–18 s** each *(was 127 s at 50 steps)* |
| Video clip, Wan turbo | **~65 s** each ← the floor |
| Assembly | ~15 s |
| Upload, parallel | **~5 s** *(was ~60 s serial)* |
| **Total** | **~7–8 min** |

**3 minutes is not reachable while every scene is a real clip.** Three Wan clips are
195 s on their own. Getting under 3 min means fewer scenes or shorter clips.

---

## 8. Known limits

- Wan is 480×832 native, upscaled to 1080p. Hunyuan I2V is 720×1280 native — a
  smaller upscale — but slower with no distilled path. True 1080p needs a second
  super-resolution stage that is not built.
- The claims rule is a prompt instruction. It reduces risk; it does not guarantee
  compliance. **Check copy before anything ships.**
- Hinglish quality dropped with the 14B brain and needed the language rule restated.
- `whip` and `zoom` transitions fall back to a fade (logged).
- The guard cannot verify apparel with a small logo.
- `edit_animate` re-renders the person, so a model's face changes between scenes.
- No avatar/lipsync stage — the `testimonial` template falls back and says so.
- **HunyuanVideo's licence excludes the EU, UK and South Korea**; Wan 2.2 is
  Apache-2.0 with no such limit.

---

## 9. Where things live

```
/workspace/reelkit/          the pipeline (in git)
  brain.py wavespeed.py costs.py compose.py animate.py voiceover.py assemble.py
  make_reel.py server.py tracer.py trace_run.py
  workflows/tpl_*.api.json   ComfyUI graphs
  runs/<id>/                 text audit trail (in git)
  work/<id>/                 media, intermediates (NOT in git)
/workspace/models-setup/     download_models.sh, MODELS.md, BAKEOFF.md
/workspace/.env              secrets, mode 600, never committed
```

Reels live on MinIO and survive the box. The box does not.
`git clone` → `./download_models.sh` → fill `.env` → `pip install -r requirements.txt`
→ `python server.py`.

---

## 10. MinIO — secrets and the one thing that trips everyone up

### Credentials

All four live in `/workspace/.env` (mode 600, gitignored). **Never in source, never
in this repo** — it is public.

```bash
MINIO_ENDPOINT=staging-storage.runkarobar.com   # host only, no scheme
MINIO_ACCESS_KEY=runkarobar
MINIO_SECRET_KEY=<secret>                        # in .env only
MINIO_BUCKET=runkarobar
```

`.env.example` in the repo root is the template. Copy it, fill it in, `chmod 600`.

Every uploader reads these from the environment and fails loudly if one is missing.
Four scripts previously had the secret hardcoded as a default; they were rewritten to
`${MINIO_SECRET_KEY:?set it in /workspace/.env}` before anything was pushed.

### The trap: this endpoint's nginx is BUCKET-SCOPED

nginx rewrites `/<key>` → `/<bucket>/<key>`, so **the host root IS the bucket**.

Every standard S3 client signs the path it transmits. That breaks here:

```
client sends   /<bucket>/<key>      and signs   /<bucket>/<key>
nginx rewrites to /<bucket>/<bucket>/<key>
MinIO verifies the REWRITTEN path   →  SignatureDoesNotMatch
```

**The `minio` Python SDK and `mc` both fail on this, no matter how correct the
credentials are.** Confirmed on this box: `mc alias set` fails, and so does `mc cp`.
The error is misleading — it looks exactly like a bad secret. A useful diagnostic:

| Test | Result |
|---|---|
| valid access key + valid secret | `SignatureDoesNotMatch` |
| **bogus** access key | `InvalidAccessKeyId` |
| valid access key + bogus secret | `SignatureDoesNotMatch` |

Because the key is validated *before* the signature is computed over the rewritten
path, a correct secret and a wrong one produce the identical error. Do not conclude
the credential is bad from `SignatureDoesNotMatch` alone.

### The fix: sign the POST-rewrite path

`minio_upload.py` does this and is why uploads work:

```
transmit  /<key>                 →  nginx rewrites to /<bucket>/<key>
sign      /<bucket>/<key>        →  matches what MinIO verifies
```

For **listing**, the canonical URI needs a trailing slash — nginx rewrites bare `/`
to `/<bucket>/`, not `/<bucket>`. That one character is the difference between 200
and 403 (`minio_list.py`).

### Usage

```bash
set -a; . /workspace/.env; set +a

python minio_upload.py out.mp4  --prefix reels                  # → reels/out.mp4
python minio_upload.py s1.png   --key images/<job>_s1.png       # explicit key
python minio_list.py --prefix videos/ref/                       # list
```

Public URLs carry **no bucket segment**:

```
https://staging-storage.runkarobar.com/reels/<name>.mp4
https://staging-storage.runkarobar.com/images/<name>.png
```

`make_reel.py` uploads the reel and every scene still in parallel (~5 s for 5 files),
giving stills a job-unique key so two runs cannot overwrite each other.

### Operational notes

- Uploads can **stall** rather than fail: one 23 MB transfer crawled at ~11 KB/s for
  8 minutes while a 3.6 MB file moved at 900 KB/s minutes later. `minio_upload.py`
  has no timeout or retry — if an upload hangs, kill it and retry rather than waiting.
- A `404` on a fresh URL usually means the PUT has not finished. MinIO writes the key
  atomically, so an object is either absent or complete, never partial.
- **Rotate the ElevenLabs, WaveSpeed and MinIO credentials** before production. All
  were pasted into chat sessions during development.

### ElevenLabs, while we are on secrets

```bash
ELEVEN_API_KEY=<secret>      # in .env only
```

**The IP restriction has been removed.** The key is unrestricted now, so a new box
needs no ElevenLabs dashboard change and `ip_not_allowed` should not appear.
Verified with a live TTS call from a fresh box on 2026-07-27. The key may still be
scoped — `/v1/user/subscription` can return a permissions error while `/v1/voices`
and TTS work fine. That error is harmless and not a sign of a bad key.

### WaveSpeed, the other remote

```bash
WAVESPEED_API_KEY=<secret>
WAVESPEED_BRAIN_MODEL=<model id>
```

Stage 0 only. **Check the balance before blaming the code** — an exhausted account
fails at submit with HTTP 200 and `{"code":400,"message":"Insufficient credits"}`,
which reads as success if you only check the status code:

```bash
curl -s -H "Authorization: Bearer $WAVESPEED_API_KEY" \
     https://api.wavespeed.ai/api/v3/balance
```

A vision call is $0.05, so a $0 balance stops every reel at Stage 0.

---

## 11. The voice (fixed 2026-07-27)

`DEFAULT_VOICES` pointed **every** language at Charlie, a deep male voice, and
the model was pinned to `eleven_multilingual_v2`. For a pipeline that mostly
advertises fashion, beauty and apparel that is the wrong read, and it was the
main reason the voiceover sounded bad.

Now: **`eleven_v3`** (current top model, 74 languages) and **female defaults** —
Zara for Hinglish/Hindi/Urdu, Bella for English. `config.elevenVoiceId` still
overrides per request.

Two things that bite:

- **v3 rejects v2's voice settings.** It quantises `stability` to 0.0/0.5/1.0 and
  ignores `style`. `tts()` branches on the model id instead of sending one block
  to both.
- **Both were read at import time**, which happens before `common.load_env()`, so
  `/workspace/.env` was silently ignored. Both are read at call time now. The
  same bug class hit `brain.BRAIN_MODEL` — worth checking before adding a third.

There is no Indian-accent voice in this account's library. Zara's "standard"
accent is the closest available fit for Hinglish.

---

## 12. Running it as a service

```bash
tmux new -d -s reel   'cd /workspace/reelkit && python server.py'   # 0.0.0.0:8189
tmux new -d -s tunnel 'cloudflared tunnel --url http://localhost:8189'
tmux capture-pane -pt tunnel | grep trycloudflare
```

`POST /make-reel` takes the bare request JSON (not wrapped in `{input}`) and
returns the snake_case Result JSON plus **`cost_usd`**. `GET /health` returns
`{"ok": true}`.

### The synchronous contract does NOT survive a Cloudflare quick tunnel

**Measured: `POST /make-reel` through `*.trycloudflare.com` returns `HTTP 524`
after ~125 s.** Cloudflare's edge gives up on an origin that has not responded in
roughly 100 s, and a reel takes 5-8 minutes. The job keeps running on the box and
finishes fine — the *caller* just never gets the response. Raising the client
timeout does not help; the 524 comes from Cloudflare, not from us.

So a quick tunnel is fine for `/health` and for development, and **cannot** carry
a synchronous render. Pick one:

1. **A Vast open port behind the Caddy auth edge** — no proxy timeout, token
   auth, works today. This is the straightforward fix.
2. **Make the endpoint async** — `POST /make-reel` returns a job id immediately,
   the caller polls `GET /result/<id>`. Survives any proxy, but the VPS contract
   changes.
3. A named Cloudflare tunnel does **not** fix this on its own — the edge timeout
   applies there too.

### One more gotcha

`*.trycloudflare.com` publishes both A and AAAA records. A box with no IPv6
egress will have `curl` pick IPv6 and fail with `HTTP 000` / exit 6 — which looks
exactly like a dead tunnel. Test with `curl -4` before concluding anything.

The quick-tunnel URL is also **ephemeral**: it changes every time `cloudflared`
restarts.

---

## 13. What it costs

`make_reel` returns `cost_usd` plus a `_cost` breakdown. `costs.py` meters
WaveSpeed per call, ElevenLabs per character and the GPU per second; rates come
from the environment, never hardcoded.

Measured on a 4x15s collection reel at **$1.847/hr**: **$0.93 for 60 s of
finished video** ($0.23 per 15 s ad) — GPU $0.52, brain $0.20, TTS $0.21.

**37% of the wall clock was a single stuck upload** (387 s for the same ~10.7 MB
that took 11 s on the other three — the §10 stall). Without it: 10.7 min and
**$0.74**. `minio_upload.py` still has no timeout and no retry; adding them is
the cheapest ~20% saving available.

---

## 14. Invented text — four causes, and why the fix is fiddly

A jewellery reel came back with a fake gold "RRBRIAR 107" brand mark on the
necklace and a row of gibberish price tags. The storyboard was clean, so this was
never the brain — it was the guards, ported wholesale from a clothing catalogue.
Four separate causes, found one at a time, each only visible once the previous
was fixed:

1. **Asserting branding that does not exist.** The prompt said "brand name",
   "logo" and "label text" seven times. Protective on a cosmetic tube; on a
   necklace with no text at all it is an instruction to *produce* branding.
2. **A negative that never mentioned text.** Garment-tuned, with "watermark"
   buried at the end of a long comma list where it carries little weight.
3. **The mark was INHERITED.** The source photo had a script-shaped object behind
   the hand, and every guard says "keep it exactly as photographed". This is
   `ERASE_SOURCE_MARK`, and it must be two-sided — erase what is on the PHOTO,
   keep what is on the PRODUCT.
4. **Erasing invites SUBSTITUTION.** With a seller watermark ("Mihnain APPARELS")
   removed, the model painted its own banner ("Premium Quality") in the same
   corner. The clause now says the vacated area must contain only the scene.

Plus `NO_SCENE_TEXT` for the set itself: ask for a "boutique interior" and you get
an invented shop sign on the back wall.

**The lesson worth keeping:** these guards are not product-neutral by default.
Anything phrased as "preserve X" becomes "create X" on a product that has no X.

## 15. Sharpness — measured, and why nothing was done about it

Wan 2.2 I2V renders at **480×832 natively** and the master is 1080×1920, so every
reel is a 2.25× upscale. That is the softness.

`4x-UltraSharp` is installed and was benchmarked at the exact working resolution:
**~1.0 s per frame** (batch 24; 3.0 s at batch 1). A 4-scene reel is 324 frames,
so a full-frame pass adds **~5.4 minutes and roughly TRIPLES** a showcase render,
for ~$0.17 more GPU. It sharpens but cannot restore detail Wan never rendered, so
it is **not wired in**.

The real lever is HunyuanVideo I2V at native 720×1280 — but it is 7.9× slower
(measured 285 s for a 3 s clip, i.e. ~3.9 s of compute per output frame) and its
61.3 GiB peak will not fit a 48 GB card. Wan stays the default.
