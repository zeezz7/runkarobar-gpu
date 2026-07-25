#!/usr/bin/env python
"""
Structurally validate every API-format workflow against ComfyUI's LIVE node
schema (/object_info). This does NOT execute anything - no render tests.

Checks per workflow:
  1. every class_type exists in this ComfyUI build
  2. every REQUIRED input is present (either a literal or a [node, slot] link)
  3. every literal fed to a COMBO input is a legal enum value
     - model-file combos are checked against the union of (files on disk) and
       (files download_models.sh is going to place there), so a still-downloading
       model is reported as PENDING rather than as an error
  4. every link [node_id, slot] points at a node that exists
  5. no cloud/API billing nodes are present
Exit code is non-zero if any hard error is found.
"""
import json, pathlib, re, sys, urllib.request

HERE = pathlib.Path(__file__).parent
OBJ = json.loads(urllib.request.urlopen(
    "http://127.0.0.1:18188/object_info", timeout=120).read())

# Model files download_models.sh is going to create (name -> folder).
EXPECTED = {}
for m in re.finditer(r'"\$M/([^"]+)"', (HERE.parent / "download_models.sh").read_text()):
    rel = m.group(1)
    EXPECTED.setdefault(rel.split("/")[-1], rel)

MODELS_ROOT = pathlib.Path("/workspace/ComfyUI/models")
ON_DISK = {p.name for p in MODELS_ROOT.rglob("*")
           if p.is_file() and p.suffix in (".safetensors", ".sft", ".gguf", ".pt")}

errors, warnings, pending = [], [], []

for path in sorted(HERE.glob("*.api.json")):
    wf = json.loads(path.read_text())
    tag = path.name
    for nid, node in wf.items():
        cls = node.get("class_type")
        if cls not in OBJ:
            errors.append(f"{tag}: node {nid} unknown class_type {cls!r}")
            continue
        if "Api" in cls or "API" in cls:
            errors.append(f"{tag}: node {nid} is a PAID CLOUD node ({cls})")
        spec = OBJ[cls]["input"]
        req = spec.get("required", {})
        opt = spec.get("optional", {})
        given = node.get("inputs", {})

        DYNAMIC = ("COMFY_AUTOGROW_V3", "COMFY_DYNAMICCOMBO_V3", "COMFY_MATCHTYPE_V3")
        dyn_roots = {k for k, d in req.items()
                     if isinstance(d[0], str) and d[0] in DYNAMIC}
        supplied_roots = {k.split(".")[0] for k in given}
        for k in req:
            if k in dyn_roots and k in supplied_roots:
                continue
            if k not in given:
                errors.append(f"{tag}: {cls}({nid}) missing required input {k!r}")

        for k, v in given.items():
            decl = req.get(k) or opt.get(k)
            if decl is None and k.split(".")[0] in dyn_roots:
                continue  # dynamic sub-input, validated by ComfyUI at runtime
            if decl is None:
                warnings.append(f"{tag}: {cls}({nid}) input {k!r} not in schema")
                continue
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                if v[0] not in wf:
                    errors.append(f"{tag}: {cls}({nid}).{k} links to missing node {v[0]}")
                continue
            allowed = decl[0]
            if isinstance(allowed, list) and allowed and isinstance(v, str):
                if v in allowed:
                    continue
                if v.endswith((".safetensors", ".sft", ".gguf", ".pt")):
                    if v in ON_DISK:
                        errors.append(
                            f"{tag}: {cls}({nid}).{k}={v!r} on disk but not offered "
                            f"by this node - wrong models/ subfolder?")
                    elif v in EXPECTED:
                        pending.append(f"{tag}: {cls}({nid}).{k}={v} -> {EXPECTED[v]} (downloading)")
                    else:
                        errors.append(f"{tag}: {cls}({nid}).{k}={v!r} is NOT in download_models.sh")
                else:
                    errors.append(
                        f"{tag}: {cls}({nid}).{k}={v!r} not a legal value "
                        f"(allowed: {allowed[:8]}{'...' if len(allowed) > 8 else ''})")

print(f"workflows checked: {len(list(HERE.glob('*.api.json')))}")
print(f"models on disk   : {len(ON_DISK)}")
print()
for p in sorted(set(pending)):
    print("PENDING ", p)
print()
for w in sorted(set(warnings)):
    print("WARN    ", w)
for e in sorted(set(errors)):
    print("ERROR   ", e)
print()
print(f"{len(set(errors))} error(s), {len(set(warnings))} warning(s), "
      f"{len(set(pending))} pending download(s)")
sys.exit(1 if errors else 0)
