"""The killer demo: real boto3 Textract client, ONE line changed.

Start the server first:
    openextract --backend mock        # or: tesseract / vlm

Then run:
    python examples/boto3_dropin.py

The ONLY difference from production AWS code is `endpoint_url`. Everything else —
the client, the call, the response parsing — is identical Textract code.
"""
import boto3

# --- The one and only change vs. AWS: point at your own server ---
ENDPOINT = "http://localhost:8080"

client = boto3.client(
    "textract",
    endpoint_url=ENDPOINT,            # <-- delete this line to go back to real AWS
    region_name="us-east-1",
    aws_access_key_id="local",        # ignored by the local server
    aws_secret_access_key="local",
)

# Any document bytes work with the mock backend; use a real image for tesseract/vlm.
with open(__file__, "rb") as f:
    sample = f.read()

# ---- Identical to AWS Textract usage from here down ----
resp = client.detect_document_text(Document={"Bytes": sample})
print("Model version:", resp["DetectDocumentTextModelVersion"])
print("Lines detected:")
for block in resp["Blocks"]:
    if block["BlockType"] == "LINE":
        print(f"  [{block['Confidence']:.1f}] {block['Text']}")

analysis = client.analyze_document(Document={"Bytes": sample}, FeatureTypes=["FORMS", "TABLES"])
kv_keys = [b for b in analysis["Blocks"]
           if b["BlockType"] == "KEY_VALUE_SET" and "KEY" in b.get("EntityTypes", [])]
print(f"\nForm fields found: {len(kv_keys)}")
tables = [b for b in analysis["Blocks"] if b["BlockType"] == "TABLE"]
print(f"Tables found: {len(tables)}")
print("\nSame boto3 code. No AWS bill. Data never left the machine.")
