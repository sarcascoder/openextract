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

## Next: VLM backend (the launch number)

Run a quantized vision-LLM and re-run the same benchmark:

```bash
# one-shot setup (CPU works for small models; GPU for speed) — see scripts/runpod_vlm.sh
export OPENEXTRACT_VLM_BASE_URL=http://localhost:11434/v1
export OPENEXTRACT_VLM_MODEL=qwen2.5-vl:7b
OPENEXTRACT_BACKEND=vlm openextract --port 8080 &
python bench/benchmark.py --endpoint http://localhost:8080
```

Target: forms+tables field accuracy within a few points of Textract. If it clears that bar,
the cost story (16–722× depending on operation) plus on-prem data residency is launch-ready.

## Notes
- These pages are clean synthetic renders; real-world scans/photos are harder. Add your own
  labeled pages to `bench/data/` (`<name>.png` + `<name>.json`) before trusting the numbers.
- Cost figures use published mid-2026 AWS rates ($1.50/1k text, $65/1k forms+tables) vs an
  amortized ~$0.09/1k local GPU estimate.
