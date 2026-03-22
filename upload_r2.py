"""
Upload Pipeline Outputs to Cloudflare R2
R2 is S3-compatible with zero egress fees — use boto3 with a custom endpoint.

Required environment variables (set in GitHub Actions secrets):
    R2_ACCOUNT_ID   — your Cloudflare account ID
    R2_ACCESS_KEY   — R2 access key ID
    R2_SECRET_KEY   — R2 secret access key
    R2_BUCKET       — bucket name (e.g. "accra-flood-risk")
"""

import os
import sys
import logging
import boto3
from botocore.client import Config

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")

FILES_TO_UPLOAD = {
    "flood_risk_map.cog.tif": "rasters/flood_risk_map.cog.tif",
    "flood_risk_map.tif":     "rasters/flood_risk_map.tif",
}


def get_r2_client():
    account_id = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def upload_file(client, local_path: str, s3_key: str, bucket: str) -> None:
    log.info("Uploading %s → r2://%s/%s", local_path, bucket, s3_key)
    extra_args = {"ContentType": "image/tiff"}
    # Make COG publicly readable for TiTiler
    if local_path.endswith(".cog.tif"):
        extra_args["ACL"] = "public-read"
    client.upload_file(local_path, bucket, s3_key, ExtraArgs=extra_args)
    log.info("Upload complete ✓")


def main():
    bucket = os.environ["R2_BUCKET"]
    client = get_r2_client()

    for filename, s3_key in FILES_TO_UPLOAD.items():
        local_path = os.path.join(OUTPUT_DIR, filename)
        if not os.path.exists(local_path):
            log.error("File not found: %s — did the processing step run?", local_path)
            sys.exit(1)
        upload_file(client, local_path, s3_key, bucket)

    # Also upload the GeoJSON boundaries
    geojson_path = "data/gadm41_GHA_2.json"
    if os.path.exists(geojson_path):
        upload_file(client, geojson_path, "vectors/gadm41_GHA_2.json", bucket)

    log.info("All uploads complete ✓")


if __name__ == "__main__":
    main()
