"""`openextract` CLI — run the server."""
from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(prog="openextract",
                                     description="Self-hosted Textract-compatible OCR server.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--backend", default=os.environ.get("OPENEXTRACT_BACKEND", "mock"),
                        choices=["mock", "tesseract", "vlm"],
                        help="OCR backend (default: mock; use vlm for production).")
    args = parser.parse_args()

    os.environ["OPENEXTRACT_BACKEND"] = args.backend
    import uvicorn
    print(f"OpenExtract serving on http://{args.host}:{args.port}  (backend={args.backend})")
    print("Point boto3 at it:  boto3.client('textract', endpoint_url='http://localhost:%d', "
          "aws_access_key_id='x', aws_secret_access_key='x', region_name='us-east-1')" % args.port)
    uvicorn.run("openextract.app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
