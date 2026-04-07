"""
ingest_slope.py — Derive Terrain Slope from DEM
================================================
Source    : Computed from accra_dem.tif (SRTM 30m)
Method    : numpy gradient (pure Python, no GDAL command line needed)
Resolution: Same as input DEM (30m)
Output    : data/accra_slope.tif  (float32, degrees, EPSG:4326)

Why slope matters for flood risk:
----------------------------------
Flat terrain (low slope) cannot drain water efficiently — it pools.
Steep terrain drains quickly and rarely floods.

In the flood risk model, slope is INVERTED before combining:
    slope_norm_inverted = 1 - slope_norm
So flat areas (slope ≈ 0°) get a HIGH risk contribution.

Method:
-------
We use numpy.gradient() to compute the rate of elevation change in
both x (east-west) and y (north-south) directions. The gradient is
then converted from rise/run to degrees using arctan.

Pixel size is converted from degrees to metres using the standard
approximation of 111,320 metres per degree of latitude at the equator.
This is accurate enough for flood risk modelling at this scale.

Usage:
    # Run DEM ingest first:
    python scripts/ingest_dem.py

    # Then derive slope:
    python scripts/ingest_slope.py
"""

import os
import logging
import numpy as np

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

# Remove conflicting PROJ installation from environment (PostgreSQL/PostGIS conflict)
# Forces rasterio to use its own bundled PROJ data instead of the system installation
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

# ── Configuration ─────────────────────────────────────────────────────────────
DATA_DIR = os.getenv("DATA_DIR", "data")
DEM_PATH   = os.path.join(DATA_DIR, "accra_dem.tif")
OUTPUT_PATH = os.path.join(DATA_DIR, "accra_slope.tif")

# Approximate metres per degree at Ghana's latitude (~5.8°N)
# More accurate than using the equatorial value (111,320 m)
# At 5.8°N: cos(5.8°) * 111,320 ≈ 110,715 m per degree longitude
# Latitude degrees are essentially constant: ~111,320 m per degree
METRES_PER_DEGREE_LAT = 111_320.0
METRES_PER_DEGREE_LON = 110_715.0  # cos(5.8°) * 111,320


def derive_slope(dem_path: str, output_path: str) -> None:
    """
    Derive terrain slope in degrees from a DEM GeoTIFF.

    Steps:
    1. Load DEM and replace nodata values with NaN
    2. Get pixel dimensions in metres from the geotransform
    3. Compute x and y gradients using numpy.gradient()
    4. Convert gradient to slope angle in degrees
    5. Write output GeoTIFF with same projection as input
    """
    import rasterio

    log.info("Loading DEM from %s...", dem_path)

    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype(np.float32)
        profile = src.profile.copy()
        transform = src.transform

        # Get pixel size from the geotransform
        # transform.a = pixel width in degrees (x direction)
        # transform.e = pixel height in degrees (y direction, negative)
        pixel_size_x_deg = abs(transform.a)
        pixel_size_y_deg = abs(transform.e)

        nodata = src.nodata
        log.info("DEM shape: %s  nodata: %s", dem.shape, nodata)

    # Replace nodata values with NaN so they don't corrupt the gradient
    if nodata is not None:
        dem[dem == nodata] = np.nan
    dem[dem < -9000] = np.nan  # Catch any remaining fill values
    dem[dem > 9000]  = np.nan  # Remove unrealistic elevation spikes

    # Convert pixel size from degrees to metres
    cell_x = pixel_size_x_deg * METRES_PER_DEGREE_LON  # east-west pixel size
    cell_y = pixel_size_y_deg * METRES_PER_DEGREE_LAT  # north-south pixel size

    log.info("Pixel size: %.2f m (x)  %.2f m (y)", cell_x, cell_y)
    log.info("Deriving slope using numpy gradient...")

    # numpy.gradient returns (dy, dx) — rate of change in each direction
    # dy = change in elevation going north-south (rows)
    # dx = change in elevation going east-west (columns)
    dy, dx = np.gradient(dem, cell_y, cell_x)

    # Slope magnitude = sqrt(dx² + dy²) — this is rise/run (dimensionless)
    # arctan converts to angle in radians, then degrees()
    slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
    slope_deg = np.degrees(slope_rad).astype(np.float32)

    # Preserve NaN where DEM had nodata
    slope_deg[np.isnan(dem)] = np.nan

    # Log slope statistics for validation
    valid = slope_deg[~np.isnan(slope_deg)]
    log.info("Slope statistics:")
    log.info("  Min   : %.2f°", float(np.min(valid)))
    log.info("  Max   : %.2f°", float(np.max(valid)))
    log.info("  Mean  : %.2f°", float(np.mean(valid)))
    log.info("  Median: %.2f°", float(np.median(valid)))

    # Write output GeoTIFF
    # Keep same CRS and transform as input DEM
    # Change dtype to float32 and set nodata to NaN
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    out_profile = profile.copy()
    out_profile.update(
        dtype="float32",
        count=1,
        compress="deflate",
        nodata=float("nan"),
    )

    with rasterio.open(output_path, "w", **out_profile) as dst:
        dst.write(slope_deg, 1)
        dst.update_tags(
            description="Terrain slope in degrees derived from SRTM 30m DEM",
            method="numpy.gradient",
            units="degrees",
            source="SRTM 30m via OpenTopography",
        )

    log.info("Slope written → %s", output_path)


def main():
    log.info("=== Slope Derivation ===")

    # Check DEM exists
    if not os.path.exists(DEM_PATH):
        log.error("DEM not found: %s", DEM_PATH)
        log.error("Run: python scripts/ingest_dem.py")
        raise SystemExit(1)

    # Skip if slope already exists
    if os.path.exists(OUTPUT_PATH):
        log.info("Slope already exists → %s", OUTPUT_PATH)
        log.info("Delete the file to force recalculation")
        return

    derive_slope(DEM_PATH, OUTPUT_PATH)
    log.info("Slope ingest complete ✓")


if __name__ == "__main__":
    main()
