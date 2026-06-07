# Benchmark results

Reproduce: `python bench/gen_samples.py` then run the server and `python bench/benchmark.py`.

## CPU baseline — Tesseract backend (no GPU)

3 synthetic invoice/PO/receipt pages, measured end-to-end through the Textract-compatible API.

| Metric | Result |
|---|---|
| Line (text) accuracy | **100.0%** |
| Field (forms) accuracy | **0.0%** |
| Avg latency | **0.17 s / page** (CPU) |
| Cost vs Textract (forms+tables) | **~722× cheaper** |

**Read this honestly:** Tesseract is a great *text* engine but has no key/value (forms) or
table understanding — hence 0% field accuracy. This is the whole reason the `vlm` backend
exists. The number to publish at launch is **forms+tables accuracy from a local vision-LLM**,
not Tesseract.

## VLM backend — Qwen3.6-35B-A3B (Q8) on RunPod, 2026-06-07

Same 3 synthetic pages, same Textract-compatible API, vision-LLM backend served by
llama.cpp-server on a RunPod GPU pod. Endpoint reached over RunPod's HTTPS proxy.

| Metric | Result |
|---|---|
| Line (text) accuracy | **100.0%** (3/3 pages) |
| Field (forms) accuracy | **100.0%** (3/3 pages) |
| Avg latency | **21.2 s / page** (35B-A3B MoE Q8 over proxy; smaller/dense models will be faster) |
| Cost vs Textract (forms+tables) | **~722× cheaper** at the cited per-1k-pages cost model |

**Read this honestly:** the dataset is 3 *clean synthetic* invoice/receipt pages — not the
real-world test you should trust before signing an enterprise contract. What this number
*does* prove:

1. The full Textract-compatible pipeline (boto3 → wire protocol → `vlm` backend → JSON-mode
   layout extraction → Block response) works end-to-end against a real hosted VLM.
2. A modern quantized multimodal model can produce **clean forms+tables on clean inputs**,
   closing the 0% field-accuracy gap that pure-OCR backends (Tesseract) hit.
3. Latency is dominated by the model + the proxy, not the OpenExtract layer — local
   datacenter latency on dense 7B vision models is typically several seconds, not 20+.

To produce the real-world launch number, drop your own labeled pages into `bench/data/`
(`<name>.png` + `<name>.json` with `lines` and `fields`) and rerun. Then update this file.

### Reproduce

```bash
export OPENEXTRACT_BACKEND=vlm
export OPENEXTRACT_VLM_BASE_URL=https://<your-pod-id>-<port>.proxy.runpod.net/v1
export OPENEXTRACT_VLM_MODEL=<model-name-from-/v1/models>
openextract --backend vlm --port 8080 &
python bench/benchmark.py --endpoint http://localhost:8080
```

## Notes
- These pages are clean synthetic renders; real-world scans/photos are harder. Add your own
  labeled pages to `bench/data/` (`<name>.png` + `<name>.json`) before trusting the numbers.
- Cost figures use published mid-2026 AWS rates ($1.50/1k text, $65/1k forms+tables) vs an
  amortized ~$0.09/1k local GPU estimate.
