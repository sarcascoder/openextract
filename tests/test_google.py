"""Google Document AI wire compatibility tests."""
import base64

import pytest
from fastapi.testclient import TestClient

from openextract.app import app

client = TestClient(app)
SAMPLE = base64.b64encode(b"doc").decode()


def _process(processor_id: str, content: str = SAMPLE) -> dict:
    r = client.post(
        f"/v1/projects/demo/locations/us/processors/{processor_id}:process",
        json={"rawDocument": {"content": content, "mimeType": "image/png"}},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_ocr_processor_text_only():
    out = _process("OCR_PROCESSOR_v1")
    doc = out["document"]
    assert doc["text"].startswith("INVOICE")
    assert doc["pages"][0]["pageNumber"] == 1
    assert doc["pages"][0]["lines"]
    assert "formFields" not in doc["pages"][0]
    assert "tables" not in doc["pages"][0]


def test_form_parser_processor_has_form_fields():
    out = _process("FORM_PARSER_PROCESSOR_v2")
    page = out["document"]["pages"][0]
    assert "formFields" in page and len(page["formFields"]) >= 1
    ff = page["formFields"][0]
    assert "textAnchor" in ff["fieldName"]
    assert "textAnchor" in ff["fieldValue"]
    # textAnchor offsets resolve into document.text
    text = out["document"]["text"]
    seg = ff["fieldName"]["textAnchor"]["textSegments"][0]
    s, e = int(seg["startIndex"]), int(seg["endIndex"])
    assert text[s:e] == "Invoice Number:" or text[s:e] == "Total Due:"


def test_layout_parser_has_tables():
    out = _process("LAYOUT_PARSER_PROCESSOR")
    page = out["document"]["pages"][0]
    assert "tables" in page and len(page["tables"]) >= 1
    table = page["tables"][0]
    assert table["headerRows"] and table["bodyRows"]
    cell = table["headerRows"][0]["cells"][0]
    assert cell["rowSpan"] == 1 and cell["colSpan"] == 1
    assert "boundingPoly" in cell["layout"]


def test_invoice_processor_has_forms_and_tables():
    out = _process("INVOICE_PROCESSOR_v1")
    page = out["document"]["pages"][0]
    assert "formFields" in page
    assert "tables" in page


def test_token_text_anchor_resolves_to_word():
    out = _process("OCR_PROCESSOR")
    page = out["document"]["pages"][0]
    text = out["document"]["text"]
    # First token in mock backend is "INVOICE"
    tok = page["tokens"][0]
    seg = tok["layout"]["textAnchor"]["textSegments"][0]
    s, e = int(seg["startIndex"]), int(seg["endIndex"])
    assert text[s:e] == "INVOICE"


def test_bounding_poly_has_four_pixel_vertices():
    out = _process("OCR_PROCESSOR")
    line = out["document"]["pages"][0]["lines"][0]
    verts = line["layout"]["boundingPoly"]["vertices"]
    assert len(verts) == 4
    assert all("x" in v and "y" in v for v in verts)
    assert verts[0]["x"] >= 0 and verts[0]["y"] >= 0  # pixel coords, not normalized


def test_missing_raw_document_400():
    r = client.post(
        "/v1/projects/demo/locations/us/processors/OCR_PROCESSOR:process", json={}
    )
    assert r.status_code == 400
    assert r.json()["error"]["status"] == "INVALID_ARGUMENT"


def test_dimension_unit_is_pixels():
    out = _process("OCR_PROCESSOR")
    dim = out["document"]["pages"][0]["dimension"]
    assert dim["unit"] == "pixels"
    assert dim["width"] > 0 and dim["height"] > 0


@pytest.mark.parametrize("processor_id,expect_forms,expect_tables", [
    ("OCR_PROCESSOR_v1", False, False),
    ("FORM_PARSER_PROCESSOR", True, True),
    ("LAYOUT_PARSER_PROCESSOR", False, True),
    ("INVOICE_PROCESSOR", True, True),
    ("EXPENSE_PROCESSOR", True, False),
])
def test_processor_id_drives_feature_set(processor_id, expect_forms, expect_tables):
    page = _process(processor_id)["document"]["pages"][0]
    assert ("formFields" in page) is expect_forms
    assert ("tables" in page) is expect_tables


def test_google_multipage_pdf():
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    for i in range(2):
        p = doc.new_page(width=595, height=842)
        p.insert_text((72, 100), f"Page {i + 1}")
    pdf_b64 = base64.b64encode(doc.tobytes()).decode()
    doc.close()
    out = _process("OCR_PROCESSOR", content=pdf_b64)
    assert len(out["document"]["pages"]) == 2
    assert [p["pageNumber"] for p in out["document"]["pages"]] == [1, 2]
