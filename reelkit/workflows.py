"""API-format ComfyUI graph builders for the reel pipeline.

Every graph here is derived from a workflow that was executed and verified on
this box (see MODELS.md). Model filenames and sampler settings match those.
"""
from __future__ import annotations

# --- model files (see MODELS.md) --------------------------------------------
FLUX_UNET = "flux1-dev-fp8-e4m3fn.safetensors"
FLUX_CLIP_L = "clip_l.safetensors"
T5_XXL = "t5xxl_fp8_e4m3fn_scaled.safetensors"      # shared LTX <-> FLUX
FLUX_VAE = "ae.safetensors"

LTX_CKPT = "ltxv-13b-0.9.8-dev-fp8.safetensors"      # VAE bundled inside

WAN_HIGH = "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"
WAN_LOW = "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"
WAN_CLIP = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"  # UMT5, NOT the T5 above
WAN_VAE = "wan_2.1_vae.safetensors"

NEG_GENERIC = ("low quality, worst quality, blurry, deformed, distorted, watermark, "
               "text overlay, jpeg artifacts, oversaturated, motion smear")


def flux_product_hero(image_name: str, prompt: str, *, width: int, height: int,
                      seed: int, denoise: float = 0.40, steps: int = 20,
                      guidance: float = 2.5, prefix: str = "reel/hero") -> dict:
    """FLUX img2img: relight/clean a product photo while preserving the product.

    denoise is deliberately low (~0.4). FLUX at high denoise will happily
    redraw a label or invent branding; keeping it low re-lights and cleans the
    shot while leaving the product's text and packaging intact.
    """
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": FLUX_UNET, "weight_dtype": "fp8_e4m3fn"}},
        "2": {"class_type": "DualCLIPLoader",
              "inputs": {"clip_name1": FLUX_CLIP_L, "clip_name2": T5_XXL,
                         "type": "flux", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": FLUX_VAE}},
        "4": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "5": {"class_type": "ImageScale",
              "inputs": {"image": ["4", 0], "upscale_method": "lanczos",
                         "width": width, "height": height, "crop": "center"}},
        "6": {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["3", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "8": {"class_type": "FluxGuidance",
              "inputs": {"conditioning": ["7", 0], "guidance": guidance}},
        "9": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["7", 0]}},
        "10": {"class_type": "KSampler",
               "inputs": {"model": ["1", 0], "positive": ["8", 0], "negative": ["9", 0],
                          "latent_image": ["6", 0], "seed": seed, "steps": steps,
                          "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
                          "denoise": denoise}},
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["3", 0]}},
        "12": {"class_type": "SaveImage",
               "inputs": {"images": ["11", 0], "filename_prefix": prefix}},
    }


def ltx_image_to_video(image_name: str, prompt: str, *, width: int, height: int,
                       length: int, seed: int, fps: float = 24.0, steps: int = 30,
                       cfg: float = 3.0, prefix: str = "reel/scene") -> dict:
    """LTXV 13B 0.9.8 fp8 image->video. length must satisfy (length-1) % 8 == 0."""
    if (length - 1) % 8:
        raise ValueError(f"LTX length must satisfy (n-1)%8==0, got {length}")
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": LTX_CKPT}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": T5_XXL, "type": "ltxv", "device": "default"}},
        "3": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "4": {"class_type": "ImageScale",
              "inputs": {"image": ["3", 0], "upscale_method": "lanczos",
                         "width": width, "height": height, "crop": "center"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": NEG_GENERIC}},
        "7": {"class_type": "LTXVImgToVideo",
              "inputs": {"positive": ["5", 0], "negative": ["6", 0], "vae": ["1", 2],
                         "image": ["4", 0], "width": width, "height": height,
                         "length": length, "batch_size": 1, "strength": 1.0}},
        "8": {"class_type": "LTXVConditioning",
              "inputs": {"positive": ["7", 0], "negative": ["7", 1], "frame_rate": 25.0}},
        "9": {"class_type": "LTXVScheduler",
              "inputs": {"steps": steps, "max_shift": 2.05, "base_shift": 0.95,
                         "stretch": True, "terminal": 0.1, "latent": ["7", 2]}},
        "10": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "11": {"class_type": "SamplerCustom",
               "inputs": {"model": ["1", 0], "add_noise": True, "noise_seed": seed,
                          "cfg": cfg, "positive": ["8", 0], "negative": ["8", 1],
                          "sampler": ["10", 0], "sigmas": ["9", 0],
                          "latent_image": ["7", 2]}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["1", 2]}},
        "13": {"class_type": "CreateVideo", "inputs": {"images": ["12", 0], "fps": fps}},
        "14": {"class_type": "SaveVideo",
               "inputs": {"video": ["13", 0], "filename_prefix": prefix,
                          "format": "mp4", "codec": "h264"}},
    }


