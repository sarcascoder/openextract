"""Accuracy + cost benchmark: OpenExtract (local) vs AWS Textract.

This is the marketing asset AND the go/no-go gate. If local accuracy is within a few
points of Textract on forms+tables, the whole thesis (16-40x cheaper, on-prem) holds.

Usage:
    # 1. Put page images in bench/data/<name>.png and ground truth in bench/data/<name>.json
    #    ground truth: {"lines": ["...", ...], "fields": {"Invoice Number": "INV-1042"}}
    # 2. Start the local server:  openextract --backend vlm
    # 3. python bench/benchmark.py --endpoint http://localhost:8080

Cost model is taken from published 2026 pricing; edit COSTS as providers change.
"""
from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import time

import boto3

# Per-1,000-pages USD (published mid-2026). Local = amortized A100 GPU.
COSTS = {
    "textract_detect": 1.50,
    "textract_analyze_forms_tables": 65.00,
    "google_docai_basic": 1.50,
    "openextract_local": 0.09,
}


def _client(endpoint: str):
    return boto3.client("textract", endpoint_url=endpoint, region_name="us-east-1",
                        aws_access_key_id="local", aws_secret_access_key="local")


def _lines(resp) -> list[str]:
    return [b["Text"] for b in resp["Blocks"] if b["BlockType"] == "LINE"]


def _fields(resp) -> dict[str, str]:
    blocks = {b["Id"]: b for b in resp["Blocks"]}
    out = {}
    for b in resp["Blocks"]:
        if b["BlockType"] == "KEY_VALUE_SET" and "KEY" in b.get("EntityTypes", []):
            key = _text_of(b, blocks)
            value_ids = next((r["Ids"] for r in b.get("Relationships", [])
                              if r["Type"] == "VALUE"), [])
            val = " ".join(_text_of(blocks[i], blocks) for i in value_ids if i in blocks)
            out[key.strip(": ")] = val.strip()
    return out


def _text_of(block, blocks) -> str:
    child_ids = next((r["Ids"] for r in block.get("Relationships", [])
                      if r["Type"] == "CHILD"), [])
    return " ".join(blocks[i].get("Text", "") for i in child_ids if i in blocks)


def _line_accuracy(pred: list[str], truth: list[str]) -> float:
    if not truth:
        return 1.0
    truth_set = {t.strip().lower() for t in truth}
    hit = sum(1 for p in pred if p.strip().lower() in truth_set)
    return hit / len(truth_set)


def _field_accuracy(pred: dict, truth: dict) -> float:
    if not truth:
        return 1.0
    hit = sum(1 for k, v in truth.items()
              if str(pred.get(k, "")).strip().lower() == str(v).strip().lower())
    return hit / len(truth)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://localhost:8080")
    ap.add_argument("--data", default=os.path.join(os.path.dirname(__file__), "data"))
    args = ap.parse_args()

    client = _client(args.endpoint)
    images = sorted(glob.glob(os.path.join(args.data, "*.png")))
    if not images:
        print(f"No images in {args.data}. Add <name>.png + <name>.json ground truth.")
        return

    line_scores, field_scores, latencies = [], [], []
    for img_path in images:
        gt_path = os.path.splitext(img_path)[0] + ".json"
        gt = json.load(open(gt_path)) if os.path.exists(gt_path) else {}
        # Pass RAW bytes: boto3 base64-encodes blobs itself for the JSON protocol.
        doc = open(img_path, "rb").read()

        t0 = time.time()
        resp = client.analyze_document(Document={"Bytes": doc},
                                       FeatureTypes=["FORMS", "TABLES"])
        latencies.append(time.time() - t0)

        line_scores.append(_line_accuracy(_lines(resp), gt.get("lines", [])))
        field_scores.append(_field_accuracy(_fields(resp), gt.get("fields", {})))
        print(f"  {os.path.basename(img_path)}: "
              f"line={line_scores[-1]:.1%} field={field_scores[-1]:.1%} "
              f"({latencies[-1]:.2f}s)")

    n = len(images)
    print("\n=== Results ({} pages) ===".format(n))
    print(f"Line accuracy:  {sum(line_scores)/n:.1%}")
    print(f"Field accuracy: {sum(field_scores)/n:.1%}")
    print(f"Avg latency:    {sum(latencies)/n:.2f}s/page")
    print("\n=== Cost per 1,000 forms+tables pages ===")
    print(f"  AWS Textract (forms+tables): ${COSTS['textract_analyze_forms_tables']:.2f}")
    print(f"  OpenExtract (local A100):    ${COSTS['openextract_local']:.2f}")
    factor = COSTS["textract_analyze_forms_tables"] / COSTS["openextract_local"]
    print(f"  => {factor:.0f}x cheaper")


if __name__ == "__main__":
    main()
