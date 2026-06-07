"""Tests for the Pro confidence + review layer."""
import base64

from fastapi.testclient import TestClient

from openextract.app import app
from openextract.confidence import aggregate, record_correction
from openextract.textract_schema import Box, KeyValue, Page

client = TestClient(app)
SAMPLE = base64.b64encode(b"doc").decode()


def _page(fields: dict[str, str], conf: float = 99.0) -> Page:
    b = Box(0, 0, 10, 10)
    return Page(width=100, height=100,
                key_values=[KeyValue(k, v, b, b, conf) for k, v in fields.items()])


def test_single_run_uses_reported_confidence():
    rep = aggregate([_page({"Total": "$10"}, conf=95.0)], threshold=90.0)
    assert rep.samples == 1
    assert rep.fields[0].status == "auto_accept"
    assert rep.fields[0].confidence == 95.0


def test_threshold_routes_to_review():
    rep = aggregate([_page({"Total": "$10"}, conf=95.0)], threshold=99.0)
    assert rep.fields[0].status == "review"
    assert len(rep.review_queue) == 1
    assert rep.auto_accept_rate == 0.0


def test_self_consistency_agreement_drives_confidence():
    # 4 runs: 3 agree on "$10", 1 says "$70" -> agreement 0.75, flagged for review.
    runs = [_page({"Total": "$10"}), _page({"Total": "$10"}),
            _page({"Total": "$10"}), _page({"Total": "$70"})]
    rep = aggregate(runs, threshold=90.0)
    f = rep.fields[0]
    assert rep.samples == 4
    assert f.value == "$10"               # modal value wins
    assert f.agreement == 0.75
    assert f.status == "review"           # 0.75 * 99 = ~74 < 90
    assert f.confidence < 90


def test_unanimous_agreement_auto_accepts():
    runs = [_page({"Invoice": "INV-1"})] * 3
    rep = aggregate(runs, threshold=90.0)
    assert rep.fields[0].agreement == 1.0
    assert rep.fields[0].status == "auto_accept"


def test_record_correction_clears_review():
    rep = aggregate([_page({"Total": "$10"}, conf=50.0)], threshold=90.0)
    assert rep.review_queue
    out = record_correction(rep, "Total", "$12.00")
    assert out["fewshot"] == "Total: $12.00"
    assert rep.fields[0].value == "$12.00"
    assert rep.fields[0].status == "auto_accept"
    assert rep.review_queue == []
    assert rep.auto_accept_rate == 1.0


def test_confidence_endpoint():
    r = client.post("/v1/extract-with-confidence",
                    json={"Document": {"Bytes": SAMPLE}, "threshold": 90, "samples": 1})
    assert r.status_code == 200
    data = r.json()
    assert "fields" in data and "review_queue" in data
    assert data["threshold"] == 90
    assert 0.0 <= data["auto_accept_rate"] <= 1.0
