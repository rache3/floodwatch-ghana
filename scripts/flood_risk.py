"""
Flood Risk Processing Script — Greater Accra Region
Author: Rachel Atia

Inputs  : DEM (EPSG:4326), Rainfall (float64), Slope (float32), 
          Landcover (float32), Waterbodies (float32)
Output  : flood_risk_map.tif      — normalised 0-1 risk score
          flood_risk_map.cog.tif  — Cloud-Optimised GeoTIFF for TiTiler

Usage   : python scripts/flood_risk.py
Config  : reads from .env file in project root
"""

# Rationale: This script processes multiple GIS layers to create a composite flood risk map.
# Flood risk is modeled as a weighted combination of elevation (DEM), precipitation intensity,
# terrain slope, land cover permeability, and proximity to water bodies. Lower elevations,
# higher rainfall, flatter slopes, impervious surfaces, and proximity to water increase risk.

import os
import logging
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject
from rasterio import MemoryFile
from rasterio.shutil import copy as rio_copy

# Rationale: dotenv allows configuration via environment variables for flexibility
# in different deployment environments without hardcoding paths or weights.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Rationale: Structured logging provides timestamps and levels for debugging
# and monitoring the processing pipeline, especially for long-running GIS operations.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config from .env ──────────────────────────────────────────────────────────
# Rationale: Environment variables allow easy configuration changes without
# modifying code. Default values ensure the script runs even without .env file.
DATA_DIR   = os.getenv("DATA_DIR",   "data")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")

DEM_PATH      = os.path.join(DATA_DIR, "accra_dem.tif")
RAINFALL_PATH = os.path.join(DATA_DIR, "accra_rainfall.tif")
SLOPE_PATH    = os.path.join(DATA_DIR, "accra_slope.tif")
LANDCOVER_PATH = os.path.join(DATA_DIR, "accra_landcover.tif")
WATERBODIES_PATH = os.path.join(DATA_DIR, "accra_waterbodies.tif")

OUTPUT_TIF = os.path.join(OUTPUT_DIR, "flood_risk_map.tif")
OUTPUT_COG = os.path.join(OUTPUT_DIR, "flood_risk_map.cog.tif")

