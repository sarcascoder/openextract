"""Pluggable OCR/extraction backends.

A backend turns raw document bytes into a normalized `Page`. The API layer then
renders that `Page` into Textract-compatible JSON, so the backend is the only thing
that changes when you swap Tesseract for a quantized VLM on RunPod.
"""
from .base import Backend
from .mock import MockBackend

__all__ = ["Backend", "MockBackend", "get_backend"]


def get_backend(name: str) -> Backend:
    name = (name or "mock").lower()
    if name == "mock":
        return MockBackend()
    if name == "tesseract":
        from .tesseract import TesseractBackend
        return TesseractBackend()
    if name == "vlm":
        from .vlm import VLMBackend
        return VLMBackend()
    raise ValueError(f"Unknown backend: {name!r} (expected mock|tesseract|vlm)")
