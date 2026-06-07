"""FastAPI server that speaks AWS Textract's JSON 1.1 wire protocol.

A real boto3 Textract client pointed at this server with `endpoint_url=` works
unchanged: boto3 POSTs to "/" with header `X-Amz-Target: Textract.<Operation>` and a
JSON body; we dispatch on that header and return Textract-shaped JSON. Auth/SigV4
headers are ignored (it's your own server).
"""
from __future__ import annotations

import base64
import os

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

import uuid

from . import __version__
from .azure_schema import analyze_result, features_for_model, operation_envelope
from .backends import get_backend
from .confidence import aggregate
from .document import split_pages
from .google_schema import features_for_processor, process_document
from .review import router as review_router, save_report
from .textract_schema import (Page, analyze_document_response,
                              detect_document_text_response)

app = FastAPI(title="OpenExtract", version=__version__)
app.include_router(review_router)

_BACKEND_NAME = os.environ.get("OPENEXTRACT_BACKEND", "mock")
_backend = get_backend(_BACKEND_NAME)


_MAX_REMOTE_BYTES = 50 * 1024 * 1024  # 50 MB cap on S3/url-source fetches


def _fetch_s3(s3: dict) -> bytes:
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
    data = body.read(_MAX_REMOTE_BYTES + 1)
    if len(data) > _MAX_REMOTE_BYTES:
        raise ValueError(f"S3 object exceeds {_MAX_REMOTE_BYTES} bytes.")
    return data


def _fetch_url(url: str) -> bytes:
    from urllib.parse import urlparse
    from urllib.request import Request, urlopen
    scheme = urlparse(url).scheme
    if scheme not in ("http", "https"):
        raise ValueError(f"urlSource scheme must be http or https, got {scheme!r}.")
    req = Request(url, headers={"User-Agent": f"openextract/{__version__}"})
    with urlopen(req, timeout=30.0) as resp:  # noqa: S310 (scheme already restricted)
        data = resp.read(_MAX_REMOTE_BYTES + 1)
    if len(data) > _MAX_REMOTE_BYTES:
        raise ValueError(f"urlSource exceeds {_MAX_REMOTE_BYTES} bytes.")
    return data


def _doc_bytes(body: dict) -> bytes:
    doc = body.get("Document", {})
    if "Bytes" in doc:
        raw = doc["Bytes"]
        # boto3 sends bytes as a base64 string over the JSON protocol.
        if isinstance(raw, str):
            return base64.b64decode(raw)
        return bytes(raw)
    if "S3Object" in doc:
        return _fetch_s3(doc["S3Object"])
    raise ValueError("Document must include Bytes or S3Object.")


def _extract_pages(document_bytes: bytes, *, feature_types: list[str] | None = None) -> list[Page]:
    """Run the backend on every page of the input (PDFs rasterized, images pass through)."""
    try:
        page_images = split_pages(document_bytes)
    except RuntimeError as e:
        raise ValueError(str(e)) from e
    return [_backend.extract(img, feature_types=feature_types) for img in page_images]


def _merge_pages(pages: list[Page]) -> Page:
    """Flatten a multi-page document into one virtual Page for the confidence aggregator."""
    if len(pages) == 1:
        return pages[0]
    merged_kvs = [kv for p in pages for kv in p.key_values]
    return Page(width=pages[0].width, height=pages[0].height, key_values=merged_kvs)


def _amz_error(code: str, message: str, status: int = 400) -> Response:
    return JSONResponse(
        status_code=status,
        content={"__type": code, "message": message},
        headers={"Content-Type": "application/x-amz-json-1.1"},
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "backend": _backend.name, "version": __version__}


@app.post("/")
async def aws_json_endpoint(request: Request) -> Response:
    target = request.headers.get("X-Amz-Target", "")
    operation = target.split(".")[-1] if target else ""
    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        document = _doc_bytes(body)
    except ValueError as e:
        return _amz_error("InvalidParameterException", str(e))

    if operation == "DetectDocumentText":
        pages = _extract_pages(document)
        result = detect_document_text_response(pages)
    elif operation == "AnalyzeDocument":
        feature_types = body.get("FeatureTypes", [])
        pages = _extract_pages(document, feature_types=feature_types)
        result = analyze_document_response(pages, feature_types)
    else:
        return _amz_error("UnknownOperationException",
                          f"Unsupported X-Amz-Target: {target!r}", status=400)

    return JSONResponse(content=result, headers={"Content-Type": "application/x-amz-json-1.1"})


# --- Convenience REST routes for non-boto3 callers ---

