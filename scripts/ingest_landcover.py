"""
ingest_landcover.py — Download ESA WorldCover Land Cover
=========================================================
Source    : ESA WorldCover 2021 (v200) — 10m global land cover map
Access    : Direct download from ESA S3 bucket (no API key needed)
Resolution: 10 metres (resampled to 30m to match DEM grid)
Output    : data/accra_landcover.tif  (uint8, class codes, EPSG:4326)

Why land cover matters for flood risk:
---------------------------------------
Urban impervious surfaces (concrete, asphalt, rooftops) cannot absorb
water. When it rains heavily over a city, nearly all water becomes
surface runoff — leading to flash flooding even in areas with good
terrain drainage.

Contrast this with vegetated areas where soil absorbs some rainfall,
or wetlands that act as natural buffers.

The current flood risk model treats a concrete car park and a grass
field at the same elevation identically. Land cover fixes this.

ESA WorldCover Classes (used in risk model):
---------------------------------------------
Class 10 — Tree cover          → LOW impervious   (low runoff)
Class 20 — Shrubland           → LOW impervious
Class 30 — Grassland           → LOW-MEDIUM impervious
Class 40 — Cropland            → MEDIUM impervious
Class 50 — Built-up (urban)    → HIGH impervious  (high runoff risk)
Class 60 — Bare/sparse veg     → MEDIUM-HIGH
Class 70 — Snow/ice            → N/A for Accra
Class 80 — Permanent water     → VERY HIGH risk (already flooded)
Class 90 — Herbaceous wetland  → HIGH risk (flood-prone by nature)
Class 95 — Mangroves           → HIGH risk (coastal flood zone)
Class 100— Moss/lichen         → LOW

The impervious surface fraction derived from these classes becomes
a new input layer in the flood risk model.

Usage:
    python scripts/ingest_landcover.py
"""

import os
import logging
import urllib.request
import urllib.error
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

# ── Configuration ─────────────────────────────────────────────────────────────
DATA_DIR         = os.getenv("DATA_DIR", "data")
OUTPUT_RAW_PATH  = os.path.join(DATA_DIR, "accra_landcover_raw.tif")
OUTPUT_PATH      = os.path.join(DATA_DIR, "accra_landcover.tif")

# Greater Accra bounding box
BBOX = {
    "west":  float(os.getenv("BBOX_WEST",  "-0.50")),
    "east":  float(os.getenv("BBOX_EAST",   "0.50")),
    "south": float(os.getenv("BBOX_SOUTH",  "5.35")),
    "north": float(os.getenv("BBOX_NORTH",  "5.95")),
}

# ── ESA WorldCover Class → Impervious Surface Fraction ────────────────────────
# These values represent the approximate fraction of impervious surface
# for each land cover class. 0.0 = fully permeable, 1.0 = fully impervious.
# Used to convert the categorical land cover map into a continuous risk layer.
IMPERVIOUSNESS = {
    10:  0.02,   # Tree cover — very low runoff
    20:  0.05,   # Shrubland
    30:  0.10,   # Grassland
    40:  0.20,   # Cropland — some bare soil
    50:  0.90,   # Built-up (urban) — dominant in central Accra
    60:  0.35,   # Bare/sparse vegetation
    70:  0.00,   # Snow/ice — not present in Ghana
    80:  1.00,   # Permanent water — already flooded zone
    90:  0.85,   # Herbaceous wetland — flood-prone
    95:  0.80,   # Mangroves — coastal flood zone
    100: 0.03,   # Moss/lichen
}


