#!/usr/bin/env python
"""
Measure Wan 2.2 S2V-14B: real local lip-sync, timed.

Builds the API graph directly. ComfyUI's /workflow/convert rejects the shipped
GUI template because it carries two variants in one file, and the graph is small
enough that hand-wiring it is clearer than fighting that.

Reuses what is already installed: umt5_xxl text encoder and wan_2.1_vae are the
SAME files the I2V path uses, so S2V only added the 16.4 GB transformer and a
0.63 GB wav2vec2 audio encoder.

  /venv/main/bin/python measure_s2v.py <image> <audio.mp3> [steps]
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time

sys.path.insert(0, "/workspace/reelkit")
import common                                              # noqa: E402

FPS = 16


def gpu_mib():
    p = subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                        "--format=csv,noheader,nounits"],
                       capture_output=True, text=True)
    try:
        return int(p.stdout.strip().splitlines()[0])
    except Exception:
        return -1


class Peak(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.peak, self._done = 0, threading.Event()

    def run(self):
        while not self._done.is_set():
            self.peak = max(self.peak, gpu_mib())
            self._done.wait(0.25)

    def stop(self):
        self._done.set(); self.join(timeout=5); return self.peak


def build(image_name, audio_name, seconds, steps, w=480, h=832):
    # 4n+1, same quantisation rule as every other Wan graph.
    length = max(int(round(seconds * FPS / 4)) * 4 + 1, 25)
    g = {
      "1":  {"class_type": "UNETLoader",
             "inputs": {"unet_name": "wan2.2_s2v_14B_fp8_scaled.safetensors",
                        "weight_dtype": "default"}},
      "2":  {"class_type": "CLIPLoader",
             "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                        "type": "wan", "device": "default"}},
      "3":  {"class_type": "VAELoader",
             "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
      "4":  {"class_type": "AudioEncoderLoader",
             "inputs": {"audio_encoder_name":
                        "wav2vec2_large_english_fp16.safetensors"}},
      "5":  {"class_type": "LoadAudio", "inputs": {"audio": audio_name}},
      "6":  {"class_type": "LoadImage", "inputs": {"image": image_name}},
      "7":  {"class_type": "AudioEncoderEncode",
             "inputs": {"audio_encoder": ["4", 0], "audio": ["5", 0]}},
      "8":  {"class_type": "CLIPTextEncode",
             "inputs": {"clip": ["2", 0],
                        "text": "a woman speaking to camera, natural expression "
                                "and gestures, sharp detail, cinematic"}},
      "9":  {"class_type": "CLIPTextEncode",
             "inputs": {"clip": ["2", 0],
                        "text": "blurry, distorted face, extra limbs, low quality, "
                                "watermark"}},
      "10": {"class_type": "ModelSamplingSD3",
             "inputs": {"model": ["1", 0], "shift": 8.0}},
      # Emits its OWN positive/negative (audio conditioning is folded in here),
      # so the sampler must take these, not nodes 8/9 directly.
      "11": {"class_type": "WanSoundImageToVideo",
             "inputs": {"positive": ["8", 0], "negative": ["9", 0],
                        "vae": ["3", 0], "width": w, "height": h,
                        "length": length, "batch_size": 1,
                        "audio_encoder_output": ["7", 0], "ref_image": ["6", 0]}},
      "12": {"class_type": "KSampler",
             "inputs": {"model": ["10", 0], "positive": ["11", 0],
                        "negative": ["11", 1], "latent_image": ["11", 2],
                        "seed": 7, "steps": steps, "cfg": 6.0,
                        "sampler_name": "uni_pc", "scheduler": "simple",
                        "denoise": 1.0}},
      "13": {"class_type": "VAEDecode",
             "inputs": {"samples": ["12", 0], "vae": ["3", 0]}},
      "14": {"class_type": "CreateVideo",
             "inputs": {"images": ["13", 0], "fps": FPS, "audio": ["5", 0]}},
      "15": {"class_type": "SaveVideo",
             "inputs": {"video": ["14", 0], "filename_prefix": "video/s2v_measure",
                        "format": "auto", "codec": "auto"}},
    }
    return g, length


def main():
    common.load_env()
    img = sys.argv[1]
    aud = sys.argv[2]
    steps = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    W = int(sys.argv[4]) if len(sys.argv) > 4 else 480
    H = int(sys.argv[5]) if len(sys.argv) > 5 else 832

    secs = common.probe_duration(aud)
    print(f"audio: {os.path.basename(aud)}  {secs:.2f}s")

    iname, aname = "s2v_ref.png", "s2v_vo.mp3"
    shutil.copyfile(img, os.path.join(common.COMFY_INPUT, iname))
    shutil.copyfile(aud, os.path.join(common.COMFY_INPUT, aname))

    g, length = build(iname, aname, secs, steps, W, H)
    print(f"graph: {length} frames @ {FPS}fps = {length/FPS:.2f}s, {steps} steps, {W}x{H}")

    # free VRAM so the peak is this model's own
    try:
        import urllib.request
        urllib.request.urlopen(urllib.request.Request(
            f"{common.COMFY}/free", method="POST",
            data=json.dumps({"unload_models": True, "free_memory": True}).encode(),
            headers={"Content-Type": "application/json"}), timeout=60).read()
    except Exception:
        pass
    time.sleep(4)
    print(f"baseline VRAM: {gpu_mib()} MiB")

    p = Peak(); p.start(); t0 = time.time()
    try:
        outs = common.comfy_run(g, timeout=3600)
    except Exception as e:
        print(f"FAILED after {time.time()-t0:.1f}s: {str(e)[:600]}")
        p.stop(); return 1
    el = time.time() - t0
    peak = p.stop()

    print(f"\n=== RESULT ===")
    print(f"  output      : {outs[0] if outs else '(none)'}")
    print(f"  wall clock  : {el:.1f}s")
    print(f"  peak VRAM   : {peak/1024:.1f} GiB ({peak} MiB)")
    print(f"  per second  : {el/max(length/FPS,0.01):.1f}s of compute per 1s of video")
    if outs:
        pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "stream=codec_type,width,height,nb_frames,duration",
                             "-of", "csv=p=0", outs[0]],
                            capture_output=True, text=True)
        print(f"  probe       : {pr.stdout.strip().replace(chr(10),' | ')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
