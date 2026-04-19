"""
ingest_waterbodies.py — Download Water Bodies from OpenStreetMap
================================================================
Source    : OpenStreetMap via Overpass API (free, no API key)
            + Fallback: HydroSHEDS river network (NASA/WWF)
Output    : data/accra_waterbodies.tif  (float32, distance in metres)

Why proximity to water matters for flood risk:
-----------------------------------------------
Areas close to rivers, lagoons, and the ocean are at significantly
higher flood risk than areas far from water bodies. During heavy
rainfall, rivers overflow their banks and coastal lagoons back up.

In Greater Accra, key water features include:
- Densu River and its delta (Weija area)
- Sakumo Lagoon (near Tema)
- Korle Lagoon (central Accra)
- Chemu Lagoon (Tema)
- Gulf of Guinea coastline

This script:
1. Downloads water body geometries from OpenStreetMap
2. Rasterizes them onto the DEM grid
3. Computes distance from each pixel to the nearest water body
4. The distance layer is then INVERTED in the risk model:
   close to water = high risk, far from water = low risk

Usage:
    python scripts/ingest_waterbodies.py
"""

import os
import logging
import json
import urllib.request  # noqa: F401
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
DATA_DIR    = os.getenv("DATA_DIR", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "accra_waterbodies.tif")
OSM_GEOJSON = os.path.join(DATA_DIR, "accra_water_osm.geojson")

# Greater Accra bounding box
BBOX = {
    "west":  float(os.getenv("BBOX_WEST",  "-0.50")),
    "east":  float(os.getenv("BBOX_EAST",   "0.50")),
    "south": float(os.getenv("BBOX_SOUTH",  "5.35")),
    "north": float(os.getenv("BBOX_NORTH",  "5.95")),
}

# Maximum distance to consider for risk calculation (in metres)
# Pixels beyond this distance get the minimum risk from this layer
MAX_DISTANCE_M = float(os.getenv("WATER_MAX_DISTANCE_M", "2000"))


# ── Overpass API Query ────────────────────────────────────────────────────────

def build_overpass_query(bbox: dict) -> str:
    """
    Build an Overpass QL query to fetch all water features in the bounding box.

    Overpass API is the query interface for OpenStreetMap data.
    We query for:
    - natural=water (lakes, ponds, lagoons)
    - natural=coastline (ocean boundary)
    - waterway=river (rivers)
    - waterway=stream (smaller streams)
    - landuse=reservoir (reservoirs, like Weija Dam)

    The query uses the [out:json] output format and includes geometry.
    """
    # Overpass bbox format: south,west,north,east (note different order from GDAL)
    bbox_str = f"{bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']}"

    query = f"""
    [out:json][timeout:60];
    (
      way["natural"="water"]({bbox_str});
      relation["natural"="water"]({bbox_str});
      way["natural"="coastline"]({bbox_str});
      way["waterway"="river"]({bbox_str});
      way["waterway"="stream"]({bbox_str});
      way["waterway"="canal"]({bbox_str});
      way["landuse"="reservoir"]({bbox_str});
      way["natural"="bay"]({bbox_str});
      relation["natural"="coastline"]({bbox_str});
    );
    out geom;
    """
    return query.strip()


