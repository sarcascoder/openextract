"""Generate synthetic invoice/form images + ground-truth JSON for the benchmark.

No GPU, no network. Renders clean documents with PIL so we have a reproducible test
set the benchmark can score any backend against.

    pip install pillow
    python bench/gen_samples.py
"""
from __future__ import annotations

import json
import os

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(OUT, exist_ok=True)


def _font(size: int):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial.ttf",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


SAMPLES = [
    {
        "name": "invoice_01",
        "title": "INVOICE",
        "lines": [
            "Acme Supplies Inc.",
            "Invoice Number: INV-1042",
            "Invoice Date: 2026-05-14",
            "Bill To: Globex Corporation",
            "Subtotal: $1,150.00",
            "Tax: $100.00",
            "Total Due: $1,250.00",
        ],
        "fields": {
            "Invoice Number": "INV-1042",
            "Invoice Date": "2026-05-14",
            "Total Due": "$1,250.00",
        },
    },
    {
        "name": "invoice_02",
        "title": "PURCHASE ORDER",
        "lines": [
            "Northwind Traders",
            "PO Number: PO-88231",
            "Order Date: 2026-04-02",
            "Vendor: Initech LLC",
            "Payment Terms: Net 30",
            "Amount: $4,820.75",
        ],
        "fields": {
            "PO Number": "PO-88231",
            "Order Date": "2026-04-02",
            "Amount": "$4,820.75",
        },
    },
    {
        "name": "receipt_01",
        "title": "RECEIPT",
        "lines": [
            "Downtown Hardware",
            "Receipt No: R-55012",
            "Date: 2026-06-01",
            "Item: Cordless Drill",
            "Quantity: 2",
            "Total: $238.00",
        ],
        "fields": {
            "Receipt No": "R-55012",
            "Date": "2026-06-01",
            "Total": "$238.00",
        },
    },
]


def render(sample: dict) -> None:
    W, H = 1000, 1300
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    title_font = _font(46)
    body_font = _font(28)

    d.text((80, 60), sample["title"], fill="black", font=title_font)
    y = 160
    for line in sample["lines"]:
        d.text((80, y), line, fill="black", font=body_font)
        y += 50

    path = os.path.join(OUT, sample["name"] + ".png")
    img.save(path)

    gt = {"lines": [sample["title"]] + sample["lines"], "fields": sample["fields"]}
    with open(os.path.join(OUT, sample["name"] + ".json"), "w") as f:
        json.dump(gt, f, indent=2)
    print("wrote", path)


if __name__ == "__main__":
    for s in SAMPLES:
        render(s)
    print(f"\n{len(SAMPLES)} samples in {OUT}")
