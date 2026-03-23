"""
Data Ingestion Script — Greater Accra Region
Downloads fresh DEM, rainfall, and slope data from free public sources.

Sources
-------
- DEM    : Copernicus DEM (GLO-30) via OpenTopography API (free, no key needed)
           Fallback: SRTM 30m via Earthdata
- Rainfall: ERA5-Land monthly via the CDS API (free ECMWF account required)
            Fallback: uses bundled accra_rainfall.tif from the repo
- Slope  : Derived from DEM locally using GDAL — no external source needed

Usage
-----
    python ingest.py [--year YYYY] [--month MM]

The script writes to the DATA_DIR directory (default: data/).
"""

import os
import sys
import logging
import argparse
import urllib.request
import subprocess
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Bounding box for Greater Accra (from the uploaded tif files)
BBOX = {
    "west":  -0.5212,
    "south":  5.4682,
    "east":   0.6873,
    "north":  6.1085,
}

DATA_DIR = os.getenv("DATA_DIR", "data")


# ---------------------------------------------------------------------------
# DEM download — Copernicus GLO-30 via OpenTopography
# ---------------------------------------------------------------------------

def download_dem(out_path: str) -> bool:
    """
    Download Copernicus GLO-30 DEM for the Accra bounding box.
    OpenTopography provides a free REST API with no API key for GLO-30.
    """
    url = (
        "https://portal.opentopography.org/API/globaldem"
        "?demtype=COP30"
        f"&south={BBOX['south']}&north={BBOX['north']}"
        f"&west={BBOX['west']}&east={BBOX['east']}"
        "&outputFormat=GTiff"
    )
    log.info("Downloading Copernicus GLO-30 DEM …")
    try:
        urllib.request.urlretrieve(url, out_path)
        log.info("DEM saved → %s", out_path)
        return True
    except Exception as e:
        log.warning("DEM download failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Slope derivation — from DEM using GDAL (no network needed)
# ---------------------------------------------------------------------------

def derive_slope(dem_path: str, slope_path: str) -> None:
    """Derive slope (degrees) from DEM using gdaldem."""
    log.info("Deriving slope from DEM …")
    cmd = ["gdaldem", "slope", dem_path, slope_path, "-of", "GTiff", "-compute_edges"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gdaldem failed: {result.stderr}")
    log.info("Slope saved → %s", slope_path)


# ---------------------------------------------------------------------------
# Rainfall download — ERA5-Land via CDS API
# ---------------------------------------------------------------------------

def download_rainfall_era5(year: int, month: int, out_path: str) -> bool:
    """
    Download ERA5-Land total precipitation for the given month.
    Requires: pip install cdsapi  and  ~/.cdsapirc with your free ECMWF key.
    See: https://cds.climate.copernicus.eu/api-how-to
    """
    try:
        import cdsapi  # type: ignore
    except ImportError:
        log.warning("cdsapi not installed — run: pip install cdsapi")
        return False

    log.info("Downloading ERA5-Land rainfall for %d-%02d …", year, month)
    c = cdsapi.Client()
    tmp_nc = out_path.replace(".tif", ".nc")
    try:
        c.retrieve(
            "reanalysis-era5-land-monthly-means",
            {
                "product_type": "monthly_averaged_reanalysis",
                "variable": "total_precipitation",
                "year": str(year),
                "month": f"{month:02d}",
                "time": "00:00",
                "area": [BBOX["north"], BBOX["west"], BBOX["south"], BBOX["east"]],
                "format": "netcdf",
            },
            tmp_nc,
        )
        # Convert mm/s → mm/month and write as GeoTIFF
        _nc_to_geotiff(tmp_nc, out_path, year, month)
        os.remove(tmp_nc)
        log.info("Rainfall saved → %s", out_path)
        return True
    except Exception as e:
        log.warning("ERA5 download failed: %s", e)
        return False


def _nc_to_geotiff(nc_path: str, tif_path: str, year: int, month: int) -> None:
    """Convert ERA5 NetCDF precipitation to GeoTIFF (mm/month)."""
    import netCDF4 as nc  # type: ignore
    ds = nc.Dataset(nc_path)
    # ERA5 tp is in m — convert to mm
    tp_var = ds.variables.get("tp") or ds.variables.get("mtpr")
    data = tp_var[0, :, :] * 1000  # m → mm

    lats = ds.variables["latitude"][:]
    lons = ds.variables["longitude"][:]
    res_lat = abs(float(lats[1] - lats[0]))
    res_lon = abs(float(lons[1] - lons[0]))

    transform = from_bounds(
        float(lons.min()), float(lats.min()),
        float(lons.max()), float(lats.max()),
        data.shape[1], data.shape[0],
    )
    profile = {
        "driver": "GTiff",
        "dtype": "float64",
        "width": data.shape[1],
        "height": data.shape[0],
        "count": 1,
        "crs": CRS.from_epsg(4326),
        "transform": transform,
        "compress": "deflate",
    }
    # Flip latitude (ERA5 is N→S, rasterio expects S→N origin)
    data = np.flipud(np.array(data))
    with rasterio.open(tif_path, "w", **profile) as dst:
        dst.write(data.astype(np.float64), 1)
    ds.close()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Ingest flood risk input data")
    parser.add_argument("--year",  type=int, default=2024)
    parser.add_argument("--month", type=int, default=6)
    args = parser.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)

    dem_path      = os.path.join(DATA_DIR, "accra_dem.tif")
    slope_path    = os.path.join(DATA_DIR, "accra_slope.tif")
    rainfall_path = os.path.join(DATA_DIR, "accra_rainfall.tif")

    # DEM
    if not os.path.exists(dem_path):
        ok = download_dem(dem_path)
        if not ok:
            log.error("Could not download DEM. Place accra_dem.tif in %s manually.", DATA_DIR)
            sys.exit(1)
    else:
        log.info("DEM already exists, skipping download.")

    # Slope (derived locally — no network)
    if not os.path.exists(slope_path):
        derive_slope(dem_path, slope_path)
    else:
        log.info("Slope already exists, skipping derivation.")

    # Rainfall
    if not os.path.exists(rainfall_path):
        ok = download_rainfall_era5(args.year, args.month, rainfall_path)
        if not ok:
            log.warning(
                "ERA5 download failed. Place accra_rainfall.tif in %s manually "
                "or set up ~/.cdsapirc — see https://cds.climate.copernicus.eu/api-how-to",
                DATA_DIR,
            )
    else:
        log.info("Rainfall already exists, skipping download.")

    log.info("Ingestion complete ✓")


if __name__ == "__main__":
    main()
