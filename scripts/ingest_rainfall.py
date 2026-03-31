"""
ingest_rainfall.py — Download Rainfall Data
============================================
Primary source : ERA5-Land monthly mean precipitation (ECMWF CDS)
Fallback source: GPM IMERG monthly mean (NASA, no API key needed)
Output         : data/accra_rainfall.tif  (float32, mm, EPSG:4326)

Why two sources?
----------------
ERA5-Land is the preferred source — it has been extensively validated
and is widely used in climate research. However it requires:
  - A free CDS API account (cds.climate.copernicus.eu)
  - A ~/.cdsapirc credentials file
  - The cdsapi Python package

GPM IMERG is the fallback — no API key, no credentials file needed.
It has slightly lower spatial resolution but is free and immediate.

ERA5 vs GPM for flood risk:
----------------------------
ERA5-Land: ~9km resolution, monthly means, validated against gauges
GPM IMERG: ~10km resolution, 30-min to monthly aggregations, near-realtime

For a static monthly risk model, ERA5 is slightly better.
For a near-realtime early warning system, GPM IMERG is the right choice
because it updates every 30 minutes with ~4 hour latency.

Usage:
    # With ERA5 (recommended, requires CDS account):
    python scripts/ingest_rainfall.py

    # Force GPM fallback:
    RAINFALL_SOURCE=gpm python scripts/ingest_rainfall.py

    # Specify year and month:
    RAINFALL_YEAR=2024 RAINFALL_MONTH=6 python scripts/ingest_rainfall.py
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
DATA_DIR    = os.getenv("DATA_DIR", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "accra_rainfall.tif")

# Temporal configuration — which month to download
YEAR  = int(os.getenv("RAINFALL_YEAR",  "2024"))
MONTH = int(os.getenv("RAINFALL_MONTH", "6"))     # June = peak rainy season

# Bounding box for Greater Accra (same as DEM)
BBOX = {
    "west":  float(os.getenv("BBOX_WEST",  "-0.50")),
    "east":  float(os.getenv("BBOX_EAST",   "0.50")),
    "south": float(os.getenv("BBOX_SOUTH",  "5.35")),
    "north": float(os.getenv("BBOX_NORTH",  "5.95")),
}

# Force a specific source (era5 or gpm). Default: try era5, fall back to gpm
RAINFALL_SOURCE = os.getenv("RAINFALL_SOURCE", "auto").lower()


# ── ERA5 Download ─────────────────────────────────────────────────────────────

def download_era5(output_path: str, year: int, month: int) -> bool:
    """
    Download ERA5-Land total precipitation for a given month.

    Requires:
    - cdsapi installed: pip install cdsapi
    - ~/.cdsapirc file with your CDS credentials:
        url: https://cds.climate.copernicus.eu/api/v2
        key: YOUR-UID:YOUR-API-KEY

    ERA5-Land precipitation is in metres per hour.
    We multiply by hours in the month to get total monthly precipitation in metres,
    then convert to millimetres (× 1000).

    Registration: https://cds.climate.copernicus.eu/user/register
    """
    try:
        import cdsapi
    except ImportError:
        log.warning("cdsapi not installed — run: pip install cdsapi")
        return False

    # Check for credentials file
    cdsapirc = os.path.expanduser("~/.cdsapirc")
    if not os.path.exists(cdsapirc):
        log.warning("CDS credentials not found at %s", cdsapirc)
        log.warning("Register at https://cds.climate.copernicus.eu and create ~/.cdsapirc")
        return False

    import calendar
    hours_in_month = 24 * calendar.monthrange(year, month)[1]
    month_str = f"{month:02d}"

    log.info("Downloading ERA5-Land precipitation for %d-%s...", year, month_str)

    try:
        c = cdsapi.Client(quiet=True)

        # Download to a temporary NetCDF file first
        tmp_nc = output_path.replace(".tif", "_tmp.nc")

        c.retrieve(
            "reanalysis-era5-land-monthly-means",
            {
                "product_type": "monthly_averaged_reanalysis",
                "variable":     "total_precipitation",
                "year":         str(year),
                "month":        month_str,
                "time":         "00:00",
                "area":         [               # [N, W, S, E]
                    BBOX["north"],
                    BBOX["west"],
                    BBOX["south"],
                    BBOX["east"],
                ],
                "format": "netcdf",
            },
            tmp_nc,
        )

        # Convert NetCDF to GeoTIFF using rasterio
        _nc_to_tiff(tmp_nc, output_path, scale_factor=hours_in_month * 1000)
        os.remove(tmp_nc)

        log.info("ERA5 rainfall downloaded → %s", output_path)
        return True

    except Exception as e:
        log.warning("ERA5 download failed: %s", e)
        # Clean up partial files
        for f in [output_path, output_path.replace(".tif", "_tmp.nc")]:
            if os.path.exists(f):
                os.remove(f)
        return False


def _nc_to_tiff(nc_path: str, tiff_path: str, scale_factor: float = 1.0) -> None:
    """
    Convert an ERA5 NetCDF file to a GeoTIFF.
    Applies a scale factor to convert from m/hr to mm/month.
    """
    try:
        import netCDF4 as nc
        import rasterio
        from rasterio.transform import from_bounds

        ds = nc.Dataset(nc_path)

        # ERA5 variable name for total precipitation
        var_name = "tp"
        data = ds.variables[var_name][0, :, :]  # First time step
        lats = ds.variables["latitude"][:]
        lons = ds.variables["longitude"][:]
        ds.close()

        # Apply scale factor (convert m/hr to mm/month)
        data = (np.array(data) * scale_factor).astype(np.float32)

        # ERA5 lats are descending (north to south) — rasterio expects this
        transform = from_bounds(
            float(lons.min()), float(lats.min()),
            float(lons.max()), float(lats.max()),
            data.shape[1], data.shape[0]
        )

        with rasterio.open(
            tiff_path, "w",
            driver="GTiff", height=data.shape[0], width=data.shape[1],
            count=1, dtype="float32", crs="EPSG:4326",
            transform=transform, compress="deflate",
        ) as dst:
            dst.write(data, 1)
            dst.update_tags(
                description="ERA5-Land total monthly precipitation",
                units="mm/month",
                year=str(nc_path),
            )

    except ImportError:
        log.error("netCDF4 not installed — run: pip install netCDF4")
        raise


# ── GPM Download ──────────────────────────────────────────────────────────────

def download_gpm(output_path: str, year: int, month: int) -> bool:
    """
    Download GPM IMERG monthly precipitation.

    GPM (Global Precipitation Measurement) IMERG Final Run provides
    monthly precipitation estimates at 0.1° resolution (~10km).

    No API key needed — data is publicly available via NASA's GESDISC.
    However some datasets require a free NASA Earthdata account.

    We use the publicly accessible IMERG data via the OpenDAP endpoint.
    If that fails we fall back to a simplified approach using the
    public HTTP archive.

    Units: mm/month (already accumulated)
    """
    import calendar

    month_str = f"{month:02d}"
    days_in_month = calendar.monthrange(year, month)[1]

    log.info("Downloading GPM IMERG monthly precipitation for %d-%s...", year, month_str)

    # GPM IMERG Final Run monthly data URL pattern
    # Note: GPM data has ~3 month latency for the Final Run product
    # Near-real-time (NRT) data is available with ~4 hour latency
    base_url = (
        "https://gpm1.gesdisc.eosdis.nasa.gov/data"
        f"/GPM_L3/GPM_3IMERGM.07/{year}"
        f"/3B-MO.MS.MRG.3IMERG.{year}{month_str}01-S000000-E235959"
        f".{month_str}.V07B.HDF5"
    )

    # Alternative: use a pre-processed monthly climatology
    # This is a simplified fallback that downloads from a public mirror
    alt_url = (
        f"https://pmm.nasa.gov/sites/default/files/imce"
        f"/GPM_IMERG_{year}_{month_str}.tif"
    )

    try:
        # Try to create a synthetic GPM-like raster from CHIRPS if direct download fails
        return _download_gpm_via_opendap(output_path, year, month, days_in_month)

    except Exception as e:
        log.warning("GPM download failed: %s", e)
        log.warning("Trying CHIRPS fallback...")
        return _download_chirps(output_path, year, month)


def _download_gpm_via_opendap(
    output_path: str, year: int, month: int, days_in_month: int
) -> bool:
    """
    Download GPM IMERG data via NASA GES DISC HTTP archive.
    Requires free NASA Earthdata account for some products.
    """
    import rasterio
    from rasterio.transform import from_bounds

    month_str = f"{month:02d}"

    # GPM IMERG Late Run (available with ~12hr latency, no Earthdata login needed)
    # This is slightly less accurate than the Final Run but freely accessible
    url = (
        "https://jsimpsonhttps.pps.eosdis.nasa.gov/imerg/gis/monthly"
        f"/{year}/{month_str}/3B-MO-L.MS.MRG.3IMERG"
        f".{year}{month_str}01.V07B.tif"
    )

    tmp_path = output_path.replace(".tif", "_gpm_tmp.tif")

    try:
        log.info("Fetching GPM IMERG from NASA GES DISC...")
        urllib.request.urlretrieve(url, tmp_path)

        # GPM data covers the whole globe — clip to our bounding box
        _clip_to_bbox(tmp_path, output_path, BBOX)
        os.remove(tmp_path)

        log.info("GPM rainfall downloaded → %s", output_path)
        return True

    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise e


def _download_chirps(output_path: str, year: int, month: int) -> bool:
    """
    Fallback: Download CHIRPS monthly precipitation.

    CHIRPS (Climate Hazards Group InfraRed Precipitation with Station data)
    is a 35+ year quasi-global rainfall dataset at 0.05° resolution (~5km).
    It is freely available with no authentication required.

    URL pattern: https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_monthly/tifs/
    """
    import rasterio

    month_str = f"{month:02d}"
    filename = f"chirps-v2.0.{year}.{month_str}.tif.gz"
    url = (
        f"https://data.chc.ucsb.edu/products/CHIRPS-2.0"
        f"/global_monthly/tifs/{filename}"
    )

    tmp_gz  = output_path.replace(".tif", "_chirps.tif.gz")
    tmp_tif = output_path.replace(".tif", "_chirps_global.tif")

    try:
        log.info("Downloading CHIRPS monthly precipitation (fallback)...")
        urllib.request.urlretrieve(url, tmp_gz)

        # Decompress .gz file
        import gzip
        with gzip.open(tmp_gz, "rb") as f_in:
            with open(tmp_tif, "wb") as f_out:
                f_out.write(f_in.read())
        os.remove(tmp_gz)

        # Clip to Greater Accra bounding box
        _clip_to_bbox(tmp_tif, output_path, BBOX)
        os.remove(tmp_tif)

        log.info("CHIRPS rainfall downloaded → %s", output_path)
        return True

    except Exception as e:
        for f in [tmp_gz, tmp_tif]:
            if os.path.exists(f):
                os.remove(f)
        log.error("CHIRPS download failed: %s", e)
        return False


def _clip_to_bbox(src_path: str, dst_path: str, bbox: dict) -> None:
    """
    Clip a global GeoTIFF to the bounding box using rasterio windowed reading.
    Much faster than downloading the whole global file.
    """
    import rasterio
    from rasterio.windows import from_bounds

    with rasterio.open(src_path) as src:
        window = from_bounds(
            bbox["west"], bbox["south"],
            bbox["east"], bbox["north"],
            src.transform,
        )
        data = src.read(1, window=window).astype(np.float32)
        transform = src.window_transform(window)
        profile = src.profile.copy()

    profile.update(
        height=data.shape[0],
        width=data.shape[1],
        transform=transform,
        dtype="float32",
        compress="deflate",
    )

    with rasterio.open(dst_path, "w", **profile) as dst:
        dst.write(data, 1)
        dst.update_tags(
            description="Monthly precipitation clipped to Greater Accra",
            units="mm/month",
        )


# ── Validation ────────────────────────────────────────────────────────────────

def validate_rainfall(output_path: str) -> None:
    """
    Log basic statistics for the downloaded rainfall raster.
    Typical June rainfall in Greater Accra: 150–250mm/month.
    """
    import rasterio

    with rasterio.open(output_path) as src:
        data = src.read(1).astype(float)
        nodata = src.nodata
        if nodata is not None:
            data[data == nodata] = float("nan")
        data[data < 0] = float("nan")  # Remove any negative values

    valid = data[~np.isnan(data)]
    log.info("Rainfall validation:")
    log.info("  Shape : %s", data.shape)
    log.info("  Min   : %.1f mm", float(np.min(valid)))
    log.info("  Max   : %.1f mm", float(np.max(valid)))
    log.info("  Mean  : %.1f mm", float(np.mean(valid)))

    # Warn if values seem unrealistic for Greater Accra
    if np.mean(valid) < 50 or np.mean(valid) > 500:
        log.warning("Mean rainfall %.1f mm seems unusual for Greater Accra", float(np.mean(valid)))
        log.warning("Expected range: 50–500 mm/month depending on season")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=== Rainfall Ingest — Year=%d Month=%02d ===", YEAR, MONTH)

    os.makedirs(DATA_DIR, exist_ok=True)

    # Skip if file already exists
    if os.path.exists(OUTPUT_PATH):
        log.info("Rainfall already exists → %s", OUTPUT_PATH)
        log.info("Delete the file to force a fresh download")
        validate_rainfall(OUTPUT_PATH)
        return

    success = False

    # Try ERA5 first (unless forced to GPM)
    if RAINFALL_SOURCE in ("auto", "era5"):
        log.info("Attempting ERA5-Land download...")
        success = download_era5(OUTPUT_PATH, YEAR, MONTH)

    # Fall back to GPM/CHIRPS
    if not success and RAINFALL_SOURCE in ("auto", "gpm"):
        log.info("Falling back to GPM IMERG / CHIRPS...")
        success = download_gpm(OUTPUT_PATH, YEAR, MONTH)

    if not success:
        log.error("All rainfall download attempts failed.")
        log.error("Manual option: copy accra_rainfall.tif to %s", DATA_DIR)
        log.error("ERA5 setup: https://cds.climate.copernicus.eu/api-how-to")
        raise SystemExit(1)

    validate_rainfall(OUTPUT_PATH)
    log.info("Rainfall ingest complete ✓")


if __name__ == "__main__":
    main()
