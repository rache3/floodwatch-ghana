"""
upload_gcs.py — Upload Pipeline Outputs to Google Cloud Storage
================================================================
Replaces the old upload_r2.py (Cloudflare R2) — migrated to GCS.

Uploads processed rasters and vectors to the GCS bucket used by
TiTiler for tile serving and the web map for boundary display.

Authentication:
    Locally    : uses Application Default Credentials (gcloud auth)
    GitHub Actions : uses Workload Identity Federation (no stored keys)

Required environment variables:
    GCS_BUCKET  — bucket name (e.g. "accra-flood-risk")

Optional:
    OUTPUT_DIR  — local directory with processed outputs (default: output)
    DATA_DIR    — local directory with input data (default: data)

Files uploaded:
    output/flood_risk_map.cog.tif  → gs://{bucket}/rasters/flood_risk_map.cog.tif
    output/flood_risk_map.tif      → gs://{bucket}/rasters/flood_risk_map.tif
    data/gadm41_GHA_accra.json     → gs://{bucket}/vectors/gadm41_GHA_accra.json

Usage:
    python scripts/upload_gcs.py

    # Or with explicit bucket:
    GCS_BUCKET=accra-flood-risk python scripts/upload_gcs.py
"""

import os
import logging

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
GCS_BUCKET  = os.getenv("GCS_BUCKET", "accra-flood-risk")
OUTPUT_DIR  = os.getenv("OUTPUT_DIR", "output")
DATA_DIR    = os.getenv("DATA_DIR",   "data")

# Files to upload: local path → GCS destination key
FILES_TO_UPLOAD = {
    # Cloud-Optimised GeoTIFF — served by TiTiler as map tiles
    os.path.join(OUTPUT_DIR, "flood_risk_map.cog.tif"): "rasters/flood_risk_map.cog.tif",

    # Standard GeoTIFF — kept as backup / for offline analysis
    os.path.join(OUTPUT_DIR, "flood_risk_map.tif"):     "rasters/flood_risk_map.tif",

    # District boundaries — used by the web map frontend
    os.path.join(DATA_DIR, "gadm41_GHA_accra.json"):    "vectors/gadm41_GHA_accra.json",
}

# Content types for each file extension
CONTENT_TYPES = {
    ".tif":     "image/tiff",
    ".tiff":    "image/tiff",
    ".json":    "application/json",
    ".geojson": "application/json",
}


def get_gcs_client():
    """
    Create an authenticated Google Cloud Storage client.

    Locally: uses Application Default Credentials from gcloud auth.
    In GitHub Actions: uses Workload Identity Federation — no stored keys.

    Install: pip install google-cloud-storage
    """
    try:
        from google.cloud import storage
    except ImportError:
        log.error("google-cloud-storage not installed")
        log.error("Run: pip install google-cloud-storage")
        raise SystemExit(1)

    try:
        client = storage.Client()
        log.info("GCS client authenticated ✓")
        return client
    except Exception as e:
        log.error("GCS authentication failed: %s", e)
        log.error("Run: gcloud auth application-default login")
        raise SystemExit(1)


def upload_file(client, local_path: str, gcs_key: str, bucket_name: str) -> bool:
    """
    Upload a single file to GCS.

    Sets appropriate content type based on file extension.
    Makes the file publicly readable so TiTiler and the web map
    can access it without authentication.

    Returns True on success, False on failure.
    """

    if not os.path.exists(local_path):
        log.error("File not found: %s", local_path)
        return False

    size_mb = os.path.getsize(local_path) / 1024 / 1024
    log.info("Uploading %s (%.1f MB) → gs://%s/%s",
             local_path, size_mb, bucket_name, gcs_key)

    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_key)

        # Set content type based on file extension
        ext = os.path.splitext(local_path)[1].lower()
        content_type = CONTENT_TYPES.get(ext, "application/octet-stream")
        blob.content_type = content_type

        # Upload the file
        blob.upload_from_filename(local_path)

        # Make publicly readable
        # Required for TiTiler to read COG tiles and web map to load GeoJSON
        blob.make_public()

        log.info("Upload complete ✓  gs://%s/%s", bucket_name, gcs_key)
        log.info("Public URL: %s", blob.public_url)
        return True

    except Exception as e:
        log.error("Upload failed for %s: %s", local_path, e)
        return False


def verify_bucket(client, bucket_name: str) -> bool:
    """
    Check that the GCS bucket exists and is accessible.
    Catches configuration errors early before attempting uploads.
    """
    try:
        bucket = client.bucket(bucket_name)
        bucket.reload()
        log.info("Bucket gs://%s is accessible ✓", bucket_name)
        return True
    except Exception as e:
        log.error("Cannot access bucket gs://%s: %s", bucket_name, e)
        log.error("Check GCS_BUCKET environment variable and IAM permissions")
        return False


def main():
    log.info("=== GCS Upload Pipeline ===")
    log.info("Bucket: gs://%s", GCS_BUCKET)

    # Validate required outputs exist before attempting upload
    missing = []
    for local_path in FILES_TO_UPLOAD:
        if not os.path.exists(local_path):
            missing.append(local_path)

    if missing:
        log.warning("The following files are missing and will be skipped:")
        for f in missing:
            log.warning("  %s", f)

    # Check at least the COG exists — it's the most important file
    cog_path = os.path.join(OUTPUT_DIR, "flood_risk_map.cog.tif")
    if not os.path.exists(cog_path):
        log.error("COG not found: %s", cog_path)
        log.error("Run: python scripts/flood_risk.py")
        raise SystemExit(1)

    # Authenticate and verify bucket
    client = get_gcs_client()
    if not verify_bucket(client, GCS_BUCKET):
        raise SystemExit(1)

    # Upload all files
    results = {}
    for local_path, gcs_key in FILES_TO_UPLOAD.items():
        if not os.path.exists(local_path):
            log.info("Skipping missing file: %s", local_path)
            results[local_path] = "skipped"
            continue

        success = upload_file(client, local_path, gcs_key, GCS_BUCKET)
        results[local_path] = "success" if success else "failed"

    # Summary
    log.info("")
    log.info("═" * 50)
    log.info("  UPLOAD SUMMARY")
    log.info("═" * 50)
    for local_path, status in results.items():
        icon = "✓" if status == "success" else ("⏭" if status == "skipped" else "✗")
        log.info("  %s  %s → %s", icon, os.path.basename(local_path), status)
    log.info("═" * 50)

    # Exit with error if any uploads failed
    if any(s == "failed" for s in results.values()):
        log.error("Some uploads failed — check errors above")
        raise SystemExit(1)

    log.info("All uploads complete ✓")
    log.info("TiTiler URL: https://titiler-z2qegb4nha-uc.a.run.app")
    log.info("Live map   : https://floodwatch.geobuildersafrica.com")


if __name__ == "__main__":
    main()
