"""Build Azure AI Document Intelligence-compatible response JSON.

Azure DI (formerly Form Recognizer) uses an async REST flow: POST `:analyze` returns
202 + an `Operation-Location` header; the client polls that URL until `status` is
`succeeded` and reads `analyzeResult`. We mirror that shape so code/SDKs written against
Azure DI can point at OpenExtract instead.

Model ids map to feature sets, like Azure's prebuilt models:
  prebuilt-read     -> text only
  prebuilt-layout   -> text + tables
  prebuilt-document -> text + tables + key/value pairs
  prebuilt-invoice  -> text + tables + key/value pairs
"""
from __future__ import annotations

from datetime import datetime, timezone

from .textract_schema import Box, Page

API_VERSION = "2024-11-30"

_FORMS_MODELS = {"prebuilt-document", "prebuilt-invoice"}
_TABLE_MODELS = {"prebuilt-layout", "prebuilt-document", "prebuilt-invoice"}


def features_for_model(model_id: str) -> tuple[bool, bool]:
    """Return (include_forms, include_tables) for a given model id."""
    return (model_id in _FORMS_MODELS, model_id in _TABLE_MODELS)


def _polygon(box: Box) -> list[float]:
    # Azure polygon: 4 corners flattened [x1,y1,...,x4,y4], in the page unit (pixels).
    return [box.x, box.y, box.x + box.w, box.y,
            box.x + box.w, box.y + box.h, box.x, box.y + box.h]


def analyze_result(pages: list[Page], model_id: str, *, forms: bool, tables: bool) -> dict:
    azure_pages: list[dict] = []
    all_key_values: list[dict] = []
    all_tables: list[dict] = []
    content_parts_global: list[str] = []
    offset = 0  # cursor into the document-wide `content` string

    for page_num, page in enumerate(pages, start=1):
        words: list[dict] = []
        lines: list[dict] = []
        page_parts: list[str] = []
        page_offset_start = offset
        for line in page.lines:
            page_parts.append(line.text)
            lines.append({
                "content": line.text,
                "polygon": _polygon(line.box),
                "spans": [{"offset": offset, "length": len(line.text)}],
            })
            for w in line.words:
                words.append({
                    "content": w.text,
                    "polygon": _polygon(w.box),
                    "confidence": round(w.confidence / 100.0, 3),
                    "span": {"offset": offset, "length": len(w.text)},
                })
            offset += len(line.text) + 1
        page_text = "\n".join(page_parts)
        content_parts_global.append(page_text)
        azure_pages.append({
            "pageNumber": page_num,
            "angle": 0,
            "width": page.width,
            "height": page.height,
            "unit": "pixel",
            "words": words,
            "lines": lines,
            "spans": [{"offset": page_offset_start, "length": len(page_text)}],
        })

        if forms:
            all_key_values.extend({
                "key": {"content": kv.key,
                        "boundingRegions": [{"pageNumber": page_num, "polygon": _polygon(kv.key_box)}]},
                "value": {"content": kv.value,
                          "boundingRegions": [{"pageNumber": page_num, "polygon": _polygon(kv.value_box)}]},
                "confidence": round(kv.confidence / 100.0, 3),
            } for kv in page.key_values)

        if tables:
            for t in page.tables:
                row_count = len(t.rows)
                col_count = max((len(r) for r in t.rows), default=0)
                cells = []
                for ri, row in enumerate(t.rows):
                    for ci, cell in enumerate(row):
                        cells.append({
                            "rowIndex": ri, "columnIndex": ci,
                            "rowSpan": 1, "columnSpan": 1,
                            "content": cell,
                            "boundingRegions": [{"pageNumber": page_num, "polygon": _polygon(t.box)}],
                        })
                all_tables.append({
                    "rowCount": row_count, "columnCount": col_count,
                    "cells": cells,
                    "boundingRegions": [{"pageNumber": page_num, "polygon": _polygon(t.box)}],
                })

    content = "\n".join(content_parts_global)
    result: dict = {
        "apiVersion": API_VERSION,
        "modelId": model_id,
        "stringIndexType": "textElements",
        "content": content,
        "pages": azure_pages,
    }
    if forms:
        result["keyValuePairs"] = all_key_values
    if tables:
        result["tables"] = all_tables
    return result


def operation_envelope(result_id: str, analyze: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "status": "succeeded",
        "createdDateTime": now,
        "lastUpdatedDateTime": now,
        "analyzeResult": analyze,
    }
