"""
Flood Risk Processing Script — Greater Accra Region
Author: Rachel Atia

Inputs  : DEM (EPSG:4326), Rainfall (float64), Slope (float32),
          Landcover (float32), Waterbodies (float32)
Output  : flood_risk_map.tif      — normalised 0-1 risk score
          flood_risk_masked.tif   — masked to Greater Accra boundary
          flood_risk_map.cog.tif  — Cloud-Optimised GeoTIFF for TiTiler

Pipeline stages:
1. Load and align all 5 input rasters to DEM reference grid
2. Normalise each layer to [0, 1]
3. Compute weighted composite risk score
4. Percentile-based reclassification
5. Mask to Greater Accra boundary
6. Write COG from masked raster

Usage   : python scripts/flood_risk.py
Config  : reads from .env file in project root
"""

import os
import json
import logging
import shutil
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
# Remove PostgreSQL's conflicting PROJ installation from the environment
# This forces rasterio to use its own bundled PROJ data
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)


# ── Config ────────────────────────────────────────────────────────────────────
DATA_DIR   = os.getenv("DATA_DIR",   "data")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")

DEM_PATH         = os.path.join(DATA_DIR, "accra_dem.tif")
RAINFALL_PATH    = os.path.join(DATA_DIR, "accra_rainfall.tif")
SLOPE_PATH       = os.path.join(DATA_DIR, "accra_slope.tif")
LANDCOVER_PATH   = os.path.join(DATA_DIR, "accra_landcover.tif")
WATERBODIES_PATH = os.path.join(DATA_DIR, "accra_waterbodies.tif")

OUTPUT_TIF    = os.path.join(OUTPUT_DIR, "flood_risk_map.tif")
OUTPUT_MASKED = os.path.join(OUTPUT_DIR, "flood_risk_masked.tif")
OUTPUT_COG    = os.path.join(OUTPUT_DIR, "flood_risk_map.cog.tif")

# Boundary file candidates — checked in order, first found is used
BOUNDARY_CANDIDATES = [
    os.path.join(DATA_DIR, "gadm41_GHA_accra.json"),  # Preferred — Greater Accra only
    "gadm41_GHA_accra.json",
    os.path.join(DATA_DIR, "gadm41_GHA_2.json"),       # Fallback — full Ghana
    "gadm41_GHA_2.json",
]