def wan_image_to_video(image_name: str, prompt: str, *, width: int, height: int,
                       length: int, seed: int, fps: float = 16.0, steps: int = 20,
                       cfg: float = 3.5, split_at: int = 10,
                       prefix: str = "reel/hero_clip") -> dict:
    """Wan 2.2 I2V 14B fp8, two-expert sampling.

    High-noise expert runs steps 0..split_at and hands its leftover-noise latent
    to the low-noise expert for split_at..end. Both files are required.

    NOTE: measured peak 32.1 GB of 32.6 GB VRAM at 720x480/81f on this box.
    Raising width/height/length from the defaults will likely OOM.
    """
    if (length - 1) % 4:
        raise ValueError(f"Wan length must satisfy (n-1)%4==0, got {length}")
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": WAN_HIGH, "weight_dtype": "default"}},
        "2": {"class_type": "UNETLoader",
              "inputs": {"unet_name": WAN_LOW, "weight_dtype": "default"}},
        "3": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": WAN_CLIP, "type": "wan", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": WAN_VAE}},
        "5": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "6": {"class_type": "ImageScale",
              "inputs": {"image": ["5", 0], "upscale_method": "lanczos",
                         "width": width, "height": height, "crop": "center"}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": prompt}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": NEG_GENERIC}},
        "9": {"class_type": "WanImageToVideo",
              "inputs": {"positive": ["7", 0], "negative": ["8", 0], "vae": ["4", 0],
                         "start_image": ["6", 0], "width": width, "height": height,
                         "length": length, "batch_size": 1}},
        "10": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 5.0}},
        "11": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["2", 0], "shift": 5.0}},
        "12": {"class_type": "KSamplerAdvanced",
               "inputs": {"model": ["10", 0], "add_noise": "enable", "noise_seed": seed,
                          "steps": steps, "cfg": cfg, "sampler_name": "euler",
                          "scheduler": "simple", "positive": ["9", 0], "negative": ["9", 1],
                          "latent_image": ["9", 2], "start_at_step": 0,
                          "end_at_step": split_at, "return_with_leftover_noise": "enable"}},
        "13": {"class_type": "KSamplerAdvanced",
               "inputs": {"model": ["11", 0], "add_noise": "disable", "noise_seed": 0,
                          "steps": steps, "cfg": cfg, "sampler_name": "euler",
                          "scheduler": "simple", "positive": ["9", 0], "negative": ["9", 1],
                          "latent_image": ["12", 0], "start_at_step": split_at,
                          "end_at_step": 10000, "return_with_leftover_noise": "disable"}},
        "14": {"class_type": "VAEDecode", "inputs": {"samples": ["13", 0], "vae": ["4", 0]}},
        "15": {"class_type": "CreateVideo", "inputs": {"images": ["14", 0], "fps": fps}},
        "16": {"class_type": "SaveVideo",
               "inputs": {"video": ["15", 0], "filename_prefix": prefix,
                          "format": "mp4", "codec": "h264"}},
    }
