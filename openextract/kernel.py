"""Public extraction kernel — the stable contract used by Pro plugins.

These helpers are deliberately small, side-effect-free (apart from network I/O on
S3/url-source inputs), and take the backend as a parameter rather than reading a
module global so plugins can call them without depending on app boot order.

A plugin like `openextract-pro` calls into this module rather than reaching into
`openextract.app` internals.
"""
from __future__ import annotations

import base64

from . import __version__
from .backends.base import Backend
from .document import split_pages
from .textract_schema import Page

MAX_REMOTE_BYTES = 50 * 1024 * 1024  # 50 MB cap on S3 / urlSource fetches


def fetch_s3(s3: dict) -> bytes:
    """Resolve a Textract-style S3Object {Bucket, Name, Version} via boto3."""
    bucket, name = s3.get("Bucket"), s3.get("Name")
    if not bucket or not name:
        raise ValueError("S3Object requires Bucket and Name.")
    try:
        import boto3
    except ImportError as e:
        raise ValueError("S3Object requires boto3 (pip install boto3).") from e
    kwargs = {"Bucket": bucket, "Key": name}
    if s3.get("Version"):
        kwargs["VersionId"] = s3["Version"]
    body = boto3.client("s3").get_object(**kwargs)["Body"]
    data = body.read(MAX_REMOTE_BYTES + 1)
    if len(data) > MAX_REMOTE_BYTES:
        raise ValueError(f"S3 object exceeds {MAX_REMOTE_BYTES} bytes.")
    return data


def fetch_url(url: str) -> bytes:
    """Fetch http(s) urlSource with timeout + size cap. Rejects other schemes."""
    from urllib.parse import urlparse
    from urllib.request import Request, urlopen
    scheme = urlparse(url).scheme
    if scheme not in ("http", "https"):
        raise ValueError(f"urlSource scheme must be http or https, got {scheme!r}.")
    req = Request(url, headers={"User-Agent": f"openextract/{__version__}"})
    with urlopen(req, timeout=30.0) as resp:  # noqa: S310 (scheme restricted)
        data = resp.read(MAX_REMOTE_BYTES + 1)
    if len(data) > MAX_REMOTE_BYTES:
        raise ValueError(f"urlSource exceeds {MAX_REMOTE_BYTES} bytes.")
    return data


def doc_bytes_from_body(body: dict) -> bytes:
    """Resolve a Textract-style Document.{Bytes|S3Object} payload to raw bytes."""
    doc = body.get("Document", {})
    if "Bytes" in doc:
        raw = doc["Bytes"]
        # boto3 sends Bytes as base64 over the JSON protocol.
        if isinstance(raw, str):
            return base64.b64decode(raw)
        return bytes(raw)
    if "S3Object" in doc:
        return fetch_s3(doc["S3Object"])
    raise ValueError("Document must include Bytes or S3Object.")


def extract_pages(backend: Backend, document_bytes: bytes, *,
                  feature_types: list[str] | None = None) -> list[Page]:
    """Run `backend` on every page of the input (PDFs rasterized; raster bytes pass through)."""
    try:
        page_images = split_pages(document_bytes)
    except RuntimeError as e:
        raise ValueError(str(e)) from e
    return [backend.extract(img, feature_types=feature_types) for img in page_images]


def merge_pages(pages: list[Page]) -> Page:
    """Flatten a multi-page document into a single virtual Page (used by aggregators)."""
    if len(pages) == 1:
        return pages[0]
    merged_kvs = [kv for p in pages for kv in p.key_values]
    return Page(width=pages[0].width, height=pages[0].height, key_values=merged_kvs)
