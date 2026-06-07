from __future__ import annotations

import base64
import json
import os
import urllib.request

from .base import Backend
from ..textract_schema import Box, KeyValue, Line, Page, Table, Word

# Prompt the VLM to emit a strict JSON layout we can map to Textract blocks.
_PROMPT = """You are an OCR + document-layout engine. Read the page image and return ONLY JSON:
{
  "width": <page pixel width>, "height": <page pixel height>,
  "lines": [{"text": str, "box": [x,y,w,h], "confidence": 0-100,
             "words": [{"text": str, "box": [x,y,w,h], "confidence": 0-100}]}],
  "key_values": [{"key": str, "value": str, "key_box":[x,y,w,h], "value_box":[x,y,w,h], "confidence":0-100}],
  "tables": [{"rows": [[cell,...],...], "box":[x,y,w,h], "confidence":0-100}]
}
Boxes are pixel coordinates. Include key_values only if forms are requested, tables only if tables requested.
No prose, no markdown fences."""


class VLMBackend(Backend):
    """Quantized vision-LLM backend via any OpenAI-compatible endpoint.

    Works with Ollama, vLLM, llama.cpp server, or a RunPod pod. Configure via env:
      OPENEXTRACT_VLM_BASE_URL   (e.g. http://localhost:11434/v1)
      OPENEXTRACT_VLM_MODEL      (e.g. qwen2.5-vl:7b)
      OPENEXTRACT_VLM_API_KEY    (optional)
    This is the production path that delivers the ~16-40x cost saving vs cloud OCR.
    """

    name = "vlm"

    def __init__(self) -> None:
        self.base_url = os.environ.get("OPENEXTRACT_VLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
        self.model = os.environ.get("OPENEXTRACT_VLM_MODEL", "qwen2.5-vl:7b")
        self.api_key = os.environ.get("OPENEXTRACT_VLM_API_KEY", "")

    def extract(self, document_bytes: bytes, *, feature_types: list[str] | None = None) -> Page:
        feats = feature_types or []
        b64 = base64.b64encode(document_bytes).decode()
        instruction = _PROMPT
        if "FORMS" not in feats:
            instruction += "\n(Do not return key_values.)"
        if "TABLES" not in feats:
            instruction += "\n(Do not return tables.)"

        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {})},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            content = json.loads(resp.read())["choices"][0]["message"]["content"]
        return self._parse(content)

    @staticmethod
    def _parse(content: str) -> Page:
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```", 2)[1].lstrip("json").strip()
        data = json.loads(content)

        def box(b):
            return Box(float(b[0]), float(b[1]), float(b[2]), float(b[3]))

        lines = [
            Line(l["text"], box(l["box"]), float(l.get("confidence", 95)),
                 [Word(w["text"], box(w["box"]), float(w.get("confidence", 95)))
                  for w in l.get("words", [])])
            for l in data.get("lines", [])
        ]
        kvs = [
            KeyValue(k["key"], k["value"], box(k["key_box"]), box(k["value_box"]),
                     float(k.get("confidence", 95)))
            for k in data.get("key_values", [])
        ]
        tables = [
            Table(t["rows"], box(t["box"]), float(t.get("confidence", 95)))
            for t in data.get("tables", [])
        ]
        return Page(float(data.get("width", 1000)), float(data.get("height", 1300)),
                    lines, kvs, tables)
