"""Multi-page PDF tests. Skipped if PyMuPDF isn't installed."""
import base64

import pytest

fitz = pytest.importorskip("fitz")  # PyMuPDF

from fastapi.testclient import TestClient

from openextract.app import app

client = TestClient(app)


def _pdf(pages: int = 2) -> bytes:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)  # A4 in points
        page.insert_text((72, 100), f"Page {i + 1} of {pages}")
    data = doc.tobytes()
    doc.close()
    return data


def test_textract_multipage_pdf_sets_page_count_and_indices():
    payload = base64.b64encode(_pdf(2)).decode()
    r = client.post(
        "/",
        headers={"X-Amz-Target": "Textract.DetectDocumentText"},
        json={"Document": {"Bytes": payload}},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["DocumentMetadata"]["Pages"] == 2
    page_blocks = [b for b in data["Blocks"] if b["BlockType"] == "PAGE"]
    assert len(page_blocks) == 2
    assert page_blocks[0]["Page"] == 1 and page_blocks[1]["Page"] == 2
    assert all(b.get("Page") in (1, 2) for b in data["Blocks"])


def test_textract_three_page_pdf():
    payload = base64.b64encode(_pdf(3)).decode()
    r = client.post(
        "/",
        headers={"X-Amz-Target": "Textract.AnalyzeDocument"},
        json={"Document": {"Bytes": payload}, "FeatureTypes": ["FORMS", "TABLES"]},
    )
    data = r.json()
    assert data["DocumentMetadata"]["Pages"] == 3
    pages_seen = sorted({b["Page"] for b in data["Blocks"] if "Page" in b})
    assert pages_seen == [1, 2, 3]


def test_azure_multipage_pdf_pages_array():
    payload = base64.b64encode(_pdf(2)).decode()
    r = client.post(
        "/documentintelligence/documentModels/prebuilt-read:analyze",
        json={"base64Source": payload},
    )
    assert r.status_code == 202
    op = r.headers["Operation-Location"]
    path = "/" + op.split("/", 3)[3]
    ar = client.get(path).json()["analyzeResult"]
    assert len(ar["pages"]) == 2
    assert [p["pageNumber"] for p in ar["pages"]] == [1, 2]


def test_azure_multipage_invoice_kvs_carry_pagenumber():
    payload = base64.b64encode(_pdf(2)).decode()
    r = client.post(
        "/documentintelligence/documentModels/prebuilt-invoice:analyze",
        json={"base64Source": payload},
    )
    op = r.headers["Operation-Location"]
    path = "/" + op.split("/", 3)[3]
    ar = client.get(path).json()["analyzeResult"]
    # mock backend returns key_values per page, so we get 2x the single-page count
    assert "keyValuePairs" in ar
    page_nums = {kv["key"]["boundingRegions"][0]["pageNumber"] for kv in ar["keyValuePairs"]}
    assert page_nums == {1, 2}


def test_non_pdf_input_still_single_page():
    payload = base64.b64encode(b"raster-bytes").decode()
    r = client.post(
        "/",
        headers={"X-Amz-Target": "Textract.DetectDocumentText"},
        json={"Document": {"Bytes": payload}},
    )
    assert r.json()["DocumentMetadata"]["Pages"] == 1
