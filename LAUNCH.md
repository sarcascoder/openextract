# OpenExtract — Launch Kit

Everything you need to promote it. Copy/paste ready. Launch order: GitHub → Show HN
(Tue–Thu, ~8–10am ET) → same day post to r/selfhosted → next day r/aws + X.

---

## Positioning (one sentence)

> Self-hosted, drop-in replacement for AWS Textract. Change one line (`endpoint_url`) and your existing boto3 code runs on a local model instead — ~16–40× cheaper, data never leaves your machine.

The hook is **not** "better OCR." It's **"keep your code, kill the bill, keep your data."**

---

## Show HN

**Title:**
`Show HN: OpenExtract – Self-hosted drop-in replacement for AWS Textract`

**Body:**
```
I kept seeing the same complaint: AWS Textract is $1.50/1k pages for plain text but
$65/1k once you turn on forms+tables, and you can't take your data off their cloud.
Every open-source OCR engine (Tesseract, PaddleOCR, DocTR) gives you raw text or
coordinates and makes you rebuild all the parsing — none of them speak Textract's API,
so leaving means a rewrite.

OpenExtract is the missing shim. It speaks Textract's exact JSON wire protocol, so a
real boto3 client works unchanged:

    client = boto3.client("textract", endpoint_url="http://localhost:8080", ...)
    client.detect_document_text(Document={"Bytes": img})   # same code, no AWS

Behind the API you plug in a backend: Tesseract for a free CPU baseline, or any
OpenAI-compatible vision model (Ollama / vLLM / a cheap GPU box) for forms+tables.
It returns the same PAGE/LINE/WORD/KEY_VALUE_SET/TABLE/CELL Block structure, so your
downstream parsing doesn't change.

Apache-2.0, runs in a container, no telemetry. Repo + benchmark harness (accuracy +
cost vs Textract on your own pages) in the link.

Honest status: API-compatibility for DetectDocumentText and AnalyzeDocument
(FORMS/TABLES) is done and tested. Google Document AI / Azure DI compatibility and
multi-page PDF are next. Would love feedback on which API surface to clone next.
```

**Replying to comments:** be honest about accuracy ("local VLMs are close on most layouts; run the benchmark on your docs and tell me where it breaks"), and never overclaim. HN rewards candor.

---

## r/selfhosted

**Title:** `OpenExtract: self-hosted OCR that's a drop-in replacement for AWS Textract (Apache-2.0)`

**Body:**
```
Built this because I wanted document OCR/forms extraction without sending invoices to
a cloud API or paying $65/1k pages. It mimics AWS Textract's API exactly, so if you (or
some tool you use) already speak Textract, you point it at your own box and nothing else
changes. Runs in Docker, CPU-only mode via Tesseract or bring your own local VLM via
Ollama/vLLM. No accounts, no telemetry, data stays home. Feedback welcome.
```

---

## r/aws (and r/devops)

**Title:** `Made an open-source, Textract-API-compatible server you can self-host to cut the bill`

**Body:** lead with the cost table, note it's for cost/data-residency cases, not a knock
on AWS. Mention boto3 `endpoint_url` is all that changes. Expect pushback on accuracy —
point to the benchmark.

---

## Product Hunt tagline

`OpenExtract — Self-hosted AWS Textract replacement. Change one line, keep your data.`

## X / Twitter

```
Spent the weekend killing my AWS Textract bill.

OpenExtract speaks Textract's exact API, so:

  boto3.client("textract", endpoint_url="http://localhost:8080")

…and your existing code runs on a local model. ~16–40x cheaper, data never leaves the box.

Apache-2.0 👇
```

---

## Demo GIF script (record with asciinema or a screen recorder, ~20s)

1. `openextract --backend mock`  → show "serving on :8080".
2. Split screen: `python examples/boto3_dropin.py` → lines + fields + tables print.
3. Highlight the single `endpoint_url=` line with a callout: "this is the only change."
4. End card: "Same boto3 code. No AWS bill. Data stays home. github.com/sarcascoder/openextract"

Put the GIF at the top of the README — it's the single highest-converting asset.

---

## The growth loop (repeatable, no ad spend)

Every time a new local VLM drops (Qwen, GOT-OCR, dots.ocr, etc.), re-run `bench/benchmark.py`
and post "local model X vs AWS Textract: accuracy + cost." Each post is fresh, useful, and
links back. The benchmark is the marketing.

---

## Monetization ladder (turn on later, only when there's demand)

1. **OSS self-host** — free. Drives stars + credibility.
2. **Pro license ($49–199/mo, CPU-only)** — per-field confidence + self-consistency review
   (the Parakh layer), schema templates, batch dashboard. No infra cost to us.
3. **Managed endpoint** — we host the GPU and charge per page far under AWS — only stand this
   up once paying users justify it. Until then, zero infra spend.
