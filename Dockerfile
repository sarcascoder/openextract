FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY openextract ./openextract
RUN pip install --no-cache-dir .

# Optional: install Tesseract backend deps + binary
# RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
#     && pip install --no-cache-dir ".[tesseract]" && rm -rf /var/lib/apt/lists/*

ENV OPENEXTRACT_BACKEND=mock
EXPOSE 8080
CMD ["openextract", "--host", "0.0.0.0", "--port", "8080"]
