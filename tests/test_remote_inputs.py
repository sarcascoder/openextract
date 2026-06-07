"""S3Object (Textract) and urlSource (Azure) input tests.

S3 is exercised by monkeypatching the fetcher so the test runs offline.
urlSource is exercised against a real HTTP server bound to localhost.
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from fastapi.testclient import TestClient

from openextract import kernel
from openextract.app import app

client = TestClient(app)


def test_textract_s3object_fetches_and_extracts(monkeypatch):
    captured: dict = {}

    def fake_fetch(s3: dict) -> bytes:
        captured.update(s3)
        return b"bytes-from-s3"

    monkeypatch.setattr(kernel, "fetch_s3", fake_fetch)

    r = client.post(
        "/",
        headers={"X-Amz-Target": "Textract.DetectDocumentText"},
        json={"Document": {"S3Object": {"Bucket": "my-bkt", "Name": "doc.pdf"}}},
    )
    assert r.status_code == 200
    assert captured == {"Bucket": "my-bkt", "Name": "doc.pdf"}
    assert r.json()["DocumentMetadata"]["Pages"] == 1


def test_textract_s3object_missing_fields():
    r = client.post(
        "/",
        headers={"X-Amz-Target": "Textract.DetectDocumentText"},
        json={"Document": {"S3Object": {"Bucket": "my-bkt"}}},  # no Name
    )
    assert r.status_code == 400
    assert r.json()["__type"] == "InvalidParameterException"


class _FixedHandler(BaseHTTPRequestHandler):
    payload = b"fixture-bytes"

    def do_GET(self):  # noqa: N802 (stdlib name)
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, *args, **kwargs):  # silence
        pass


def _serve_once():
    server = HTTPServer(("127.0.0.1", 0), _FixedHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def test_azure_urlsource_fetches_and_analyzes():
    server, port = _serve_once()
    try:
        r = client.post(
            "/documentintelligence/documentModels/prebuilt-read:analyze",
            json={"urlSource": f"http://127.0.0.1:{port}/doc"},
        )
        assert r.status_code == 202
        op = r.headers["Operation-Location"]
        path = "/" + op.split("/", 3)[3]
        ar = client.get(path).json()["analyzeResult"]
        assert ar["pages"][0]["pageNumber"] == 1
    finally:
        server.shutdown()


def test_azure_no_source_400():
    r = client.post(
        "/documentintelligence/documentModels/prebuilt-read:analyze", json={}
    )
    assert r.status_code == 400


def test_azure_urlsource_rejects_non_http_scheme():
    r = client.post(
        "/documentintelligence/documentModels/prebuilt-read:analyze",
        json={"urlSource": "file:///etc/passwd"},
    )
    assert r.status_code == 400
    assert "scheme" in r.json()["error"]["message"]