def find_worldcover_tile(bbox: dict) -> list:
    """
    ESA WorldCover tiles are 3° × 3° with filenames based on their
    SW corner. Greater Accra (roughly 5.35-5.95°N, -0.5-0.5°E)
    falls in the tile(s) starting at N03E000 and/or N06W003.

    Returns a list of tile names that cover the bounding box.
    """
    tiles = []

    # Calculate tile corners (3° grid, SW corner convention)
    for lat_start in range(int(bbox["south"] // 3) * 3,
                           int(bbox["north"] // 3) * 3 + 3, 3):
        for lon_start in range(int(bbox["west"] // 3) * 3,
                               int(bbox["east"] // 3) * 3 + 3, 3):
            # Format: N03E000 or S03W003
            lat_str = f"N{abs(lat_start):02d}" if lat_start >= 0 else f"S{abs(lat_start):02d}"
            lon_str = f"E{abs(lon_start):03d}" if lon_start >= 0 else f"W{abs(lon_start):03d}"
            tiles.append(f"{lat_str}{lon_str}")

    log.info("WorldCover tiles needed: %s", tiles)
    return tiles


def download_worldcover_tile(tile_name: str, output_path: str) -> bool:
    """
    Download a single ESA WorldCover 2021 tile from the ESA S3 bucket.

    ESA WorldCover v200 (2021) is freely available at:
    https://esa-worldcover.s3.eu-central-1.amazonaws.com/

    Tile format: ESA_WorldCover_10m_2021_v200_{tile}_Map.tif
    File size: typically 200-500MB per 3°×3° tile at 10m resolution
    """
    filename = f"ESA_WorldCover_10m_2021_v200_{tile_name}_Map.tif"
    url = (
        f"https://esa-worldcover.s3.eu-central-1.amazonaws.com"
        f"/v200/2021/map/{filename}"
    )

    log.info("Downloading ESA WorldCover tile %s...", tile_name)
    log.info("URL: %s", url)
    log.info("Note: Tile files are 200-500MB — this may take several minutes")

    try:
        # Show download progress
        def progress_hook(count, block_size, total_size):
            if total_size > 0 and count % 100 == 0:
                percent = min(100, count * block_size * 100 / total_size)
                mb_done = count * block_size / 1024 / 1024
                mb_total = total_size / 1024 / 1024
                log.info("  Progress: %.0f%% (%.0f / %.0f MB)",
                         percent, mb_done, mb_total)

        urllib.request.urlretrieve(url, output_path, reporthook=progress_hook)

        size_mb = os.path.getsize(output_path) / 1024 / 1024
        log.info("Tile downloaded (%.0f MB) → %s", size_mb, output_path)
        return True

    except urllib.error.HTTPError as e:
        log.error("HTTP error %s: tile %s may not exist", e.code, tile_name)
        return False
    except urllib.error.URLError as e:
        log.error("Network error: %s", e.reason)
        return False


def clip_and_resample(src_path: str, dst_path: str, bbox: dict,
                      target_shape: tuple = None) -> None:
    """
    Clip the WorldCover tile to the study area bounding box.
    Optionally resample to match the DEM grid (30m).

    WorldCover is at 10m — we resample to 30m to match the DEM
    using nearest neighbour resampling (preserves class codes).
    """
    import rasterio
    from rasterio.windows import from_bounds
    from rasterio.enums import Resampling
    from rasterio.warp import reproject, calculate_default_transform

    log.info("Clipping WorldCover to Greater Accra bounding box...")

    with rasterio.open(src_path) as src:
        # Clip to bounding box
        window = from_bounds(
            bbox["west"], bbox["south"],
            bbox["east"], bbox["north"],
            src.transform,
        )
        data = src.read(1, window=window)
        transform = src.window_transform(window)
        profile = src.profile.copy()

    profile.update(
        height=data.shape[0],
        width=data.shape[1],
        transform=transform,
        compress="deflate",
    )

    # If target_shape provided, resample to match DEM grid
    if target_shape is not None:
        log.info("Resampling from %s to %s (nearest neighbour)...",
                 data.shape, target_shape)

        import rasterio
        from rasterio.transform import from_bounds as tform_from_bounds

        dst_transform = tform_from_bounds(
            bbox["west"], bbox["south"],
            bbox["east"], bbox["north"],
            target_shape[1], target_shape[0],
        )

        dst_data = np.empty(target_shape, dtype=data.dtype)

        reproject(
            source=data,
            destination=dst_data,
            src_transform=transform,
            src_crs="EPSG:4326",
            dst_transform=dst_transform,
            dst_crs="EPSG:4326",
            resampling=Resampling.nearest,  # Nearest neighbour preserves class codes
        )

        profile.update(
            height=target_shape[0],
            width=target_shape[1],
            transform=dst_transform,
        )
        data = dst_data

    with rasterio.open(dst_path, "w", **profile) as dst:
        dst.write(data, 1)
        dst.update_tags(
            description="ESA WorldCover 2021 land cover clipped to Greater Accra",
            source="ESA WorldCover v200 2021",
            resolution="30m (resampled from 10m)",
            classes="10=Tree, 20=Shrub, 30=Grass, 40=Crop, 50=Urban, 60=Bare, 80=Water, 90=Wetland",
        )

    log.info("WorldCover clipped → %s  shape=%s", dst_path, data.shape)


def compute_imperviousness(landcover_path: str, output_path: str) -> None:
    """
    Convert categorical land cover classes to a continuous imperviousness
    fraction raster (0.0 = permeable, 1.0 = fully impervious).

    This is what gets used in the flood risk model — not the raw class codes.
    The imperviousness fraction represents how much rainfall becomes runoff.
    """
    import rasterio

    log.info("Computing imperviousness fraction from land cover classes...")

    with rasterio.open(landcover_path) as src:
        lc = src.read(1).astype(np.float32)
        profile = src.profile.copy()

    # Map each class code to its imperviousness fraction
    imperv = np.full_like(lc, 0.15, dtype=np.float32)  # Default: 15%
    for class_code, fraction in IMPERVIOUSNESS.items():
        imperv[lc == class_code] = fraction

    # Log class distribution
    log.info("Land cover class distribution:")
    class_names = {
        10: "Tree cover", 20: "Shrubland", 30: "Grassland",
        40: "Cropland",   50: "Built-up",  60: "Bare/sparse",
        80: "Water",      90: "Wetland",   95: "Mangroves",
    }
    total_pixels = lc.size
    for code, name in class_names.items():
        count = np.sum(lc == code)
        if count > 0:
            log.info("  Class %3d (%s): %.1f%%",
                     code, name, 100 * count / total_pixels)

    log.info("Imperviousness statistics:")
    log.info("  Min : %.2f  Max : %.2f  Mean: %.2f",
             float(np.min(imperv)), float(np.max(imperv)), float(np.mean(imperv)))

    profile.update(dtype="float32", compress="deflate", nodata=None)

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(imperv, 1)
        dst.update_tags(
            description="Impervious surface fraction derived from ESA WorldCover",
            units="fraction (0=permeable, 1=impervious)",
            note="High values = high runoff = higher flood risk contribution",
        )

    log.info("Imperviousness raster written → %s", output_path)


def get_dem_shape() -> tuple:
    """
    Read the DEM to get the target shape for resampling.
    Returns (height, width) or None if DEM doesn't exist.
    """
    import rasterio
    dem_path = os.path.join(DATA_DIR, "accra_dem.tif")
    if os.path.exists(dem_path):
        with rasterio.open(dem_path) as src:
            return src.shape
    return None


def main():
    log.info("=== Land Cover Ingest — ESA WorldCover 2021 ===")

    os.makedirs(DATA_DIR, exist_ok=True)

    # Skip if final output already exists
    if os.path.exists(OUTPUT_PATH):
        log.info("Land cover already exists → %s", OUTPUT_PATH)
        log.info("Delete the file to force a fresh download")
        return

    # Get DEM shape for resampling (match resolution)
    dem_shape = get_dem_shape()
    if dem_shape:
        log.info("Will resample to match DEM shape: %s", dem_shape)
    else:
        log.warning("DEM not found — will not resample. Run ingest_dem.py first.")

    # Find which tiles we need
    tiles = find_worldcover_tile(BBOX)

    # Download tiles
    tile_paths = []
    for tile in tiles:
        tile_path = os.path.join(DATA_DIR, f"worldcover_{tile}.tif")
        if os.path.exists(tile_path):
            log.info("Tile already downloaded: %s", tile_path)
            tile_paths.append(tile_path)
            continue

        success = download_worldcover_tile(tile, tile_path)
        if success:
            tile_paths.append(tile_path)
        else:
            log.error("Failed to download tile %s", tile)

    if not tile_paths:
        log.error("No WorldCover tiles downloaded.")
        log.error("Check your internet connection and try again.")
        raise SystemExit(1)

    # If multiple tiles, merge them first (for this bbox usually just one)
    if len(tile_paths) == 1:
        raw_tile = tile_paths[0]
    else:
        log.info("Merging %d tiles...", len(tile_paths))
        raw_tile = os.path.join(DATA_DIR, "worldcover_merged.tif")
        _merge_tiles(tile_paths, raw_tile)

    # Clip and optionally resample to DEM grid
    clip_and_resample(raw_tile, OUTPUT_RAW_PATH, BBOX, target_shape=dem_shape)

    # Convert class codes to imperviousness fraction
    compute_imperviousness(OUTPUT_RAW_PATH, OUTPUT_PATH)

    log.info("Land cover ingest complete ✓")
    log.info("Raw classes  → %s", OUTPUT_RAW_PATH)
    log.info("Imperviousness → %s", OUTPUT_PATH)


def _merge_tiles(tile_paths: list, output_path: str) -> None:
    """Merge multiple WorldCover tiles into one using rasterio merge."""
    import rasterio
    from rasterio.merge import merge

    datasets = [rasterio.open(p) for p in tile_paths]
    mosaic, transform = merge(datasets)
    profile = datasets[0].profile.copy()

    for ds in datasets:
        ds.close()

    profile.update(
        height=mosaic.shape[1],
        width=mosaic.shape[2],
        transform=transform,
        compress="deflate",
    )

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(mosaic)

    log.info("Tiles merged → %s", output_path)


if __name__ == "__main__":
    main()
