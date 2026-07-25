#!/usr/bin/env python
"""
Upload to the bucket-scoped MinIO endpoint behind nginx.

Why this exists instead of the minio SDK or `mc`:
    This endpoint's nginx is BUCKET-SCOPED - it rewrites  /<key>  ->  /<bucket>/<key>,
    so the host root IS the bucket. Every normal S3 client signs the path it
    transmits, so:
        client sends   /<bucket>/<key>   and signs   /<bucket>/<key>
        nginx rewrites to                /<bucket>/<bucket>/<key>
        MinIO verifies against the REWRITTEN path -> SignatureDoesNotMatch
    Neither the minio SDK nor `mc` can express "sign a different path than you
    send", so both fail no matter how correct the credentials are.

    The fix is to sign the POST-rewrite path while transmitting the PRE-rewrite
    one:
        transmit  /<key>
        sign      /<bucket>/<key>
    nginx turns the transmitted path into exactly what we signed, and SigV4
    validates.

Public URLs therefore carry NO bucket segment:
    https://<host>/<key>

Usage:
    python minio_upload.py <file> [<file> ...] --prefix images
    python minio_upload.py out.png --key images/custom-name.png
"""
import argparse
import datetime
import hashlib
import hmac
import mimetypes
import os
import sys
import urllib.error
import urllib.request

REGION = os.environ.get("MINIO_REGION", "us-east-1")
SERVICE = "s3"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _signing_key(secret: str, datestamp: str, region: str, service: str) -> bytes:
    k = _sign(f"AWS4{secret}".encode(), datestamp)
    k = _sign(k, region)
    k = _sign(k, service)
    return _sign(k, "aws4_request")


def put_object(host, bucket, key, path, access_key, secret_key,
               region=REGION, content_type=None):
    """PUT <file> so it lands at https://host/<key> through the nginx rewrite."""
    payload_hash = _sha256_file(path)
    size = os.path.getsize(path)
    content_type = content_type or mimetypes.guess_type(path)[0] or "application/octet-stream"

    now = datetime.datetime.now(datetime.timezone.utc)
    amzdate = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")

    # THE KEY DETAIL: transmit /<key>, but sign /<bucket>/<key>.
    transmit_path = "/" + key.lstrip("/")
    signed_path = "/" + bucket.strip("/") + "/" + key.lstrip("/")

    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amzdate}\n"
    )
    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"

    canonical_request = "\n".join([
        "PUT", signed_path, "", canonical_headers, signed_headers, payload_hash])

    scope = f"{datestamp}/{region}/{SERVICE}/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amzdate, scope, _sha256(canonical_request.encode())])

    signature = hmac.new(
        _signing_key(secret_key, datestamp, region, SERVICE),
        string_to_sign.encode(), hashlib.sha256).hexdigest()

    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}")

    url = f"https://{host}{transmit_path}"
    with open(path, "rb") as fh:
        req = urllib.request.Request(url, data=fh.read(), method="PUT")
        req.add_header("Content-Type", content_type)
        req.add_header("x-amz-content-sha256", payload_hash)
        req.add_header("x-amz-date", amzdate)
        req.add_header("Authorization", authorization)
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                return url, r.status, size
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:800]
            raise SystemExit(f"upload failed HTTP {e.code} for {url}\n{body}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--prefix", default="images",
                    help="key prefix, e.g. 'images' or 'reels'")
    ap.add_argument("--key", help="explicit key (single file only)")
    args = ap.parse_args()

    host = os.environ["MINIO_ENDPOINT"].replace("https://", "").replace("http://", "").rstrip("/")
    bucket = os.environ["MINIO_BUCKET"]
    ak = os.environ["MINIO_ACCESS_KEY"]
    sk = os.environ["MINIO_SECRET_KEY"]

    if args.key and len(args.files) > 1:
        raise SystemExit("--key only works with a single file")

    for f in args.files:
        if not os.path.isfile(f):
            raise SystemExit(f"not a file: {f}")
        key = args.key or f"{args.prefix.strip('/')}/{os.path.basename(f)}"
        url, status, size = put_object(host, bucket, key, f, ak, sk)
        print(f"{url}   (HTTP {status}, {size/1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
