#!/usr/bin/env bash
# One-shot: stand up a quantized vision-LLM and point OpenExtract at it, then benchmark.
# Use on a RunPod pod (or any GPU box) for a FEW HOURS to get the launch accuracy number.
# This is one-time validation, not an ongoing cost — the OSS product self-hosts on the
# user's own hardware.
#
# Usage:
#   bash scripts/runpod_vlm.sh [MODEL]
#   bash scripts/runpod_vlm.sh qwen2.5-vl:7b
set -euo pipefail

MODEL="${1:-qwen2.5-vl:7b}"
PORT="${PORT:-8080}"

echo ">> Installing Ollama (skips if present)…"
command -v ollama >/dev/null 2>&1 || curl -fsSL https://ollama.com/install.sh | sh

echo ">> Starting Ollama server…"
ollama serve >/tmp/ollama.log 2>&1 &
sleep 5

echo ">> Pulling model: $MODEL (one-time download)…"
ollama pull "$MODEL"

echo ">> Installing OpenExtract…"
pip install -e . >/dev/null

echo ">> Generating benchmark samples (if none)…"
[ -z "$(ls bench/data/*.png 2>/dev/null)" ] && { pip install -q pillow; python bench/gen_samples.py; }

echo ">> Starting OpenExtract with the VLM backend on :$PORT…"
export OPENEXTRACT_BACKEND=vlm
export OPENEXTRACT_VLM_BASE_URL="http://localhost:11434/v1"
export OPENEXTRACT_VLM_MODEL="$MODEL"
openextract --backend vlm --port "$PORT" >/tmp/openextract.log 2>&1 &
sleep 6

echo ">> Running benchmark vs Textract pricing…"
python bench/benchmark.py --endpoint "http://localhost:$PORT"

echo ""
echo ">> Done. To compare another model:  bash scripts/runpod_vlm.sh <model-tag>"
echo ">> Add your own labeled pages to bench/data/ for a real-world number."
