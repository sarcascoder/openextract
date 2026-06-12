# OpenExtract

> **Self-hosted, API-compatible drop-in replacement for AWS Textract, Azure Document Intelligence, and Google Document AI.**
> Change one line. Cut your bill 16–722×. Bring your own model. Apache-2.0.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/openextract.svg)](https://pypi.org/project/openextract/)
[![Docker](https://img.shields.io/docker/v/sarcascoder/openextract?label=docker)](https://hub.docker.com/r/sarcascoder/openextract)

🌐 **[openextract.dev](https://openextract.dev)** — landing + live cost calculator
📦 **`pip install openextract`** or `docker run sarcascoder/openextract`

---

## The one-line pitch

```python
# before
client = boto3.client("textract", region_name="us-east-1")

# after
client = boto3.client(
    "textract",
    endpoint_url="http://localhost:8080",   # only addition
    region_name="us-east-1",
)
```

Same `Block` structure. Same `KEY_VALUE_SET / TABLE / CELL` hierarchy. Same `Geometry / Confidence / Relationships`. Your downstream parsers don't change.

Works for **Azure Document Intelligence** and **Google Document AI** SDKs the same way — point them at OpenExtract instead of the cloud endpoint.

---

## Cost math

| Operation | AWS Textract | OpenExtract (self-hosted, A100) | Savings |
|---|---:|---:|---:|
| Plain text | $1.50 / 1k pages | ~$0.09 / 1k pages | **~16×** |
| Forms + tables | $65.00 / 1k pages | ~$0.09 / 1k pages | **~722×** |
| Example: 200k forms/month | ~$13,000/mo | <$50/mo + GPU | $156K/yr saved |

Pricing as of mid-2026. Interactive calculator: [openextract.dev](https://openextract.dev).

---

## Quick start

```bash
pip install "openextract[pdf]"
openextract serve --backend mock --port 8080      # zero-GPU demo
```

For production:

```bash
# Classical OCR backend (CPU, plain text only)
openextract serve --backend classical --port 8080

# VLM backend (forms + tables) — point at any OpenAI-compatible inference endpoint
export OPENEXTRACT_VLM_BASE_URL=http://localhost:11434/v1
openextract serve --backend vlm --model your-vlm --port 8080
```

Then in your existing code:

```python
import boto3
client = boto3.client("textract", endpoint_url="http://localhost:8080", region_name="us-east-1")
res = client.analyze_document(Document={"Bytes": pdf_bytes}, FeatureTypes=["FORMS", "TABLES"])
# res.Blocks looks exactly like Textract's response.
```

---

## Supported backends

| Backend | Mode | Line acc. | Field acc. | Speed | Hardware |
|---|---|---|---|---|---|
| `mock` | demo / CI | — | — | <1ms | none |
| `classical` | CPU baseline | 100% | 0% (no forms) | 0.17s / page | CPU |
| `vlm` (compact open-source) | GPU production | 98% | 94% | 1.2s / page | modern laptop or 24GB GPU |
| `vlm` (production-grade open-source) | GPU production | 100% | 100% | 0.6s / page | single modern GPU |

Accuracy numbers are on a clean synthetic test set. **Run [parakh](https://github.com/sarcascoder/parakh) (also OSS) on your corpus for real numbers.**

---

## API surface

### AWS Textract
- `DetectDocumentText` (sync + async)
- `AnalyzeDocument` with `FORMS`, `TABLES`, `SIGNATURES`
- Inputs: `Document.Bytes`, `Document.S3Object`
- Output: full `Block` hierarchy

### Azure Document Intelligence
- `POST .../documentModels/{model}:analyze` → 202 + polling
- Shipped: `prebuilt-read`, `prebuilt-layout`, `prebuilt-document`
- Roadmap: `prebuilt-invoice`, `prebuilt-receipt`, `prebuilt-id`
- Inputs: `base64Source`, `urlSource`

### Google Document AI
- `POST /v1/projects/{p}/locations/{l}/processors/{id}:process`
- Input: `rawDocument.content` (base64)
- Output: structured `document` with `pages[]`, `text`, fields

### Convenience routes
- `POST /v1/detect-document-text` — clean modern endpoint for non-SDK callers
- `POST /v1/analyze-document` — same, with FORMS/TABLES toggle

---

## What this is not

- **Not a magic accuracy upgrade.** If Textract works for you, OpenExtract usually matches it ±a few percent on clean docs. The pitch is cost + privacy + control.
- **Not for the no-GPU crowd at scale.** Tesseract is fine for low-stakes text. Forms + tables need a VLM endpoint somewhere.
- **Not feature-complete on Azure prebuilt models yet.** See roadmap.

---

## OpenExtract Pro (closed-source plugin)

For prod-grade workflows:

- **Calibrated confidence** — per-field, not heuristic
- **Self-consistency** — run N stochastic VLM passes, report agreement
- **Human-review web UI** — flag low-confidence fields for correction
- **Correction → few-shot loop** — your corrections feed future runs

`pip install openextract-pro` + `OPENEXTRACT_LICENSE_KEY`. **$199/mo per deployment.**

Without the key, the OSS server runs unchanged (Pro endpoints return 404).

---

## OpenExtract Cloud (private beta)

Don't want to manage a GPU? Use the hosted version:

- `api.openextract.dev`
- $0.10 / 1k pages
- EU + US regions
- Same Textract-compatible API
- Stripe metered billing

**[Join the private beta →](https://openextract.dev#contact)**

---

## The OpenExtract family

OpenExtract is the flagship of a tightly-scoped family of OSS tools:

| Tool | What it does | When you need it |
|---|---|---|
| **openextract** | drop-in Textract/Azure/Google replacement | always |
| **[parakh](https://github.com/sarcascoder/parakh)** | field-level extraction eval, CI gate | when you ask "does this actually work on my docs?" |
| **[taul](https://github.com/sarcascoder/taul)** | reading-order scoring (separate from char accuracy) | when your OCR is "98%" but your RAG returns garbage |
| **[TurboQuant](https://github.com/sarcascoder/turboquant)** | 5× KV-cache compression on your VLM | when the GPU bill on the OpenExtract backend hurts |

All Apache-2.0 or MIT. All built by the same hand.

---

## Citation / attribution

If OpenExtract saves you money, the kindest thing is to ⭐ the repo and tell a colleague. If you publish using it, please cite:

```bibtex
@misc{tripathi2026openextract,
  title = {OpenExtract: Self-hosted, API-compatible Document AI},
  author = {Tripathi, Anupam Deep},
  year = {2026},
  howpublished = {\url{https://github.com/sarcascoder/openextract}}
}
```

---

## Who's behind this

**Anupam Deep Tripathi** — Founding AI Engineer at Hashteelab, IIT Tirupati '25. Reimplemented ICLR 2026 TurboQuant from scratch. Production OCR / VLM / RAG / edge-AI deployments across legal, manufacturing, automotive, cement.

If your team is paying meaningful money to Textract / Azure DocInt / Google Doc AI and you want a one-call assessment of the migration, my email is below.

📧 **tanupam760@gmail.com** · [LinkedIn](https://www.linkedin.com/in/anupam-tripathi-61567326a/) · [openextract.dev](https://openextract.dev)
