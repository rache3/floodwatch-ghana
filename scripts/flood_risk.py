"""
Flood Risk Processing Script — Greater Accra Region
Author: Rachel Atia

Inputs  : DEM (EPSG:4326), Rainfall (float64), Slope (float32)
Output  : flood_risk_map.tif      — normalised 0-1 risk score
          flood_risk_map.cog.tif  — Cloud-Optimised GeoTIFF for TiTiler

Usage   : python scripts/flood_risk.py
Config  : reads from .env file in project root
"""

import os
import logging
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject
from rasterio import MemoryFile
from rasterio.shutil import copy as rio_copy

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

# ── Config from .env ──────────────────────────────────────────────────────────
DATA_DIR   = os.getenv("DATA_DIR",   "data")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")

DEM_PATH      = os.path.join(DATA_DIR, "accra_dem.tif")
RAINFALL_PATH = os.path.join(DATA_DIR, "accra_rainfall.tif")
SLOPE_PATH    = os.path.join(DATA_DIR, "accra_slope.tif")

OUTPUT_TIF = os.path.join(OUTPUT_DIR, "flood_risk_map.tif")
OUTPUT_COG = os.path.join(OUTPUT_DIR, "flood_risk_map.cog.tif")

WEIGHTS = {
    "dem":      float(os.getenv("WEIGHT_DEM",      "0.40")),
    "rainfall": float(os.getenv("WEIGHT_RAINFALL",  "0.35")),
    "slope":    float(os.getenv("WEIGHT_SLOPE",     "0.25")),
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_raster(path):
    """Load raster as float32 numpy array, replacing nodata with nan."""
    with rasterio.open(path) as src:
        data = src.read(1).astype(np.float32)
        profile = src.profile.copy()
        nodata = src.nodata
        if nodata is not None:
            data[data == nodata] = np.nan
        # Also mask extreme fill values common in SRTM/terrain data
        data[data < -9000] = np.nan
        data[data > 9000]  = np.nan
    return data, profile


def align_to_reference(src_path, ref_profile):
    """Reproject and resample src_path to match ref_profile grid."""
    with rasterio.open(src_path) as src:
        dst_arr = np.full(
            (ref_profile["height"], ref_profile["width"]),
            fill_value=np.nan,
            dtype=np.float32,
        )
        reproject(
            source=rasterio.band(src, 1),
            destination=dst_arr,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=ref_profile["transform"],
            dst_crs=ref_profile["crs"],
            resampling=Resampling.bilinear,
            src_nodata=src.nodata,
            dst_nodata=np.nan,
        )
    # Clean up any remaining fill values
    dst_arr[dst_arr < -9000] = np.nan
    dst_arr[dst_arr > 9000]  = np.nan
    return dst_arr


def normalise(arr, invert=False):
    """Min-max normalise to [0, 1] ignoring NaN. Invert if needed."""
    a_min = np.nanmin(arr)
    a_max = np.nanmax(arr)
    if a_max == a_min:
        return np.zeros_like(arr, dtype=np.float32)
    norm = (arr - a_min) / (a_max - a_min)
    return (1.0 - norm).astype(np.float32) if invert else norm.astype(np.float32)


def write_cog(src_path, dst_path):
    """Convert GeoTIFF to Cloud-Optimised GeoTIFF."""
    copy_opts = {
        "driver": "GTiff",
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
        "compress": "deflate",
        "predictor": 2,
        "copy_src_overviews": True,
    }
    with rasterio.open(src_path) as src:
        with MemoryFile() as memfile:
            with memfile.open(**src.profile) as mem:
                mem.write(src.read())
                mem.build_overviews([2, 4, 8, 16, 32], Resampling.average)
                mem.update_tags(ns="rio_overview", resampling="average")
                rio_copy(mem, dst_path, **copy_opts)
    log.info("COG written → %s", dst_path)


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Validate inputs exist
    for path, name in [(DEM_PATH, "DEM"), (RAINFALL_PATH, "Rainfall"), (SLOPE_PATH, "Slope")]:
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"{name} not found: {path}\n"
                f"Run: python scripts/ingest.py"
            )

    log.info("Weights: DEM=%.0f%% Rainfall=%.0f%% Slope=%.0f%%",
             WEIGHTS['dem']*100, WEIGHTS['rainfall']*100, WEIGHTS['slope']*100)

    # 1. Load DEM as reference grid
    log.info("Loading DEM as reference grid...")
    dem_raw, ref_profile = load_raster(DEM_PATH)
    log.info("DEM shape: %s  valid pixels: %d%%",
             dem_raw.shape,
             int(100 * np.sum(~np.isnan(dem_raw)) / dem_raw.size))

    # 2. Align rainfall and slope to DEM grid
    log.info("Aligning rainfall to DEM grid...")
    rainfall_raw = align_to_reference(RAINFALL_PATH, ref_profile)

    log.info("Aligning slope to DEM grid...")
    slope_raw = align_to_reference(SLOPE_PATH, ref_profile)

    # 3. Normalise layers
    log.info("Normalising layers...")
    dem_norm      = normalise(dem_raw,      invert=True)   # low elev = high risk
    rainfall_norm = normalise(rainfall_raw, invert=False)  # high rain = high risk
    slope_norm    = normalise(slope_raw,    invert=True)   # flat = high risk

    # 4. Weighted composite score
    log.info("Computing weighted flood risk score...")
    risk = (
        WEIGHTS["dem"]      * dem_norm      +
        WEIGHTS["rainfall"] * rainfall_norm +
        WEIGHTS["slope"]    * slope_norm
    ).astype(np.float32)

    # Preserve NaN where DEM has no data
    risk[np.isnan(dem_raw)] = np.nan

    # Reclassify to percentile-based risk tiers
    log.info("Reclassifying to percentile-based risk tiers...")
    valid_pixels = risk[~np.isnan(risk)]
    p25 = np.percentile(valid_pixels, 25)
    p75 = np.percentile(valid_pixels, 75)
    log.info("Percentiles  p25=%.4f  p75=%.4f", p25, p75)

    # Rescale so low risk = 0, moderate = 0.5, high = 1
    # based on local distribution rather than absolute values
    risk_classified = np.where(
        np.isnan(risk), np.nan,
        np.where(risk < p25, risk / p25 * 0.33,
        np.where(risk < p75,
                 0.33 + (risk - p25) / (p75 - p25) * 0.34,
                 0.67 + (risk - p75) / (np.nanmax(risk) - p75) * 0.33))
    ).astype(np.float32)

    risk = risk_classified

    valid_count = np.sum(~np.isnan(risk))
    log.info("Risk stats  min=%.4f  max=%.4f  mean=%.4f  valid_pixels=%d",
             np.nanmin(risk), np.nanmax(risk), np.nanmean(risk), valid_count)

    if valid_count == 0:
        raise ValueError("All risk values are NaN — check input rasters.")

    # 5. Write GeoTIFF
    out_profile = ref_profile.copy()
    out_profile.update(
        dtype="float32",
        count=1,
        compress="deflate",
        nodata=np.nan,
    )
    log.info("Writing GeoTIFF → %s", OUTPUT_TIF)
    with rasterio.open(OUTPUT_TIF, "w", **out_profile) as dst:
        dst.write(risk, 1)
        dst.update_tags(
            description="Flood risk score (0=low, 1=high)",
            weights=str(WEIGHTS),
            crs="EPSG:4326",
        )

    # 6. Write COG
    log.info("Building Cloud-Optimised GeoTIFF...")
    write_cog(OUTPUT_TIF, OUTPUT_COG)

    log.info("Pipeline complete ✓")
    log.info("Outputs saved to: %s/", OUTPUT_DIR)


if __name__ == "__main__":
    run()