def download_osm_water(output_geojson: str) -> bool:
    """
    Download water body geometries from OpenStreetMap via the Overpass API.

    The Overpass API is free and does not require an API key.
    Rate limits apply — avoid querying too frequently.
    Public endpoint: https://overpass-api.de/api/interpreter

    Includes exponential backoff retries to handle flaky API responses (429/504).
    """
    import urllib.parse
    import time

    log.info("Querying OpenStreetMap Overpass API for water features...")

    query = build_overpass_query(BBOX)
    url = "https://overpass-api.de/api/interpreter"
    
    max_retries = 5
    retry_delay = 5  # seconds

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                url,
                data=urllib.parse.urlencode({"data": query}).encode("utf-8"),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            log.info("Attempt %d/%d: Sending Overpass query (timeout: 180s)...", attempt, max_retries)
            with urllib.request.urlopen(req, timeout=200) as response:
                raw = response.read().decode("utf-8")

            data = json.loads(raw)
            element_count = len(data.get("elements", []))
            log.info("OSM returned %d water features", element_count)

            if element_count == 0:
                log.warning("No water features returned — check bounding box")
                return False

            # Convert OSM JSON to GeoJSON
            geojson = osm_to_geojson(data)

            with open(output_geojson, "w") as f:
                json.dump(geojson, f)

            log.info("Water features saved → %s (%d features)",
                     output_geojson, len(geojson["features"]))
            return True

        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            log.warning("Overpass API attempt %d failed: %s", attempt, str(e))
            if attempt < max_retries:
                sleep_time = retry_delay * (2 ** (attempt - 1))
                log.info("Retrying in %d seconds...", sleep_time)
                time.sleep(sleep_time)
            else:
                log.error("All Overpass API retries exhausted.")
                return False
        except Exception as e:
            log.error("Unexpected error during OSM ingest: %s", e)
            return False
    
    return False


def osm_to_geojson(osm_data: dict) -> dict:
    """
    Convert Overpass API JSON response to GeoJSON format.

    OSM ways have a list of geometry nodes. We convert each way to
    either a LineString (waterways) or a Polygon (water areas).
    """
    features = []

    for element in osm_data.get("elements", []):
        if element.get("type") != "way":
            continue

        geometry = element.get("geometry", [])
        if not geometry:
            continue

        # Extract coordinates [lon, lat]
        coords = [[node["lon"], node["lat"]] for node in geometry]
        if len(coords) < 2:
            continue

        tags = element.get("tags", {})

        # Determine geometry type
        # Closed ways (first == last point) with water tag = Polygon
        # Open ways with waterway tag = LineString
        if (coords[0] == coords[-1] and
                tags.get("natural") in ("water", "coastline", "bay") or
                tags.get("landuse") == "reservoir"):
            geom_type = "Polygon"
            coordinates = [coords]
        else:
            geom_type = "LineString"
            coordinates = coords

        features.append({
            "type": "Feature",
            "geometry": {
                "type": geom_type,
                "coordinates": coordinates,
            },
            "properties": {
                "osm_id":   element.get("id"),
                "natural":  tags.get("natural", ""),
                "waterway": tags.get("waterway", ""),
                "landuse":  tags.get("landuse", ""),
                "name":     tags.get("name", ""),
            }
        })

    return {"type": "FeatureCollection", "features": features}


# ── Rasterization and Distance Calculation ────────────────────────────────────

