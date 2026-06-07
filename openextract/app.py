"""FastAPI server that speaks AWS Textract, Azure DI, and Google Document AI.

The OSS core handles the three wire protocols and exposes a pluggable backend.
The closed-source `openextract_pro` package, if installed, adds calibrated
confidence and the /review UI by mounting its endpoints via `pro_loader`.
"""
from __future__ import annotations

import base64
import os
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from . import __version__
from .azure_schema import analyze_result, features_for_model, operation_envelope
from .backends import get_backend
from .google_schema import features_for_processor, process_document
from .kernel import doc_bytes_from_body, extract_pages, fetch_url
from .pro_loader import maybe_mount
from .textract_schema import (analyze_document_response,
                              detect_document_text_response)

app = FastAPI(title="OpenExtract", version=__version__)

_BACKEND_NAME = os.environ.get("OPENEXTRACT_BACKEND", "mock")
_backend = get_backend(_BACKEND_NAME)
app.state.backend = _backend

# Pro plugin (calibrated confidence + /review UI) mounts here if installed.
_pro_mounted = maybe_mount(app, _backend)


def _amz_error(code: str, message: str, status: int = 400) -> Response:
    return JSONResponse(
        status_code=status,
        content={"__type": code, "message": message},
        headers={"Content-Type": "application/x-amz-json-1.1"},
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "backend": _backend.name, "version": __version__,
            "pro": _pro_mounted}


@app.post("/")
async def aws_json_endpoint(request: Request) -> Response:
    target = request.headers.get("X-Amz-Target", "")
    operation = target.split(".")[-1] if target else ""
    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        document = doc_bytes_from_body(body)
    except ValueError as e:
        return _amz_error("InvalidParameterException", str(e))

    if operation == "DetectDocumentText":
        pages = extract_pages(_backend, document)
        result = detect_document_text_response(pages)
    elif operation == "AnalyzeDocument":
        feature_types = body.get("FeatureTypes", [])
        pages = extract_pages(_backend, document, feature_types=feature_types)
        result = analyze_document_response(pages, feature_types)
    else:
        return _amz_error("UnknownOperationException",
                          f"Unsupported X-Amz-Target: {target!r}", status=400)

    return JSONResponse(content=result, headers={"Content-Type": "application/x-amz-json-1.1"})


# --- Convenience REST routes for non-boto3 callers ---

@app.post("/v1/detect-document-text")
async def rest_detect(request: Request) -> JSONResponse:
    body = await request.json()
    pages = extract_pages(_backend, doc_bytes_from_body(body))
    return JSONResponse(detect_document_text_response(pages))


@app.post("/v1/analyze-document")
async def rest_analyze(request: Request) -> JSONResponse:
    body = await request.json()
    feature_types = body.get("FeatureTypes", ["FORMS", "TABLES"])
    pages = extract_pages(_backend, doc_bytes_from_body(body), feature_types=feature_types)
    return JSONResponse(analyze_document_response(pages, feature_types))


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
            doc = fetch_url(url)
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
    pages = extract_pages(_backend, doc, feature_types=feats)
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
        pages = extract_pages(_backend, document, feature_types=feats)
    except ValueError as e:
        return _google_error(str(e))

    return JSONResponse(process_document(pages, processor_id, forms=forms, tables=tables))
