"""Tests for Azure Document Intelligence wire compatibility (async analyze + poll)."""
import base64

from fastapi.testclient import TestClient

from openextract.app import app

client = TestClient(app)
SAMPLE = base64.b64encode(b"doc").decode()


def _analyze(model_id: str):
    r = client.post(f"/documentintelligence/documentModels/{model_id}:analyze",
                    json={"base64Source": SAMPLE})
    assert r.status_code == 202
    op = r.headers["Operation-Location"]
    # Strip scheme/host -> path the TestClient can GET.
    path = "/" + op.split("/", 3)[3]
    return client.get(path)


def test_read_model_text_only():
    r = _analyze("prebuilt-read")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "succeeded"
    ar = data["analyzeResult"]
    assert ar["modelId"] == "prebuilt-read"
    assert ar["pages"][0]["unit"] == "pixel"
    assert ar["pages"][0]["lines"]
    assert "keyValuePairs" not in ar       # read = no forms
    assert "tables" not in ar              # read = no tables


def test_layout_model_has_tables_no_forms():
    ar = _analyze("prebuilt-layout").json()["analyzeResult"]
    assert "tables" in ar and ar["tables"][0]["rowCount"] >= 1
    assert "keyValuePairs" not in ar


def test_document_model_has_forms_and_tables():
    ar = _analyze("prebuilt-document").json()["analyzeResult"]
    assert "keyValuePairs" in ar and len(ar["keyValuePairs"]) >= 1
    assert "tables" in ar
    # Confidence normalized to 0..1 (Azure style), not 0..100.
    assert 0.0 <= ar["keyValuePairs"][0]["confidence"] <= 1.0
    poly = ar["pages"][0]["lines"][0]["polygon"]
    assert len(poly) == 8                  # 4 corners flattened


def test_missing_source_errors():
    r = client.post("/documentintelligence/documentModels/prebuilt-read:analyze", json={})
    assert r.status_code == 400


def test_unknown_result_id_404():
    r = client.get("/documentintelligence/documentModels/prebuilt-read/analyzeResults/nope")
    assert r.status_code == 404