def rasterize_water(geojson_path: str, reference_dem: str,
                    output_path: str) -> None:
    """
    Rasterize water body geometries onto the DEM grid.
    Then compute Euclidean distance from each pixel to the nearest water pixel.

    Steps:
    1. Read reference DEM to get grid dimensions, CRS, and transform
    2. Rasterize GeoJSON water features onto that grid (binary: 1=water, 0=land)
    3. Apply scipy distance_transform_edt to get distance in pixels
    4. Convert pixel distances to metres using pixel size
    5. Cap at MAX_DISTANCE_M and invert so close=high, far=low
    """
    import rasterio
    from rasterio.features import rasterize as rio_rasterize

    log.info("Rasterizing water features onto DEM grid...")

    # Load reference DEM for grid parameters
    with rasterio.open(reference_dem) as src:
        profile = src.profile.copy()
        transform = src.transform
        height = src.height
        width = src.width
        pixel_size_x = abs(transform.a)   # degrees per pixel (x)
        pixel_size_y = abs(transform.e)   # degrees per pixel (y)

    # Convert pixel size to approximate metres
    # At Ghana's latitude (~5.8°N)
    metres_per_pixel_x = pixel_size_x * 110_715
    metres_per_pixel_y = pixel_size_y * 111_320
    metres_per_pixel = (metres_per_pixel_x + metres_per_pixel_y) / 2

    log.info("Pixel size: %.1f m", metres_per_pixel)

    # Load GeoJSON features
    with open(geojson_path) as f:
        geojson = json.load(f)

    features = geojson.get("features", [])
    log.info("Rasterizing %d water features...", len(features))

    # Prepare shapes for rasterio.rasterize
    # Each shape is (geometry, value) — we use value=1 for water
    shapes = []
    for feat in features:
        geom = feat.get("geometry")
        if geom:
            try:
                shapes.append((geom, 1))
            except Exception:
                pass

    if not shapes:
        log.error("No valid geometries to rasterize")
        raise ValueError("No water geometries found in GeoJSON")

    # Rasterize: 1 = water, 0 = land
    water_mask = rio_rasterize(
        shapes,
        out_shape=(height, width),
        transform=transform,
        fill=0,           # Default value for non-water pixels
        dtype=np.uint8,
        all_touched=True, # Include pixels touched by line geometries (rivers)
    )

    water_pixel_count = np.sum(water_mask)
    log.info("Water pixels: %d (%.1f%% of grid)",
             water_pixel_count, 100 * water_pixel_count / water_mask.size)

    if water_pixel_count == 0:
        log.warning("No water pixels after rasterization — check GeoJSON CRS")

    # Compute distance transform
    # scipy.ndimage.distance_transform_edt computes Euclidean distance
    # in pixels from each non-water pixel to the nearest water pixel
    log.info("Computing distance to nearest water body...")
    try:
        from scipy.ndimage import distance_transform_edt
    except ImportError:
        log.error("scipy not installed — run: pip install scipy")
        raise

    # distance_transform_edt operates on binary mask where 0=target
    # We want distance from non-water (1) to water (0)
    # So we pass (water_mask == 0) → True where water, False where land
    # Actually: pass the complement — distance from land pixels to water
    distance_pixels = distance_transform_edt(water_mask == 0)

    # Convert from pixels to metres
    distance_metres = (distance_pixels * metres_per_pixel).astype(np.float32)

    # Cap at maximum distance
    distance_metres = np.minimum(distance_metres, MAX_DISTANCE_M)

    log.info("Distance statistics:")
    log.info("  Min  : %.0f m (should be 0 — pixels directly on water)", float(np.min(distance_metres)))
    log.info("  Max  : %.0f m (capped at %.0f m)", float(np.max(distance_metres)), MAX_DISTANCE_M)
    log.info("  Mean : %.0f m", float(np.mean(distance_metres)))

    # Write output
    out_profile = profile.copy()
    out_profile.update(
        dtype="float32",
        count=1,
        compress="deflate",
        nodata=None,
    )

    with rasterio.open(output_path, "w", **out_profile) as dst:
        dst.write(distance_metres, 1)
        dst.update_tags(
            description="Distance to nearest water body in metres",
            units="metres",
            max_distance=str(MAX_DISTANCE_M),
            source="OpenStreetMap via Overpass API",
            note="In risk model: inverted so close=high risk, far=low risk",
        )

    log.info("Distance raster written → %s", output_path)


def main():
    log.info("=== Water Bodies Ingest — OpenStreetMap ===")

    os.makedirs(DATA_DIR, exist_ok=True)

    dem_path = os.path.join(DATA_DIR, "accra_dem.tif")
    if not os.path.exists(dem_path):
        log.error("DEM not found: %s", dem_path)
        log.error("Run: python scripts/ingest_dem.py")
        raise SystemExit(1)

    # Skip if output already exists
    if os.path.exists(OUTPUT_PATH):
        log.info("Water bodies already exists → %s", OUTPUT_PATH)
        log.info("Delete the file to force a fresh download")
        return

    # Download water features from OSM
    if not os.path.exists(OSM_GEOJSON):
        success = download_osm_water(OSM_GEOJSON)
        if not success:
            log.error("OSM download failed.")
            log.error("Check your internet connection and try again.")
            raise SystemExit(1)
    else:
        log.info("OSM GeoJSON already exists → %s", OSM_GEOJSON)

    # Rasterize and compute distance
    try:
        rasterize_water(OSM_GEOJSON, dem_path, OUTPUT_PATH)
    except ImportError as e:
        log.error("Missing dependency: %s", e)
        log.error("Run: pip install scipy shapely")
        raise SystemExit(1)

    log.info("Water bodies ingest complete ✓")
    log.info("Output → %s", OUTPUT_PATH)


if __name__ == "__main__":
    main()
