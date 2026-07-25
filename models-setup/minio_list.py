#!/usr/bin/env python
"""
List (and optionally download) objects from the bucket-scoped MinIO endpoint
behind nginx. Companion to minio_upload.py.

Why this exists instead of the minio SDK or `mc`:
    Same reason as minio_upload.py - this endpoint's nginx is BUCKET-SCOPED and
    rewrites  /<key>  ->  /<bucket>/<key>,  so the host root IS the bucket.
    Every normal S3 client signs the path it transmits, so the rewrite always
    invalidates the signature. The fix is to sign the POST-rewrite path while
    transmitting the PRE-rewrite one:
        transmit  /<key>          sign  /<bucket>/<key>

THE TRAILING-SLASH DETAIL (specific to listing, and the whole reason this file
exists separately from minio_upload.py):
    A ListObjectsV2 is a GET on the *bucket root*, i.e. the transmitted path is
    bare "/" with the query "?list-type=2". Applying the upload rule literally
    ("/" + bucket + "/" + key, with an empty key) gives "/runkarobar" - and that
    fails with 403 SignatureDoesNotMatch.

    nginx's rewrite does NOT strip the slash: it turns the transmitted "/" into
    "/runkarobar/" - WITH a trailing slash. MinIO helpfully echoes the path it
    actually verified in the error body:
        <Resource>/runkarobar/</Resource>
    So the canonical URI that must be signed for a bucket-level GET is
        /<bucket>/          <- trailing slash REQUIRED
    Confirmed empirically: signing "/runkarobar/" -> HTTP 200, while signing
    "/runkarobar" or "/" -> HTTP 403 SignatureDoesNotMatch.

    Object-level GETs keep the upload rule (no trailing slash):
        transmit /<key>   sign /<bucket>/<key>
    ...though object GETs are public on this endpoint and need no signature at
    all - https://<host>/<key> just works, which is what --download uses.

Usage:
    python minio_list.py                        # every key in the bucket
    python minio_list.py --prefix videos/ref/   # only that prefix
    python minio_list.py --prefix videos/ref/ --long          # + size / mtime
    python minio_list.py --prefix videos/ref/ --download ./out  # fetch them too

Env (same vars as minio_upload.py):
    MINIO_ENDPOINT MINIO_BUCKET MINIO_ACCESS_KEY MINIO_SECRET_KEY [MINIO_REGION]
"""
import argparse
import datetime
import hashlib
import hmac
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

REGION = os.environ.get("MINIO_REGION", "us-east-1")
SERVICE = "s3"
S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _signing_key(secret: str, datestamp: str, region: str, service: str) -> bytes:
    k = _sign(f"AWS4{secret}".encode(), datestamp)
    k = _sign(k, region)
    k = _sign(k, service)
    return _sign(k, "aws4_request")


def _canonical_query(params: dict) -> str:
    """SigV4 canonical query string: sorted, RFC3986-encoded, k=v joined by &."""
    return "&".join(
        f"{urllib.parse.quote(str(k), safe='-_.~')}={urllib.parse.quote(str(v), safe='-_.~')}"
        for k, v in sorted(params.items()))


def _signed_get(host, signed_path, params, access_key, secret_key, region=REGION):
    """GET https://host/?<params>, signing `signed_path` instead of what we send."""
    now = datetime.datetime.now(datetime.timezone.utc)
    amzdate = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    canonical_query = _canonical_query(params)

    canonical_headers = (
        f"host:{host}\n"
        f"x-amz-content-sha256:{EMPTY_SHA256}\n"
        f"x-amz-date:{amzdate}\n"
    )
    signed_headers = "host;x-amz-content-sha256;x-amz-date"

    canonical_request = "\n".join([
        "GET", signed_path, canonical_query,
        canonical_headers, signed_headers, EMPTY_SHA256])

    scope = f"{datestamp}/{region}/{SERVICE}/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amzdate, scope, _sha256(canonical_request.encode())])

    signature = hmac.new(
        _signing_key(secret_key, datestamp, region, SERVICE),
        string_to_sign.encode(), hashlib.sha256).hexdigest()

    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}")

    # Transmit the PRE-rewrite path (bare "/"), not the signed one.
    url = f"https://{host}/?{canonical_query}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("x-amz-content-sha256", EMPTY_SHA256)
    req.add_header("x-amz-date", amzdate)
    req.add_header("Authorization", authorization)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:800]
        raise SystemExit(f"list failed HTTP {e.code} for {url}\n{body}")


def list_objects(host, bucket, access_key, secret_key, prefix="",
                 region=REGION, max_keys=1000):
    """ListObjectsV2 over the whole bucket (follows continuation tokens)."""
    # See module docstring: bucket-level GET signs /<bucket>/ WITH trailing slash.
    signed_path = "/" + bucket.strip("/") + "/"
    token = None
    out = []
    while True:
        params = {"list-type": "2", "max-keys": str(max_keys)}
        if prefix:
            params["prefix"] = prefix
        if token:
            params["continuation-token"] = token
        xml = _signed_get(host, signed_path, params, access_key, secret_key, region)
        root = ET.fromstring(xml)
        for c in root.findall(f"{S3_NS}Contents"):
            out.append({
                "key": c.findtext(f"{S3_NS}Key"),
                "size": int(c.findtext(f"{S3_NS}Size") or 0),
                "last_modified": c.findtext(f"{S3_NS}LastModified"),
                "etag": (c.findtext(f"{S3_NS}ETag") or "").strip('"'),
            })
        if (root.findtext(f"{S3_NS}IsTruncated") or "false").lower() != "true":
            break
        token = root.findtext(f"{S3_NS}NextContinuationToken")
        if not token:
            break
    return out


def download(host, key, dest_dir):
    """Object GETs are public here - no signature, no bucket segment in the URL."""
    url = f"https://{host}/{key.lstrip('/')}"
    dest = os.path.join(dest_dir, key.replace("/", "_"))
    os.makedirs(dest_dir, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=300) as r, open(dest, "wb") as fh:
            fh.write(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"download failed HTTP {e.code} for {url}")
    return dest, os.path.getsize(dest)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--prefix", default="", help="key prefix, e.g. 'videos/ref/'")
    ap.add_argument("--long", action="store_true", help="show size and last-modified")
    ap.add_argument("--download", metavar="DIR",
                    help="also download every listed key into DIR")
    args = ap.parse_args()

    host = os.environ["MINIO_ENDPOINT"].replace("https://", "").replace("http://", "").rstrip("/")
    bucket = os.environ["MINIO_BUCKET"]
    ak = os.environ["MINIO_ACCESS_KEY"]
    sk = os.environ["MINIO_SECRET_KEY"]

    objs = list_objects(host, bucket, ak, sk, prefix=args.prefix)
    for o in objs:
        if args.long:
            print(f"{o['size']:>12}  {o['last_modified']}  {o['key']}")
        else:
            print(o["key"])
    print(f"# {len(objs)} object(s)"
          + (f" under prefix '{args.prefix}'" if args.prefix else " in bucket"),
          file=sys.stderr)

    if args.download:
        for o in objs:
            dest, size = download(host, o["key"], args.download)
            print(f"# saved {dest} ({size} bytes)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
