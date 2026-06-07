"""Document preprocessing: PDF rasterization to per-page image bytes.

Backends consume raster images (PNG/JPEG bytes). A multi-page PDF is rasterized
to N images so the backend runs once per page; single-page raster inputs pass
through unchanged. Keep PDF support optional: PyMuPDF is a heavy native dep, so
it lives in the `[pdf]` extra and is only imported when a PDF is detected.
"""
from __future__ import annotations

PDF_MAGIC = b"%PDF"
DEFAULT_DPI = 200


def is_pdf(document_bytes: bytes) -> bool:
    return document_bytes[:4] == PDF_MAGIC


def rasterize_pdf(document_bytes: bytes, *, dpi: int = DEFAULT_DPI) -> list[bytes]:
    """Render each PDF page to PNG bytes. Requires `pip install openextract[pdf]`."""
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise RuntimeError(
            "PDF input requires PyMuPDF. Install with: pip install 'openextract[pdf]'"
        ) from e
    doc = fitz.open(stream=document_bytes, filetype="pdf")
    try:
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        return [doc.load_page(i).get_pixmap(matrix=matrix).tobytes("png")
                for i in range(doc.page_count)]
    finally:
        doc.close()


def split_pages(document_bytes: bytes) -> list[bytes]:
    """One raster image per page. PDFs are rasterized; raster inputs pass through."""
    if is_pdf(document_bytes):
        return rasterize_pdf(document_bytes)
    return [document_bytes]
