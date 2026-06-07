from __future__ import annotations

import io

from .base import Backend
from ..textract_schema import Box, Line, Page, Word


class TesseractBackend(Backend):
    """CPU OCR via pytesseract. Good baseline; no forms/tables structure.

    Requires the `tesseract` system binary and `pip install pytesseract pillow`.
    Produces LINE/WORD blocks with real bounding boxes and confidences.
    """

    name = "tesseract"

    def __init__(self) -> None:
        import pytesseract  # noqa: F401  (fail fast if missing)
        from PIL import Image  # noqa: F401

    def extract(self, document_bytes: bytes, *, feature_types: list[str] | None = None) -> Page:
        import pytesseract
        from PIL import Image
        from pytesseract import Output

        img = Image.open(io.BytesIO(document_bytes))
        page_w, page_h = float(img.width), float(img.height)
        data = pytesseract.image_to_data(img, output_type=Output.DICT)

        # Group words into lines by (block, par, line) key.
        line_map: dict[tuple, list[int]] = {}
        for i, text in enumerate(data["text"]):
            if not text.strip():
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            line_map.setdefault(key, []).append(i)

        lines: list[Line] = []
        for key, idxs in line_map.items():
            words: list[Word] = []
            xs, ys, x2s, y2s = [], [], [], []
            for i in idxs:
                box = Box(float(data["left"][i]), float(data["top"][i]),
                          float(data["width"][i]), float(data["height"][i]))
                conf = max(float(data["conf"][i]), 0.0)
                words.append(Word(data["text"][i], box, conf))
                xs.append(box.x); ys.append(box.y)
                x2s.append(box.x + box.w); y2s.append(box.y + box.h)
            lx, ly = min(xs), min(ys)
            line_box = Box(lx, ly, max(x2s) - lx, max(y2s) - ly)
            line_conf = sum(w.confidence for w in words) / len(words)
            lines.append(Line(" ".join(w.text for w in words), line_box, line_conf, words))

        return Page(width=page_w, height=page_h, lines=lines)
