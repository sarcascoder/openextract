"""Optional integration point for OpenExtract Pro.

If the closed-source `openextract_pro` package is installed (and licensed), its
`plugin.mount(app, backend)` hook is invoked at server boot to register the Pro
endpoints (calibrated confidence, /review UI, record_correction). When it isn't
installed the OSS server runs unchanged — no behavior, no errors.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from .backends.base import Backend

log = logging.getLogger(__name__)


def maybe_mount(app: "FastAPI", backend: "Backend") -> bool:
    """Mount the Pro plugin if importable + licensed. Returns True if mounted."""
    try:
        from openextract_pro.plugin import mount
    except ImportError:
        return False
    try:
        return bool(mount(app, backend))
    except Exception:
        log.exception("openextract_pro plugin failed to mount; continuing without Pro.")
        return False