@app.post("/v1/detect-document-text")
async def rest_detect(request: Request) -> JSONResponse:
    body = await request.json()
    pages = _extract_pages(_doc_bytes(body))
    return JSONResponse(detect_document_text_response(pages))


@app.post("/v1/analyze-document")
async def rest_analyze(request: Request) -> JSONResponse:
    body = await request.json()
    feature_types = body.get("FeatureTypes", ["FORMS", "TABLES"])
    pages = _extract_pages(_doc_bytes(body), feature_types=feature_types)
    return JSONResponse(analyze_document_response(pages, feature_types))


# --- Pro: calibrated confidence + human-review routing ---

@app.post("/v1/extract-with-confidence")
async def rest_confidence(request: Request) -> JSONResponse:
    """Extract form fields with calibrated confidence and a review queue.

    Body: {"Document": {"Bytes": ...}, "threshold": 90, "samples": 1}
    `samples` > 1 triggers self-consistency (best with a stochastic VLM backend).
    """
    body = await request.json()
    threshold = float(body.get("threshold", 90.0))
    samples = max(1, int(body.get("samples", 1)))
    doc = _doc_bytes(body)
    samples_pages = [_merge_pages(_extract_pages(doc, feature_types=["FORMS"]))
                     for _ in range(samples)]
    report = aggregate(samples_pages, threshold=threshold)
    payload = report.to_dict()
    if bool(body.get("persist", True)):
        # Persist so the /review UI can show the report; default on for ergonomics.
        payload["report_id"] = save_report(report)
    return JSONResponse(payload)


# --- Azure AI Document Intelligence wire compatibility (async analyze + poll) ---

_AZURE_RESULTS: dict[str, dict] = {}


@app.post("/documentintelligence/documentModels/{model_id}:analyze")
async def azure_analyze(model_id: str, request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:
        body = {}
    src = body.get("base64Source")
    url = body.get("urlSource")
    if src:
        doc = base64.b64decode(src)
    elif url:
        try:
            doc = _fetch_url(url)
        except ValueError as e:
            return JSONResponse(status_code=400,
                                content={"error": {"code": "InvalidRequest",
                                                   "message": str(e)}})
    else:
        return JSONResponse(status_code=400,
                            content={"error": {"code": "InvalidRequest",
                                               "message": "Provide base64Source or urlSource."}})
    include_forms, include_tables = features_for_model(model_id)
    feats = (["FORMS"] if include_forms else []) + (["TABLES"] if include_tables else [])
    pages = _extract_pages(doc, feature_types=feats)
    analyze = analyze_result(pages, model_id, forms=include_forms, tables=include_tables)

    result_id = str(uuid.uuid4())
    _AZURE_RESULTS[result_id] = operation_envelope(result_id, analyze)
    base = str(request.base_url).rstrip("/")
    op_loc = (f"{base}/documentintelligence/documentModels/{model_id}"
              f"/analyzeResults/{result_id}?api-version={analyze['apiVersion']}")
    return Response(status_code=202, headers={"Operation-Location": op_loc,
                                              "apim-request-id": result_id})


@app.get("/documentintelligence/documentModels/{model_id}/analyzeResults/{result_id}")
async def azure_result(model_id: str, result_id: str) -> Response:
    result = _AZURE_RESULTS.get(result_id)
    if result is None:
        return JSONResponse(status_code=404,
                            content={"error": {"code": "NotFound",
                                               "message": "Result not found."}})
    return JSONResponse(content=result)


# --- Google Document AI wire compatibility (sync :process) ---

def _google_error(message: str, status: int = 400, code: str = "INVALID_ARGUMENT") -> JSONResponse:
    return JSONResponse(status_code=status,
                        content={"error": {"code": status, "status": code, "message": message}})


@app.post("/v1/projects/{project}/locations/{location}/processors/{processor_id}:process")
async def google_process(project: str, location: str, processor_id: str,
                         request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:
        body = {}
    raw = body.get("rawDocument") or body.get("inlineDocument") or {}
    content = raw.get("content")
    if not content:
        return _google_error("rawDocument.content (base64) is required.")
    try:
        document = base64.b64decode(content)
    except Exception:
        return _google_error("rawDocument.content must be base64-encoded.")

    forms, tables = features_for_processor(processor_id)
    feats = (["FORMS"] if forms else []) + (["TABLES"] if tables else [])
    try:
        pages = _extract_pages(document, feature_types=feats)
    except ValueError as e:
        return _google_error(str(e))

    return JSONResponse(process_document(pages, processor_id, forms=forms, tables=tables))
