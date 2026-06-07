"""Smoke + protocol tests. Run with: pytest -q"""
import base64

from fastapi.testclient import TestClient

from openextract.app import app

client = TestClient(app)
SAMPLE = base64.b64encode(b"fake-document-bytes").decode()


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_detect_document_text_aws_protocol():
    r = client.post(
        "/",
        headers={"X-Amz-Target": "Textract.DetectDocumentText",
                 "Content-Type": "application/x-amz-json-1.1"},
        json={"Document": {"Bytes": SAMPLE}},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["DetectDocumentTextModelVersion"] == "1.0"
    block_types = {b["BlockType"] for b in data["Blocks"]}
    assert "PAGE" in block_types and "LINE" in block_types and "WORD" in block_types
    # PAGE must be first, like real Textract.
    assert data["Blocks"][0]["BlockType"] == "PAGE"
    # Geometry is normalized 0..1.
    for b in data["Blocks"]:
        bb = b["Geometry"]["BoundingBox"]
        assert 0.0 <= bb["Left"] <= 1.0 and 0.0 <= bb["Top"] <= 1.0


def test_analyze_document_forms_and_tables():
    r = client.post(
        "/",
        headers={"X-Amz-Target": "Textract.AnalyzeDocument"},
        json={"Document": {"Bytes": SAMPLE}, "FeatureTypes": ["FORMS", "TABLES"]},
    )
    assert r.status_code == 200
    data = r.json()
    types = [b["BlockType"] for b in data["Blocks"]]
    assert "KEY_VALUE_SET" in types
    assert "TABLE" in types and "CELL" in types
    # KEY/VALUE entity types present.
    kv = [b for b in data["Blocks"] if b["BlockType"] == "KEY_VALUE_SET"]
    assert any("KEY" in b.get("EntityTypes", []) for b in kv)
    assert any("VALUE" in b.get("EntityTypes", []) for b in kv)


def test_unknown_operation_errors():
    r = client.post("/", headers={"X-Amz-Target": "Textract.Nope"},
                    json={"Document": {"Bytes": SAMPLE}})
    assert r.status_code == 400
    assert r.json()["__type"] == "UnknownOperationException"


def test_rest_route():
    r = client.post("/v1/analyze-document",
                    json={"Document": {"Bytes": SAMPLE}, "FeatureTypes": ["FORMS"]})
    assert r.status_code == 200
    assert "Blocks" in r.json()
