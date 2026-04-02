"""
ingest_dem.py — Download SRTM 30m Digital Elevation Model
==========================================================
Source    : OpenTopography REST API (SRTMGL1 — NASA/USGS)
Resolution: 30 metres
Coverage  : Greater Accra bounding box
Output    : data/accra_dem.tif  (int16, EPSG:4326, nodata=-32768)

Why SRTM?
---------
SRTM (Shuttle Radar Topography Mission) is the most widely used
global elevation dataset. It covers latitudes 56°S to 60°N at 30m
resolution and is freely available with no API key via OpenTopography.

The Copernicus GLO-30 dataset has higher accuracy but now requires a
paid API key. SRTM is a reliable, free alternative for flood risk work.

Usage:
    python scripts/ingest_dem.py

    # Or with custom bounding box:
    BBOX_WEST=-0.50 BBOX_EAST=0.50 BBOX_SOUTH=5.35 BBOX_NORTH=5.95 \
    python scripts/ingest_dem.py
"""

import os
import logging
import urllib.request
import urllib.error


# ── Load .env if present ──────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)
# Remove PostgreSQL's conflicting PROJ installation from the environment
# This forces rasterio to use its own bundled PROJ data
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)


# ── Configuration ─────────────────────────────────────────────────────────────
# Bounding box for Greater Accra Region, Ghana (EPSG:4326)
# Extend slightly beyond the district boundary to avoid edge clipping
BBOX = {
    "west":  float(os.getenv("BBOX_WEST",  "-0.50")),
    "east":  float(os.getenv("BBOX_EAST",   "0.50")),
    "south": float(os.getenv("BBOX_SOUTH",  "5.35")),
    "north": float(os.getenv("BBOX_NORTH",  "5.95")),
}

# Output directory and file path
DATA_DIR = os.getenv("DATA_DIR", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "accra_dem.tif")

# OpenTopography public demo API key (works for SRTMGL1, no registration needed)
# For higher rate limits register free at portal.opentopography.org
OT_API_KEY = os.getenv("OPENTOPO_API_KEY", "demoapikeyot2022")


def build_url(bbox: dict, api_key: str) -> str:
    """
    Build the OpenTopography API URL for SRTM 30m download.

    OpenTopography provides a REST API that returns a GeoTIFF clipped
    to the requested bounding box. No preprocessing needed — the file
    is ready to use directly.
    """
    return (
        "https://portal.opentopography.org/API/globaldem"
        f"?demtype=SRTMGL1"           # SRTM 1 arc-second (30m) product
        f"&south={bbox['south']}"
        f"&north={bbox['north']}"
        f"&west={bbox['west']}"
        f"&east={bbox['east']}"
        f"&outputFormat=GTiff"         # Return as GeoTIFF
        f"&API_Key={api_key}"
    )


def download_dem(output_path: str) -> bool:
    """
    Download the SRTM 30m DEM for the configured bounding box.

    Returns True on success, False on failure.
    The downloaded file is a GeoTIFF with:
      - CRS: EPSG:4326 (WGS84 geographic)
      - Data type: int16
      - NoData value: -32768
      - Values: elevation in metres above sea level
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    url = build_url(BBOX, OT_API_KEY)
    log.info("Downloading SRTM 30m DEM...")
    log.info("Bounding box: W=%.2f E=%.2f S=%.2f N=%.2f",
             BBOX["west"], BBOX["east"], BBOX["south"], BBOX["north"])

    try:
        urllib.request.urlretrieve(url, output_path)

        size_mb = os.path.getsize(output_path) / 1024 / 1024
        log.info("DEM downloaded (%.1f MB) → %s", size_mb, output_path)

        # Sanity check — a valid DEM for this area should be at least 1MB
        if size_mb < 1.0:
            log.warning("File is very small (%.1f MB) — may be an error response", size_mb)
            return False

        return True

    except urllib.error.HTTPError as e:
        log.error("HTTP error %s: %s", e.code, e.reason)
        if e.code == 401:
            log.error("API key rejected. Check OPENTOPO_API_KEY in .env")
        elif e.code == 400:
            log.error("Bad request — check bounding box coordinates")
        return False

    except urllib.error.URLError as e:
        log.error("Network error: %s", e.reason)
        log.error("Check your internet connection and try again")
        return False


def validate_dem(output_path: str) -> bool:
    """
    Open the downloaded DEM with rasterio and log basic statistics.
    This catches cases where the download succeeded but the file is corrupt.
    """
    try:
        import numpy as np
        import rasterio

        with rasterio.open(output_path) as src:
            data = src.read(1).astype(float)
            nodata = src.nodata or -32768
            data[data == nodata] = float("nan")

            log.info("DEM validation:")
            log.info("  Shape    : %s", src.shape)
            log.info("  CRS      : %s", src.crs)
            log.info("  Bounds   : %s", src.bounds)
            log.info("  Elevation: min=%.0f m  max=%.0f m  mean=%.0f m",
                     float(np.nanmin(data)),
                     float(np.nanmax(data)),
                     float(np.nanmean(data)))

        return True

    except Exception as e:
        log.error("DEM validation failed: %s", e)
        return False


def main():
    log.info("=== DEM Ingest — SRTM 30m ===")

    # Skip download if file already exists and is recent
    if os.path.exists(OUTPUT_PATH):
        size_mb = os.path.getsize(OUTPUT_PATH) / 1024 / 1024
        log.info("DEM already exists (%.1f MB) → %s", size_mb, OUTPUT_PATH)
        log.info("Delete the file to force a fresh download")
        validate_dem(OUTPUT_PATH)
        return

    success = download_dem(OUTPUT_PATH)

    if not success:
        log.error("DEM download failed. Place accra_dem.tif in %s manually.", DATA_DIR)
        raise SystemExit(1)

    validate_dem(OUTPUT_PATH)
    log.info("DEM ingest complete ✓")


if __name__ == "__main__":
    main()
