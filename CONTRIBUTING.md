# Contributing to OpenExtract

Thanks for helping make leaving metered cloud OCR free.

## Dev setup

```bash
git clone https://github.com/sarcascoder/openextract
cd openextract
pip install -e ".[dev]"
pytest -q
```

## Where to help most

- **New API-compatibility targets.** Google Document AI and Azure Document Intelligence
  wire compatibility (request/response shapes) unlock more migrations. See `openextract/app.py`.
- **Backends.** New entries under `openextract/backends/` (must return a normalized `Page`).
  High-value: better local VLM prompts, layout/table reconstruction, PDF multi-page.
- **Benchmark datasets.** Add labeled pages under `bench/data/` and report accuracy vs. Textract.

## Ground rules

- Keep the core dependency-light (FastAPI + uvicorn only). Heavy deps go in optional extras.
- Every new operation needs a test in `tests/` and a note in the README compatibility table.
- Match Textract's `Block` shape exactly — compatibility is the whole point.

## License

By contributing you agree your work is licensed under Apache-2.0.
