"""MinIO upload.

Config comes from the environment only — no secrets in this file:

    MINIO_ENDPOINT    host only, no scheme (the SDK wants it that way)
    MINIO_ACCESS_KEY
    MINIO_SECRET_KEY
    MINIO_BUCKET
    MINIO_SECURE      optional, default "true"
    MINIO_REGION      optional, default "us-east-1"

Two endpoint layouts are supported, detected at runtime:

* **standard**  — `https://host/<bucket>/<key>`. Uses the `minio` SDK.
* **bucket-scoped proxy** — a reverse proxy rewrites `/<key>` to
  `/<bucket>/<key>`, so the host root *is* the bucket. The SDK cannot be used
  here: it sends `/<bucket>/<key>`, the proxy rewrites that to
  `/<bucket>/<bucket>/<key>`, and because SigV4 signs the *pre-rewrite* path the
  request fails with `SignatureDoesNotMatch` regardless of whether the
  credentials are correct. For this layout we sign the post-rewrite path and PUT
  to the pre-rewrite one.

`staging-storage.runkarobar.com` is the bucket-scoped kind.
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import requests


class StorageError(RuntimeError):
    pass


@dataclass
class Config:
    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    secure: bool = True
    region: str = "us-east-1"

    @property
    def base(self) -> str:
        return f"{'https' if self.secure else 'http'}://{self.endpoint}"

    @classmethod
    def from_env(cls) -> "Config":
        missing = [k for k in ("MINIO_ENDPOINT", "MINIO_ACCESS_KEY",
                               "MINIO_SECRET_KEY", "MINIO_BUCKET")
                   if not os.environ.get(k)]
        if missing:
            raise StorageError("missing env vars: " + ", ".join(missing))
        ep = os.environ["MINIO_ENDPOINT"].strip()
        ep = re.sub(r"^https?://", "", ep).rstrip("/")   # SDK wants host only
        return cls(endpoint=ep,
                   access_key=os.environ["MINIO_ACCESS_KEY"],
                   secret_key=os.environ["MINIO_SECRET_KEY"],
                   bucket=os.environ["MINIO_BUCKET"],
                   secure=os.environ.get("MINIO_SECURE", "true").lower() != "false",
                   region=os.environ.get("MINIO_REGION", "us-east-1"))


def detect_layout(cfg: Config, timeout: int = 20) -> str:
    """Return "bucket_scoped" or "standard" by reading the server's Resource echo."""
    probe = f"__layout_probe_{uuid.uuid4().hex[:8]}"
    try:
        r = requests.get(f"{cfg.base}/{probe}", timeout=timeout)
        m = re.search(r"<Resource>([^<]*)</Resource>", r.text or "")
    except requests.RequestException as e:
        raise StorageError(f"cannot reach {cfg.base}: {e}") from e
    if m:
        resource = m.group(1)
        if resource == f"/{cfg.bucket}/{probe}":
            return "bucket_scoped"
        if resource == f"/{probe}":
            return "standard"
    return "standard"


# --------------------------------------------------------------------------- #
# SigV4 for the bucket-scoped proxy case
# --------------------------------------------------------------------------- #
def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _put_signed(cfg: Config, key: str, body: bytes, content_type: str) -> None:
    """PUT to /<key> but sign /<bucket>/<key>, matching what the proxy forwards."""
    t = datetime.datetime.now(datetime.timezone.utc)
    amzdate = t.strftime("%Y%m%dT%H%M%SZ")
    datestamp = t.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()

    signed_path = f"/{cfg.bucket}/{key}"
    canon_headers = (f"content-type:{content_type}\nhost:{cfg.endpoint}\n"
                     f"x-amz-content-sha256:{payload_hash}\nx-amz-date:{amzdate}\n")
    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
    canon_req = (f"PUT\n{signed_path}\n\n{canon_headers}\n{signed_headers}\n{payload_hash}")

    scope = f"{datestamp}/{cfg.region}/s3/aws4_request"
    sts = ("AWS4-HMAC-SHA256\n" + amzdate + "\n" + scope + "\n" +
           hashlib.sha256(canon_req.encode()).hexdigest())
    k = _sign(("AWS4" + cfg.secret_key).encode(), datestamp)
    k = _sign(k, cfg.region)
    k = _sign(k, "s3")
    k = _sign(k, "aws4_request")
    sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()

    headers = {
        "Authorization": (f"AWS4-HMAC-SHA256 Credential={cfg.access_key}/{scope}, "
                          f"SignedHeaders={signed_headers}, Signature={sig}"),
        "x-amz-date": amzdate,
        "x-amz-content-sha256": payload_hash,
        "Content-Type": content_type,
    }
    r = requests.put(f"{cfg.base}/{key}", data=body, headers=headers, timeout=600)
    if r.status_code not in (200, 201):
        raise StorageError(f"upload failed HTTP {r.status_code}: {r.text[:400]}")


def upload(path: Path, key: str, cfg: Config | None = None,
           content_type: str = "video/mp4") -> str:
    """Upload `path` to `key` in the bucket. Returns the public URL."""
    cfg = cfg or Config.from_env()
    path = Path(path)
    if not path.is_file():
        raise StorageError(f"file to upload not found: {path}")

    layout = detect_layout(cfg)

    if layout == "standard":
        try:
            from minio import Minio
        except ImportError as e:
            raise StorageError("minio SDK not installed (pip install minio)") from e
        client = Minio(cfg.endpoint, access_key=cfg.access_key,
                       secret_key=cfg.secret_key, secure=cfg.secure, region=cfg.region)
        if not client.bucket_exists(cfg.bucket):
            raise StorageError(f"bucket does not exist: {cfg.bucket}")
        client.fput_object(cfg.bucket, key, str(path), content_type=content_type)
        return f"{cfg.base}/{cfg.bucket}/{key}"

    _put_signed(cfg, key, path.read_bytes(), content_type)
    return f"{cfg.base}/{key}"


def verify_public(url: str, timeout: int = 30) -> tuple[bool, int, int]:
    """HEAD the URL anonymously. Returns (ok, status_code, content_length)."""
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        return r.status_code == 200, r.status_code, int(r.headers.get("Content-Length") or 0)
    except requests.RequestException:
        return False, 0, 0
