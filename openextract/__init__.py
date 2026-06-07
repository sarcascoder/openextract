"""OpenExtract — a self-hosted, API-compatible drop-in replacement for AWS Textract.

Point your existing boto3 Textract client at this server (endpoint_url=...) and it
works unchanged, but inference runs on a local/quantized VLM (or Tesseract) instead
of metered cloud OCR. ~16-40x cheaper, data never leaves your machine.
"""

__version__ = "0.1.0"
