"""
Flood Risk Pipeline - Greater Accra Region
Rebuilt from original GEE work (Rachel Atia, 2024)

Inputs  : DEM (int16, EPSG:4326), Rainfall (float64), Slope (float32)
Output  : flood_risk_map.tif  — normalised 0-1 risk score (float32)
          flood_risk_map.cog.tif — Cloud-Optimised GeoTIFF for tile serving

Pipeline stages
---------------
1. Align all rasters to a common grid (DEM is the reference)
2. Normalise each layer to [0, 1]
3. Compute weighted composite risk score
4. Write standard GeoTIFF + Cloud-Optimised GeoTIFF (COG)
"""

import os
import logging
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject, calculate_default_transform
from rasterio import MemoryFile
from rasterio.shutil import copy as rio_copy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — edit weights to tune the risk model
# ---------------------------------------------------------------------------
DATA_DIR   = os.getenv("DATA_DIR",   "data")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")

DEM_PATH      = os.path.join(DATA_DIR, "accra_dem.tif")
RAINFALL_PATH = os.path.join(DATA_DIR, "accra_rainfall.tif")
SLOPE_PATH    = os.path.join(DATA_DIR, "accra_slope.tif")

OUTPUT_TIF    = os.path.join(OUTPUT_DIR, "flood_risk_map.tif")
OUTPUT_COG    = os.path.join(OUTPUT_DIR, "flood_risk_map.cog.tif")

# Weights must sum to 1.0
# Low elevation  → higher risk  (inverted)
# High rainfall  → higher risk
# Low slope      → higher risk  (flat = water pools) (inverted)
WEIGHTS = {
    "dem":      0.40,   # elevation is the strongest predictor
    "rainfall": 0.35,   # rainfall intensity
    "slope":    0.25,   # terrain slope (flat areas accumulate water)
}

assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def normalise(arr: np.ndarray, invert: bool = False) -> np.ndarray:
    """Min-max normalise to [0, 1]. Optionally invert so high raw = low risk."""
    a_min, a_max = np.nanmin(arr), np.nanmax(arr)
    if a_max == a_min:
        return np.zeros_like(arr, dtype=np.float32)
    norm = (arr - a_min) / (a_max - a_min)
    return (1.0 - norm) if invert else norm


def align_to_reference(src_path: str, ref_profile: dict) -> np.ndarray:
    """
    Reproject + resample src_path to match ref_profile's CRS, transform,
    width and height. Returns a float32 numpy array.
    """
    with rasterio.open(src_path) as src:
        dst_arr = np.empty(
            (ref_profile["height"], ref_profile["width"]), dtype=np.float32
        )
        reproject(
            source=rasterio.band(src, 1),
            destination=dst_arr,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=ref_profile["transform"],
            dst_crs=ref_profile["crs"],
            resampling=Resampling.bilinear,
        )
    return dst_arr


def write_cog(src_path: str, dst_path: str) -> None:
    """Convert a GeoTIFF to a Cloud-Optimised GeoTIFF (COG)."""
    copy_opts = {
        "driver": "GTiff",
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
        "compress": "deflate",
        "predictor": 2,
        "copy_src_overviews": True,
    }
    # Build overviews in a memory file first
    with rasterio.open(src_path) as src:
        with MemoryFile() as memfile:
            with memfile.open(**src.profile) as mem:
                mem.write(src.read())
                overview_levels = [2, 4, 8, 16, 32]
                mem.build_overviews(overview_levels, Resampling.average)
                mem.update_tags(ns="rio_overview", resampling="average")
                rio_copy(mem, dst_path, **copy_opts)
    log.info("COG written → %s", dst_path)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── 1. Load reference grid from DEM ────────────────────────────────────
    log.info("Loading DEM as reference grid …")
    with rasterio.open(DEM_PATH) as dem_src:
        ref_profile = dem_src.profile.copy()
        dem_raw = dem_src.read(1).astype(np.float32)

    # ── 2. Align rainfall and slope to DEM grid ────────────────────────────
    log.info("Aligning rainfall to DEM grid …")
    rainfall_raw = align_to_reference(RAINFALL_PATH, ref_profile)

    log.info("Aligning slope to DEM grid …")
    slope_raw = align_to_reference(SLOPE_PATH, ref_profile)

    # ── 3. Normalise layers ────────────────────────────────────────────────
    log.info("Normalising layers …")
    dem_norm      = normalise(dem_raw,      invert=True)   # low elev = high risk
    rainfall_norm = normalise(rainfall_raw, invert=False)  # high rain = high risk
    slope_norm    = normalise(slope_raw,    invert=True)   # flat = high risk

    # ── 4. Weighted composite score ────────────────────────────────────────
    log.info("Computing weighted flood risk score …")
    risk = (
        WEIGHTS["dem"]      * dem_norm      +
        WEIGHTS["rainfall"] * rainfall_norm +
        WEIGHTS["slope"]    * slope_norm
    ).astype(np.float32)

    log.info(
        "Risk stats  min=%.4f  max=%.4f  mean=%.4f",
        risk.min(), risk.max(), risk.mean()
    )

    # ── 5. Write output GeoTIFF ────────────────────────────────────────────
    out_profile = ref_profile.copy()
    out_profile.update(dtype="float32", count=1, compress="deflate")

    log.info("Writing GeoTIFF → %s", OUTPUT_TIF)
    with rasterio.open(OUTPUT_TIF, "w", **out_profile) as dst:
        dst.write(risk, 1)
        dst.update_tags(
            description="Flood risk score (0=low, 1=high)",
            weights=str(WEIGHTS),
            crs="EPSG:4326",
        )

    # ── 6. Write COG for TiTiler ───────────────────────────────────────────
    log.info("Building Cloud-Optimised GeoTIFF …")
    write_cog(OUTPUT_TIF, OUTPUT_COG)

    log.info("Pipeline complete ✓")


if __name__ == "__main__":
    run()