# Weights must sum to 1.0
# DEM (30%)         — elevation is the primary flood driver
# Rainfall (25%)    — precipitation drives runoff
# Slope (20%)       — flat terrain pools water
# Landcover (15%)   — impervious surfaces increase runoff
# Waterbodies (10%) — proximity to water = higher risk
WEIGHTS = {
    "dem":         float(os.getenv("WEIGHT_DEM",         "0.30")),
    "rainfall":    float(os.getenv("WEIGHT_RAINFALL",    "0.25")),
    "slope":       float(os.getenv("WEIGHT_SLOPE",       "0.20")),
    "landcover":   float(os.getenv("WEIGHT_LANDCOVER",   "0.15")),
    "waterbodies": float(os.getenv("WEIGHT_WATERBODIES", "0.10")),
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
 

def mask_to_boundary(src_path: str, dst_path: str) -> None:
    """
    Clip raster to Greater Accra district boundary.

    Uses Shapely buffer(-0.001) to shrink the boundary slightly,
    eliminating pixel bleeding at tile edges — a known issue with
    TiTiler serving COGs that extend right to the boundary edge.

    Falls back to copying the file unchanged if no boundary file is found.
    """
    from rasterio.mask import mask as rio_mask
    from shapely.geometry import shape, mapping
    from shapely.ops import unary_union

    # Find boundary file
    boundary_path = next(
        (p for p in BOUNDARY_CANDIDATES if os.path.exists(p)), None
    )

    if not boundary_path:
        log.warning("No boundary file found — skipping mask step")
        log.warning("Searched: %s", BOUNDARY_CANDIDATES)
        shutil.copy(src_path, dst_path)
        return

    log.info("Using boundary file: %s", boundary_path)

    with open(boundary_path) as f:
        gj = json.load(f)

    # Filter to Greater Accra features
    # Handle both "GreaterAccra" (no space) and "Greater Accra" (with space)
    accra_shapes = [
        shape(f["geometry"]) for f in gj["features"]
        if f["properties"].get("NAME_1", "").replace(" ", "") == "GreaterAccra"
    ]

    if not accra_shapes:
        log.warning("No Greater Accra features found in %s", boundary_path)
        shutil.copy(src_path, dst_path)
        return

    log.info("Masking to %d district polygons...", len(accra_shapes))

    # Merge all districts into one polygon and shrink slightly
    # to prevent pixel bleeding at the boundary edge
    merged = unary_union(accra_shapes).buffer(-0.001)

    with rasterio.open(src_path) as src:
        out_image, out_transform = rio_mask(
            src,
            [mapping(merged)],
            crop=True,
            nodata=np.nan,
            all_touched=False,
        )
        out_meta = src.meta.copy()
        out_meta.update({
            "height":    out_image.shape[1],
            "width":     out_image.shape[2],
            "transform": out_transform,
            "nodata":    np.nan,
            "dtype":     "float32",
        })
        with rasterio.open(dst_path, "w", **out_meta) as dst:
            dst.write(out_image)

    log.info("Masked raster → %s", dst_path)


def write_cog(src_path: str, dst_path: str) -> None:
    """Convert GeoTIFF to Cloud-Optimised GeoTIFF for TiTiler."""
    copy_opts = {
        "driver":            "GTiff",
        "tiled":             True,
        "blockxsize":        512,
        "blockysize":        512,
        "compress":          "deflate",
        "predictor":         2,
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

    # Validate all inputs exist
    required_inputs = [
        (DEM_PATH,         "DEM"),
        (RAINFALL_PATH,    "Rainfall"),
        (SLOPE_PATH,       "Slope"),
        (LANDCOVER_PATH,   "Landcover"),
        (WATERBODIES_PATH, "Waterbodies"),
    ]
    for path, name in required_inputs:
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"{name} not found: {path}\n"
                f"Run: python scripts/ingest.py"
            )

    log.info(
        "Weights: DEM=%.0f%% Rainfall=%.0f%% Slope=%.0f%% "
        "Landcover=%.0f%% Waterbodies=%.0f%%",
        WEIGHTS['dem']*100, WEIGHTS['rainfall']*100, WEIGHTS['slope']*100,
        WEIGHTS['landcover']*100, WEIGHTS['waterbodies']*100,
    )

    # 1. Load DEM as reference grid
    log.info("Loading DEM as reference grid...")
    dem_raw, ref_profile = load_raster(DEM_PATH)
    log.info("DEM shape: %s  valid pixels: %d%%",
             dem_raw.shape,
             int(100 * np.sum(~np.isnan(dem_raw)) / dem_raw.size))

    # 2. Align all layers to DEM grid
    log.info("Aligning rainfall to DEM grid...")
    rainfall_raw = align_to_reference(RAINFALL_PATH, ref_profile)

    log.info("Aligning slope to DEM grid...")
    slope_raw = align_to_reference(SLOPE_PATH, ref_profile)

    log.info("Aligning landcover to DEM grid...")
    landcover_raw = align_to_reference(LANDCOVER_PATH, ref_profile)

    log.info("Aligning waterbodies to DEM grid...")
    waterbodies_raw = align_to_reference(WATERBODIES_PATH, ref_profile)

    # 3. Normalise layers
    log.info("Normalising layers...")
    dem_norm         = normalise(dem_raw,         invert=True)   # low elev = high risk
    rainfall_norm    = normalise(rainfall_raw,    invert=False)  # high rain = high risk
    slope_norm       = normalise(slope_raw,       invert=True)   # flat = high risk
    landcover_norm   = normalise(landcover_raw,   invert=False)  # impervious = high risk
    waterbodies_norm = normalise(waterbodies_raw, invert=True)   # close to water = high risk

    # 4. Weighted composite score
    log.info("Computing weighted flood risk score...")
    risk = (
        WEIGHTS["dem"]         * dem_norm         +
        WEIGHTS["rainfall"]    * rainfall_norm    +
        WEIGHTS["slope"]       * slope_norm       +
        WEIGHTS["landcover"]   * landcover_norm   +
        WEIGHTS["waterbodies"] * waterbodies_norm
    ).astype(np.float32)

    # Preserve NaN where DEM has no data
    risk[np.isnan(dem_raw)] = np.nan

    # 5. Percentile-based reclassification
    log.info("Reclassifying to percentile-based risk tiers...")
    valid_pixels = risk[~np.isnan(risk)]
    p25 = np.percentile(valid_pixels, 25)
    p75 = np.percentile(valid_pixels, 75)
    log.info("Percentiles  p25=%.4f  p75=%.4f", p25, p75)

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

    # 6. Write standard GeoTIFF
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

    # 7. Mask to Greater Accra boundary
    log.info("Masking to Greater Accra boundary...")
    mask_to_boundary(OUTPUT_TIF, OUTPUT_MASKED)

    # 8. Write COG from masked raster
    log.info("Building Cloud-Optimised GeoTIFF...")
    write_cog(OUTPUT_MASKED, OUTPUT_COG)

    log.info("Pipeline complete ✓")
    log.info("Outputs:")
    log.info("  Raw GeoTIFF  → %s", OUTPUT_TIF)
    log.info("  Masked       → %s", OUTPUT_MASKED)
    log.info("  COG          → %s", OUTPUT_COG)


if __name__ == "__main__":
    run()
