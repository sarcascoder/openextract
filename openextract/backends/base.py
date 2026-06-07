from __future__ import annotations

from abc import ABC, abstractmethod

from ..textract_schema import Page


class Backend(ABC):
    """Turn raw document bytes into a normalized Page."""

    name: str = "base"

    @abstractmethod
    def extract(self, document_bytes: bytes, *, feature_types: list[str] | None = None) -> Page:
        """Return a normalized Page. `feature_types` mirrors Textract (FORMS/TABLES)."""
        raise NotImplementedError
