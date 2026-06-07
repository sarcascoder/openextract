"""Build AWS Textract-compatible response JSON (Block structure).

We mirror the exact shape boto3 expects so existing client code parses our output
unchanged. Reference: Textract DetectDocumentText / AnalyzeDocument Block model.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional


# ---- Normalized internal representation (what backends produce) ----

@dataclass
class Box:
    """Pixel-space bounding box."""
    x: float
    y: float
    w: float
    h: float


@dataclass
class Word:
    text: str
    box: Box
    confidence: float = 99.0


@dataclass
class Line:
    text: str
    box: Box
    confidence: float = 99.0
    words: list[Word] = field(default_factory=list)


@dataclass
class KeyValue:
    key: str
    value: str
    key_box: Box
    value_box: Box
    confidence: float = 99.0


@dataclass
class Table:
    rows: list[list[str]]
    box: Box
    confidence: float = 99.0


@dataclass
class Page:
    width: float
    height: float
    lines: list[Line] = field(default_factory=list)
    key_values: list[KeyValue] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)


# ---- Block builders ----

def _id() -> str:
    return str(uuid.uuid4())


def _geometry(box: Box, page_w: float, page_h: float) -> dict:
    left = box.x / page_w if page_w else 0.0
    top = box.y / page_h if page_h else 0.0
    width = box.w / page_w if page_w else 0.0
    height = box.h / page_h if page_h else 0.0
    return {
        "BoundingBox": {"Width": width, "Height": height, "Left": left, "Top": top},
        "Polygon": [
            {"X": left, "Y": top},
            {"X": left + width, "Y": top},
            {"X": left + width, "Y": top + height},
            {"X": left, "Y": top + height},
        ],
    }


def build_blocks(page: Page, *, include_forms: bool = False, include_tables: bool = False,
                 page_index: int = 1) -> list[dict]:
    """Return Textract Blocks for one page; `page_index` is the 1-based page number."""
    blocks: list[dict] = []
    page_id = _id()
    child_ids: list[str] = []

    for line in page.lines:
        line_id = _id()
        word_ids: list[str] = []
        for w in line.words:
            wid = _id()
            word_ids.append(wid)
            blocks.append({
                "BlockType": "WORD",
                "Id": wid,
                "Text": w.text,
                "Confidence": round(w.confidence, 2),
                "TextType": "PRINTED",
                "Geometry": _geometry(w.box, page.width, page.height),
                "Page": page_index,
            })
        line_block = {
            "BlockType": "LINE",
            "Id": line_id,
            "Text": line.text,
            "Confidence": round(line.confidence, 2),
            "Geometry": _geometry(line.box, page.width, page.height),
            "Page": page_index,
        }
        if word_ids:
            line_block["Relationships"] = [{"Type": "CHILD", "Ids": word_ids}]
        blocks.append(line_block)
        child_ids.append(line_id)

    if include_forms:
        for kv in page.key_values:
            key_id, value_id = _id(), _id()
            key_word, value_word = _id(), _id()
            child_ids.extend([key_id, value_id])
            blocks.append({
                "BlockType": "WORD", "Id": key_word, "Text": kv.key,
                "Confidence": round(kv.confidence, 2), "TextType": "PRINTED",
                "Geometry": _geometry(kv.key_box, page.width, page.height), "Page": page_index,
            })
            blocks.append({
                "BlockType": "WORD", "Id": value_word, "Text": kv.value,
                "Confidence": round(kv.confidence, 2), "TextType": "PRINTED",
                "Geometry": _geometry(kv.value_box, page.width, page.height), "Page": page_index,
            })
            blocks.append({
                "BlockType": "KEY_VALUE_SET", "Id": key_id,
                "EntityTypes": ["KEY"], "Confidence": round(kv.confidence, 2),
                "Geometry": _geometry(kv.key_box, page.width, page.height), "Page": page_index,
                "Relationships": [
                    {"Type": "VALUE", "Ids": [value_id]},
                    {"Type": "CHILD", "Ids": [key_word]},
                ],
            })
            blocks.append({
                "BlockType": "KEY_VALUE_SET", "Id": value_id,
                "EntityTypes": ["VALUE"], "Confidence": round(kv.confidence, 2),
                "Geometry": _geometry(kv.value_box, page.width, page.height), "Page": page_index,
                "Relationships": [{"Type": "CHILD", "Ids": [value_word]}],
            })

    if include_tables:
        for table in page.tables:
            table_id = _id()
            cell_ids: list[str] = []
            for r, row in enumerate(table.rows, start=1):
                for c, cell_text in enumerate(row, start=1):
                    cell_id = _id()
                    word_id = _id()
                    cell_ids.append(cell_id)
                    blocks.append({
                        "BlockType": "WORD", "Id": word_id, "Text": cell_text,
                        "Confidence": round(table.confidence, 2), "TextType": "PRINTED",
                        "Geometry": _geometry(table.box, page.width, page.height), "Page": page_index,
                    })
                    blocks.append({
                        "BlockType": "CELL", "Id": cell_id,
                        "RowIndex": r, "ColumnIndex": c,
                        "RowSpan": 1, "ColumnSpan": 1,
                        "Confidence": round(table.confidence, 2),
                        "Geometry": _geometry(table.box, page.width, page.height), "Page": page_index,
                        "Relationships": [{"Type": "CHILD", "Ids": [word_id]}],
                    })
            table_block = {
                "BlockType": "TABLE", "Id": table_id,
                "Confidence": round(table.confidence, 2),
                "Geometry": _geometry(table.box, page.width, page.height), "Page": page_index,
            }
            if cell_ids:
                table_block["Relationships"] = [{"Type": "CHILD", "Ids": cell_ids}]
            blocks.append(table_block)
            child_ids.append(table_id)

    page_block = {
        "BlockType": "PAGE",
        "Id": page_id,
        "Geometry": _geometry(Box(0, 0, page.width, page.height), page.width, page.height),
        "Page": page_index,
    }
    if child_ids:
        page_block["Relationships"] = [{"Type": "CHILD", "Ids": child_ids}]
    # PAGE block goes first within a page, like Textract.
    return [page_block] + blocks


def _all_blocks(pages: list[Page], *, include_forms: bool = False,
                include_tables: bool = False) -> list[dict]:
    out: list[dict] = []
    for i, p in enumerate(pages, start=1):
        out.extend(build_blocks(p, include_forms=include_forms,
                                include_tables=include_tables, page_index=i))
    return out


def detect_document_text_response(pages: list[Page]) -> dict:
    return {
        "DocumentMetadata": {"Pages": len(pages)},
        "Blocks": _all_blocks(pages),
        "DetectDocumentTextModelVersion": "1.0",
    }


def analyze_document_response(pages: list[Page], feature_types: list[str]) -> dict:
    include_forms = "FORMS" in feature_types
    include_tables = "TABLES" in feature_types
    return {
        "DocumentMetadata": {"Pages": len(pages)},
        "Blocks": _all_blocks(pages, include_forms=include_forms, include_tables=include_tables),
        "AnalyzeDocumentModelVersion": "1.0",
    }
