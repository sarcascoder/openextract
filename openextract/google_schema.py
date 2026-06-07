"""Google Document AI wire compatibility.

Google Document AI clients POST to
  /v1/projects/{p}/locations/{l}/processors/{id}:process
with `rawDocument.content` (base64) and read `document.{text, pages[]}` back.
We accept any project/location/processor id and infer the feature set from the
processor id substring (matches the public OCR_PROCESSOR / FORM_PARSER_PROCESSOR /
LAYOUT_PARSER_PROCESSOR / INVOICE_PROCESSOR families). Auth headers are ignored —
this is your own server.

The output `document.text` is built as: line text per page (lines separated by
`\n`, pages by `\n`), then key/value/cell text appended for forms/tables so every
`textAnchor` resolves into a valid substring of `text`.
"""
from __future__ import annotations

from .textract_schema import Box, Page

# Substring → feature inference, matching Google's prebuilt processor families.
_FORM_HINTS = ("form", "invoice", "expense", "document")
_TABLE_HINTS = ("layout", "form", "invoice", "table")


def features_for_processor(processor_id: str) -> tuple[bool, bool]:
    """Return (forms, tables) inferred from the processor id."""
    pid = processor_id.lower()
    forms = any(s in pid for s in _FORM_HINTS)
    tables = any(s in pid for s in _TABLE_HINTS)
    return forms, tables


def _vertices(box: Box) -> list[dict]:
    return [
        {"x": box.x, "y": box.y},
        {"x": box.x + box.w, "y": box.y},
        {"x": box.x + box.w, "y": box.y + box.h},
        {"x": box.x, "y": box.y + box.h},
    ]


def _layout(start: int, end: int, box: Box, confidence: float = 0.99) -> dict:
    """Google Document AI Layout: textAnchor (offsets into document.text) + boundingPoly."""
    return {
        "textAnchor": {
            "textSegments": [{"startIndex": str(start), "endIndex": str(end)}]
        },
        "boundingPoly": {"vertices": _vertices(box)},
        "confidence": round(confidence, 3),
        "orientation": "PAGE_UP",
    }


class _TextBuilder:
    __slots__ = ("parts", "offset")

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.offset = 0

    def push(self, s: str) -> tuple[int, int]:
        start = self.offset
        self.parts.append(s)
        self.offset += len(s)
        return start, self.offset

    def newline(self) -> None:
        self.parts.append("\n")
        self.offset += 1

    def text(self) -> str:
        return "".join(self.parts)


def process_document(pages: list[Page], processor_id: str, *,
                     forms: bool, tables: bool) -> dict:
    tb = _TextBuilder()
    google_pages: list[dict] = []

    for page_num, page in enumerate(pages, start=1):
        page_start = tb.offset
        tokens: list[dict] = []
        lines_out: list[dict] = []

        for line in page.lines:
            line_start, line_end = tb.push(line.text)
            lines_out.append({
                "layout": _layout(line_start, line_end, line.box, line.confidence / 100.0)
            })
            # Approximate per-word offsets by searching within the line text.
            search_from = 0
            for w in line.words:
                local_idx = line.text.find(w.text, search_from)
                if local_idx < 0:
                    # Word not found verbatim in line text; emit a zero-length anchor
                    # at the line start so wire shape stays valid.
                    w_start = line_start
                    w_end = line_start
                else:
                    w_start = line_start + local_idx
                    w_end = w_start + len(w.text)
                    search_from = local_idx + len(w.text)
                tokens.append({
                    "layout": _layout(w_start, w_end, w.box, w.confidence / 100.0),
                    "detectedBreak": {"type": "SPACE"},
                })
            tb.newline()  # separate lines

        page_end = tb.offset

        page_obj: dict = {
            "pageNumber": page_num,
            "dimension": {"width": page.width, "height": page.height, "unit": "pixels"},
            "layout": _layout(page_start, page_end,
                              Box(0, 0, page.width, page.height), 1.0),
            "lines": lines_out,
            "tokens": tokens,
        }

        if forms:
            form_fields: list[dict] = []
            for kv in page.key_values:
                k_start, k_end = tb.push(kv.key)
                tb.newline()
                v_start, v_end = tb.push(kv.value)
                tb.newline()
                form_fields.append({
                    "fieldName": _layout(k_start, k_end, kv.key_box, kv.confidence / 100.0),
                    "fieldValue": _layout(v_start, v_end, kv.value_box, kv.confidence / 100.0),
                    "valueType": "unfilled",
                })
            page_obj["formFields"] = form_fields

        if tables:
            tables_out: list[dict] = []
            for t in page.tables:
                header_rows: list[dict] = []
                body_rows: list[dict] = []
                table_text_start = tb.offset
                for r_idx, row in enumerate(t.rows):
                    cells: list[dict] = []
                    for cell in row:
                        c_start, c_end = tb.push(cell)
                        tb.newline()
                        cells.append({
                            "layout": _layout(c_start, c_end, t.box, t.confidence / 100.0),
                            "rowSpan": 1, "colSpan": 1,
                        })
                    (header_rows if r_idx == 0 else body_rows).append({"cells": cells})
                tables_out.append({
                    "layout": _layout(table_text_start, tb.offset, t.box,
                                      t.confidence / 100.0),
                    "headerRows": header_rows,
                    "bodyRows": body_rows,
                })
            page_obj["tables"] = tables_out

        google_pages.append(page_obj)

    return {
        "document": {
            "mimeType": "application/json",
            "text": tb.text(),
            "pages": google_pages,
        }
    }