# Rationale: Weights reflect expert judgment on relative importance of flood risk factors.
# DEM (30%) - Elevation is primary determinant of drainage and flood potential.
# Rainfall (25%) - Precipitation drives runoff and flood magnitude.
# Slope (20%) - Steeper slopes reduce ponding and accelerate drainage.
# Landcover (15%) - Impervious surfaces increase runoff vs permeable vegetation.
# Waterbodies (10%) - Proximity to existing water bodies indicates flood-prone areas.
# Weights sum to 1.0 for proper normalization.
WEIGHTS = {
    "dem":      float(os.getenv("WEIGHT_DEM",      "0.30")),
    "rainfall": float(os.getenv("WEIGHT_RAINFALL",  "0.25")),
    "slope":    float(os.getenv("WEIGHT_SLOPE",     "0.20")),
    "landcover": float(os.getenv("WEIGHT_LANDCOVER", "0.15")),
    "waterbodies": float(os.getenv("WEIGHT_WATERBODIES", "0.10")),
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_raster(path):
    """Load raster as float32 numpy array, replacing nodata with nan."""
    # Rationale: float32 provides sufficient precision for GIS data while saving memory.
    # NaN masking allows proper handling of missing data in calculations.
    # Extreme value masking removes common fill values in terrain datasets.
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
    # Rationale: Bilinear resampling provides smooth interpolation for continuous data
    # like rainfall and slope, preserving spatial patterns better than nearest neighbor.
    # NaN as dst_nodata ensures missing data is properly handled in reprojection.
    # Additional extreme value cleanup handles artifacts from reprojection.
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
    # Rationale: Min-max normalization scales all layers to comparable [0,1] range
    # for weighted combination. Inversion handles factors where lower values = higher risk
    # (e.g., elevation: lower elevation = higher flood risk).
    # NaN-aware operations prevent propagation of missing data.
    a_min = np.nanmin(arr)
    a_max = np.nanmax(arr)
    if a_max == a_min:
        return np.zeros_like(arr, dtype=np.float32)
    norm = (arr - a_min) / (a_max - a_min)
    return (1.0 - norm).astype(np.float32) if invert else norm.astype(np.float32)


def write_cog(src_path, dst_path):
    """Convert GeoTIFF to Cloud-Optimised GeoTIFF."""
    # Rationale: COG format enables efficient cloud storage and streaming,
    # with internal overviews for fast visualization at multiple zoom levels.
    # Tiling and compression reduce file size and improve access performance.
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
    # Rationale: Early validation prevents cryptic errors later in processing
    # and provides clear guidance on missing data requirements.
    required_inputs = [
        (DEM_PATH, "DEM"), 
        (RAINFALL_PATH, "Rainfall"), 
        (SLOPE_PATH, "Slope"),
        (LANDCOVER_PATH, "Landcover"),
        (WATERBODIES_PATH, "Waterbodies")
    ]
    for path, name in required_inputs:
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"{name} not found: {path}\n"
                f"Run: python scripts/ingest.py"
            )

    log.info("Weights: DEM=%.0f%% Rainfall=%.0f%% Slope=%.0f%% Landcover=%.0f%% Waterbodies=%.0f%%",
             WEIGHTS['dem']*100, WEIGHTS['rainfall']*100, WEIGHTS['slope']*100,
             WEIGHTS['landcover']*100, WEIGHTS['waterbodies']*100)

    # 1. Load DEM as reference grid
    # Rationale: DEM typically has the finest resolution and most complete coverage,
    # making it ideal as the reference grid for spatial alignment of all other layers.
    log.info("Loading DEM as reference grid...")
    dem_raw, ref_profile = load_raster(DEM_PATH)
    log.info("DEM shape: %s  valid pixels: %d%%",
             dem_raw.shape,
             int(100 * np.sum(~np.isnan(dem_raw)) / dem_raw.size))

    # 2. Align rainfall and slope to DEM grid
    # Rationale: All layers must share the same spatial reference system and grid
    # for pixel-wise mathematical operations. Reprojection ensures consistent analysis.
    log.info("Aligning rainfall to DEM grid...")
    rainfall_raw = align_to_reference(RAINFALL_PATH, ref_profile)

    log.info("Aligning slope to DEM grid...")
    slope_raw = align_to_reference(SLOPE_PATH, ref_profile)

    log.info("Aligning landcover to DEM grid...")
    landcover_raw = align_to_reference(LANDCOVER_PATH, ref_profile)

    log.info("Aligning waterbodies to DEM grid...")
    waterbodies_raw = align_to_reference(WATERBODIES_PATH, ref_profile)

    # 3. Normalise layers
    # Rationale: Normalization scales all input layers to [0,1] range for fair
    # weighted combination. Inversion handles factors where relationship to risk
    # is inverse (e.g., higher elevation = lower risk).
    log.info("Normalising layers...")
    dem_norm      = normalise(dem_raw,      invert=True)   # low elev = high risk
    rainfall_norm = normalise(rainfall_raw, invert=False)  # high rain = high risk
    slope_norm    = normalise(slope_raw,    invert=True)   # flat = high risk
    landcover_norm = normalise(landcover_raw, invert=False) # impervious = high risk
    waterbodies_norm = normalise(waterbodies_raw, invert=True) # close to water = high risk

    # 4. Weighted composite score
    # Rationale: Multi-criteria decision analysis combines factors with expert weights
    # to produce integrated flood risk assessment. Weighted sum preserves relative
    # importance of different risk drivers.
    log.info("Computing weighted flood risk score...")
    risk = (
        WEIGHTS["dem"]      * dem_norm      +
        WEIGHTS["rainfall"] * rainfall_norm +
        WEIGHTS["slope"]    * slope_norm    +
        WEIGHTS["landcover"] * landcover_norm +
        WEIGHTS["waterbodies"] * waterbodies_norm
    ).astype(np.float32)

    # Preserve NaN where DEM has no data
    # Rationale: Maintains spatial extent of valid analysis area, avoiding
    # extrapolation into areas with insufficient data.
    risk[np.isnan(dem_raw)] = np.nan

    # Reclassify to percentile-based risk tiers
    # Rationale: Percentile-based classification adapts to local data distribution
    # rather than absolute thresholds, providing relative risk assessment.
    # Three tiers (low/moderate/high) provide actionable risk categories.
    log.info("Reclassifying to percentile-based risk tiers...")
    valid_pixels = risk[~np.isnan(risk)]
    p25 = np.percentile(valid_pixels, 25)
    p75 = np.percentile(valid_pixels, 75)
    log.info("Percentiles  p25=%.4f  p75=%.4f", p25, p75)

    # Rescale so low risk = 0, moderate = 0.5, high = 1
    # based on local distribution rather than absolute values
    # Rationale: Non-linear scaling emphasizes extreme risk areas while maintaining
    # three distinct risk categories. 25th/75th percentiles define moderate risk zone,
    # with equal weighting for low/moderate/high categories (33% each of scale).
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
    # Rationale: Standard GeoTIFF format ensures compatibility with GIS software.
    # Float32 preserves precision, deflate compression reduces file size.
    # Metadata tags document the processing parameters for reproducibility.
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
    # Rationale: Cloud-Optimized GeoTIFF enables efficient web serving and
    # visualization through tile-based access patterns used by mapping applications.
    log.info("Building Cloud-Optimised GeoTIFF...")
    write_cog(OUTPUT_TIF, OUTPUT_COG)

    log.info("Pipeline complete ✓")
    log.info("Outputs saved to: %s/", OUTPUT_DIR)


if __name__ == "__main__":
    # Rationale: Standard Python idiom for script execution, allowing the module
    # to be imported without running the pipeline, or executed directly from command line.
    run()