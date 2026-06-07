"""Pro feature: calibrated confidence + human-review routing.

Cloud OCR gives you a number per field, but models are overconfident — a raw 99%
is not a 99% chance of being right. This layer adds two things that make extraction
*trustworthy* enough to auto-accept:

  1. Self-consistency: run a stochastic backend N times; a field's confidence is how
     often the runs agree on the same value (disagreement = uncertainty the model
     hides). Deterministic backends fall back to reported confidence.
  2. A safe auto-accept threshold + a review queue: fields above the threshold are
     auto-accepted; the rest are routed to a human, so you get straight-through
     processing where it's safe and review only where it isn't.

This is the paid tier. The OSS core extracts; this decides what you can trust.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Optional

from .textract_schema import Page


@dataclass
class FieldResult:
    key: str
    value: str
    confidence: float          # 0..100
    status: str                # "auto_accept" | "review"
    agreement: Optional[float] = None  # fraction of runs agreeing (self-consistency)


@dataclass
class ConfidenceReport:
    threshold: float
    samples: int
    fields: list[FieldResult] = field(default_factory=list)
    review_queue: list[FieldResult] = field(default_factory=list)
    auto_accept_rate: float = 0.0

    def to_dict(self) -> dict:
        return {
            "threshold": self.threshold,
            "samples": self.samples,
            "auto_accept_rate": round(self.auto_accept_rate, 4),
            "fields": [asdict(f) for f in self.fields],
            "review_queue": [asdict(f) for f in self.review_queue],
        }


def _fields_from_page(page: Page) -> dict[str, tuple[str, float]]:
    """key -> (value, reported_confidence)."""
    out: dict[str, tuple[str, float]] = {}
    for kv in page.key_values:
        out[kv.key.strip(": ")] = (kv.value.strip(), kv.confidence)
    return out


def aggregate(pages: list[Page], *, threshold: float = 90.0) -> ConfidenceReport:
    """Build a confidence report from one or more extraction runs of the same document.

    - len(pages) == 1  -> use the backend's reported per-field confidence.
    - len(pages) > 1   -> self-consistency: modal value wins; confidence = agreement %.
    """
    if not pages:
        return ConfidenceReport(threshold=threshold, samples=0)

    samples = len(pages)
    per_run = [_fields_from_page(p) for p in pages]
    all_keys: list[str] = []
    for run in per_run:
        for k in run:
            if k not in all_keys:
                all_keys.append(k)

    results: list[FieldResult] = []
    for key in all_keys:
        values = [run[key][0] for run in per_run if key in run]
        reported = [run[key][1] for run in per_run if key in run]

        if samples > 1:
            counts = Counter(values)
            modal_value, modal_n = counts.most_common(1)[0]
            agreement = modal_n / samples
            # Confidence is driven by agreement, nudged by reported confidence on the
            # runs that produced the modal value.
            modal_conf = [reported[i] for i, v in enumerate(values) if v == modal_value]
            blended = 100.0 * agreement * (sum(modal_conf) / len(modal_conf) / 100.0)
            value, confidence, agr = modal_value, round(blended, 2), round(agreement, 3)
        else:
            value = values[0]
            confidence = round(reported[0], 2)
            agr = None

        status = "auto_accept" if confidence >= threshold else "review"
        results.append(FieldResult(key, value, confidence, status, agr))

    review = [f for f in results if f.status == "review"]
    rate = (len(results) - len(review)) / len(results) if results else 0.0
    return ConfidenceReport(
        threshold=threshold, samples=samples,
        fields=results, review_queue=review, auto_accept_rate=rate,
    )


def record_correction(report: ConfidenceReport, key: str, corrected_value: str) -> dict:
    """Apply a human correction; returns a few-shot example for the extractor prompt.

    The corrected value becomes ground truth and an example you feed back to the model
    so it stops making the same mistake — the correction loop that improves accuracy
    over time.
    """
    for f in report.fields:
        if f.key == key:
            f.value = corrected_value
            f.confidence = 100.0
            f.status = "auto_accept"
            if f in report.review_queue:
                report.review_queue.remove(f)
            break
    report.auto_accept_rate = (
        (len(report.fields) - len(report.review_queue)) / len(report.fields)
        if report.fields else 0.0
    )
    return {"field": key, "value": corrected_value,
            "fewshot": f"{key}: {corrected_value}"}
