"""Local review UI tests."""
import base64

from fastapi.testclient import TestClient

from openextract.app import app
from openextract.review import _REPORTS

client = TestClient(app)
SAMPLE = base64.b64encode(b"doc").decode()


def _submit(threshold: float = 99.5) -> str:
    """Submit a doc with a high threshold so something lands in the review queue."""
    r = client.post(
        "/v1/extract-with-confidence",
        json={"Document": {"Bytes": SAMPLE}, "threshold": threshold, "samples": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert "report_id" in body
    assert len(body["review_queue"]) >= 1
    return body["report_id"]


def test_confidence_endpoint_returns_report_id():
    rid = _submit()
    assert rid in _REPORTS


def test_confidence_endpoint_respects_persist_false():
    before = len(_REPORTS)
    r = client.post(
        "/v1/extract-with-confidence",
        json={"Document": {"Bytes": SAMPLE}, "persist": False},
    )
    assert "report_id" not in r.json()
    assert len(_REPORTS) == before


def test_review_index_lists_report():
    rid = _submit()
    r = client.get("/review")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert rid[:8] in r.text


def test_review_detail_shows_review_field():
    rid = _submit()
    r = client.get(f"/review/{rid}")
    assert r.status_code == 200
    # MockBackend's KeyValue keys are "Invoice Number" / "Total Due"
    assert "Invoice Number" in r.text or "Total Due" in r.text
    # A correction form is rendered for review-status fields.
    assert "/correct" in r.text


def test_review_detail_404_for_unknown_id():
    r = client.get("/review/does-not-exist")
    assert r.status_code == 404


def test_correction_removes_field_from_review_queue():
    rid = _submit()
    rep = _REPORTS[rid]
    field = rep.review_queue[0]
    r = client.post(
        f"/review/{rid}/correct",
        data={"key": field.key, "value": "CORRECTED"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == f"/review/{rid}"
    # The field is no longer in review.
    rep = _REPORTS[rid]
    assert all(f.key != field.key for f in rep.review_queue)
    matched = [f for f in rep.fields if f.key == field.key][0]
    assert matched.value == "CORRECTED"
    assert matched.status == "auto_accept"


def test_correction_on_unknown_report_redirects_to_index():
    r = client.post(
        "/review/nope/correct",
        data={"key": "x", "value": "y"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/review"
