# =============================================================================
#  reelkit - RunPod serverless worker
# =============================================================================
#  NO WEIGHTS ARE BAKED IN. ~150 GB of models live on a RunPod Network Volume
#  mounted at /runpod-volume, populated once by volume_setup.sh. That is what
#  keeps this image small enough to pull on a cold start.
#
#  Pinned deliberately, both of them:
#    torch 2.10.0+cu130   - matches the box this pipeline was built and measured
#                           on. The GPU is Blackwell (cc 12.0), which needs a
#                           CUDA >= 12.8 build; a cu124 wheel installs fine and
#                           then dies at the first GPU op with "no kernel image
#                           is available".
#    ComfyUI 0.28.0       - EXACT. A different version renames nodes and the
#                           saved workflows in workflows/*.api.json stop
#                           resolving. Pinned by commit, not by tag, because a
#                           tag can be moved.
#
#  No custom nodes are installed, and none are needed: all 39 node classes the
#  workflows use are core ComfyUI 0.28.0 (verified against /object_info).
#
#  No Wan 2.2 S2V, no talking-avatar, no lip-sync anywhere.
# =============================================================================
FROM pytorch/pytorch:2.10.0-cuda13.0-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1

# ffmpeg is not optional - assemble.py is ffmpeg from end to end.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ffmpeg libgl1 libglib2.0-0 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# --- ComfyUI, pinned ---------------------------------------------------------
ARG COMFYUI_COMMIT=700821e1364eaab0e8f21c538a2131719fec57bf
RUN git clone --filter=blob:none https://github.com/comfyanonymous/ComfyUI.git /opt/ComfyUI \
    && cd /opt/ComfyUI \
    && git checkout ${COMFYUI_COMMIT} \
    && python -c "import re;v=open('comfyui_version.py').read();assert '0.28.0' in v, v" \
    && pip install -r requirements.txt

# --- reelkit dependencies ----------------------------------------------------
#  runpod            the serverless SDK
#  compressed-tensors / accelerate  transformers needs both for the VL guard
#  Like the COPY list above, this is an EXPLICIT list - reelkit/requirements.txt
#  is NOT installed here. A dep added only there ships a build whose import
#  fails at call time (anthropic taught us: "No module named 'anthropic'",
#  silently falling back to wavespeed).
RUN pip install \
        runpod \
        anthropic \
        compressed-tensors \
        accelerate \
        fastapi \
        "uvicorn[standard]" \
        minio \
        pillow \
        numpy \
        scipy \
        transformers

# --- point ComfyUI at the Network Volume ------------------------------------
#  extra_model_paths.yaml rather than symlinks: it survives the volume being
#  absent (ComfyUI still boots, just finds no models) which makes a
#  misconfigured endpoint diagnosable instead of a crash loop. base_path must
#  match the layout volume_setup.sh creates, exactly.
RUN printf '%s\n' \
    'reelkit:' \
    '    base_path: /runpod-volume/ComfyUI/' \
    '    checkpoints: models/checkpoints' \
    '    diffusion_models: models/diffusion_models' \
    '    text_encoders: models/text_encoders' \
    '    clip_vision: models/clip_vision' \
    '    vae: models/vae' \
    '    loras: models/loras' \
    '    upscale_models: models/upscale_models' \
    '    background_removal: models/background_removal' \
    > /opt/ComfyUI/extra_model_paths.yaml

# --- reelkit source ----------------------------------------------------------
#  Explicit file list, not COPY . . - that would drag in runs/, work/, any
#  stray .env and every rendered mp4.
WORKDIR /opt/reelkit
#  NOTE: sources are repo-root-relative (prefixed reelkit/) because RunPod's
#  GitHub build uses the REPOSITORY ROOT as the build context, not this folder.
#  EVERY new .py module MUST be added here or the build succeeds and the worker
#  crash-loops at boot with ModuleNotFoundError (llm.py taught us: 2026-08-01,
#  all workers unhealthy).
COPY reelkit/handler.py reelkit/make_reel.py reelkit/make_photos.py \
     reelkit/brain.py reelkit/llm.py reelkit/compose.py \
     reelkit/animate.py reelkit/voiceover.py reelkit/assemble.py reelkit/sfx.py \
     reelkit/minio_upload.py reelkit/validate_image.py reelkit/common.py \
     reelkit/costs.py reelkit/wavespeed.py reelkit/ws_image.py \
     reelkit/guards.py reelkit/avatar.py \
     reelkit/tracer.py reelkit/trace_run.py ./
COPY reelkit/workflows/ ./workflows/

# --- runtime wiring ----------------------------------------------------------
#  COMFY_URL: common.py defaults to :18188 (this box's supervisor port); the
#  container runs ComfyUI on the conventional :8188.
#  QWEN_VL_DIR: the OCR guard is a transformers checkpoint, so it sits OUTSIDE
#  the ComfyUI tree and is not covered by extra_model_paths.yaml.
#  COMFY_INPUT/COMFY_OUTPUT: ComfyUI here runs from /opt/ComfyUI, so its input/
#  output dirs are /opt/ComfyUI/{input,output}. common.py stages product images
#  into COMFY_INPUT and reads results from COMFY_OUTPUT; these MUST match the
#  running ComfyUI or LoadImage fails with "Invalid image file" (HTTP 400). The
#  common.py default (/workspace/ComfyUI) is the old box layout, hence override.
ENV COMFY_URL=http://127.0.0.1:8188 \
    COMFY_INPUT=/opt/ComfyUI/input \
    COMFY_OUTPUT=/opt/ComfyUI/output \
    QWEN_VL_DIR=/runpod-volume/models/qwen2.5-vl/Qwen2.5-VL-7B-Instruct \
    REELKIT_VIDEO_MODEL=wan \
    PYTHONPATH=/opt/reelkit

#  SECRETS ARE NOT BAKED IN. WAVESPEED_API_KEY, ELEVEN_API_KEY and MINIO_* come
#  from the RunPod endpoint's environment at runtime.

# --- entrypoint --------------------------------------------------------------
#  ComfyUI must be UP before the first job, or that job fails on a connection
#  refused. The script starts it in the background, blocks on /system_stats,
#  then execs the handler.
COPY reelkit/start.sh /opt/start.sh
RUN chmod +x /opt/start.sh
ENTRYPOINT ["/opt/start.sh"]
