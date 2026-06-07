from __future__ import annotations

from .base import Backend
from ..textract_schema import Box, KeyValue, Line, Page, Table, Word


class MockBackend(Backend):
    """Deterministic backend with no dependencies.

    Used for tests, CI, and the boto3 drop-in demo so the server runs anywhere
    (no GPU, no system binaries). Swap for `tesseract` or `vlm` in production.
    """

    name = "mock"

    def extract(self, document_bytes: bytes, *, feature_types: list[str] | None = None) -> Page:
        page_w, page_h = 1000.0, 1300.0
        lines = [
            Line(text="INVOICE", box=Box(80, 60, 200, 40), confidence=99.5,
                 words=[Word("INVOICE", Box(80, 60, 200, 40), 99.5)]),
            Line(text="Invoice Number: INV-1042", box=Box(80, 140, 360, 28), confidence=98.7,
                 words=[Word("Invoice", Box(80, 140, 110, 28), 98.9),
                        Word("Number:", Box(195, 140, 100, 28), 98.6),
                        Word("INV-1042", Box(300, 140, 140, 28), 98.5)]),
            Line(text="Total Due: $1,250.00", box=Box(80, 180, 300, 28), confidence=98.1,
                 words=[Word("Total", Box(80, 180, 80, 28), 98.4),
                        Word("Due:", Box(165, 180, 60, 28), 98.0),
                        Word("$1,250.00", Box(230, 180, 150, 28), 97.9)]),
        ]
        key_values = [
            KeyValue("Invoice Number:", "INV-1042", Box(80, 140, 110, 28), Box(300, 140, 140, 28), 98.5),
            KeyValue("Total Due:", "$1,250.00", Box(80, 180, 80, 28), Box(230, 180, 150, 28), 97.9),
        ]
        tables = [
            Table(rows=[["Item", "Qty", "Price"], ["Widget", "5", "$250.00"]],
                  box=Box(80, 260, 600, 120), confidence=97.0),
        ]
        return Page(width=page_w, height=page_h, lines=lines,
                    key_values=key_values, tables=tables)
