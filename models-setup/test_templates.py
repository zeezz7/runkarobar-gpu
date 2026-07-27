#!/usr/bin/env python
"""
Render ONE reel per template on the SAME product, through POST /make-reel.

Goes to localhost:8189 rather than the Cloudflare tunnel on purpose: the quick
tunnel 524s at ~100s (documented in FLOW.md §12) and a reel takes minutes. The
request/response contract is identical either way - this exercises the same
endpoint, just without an edge proxy that cannot wait.

  /venv/main/bin/python test_templates.py                 # all six
  /venv/main/bin/python test_templates.py ad testimonial  # named only
"""
import json
import sys
import time
import urllib.request

API = "http://127.0.0.1:8189"
# Apparel: the only product that exercises every template honestly (outfit-check
# and the ad/testimonial presenters all need something wearable).
PRODUCT = ("https://staging-storage.runkarobar.com/videos/uploads/"
           "1785150296652-826672de130d6770-WhatsApp_Image_2026-07-27_at_4.32.11_PM.jpg")

# Length left unset so each template's own default applies (showcase 15,
# ad 20, outfit-check 30, ...) - that is part of what is being tested.
TEMPLATES = ["showcase", "outfit-check", "ad", "ai-director",
             "unboxing", "testimonial"]

# The response keys the VPS depends on. Asserted per render.
CONTRACT = ["reel_1080p_url", "reel_720p_url", "scene_image_urls",
            "storyboard", "durationSec"]


def post(path, payload, timeout=3600):
    req = urllib.request.Request(
        API + path, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main():
    want = sys.argv[1:] or TEMPLATES
    results = []
    for tpl in want:
        print(f"\n{'='*74}\n== template: {tpl}\n{'='*74}", flush=True)
        t0 = time.time()
        rec = {"template": tpl}
        try:
            res = post("/make-reel", {
                "product_images": [PRODUCT],
                "brief": ("Premium reel for this embroidered lawn suit - "
                          "aspirational, scroll-stopping, warm female Hinglish "
                          "voiceover."),
                "config": {"resolution": "1080p", "aspectRatio": "9:16",
                           "language": "hinglish", "brandName": "The Collection",
                           "captions": False, "template": tpl},
            })
            sb = res.get("storyboard") or {}
            rec.update({
                "ok": True,
                "reel_url": res.get("reel_1080p_url"),
                "durationSec": res.get("durationSec"),
                "cost_usd": res.get("cost_usd"),
                "missing_contract_keys": [k for k in CONTRACT if k not in res],
                "concept": sb.get("concept"),
                "methods": [s.get("method") for s in sb.get("scenes", [])],
                "modes": [s.get("mode") for s in sb.get("scenes", [])],
                "badges": [b.get("text") for b in (sb.get("badges") or [])],
                "vo": [s.get("vo") for s in sb.get("scenes", [])],
                "avatar_scenes": (res.get("_cost") or {}).get("avatar_scenes", 0),
                "stills": len(res.get("scene_image_urls") or []),
            })
        except Exception as e:
            rec.update({"ok": False, "error": f"{type(e).__name__}: {str(e)[:400]}"})
        rec["seconds"] = round(time.time() - t0, 1)
        print(json.dumps(rec, indent=2, ensure_ascii=False), flush=True)
        results.append(rec)
        json.dump(results,
                  open("/workspace/models-setup/logs/test_templates.json", "w"),
                  indent=2, ensure_ascii=False)

    print(f"\n{'='*74}\nSUMMARY")
    print(f"{'TEMPLATE':<14}{'OK':<4}{'DUR':>6}{'SECS':>8}  {'METHODS':<38}BADGES")
    for r in results:
        print(f"{r['template']:<14}{'y' if r.get('ok') else 'N':<4}"
              f"{str(r.get('durationSec','-')):>6}{r['seconds']:>8}  "
              f"{','.join(r.get('methods') or [])[:36]:<38}"
              f"{','.join(r.get('badges') or []) or '-'}")
    return 0 if all(r.get("ok") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
