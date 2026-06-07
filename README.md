# OpenExtract

**A self-hosted, API-compatible drop-in replacement for AWS Textract.**
Point your existing `boto3` Textract code at OpenExtract by changing **one line** (`endpoint_url`).
Inference runs on a local/quantized vision-LLM (or Tesseract) instead of metered cloud OCR —
so it's **~16–40× cheaper** and your documents **never leave your machine**.

```python
import boto3
client = boto3.client(
    "textract",
    endpoint_url="http://localhost:8080",   # <-- the only change. delete it to go back to AWS.
    region_name="us-east-1",
    aws_access_key_id="local", aws_secret_access_key="local",
)
resp = client.detect_document_text(Document={"Bytes": img_bytes})   # identical Textract code
```

## Why this exists

Every OSS OCR engine (Tesseract, PaddleOCR, DocTR, GOT-OCR) outputs raw text or coordinates and
forces you to rebuild all the parsing. None of them speak the cloud providers' API shape — so
leaving Textract means a code rewrite. **OpenExtract is the shim that makes leaving free:** same
request, same `Block` response structure, your code unchanged.

### The bill it kills (published mid-2026 pricing)

| Operation | AWS Textract | OpenExtract (local A100) | Cheaper by |
|---|---|---|---|
| Plain text (`DetectDocumentText`) | $1.50 / 1k pages | ~$0.09 / 1k pages | ~16× |
| Forms + Tables (`AnalyzeDocument`) | $65.00 / 1k pages | ~$0.09 / 1k pages | ~700× |
| 200k forms-pages / month | ~$13,000 / mo | <$50 / mo + GPU | — |

Plus: no per-cloud egress fees, no per-processor hosting fees, full data residency / HIPAA-friendly
air-gap.

## Quickstart

```bash
pip install openextract
openextract --backend mock          # runs anywhere, no GPU, for the demo/tests
# then, in another shell:
python examples/boto3_dropin.py
```

Production backend (quantized VLM via Ollama / vLLM / RunPod, OpenAI-compatible):

```bash
export OPENEXTRACT_VLM_BASE_URL=http://localhost:11434/v1
export OPENEXTRACT_VLM_MODEL=qwen2.5-vl:7b
openextract --backend vlm
```

CPU baseline (Tesseract):

```bash
pip install "openextract[tesseract]"   # needs the tesseract system binary
openextract --backend tesseract
```

## Compatibility

**AWS Textract** — AWS JSON 1.1 wire protocol on `/` (dispatches on `X-Amz-Target`), so real
`boto3` works unchanged.
- `DetectDocumentText`, `AnalyzeDocument` (`FORMS`, `TABLES`).
- `Document.Bytes` and `Document.S3Object` (`Bucket`/`Name`/`Version`) inputs.
- `Block` structure mirrors Textract: `PAGE`/`LINE`/`WORD`/`KEY_VALUE_SET`/`TABLE`/`CELL`,
  normalized `Geometry`, `Relationships`, `Confidence`.

**Azure AI Document Intelligence** — the async REST flow: `POST .../documentModels/{model}:analyze`
returns `202` + `Operation-Location`; poll it for the `analyzeResult`. Model ids map to features:
`prebuilt-read` (text), `prebuilt-layout` (+tables), `prebuilt-document` / `prebuilt-invoice`
(+key/value pairs). Polygons + `0..1` confidences in Azure's shape. Accepts `base64Source` or
`urlSource`.

**Google Document AI** — sync `:process` on
`/v1/projects/{p}/locations/{l}/processors/{id}:process`. `rawDocument.content` (base64) in;
`{document: {text, pages: [{layout, lines, tokens, formFields, tables, ...}]}}` out, in Google's
shape (`textAnchor.textSegments` offsets into `document.text`, pixel `boundingPoly.vertices`,
0..1 `confidence`). Feature set inferred from processor id: OCR / FORM_PARSER / LAYOUT_PARSER /
INVOICE / EXPENSE.

**Multi-page PDFs** — submit a PDF directly; OpenExtract rasterizes each page and runs the backend
per page. `DocumentMetadata.Pages` (Textract), `pages[]` (Azure), and `document.pages[]` (Google)
carry the correct page indices. Install with `pip install "openextract[pdf]"` (uses PyMuPDF; no
system deps).

Convenience REST routes (`/v1/detect-document-text`, `/v1/analyze-document`) for non-SDK callers.

## Backends

| Backend | Use | Deps |
|---|---|---|
| `mock` | demo, CI, tests (deterministic, zero deps) | none |
| `tesseract` | CPU text baseline | `tesseract` binary + `pytesseract` |
| `vlm` | **production** — quantized VLM, forms+tables | any OpenAI-compatible endpoint |

## Benchmark = the go/no-go gate

`bench/benchmark.py` measures local accuracy and cost vs. Textract on your own pages. If local
forms+tables accuracy is within a few points of Textract, the thesis holds. **Run this first.**

Reproduce the included sample set with `python bench/gen_samples.py`. Verified CPU baseline
(Tesseract backend, no GPU): **100% line accuracy, 0.17s/page, ~722× cheaper than Textract on
forms+tables** — but **0% field accuracy**, since Tesseract has no forms understanding. That gap
is exactly why the `vlm` backend exists; see [`bench/RESULTS.md`](bench/RESULTS.md).

## Pro: calibrated confidence + human review

Cloud OCR hands you an overconfident number per field. The Pro layer makes extraction
*trustworthy enough to auto-accept*: it routes only low-confidence fields to a human and
auto-accepts the rest, with optional self-consistency (run a stochastic VLM N times; a
field's confidence is how often the runs agree).

```bash
curl -s localhost:8080/v1/extract-with-confidence \
  -d '{"Document":{"Bytes":"<base64>"},"threshold":90,"samples":5}'
```
```json
{
  "threshold": 90, "samples": 5, "auto_accept_rate": 0.67,
  "fields": [
    {"key": "Invoice Number", "value": "INV-1042", "confidence": 99.0, "status": "auto_accept", "agreement": 1.0},
    {"key": "Total Due", "value": "$1,250.00", "confidence": 74.2, "status": "review", "agreement": 0.8}
  ],
  "review_queue": [ {"key": "Total Due", "...": "..."} ]
}
```

Corrections become few-shot examples you feed back to the model (`record_correction`), so
accuracy improves over time. This is the basis of the paid tier.

A minimal local review UI is bundled: every call to `/v1/extract-with-confidence` persists a
report (pass `"persist": false` to opt out); visit `http://localhost:8080/review` to see
pending queues, correct fields in-line, and feed corrections back to the model. Single-binary,
single-node, no extra services to run.

## Roadmap

- ~~Azure Document Intelligence wire compatibility~~ — **shipped**.
- ~~Google Document AI wire compatibility~~ — **shipped** (third drop-in target).
- ~~Per-field confidence + self-consistency review layer~~ — **shipped**.
- ~~S3Object/urlSource input, multi-page PDFs~~ — **shipped**.
- ~~Local review UI for the Pro queue~~ — **shipped**.
- Managed hosted endpoint (pay-per-page far below AWS) for teams who don't want to run GPUs.
- Improved VLM prompt + few-shot injection from saved corrections.

## License

Apache-2.0 © sarcascoder
