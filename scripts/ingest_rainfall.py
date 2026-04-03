"""
ingest_rainfall.py — Download Monthly Precipitation
=====================================================
Primary source : GPM IMERG Final Run (NASA) — actual monthly precipitation
                 0.1° resolution (~10km), bias-corrected against rain gauges
                 Requires free NASA Earthdata account
Fallback 1     : GPM IMERG Late Run — near real-time, ~12 hour latency
Fallback 2     : ERA5-Land monthly mean (ECMWF CDS) — requires CDS account
Fallback 3     : CHIRPS v2.0 — no authentication required
Output         : data/accra_rainfall.tif  (float32, mm/month, EPSG:4326)

Why GPM IMERG over ERA5:
--------------------------
ERA5 provides climatological monthly means — essentially a historical
average. GPM IMERG provides ACTUAL rainfall for the specific month being
processed. This means:

- If June 2024 had unusually heavy rainfall, GPM captures it
- ERA5 would return the same June average regardless of the actual year
- GPM updates near-real-time — Late Run available within 12 hours
- This makes FloodWatch genuinely responsive to real rainfall conditions

GPM IMERG Products:
--------------------
Final Run  — best accuracy, bias-corrected against rain gauges
             ~3.5 month latency — use for historical months
Late Run   — near real-time, ~12 hour latency, no gauge correction
             use for recent months where Final Run not yet available
Early Run  — fastest, ~4 hour latency, least accurate (not used here)

Resolution : 0.1° x 0.1° (~10km)
Coverage   : 60S to 60N — covers Ghana perfectly
Units      : mm/month (accumulated)

Authentication:
---------------
GPM IMERG requires a free NASA Earthdata account:
  Register : https://urs.earthdata.nasa.gov/users/new
  Set .env :
    EARTHDATA_USER=your_username
    EARTHDATA_PASS=your_password

Also requires h5py for HDF5 parsing:
  pip install h5py

Usage:
    python scripts/ingest_rainfall.py

    # Force specific source:
    RAINFALL_SOURCE=gpm_final  python scripts/ingest_rainfall.py
    RAINFALL_SOURCE=gpm_late   python scripts/ingest_rainfall.py
    RAINFALL_SOURCE=chirps     python scripts/ingest_rainfall.py
"""

import os
import gzip
import logging
import calendar
import urllib.request
import urllib.error
import numpy as np
from datetime import date

# Remove conflicting PROJ installation from environment (PostgreSQL/PostGIS)
# Forces rasterio to use its own bundled PROJ data
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

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

YEAR  = int(os.getenv("RAINFALL_YEAR",  "2024"))
MONTH = int(os.getenv("RAINFALL_MONTH", "6"))

# Source: auto = GPM Final → GPM Late → ERA5 → CHIRPS
RAINFALL_SOURCE = os.getenv("RAINFALL_SOURCE", "auto").lower()

# NASA Earthdata credentials
EARTHDATA_USER = os.getenv("EARTHDATA_USER", "")
EARTHDATA_PASS = os.getenv("EARTHDATA_PASS", "")

# Greater Accra bounding box
BBOX = {
    "west":  float(os.getenv("BBOX_WEST",  "-0.50")),
    "east":  float(os.getenv("BBOX_EAST",   "0.50")),
    "south": float(os.getenv("BBOX_SOUTH",  "5.35")),
    "north": float(os.getenv("BBOX_NORTH",  "5.95")),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def months_ago(year: int, month: int) -> int:
    """How many months ago was this year/month from today."""
    today = date.today()
    return (today.year - year) * 12 + (today.month - month)


def build_earthdata_opener() -> urllib.request.OpenerDirector:
    """Build URL opener with NASA Earthdata Basic Auth + cookie support."""
    password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    password_mgr.add_password(
        None,
        "https://urs.earthdata.nasa.gov",
        EARTHDATA_USER,
        EARTHDATA_PASS,
    )
    auth_handler   = urllib.request.HTTPBasicAuthHandler(password_mgr)
    cookie_handler = urllib.request.HTTPCookieProcessor()
    return urllib.request.build_opener(auth_handler, cookie_handler)


def write_raster(data: np.ndarray, output_path: str,
                 source: str, year: int, month: int) -> None:
    """Write rainfall array as GeoTIFF over Greater Accra bounding box."""
    import rasterio
    from rasterio.transform import from_bounds

    rows, cols = data.shape
    transform  = from_bounds(
        BBOX["west"], BBOX["south"],
        BBOX["east"], BBOX["north"],
        cols, rows,
    )

    os.makedirs(DATA_DIR, exist_ok=True)

    with rasterio.open(
        output_path, "w",
        driver="GTiff",
        height=rows, width=cols,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        compress="deflate",
    ) as dst:
        dst.write(data.astype(np.float32), 1)
        dst.update_tags(
            description="Monthly total precipitation — Greater Accra",
            source=source,
            year=str(year),
            month=f"{month:02d}",
            units="mm/month",
        )

    log.info("Rainfall raster written → %s", output_path)


def validate(output_path: str) -> None:
    """Log rainfall statistics and flag suspicious values."""
    import rasterio

    with rasterio.open(output_path) as src:
        data = src.read(1).astype(float)
        nodata = src.nodata
        if nodata is not None:
            data[data == nodata] = float("nan")
        data[data < 0] = float("nan")

    valid = data[~np.isnan(data)]
    if len(valid) == 0:
        log.warning("No valid rainfall pixels")
        return

    log.info("Rainfall stats:")
    log.info("  Min  : %.1f mm/month", float(np.min(valid)))
    log.info("  Max  : %.1f mm/month", float(np.max(valid)))
    log.info("  Mean : %.1f mm/month", float(np.mean(valid)))

    mean = float(np.mean(valid))
    if mean < 10 or mean > 600:
        log.warning("Mean %.1f mm seems unusual — check data", mean)


# ── GPM IMERG Final Run ───────────────────────────────────────────────────────

def download_gpm_final(year: int, month: int) -> bool:
    """
    Download GPM IMERG Final Run monthly precipitation.

    Most accurate GPM product — bias-corrected against GPCC rain gauge data.
    Available with ~3.5 month latency. Best for historical analysis.

    File format: HDF5 (.HDF5)
    Variable   : Grid/precipitation (mm/hr mean — multiply by hours in month)
    Global grid: 0.1 degree, -180 to 180 lon, -90 to 90 lat
    """
    if not EARTHDATA_USER or not EARTHDATA_PASS:
        log.warning("NASA Earthdata credentials not set — skipping GPM Final")
        return False

    if months_ago(year, month) < 4:
        log.info("GPM Final Run not yet available for %d-%02d — too recent",
                 year, month)
        return False

    month_str = f"{month:02d}"
    days      = calendar.monthrange(year, month)[1]

    filename = (
        f"3B-MO.MS.MRG.3IMERG.{year}{month_str}01"
        f"-S000000-E235959.{month_str}.V07B.HDF5"
    )
    url = (
        f"https://gpm1.gesdisc.eosdis.nasa.gov/data"
        f"/GPM_L3/GPM_3IMERGM.07/{year}/{filename}"
    )

    log.info("Downloading GPM IMERG Final Run %d-%02d...", year, month)
    tmp = os.path.join(DATA_DIR, f"gpm_final_tmp.HDF5")

    try:
        opener = build_earthdata_opener()
        urllib.request.install_opener(opener)
        urllib.request.urlretrieve(url, tmp)
        log.info("Downloaded %.1f MB", os.path.getsize(tmp) / 1024 / 1024)

        data = _parse_gpm_hdf5(tmp, days)
        os.remove(tmp)

        if data is None:
            return False

        write_raster(data, OUTPUT_PATH, "GPM IMERG Final Run V07B", year, month)
        return True

    except urllib.error.HTTPError as e:
        log.warning("GPM Final Run HTTP %s: %s", e.code, e.reason)
        if os.path.exists(tmp):
            os.remove(tmp)
        return False
    except Exception as e:
        log.warning("GPM Final Run failed: %s", e)
        if os.path.exists(tmp):
            os.remove(tmp)
        return False


# ── GPM IMERG Late Run ────────────────────────────────────────────────────────

def download_gpm_late(year: int, month: int) -> bool:
    """
    Download GPM IMERG Late Run monthly precipitation.

    Near real-time — available within ~12 hours of month end.
    No bias correction against gauges but good accuracy.
    Used for recent months where Final Run is not yet available.
    """
    if not EARTHDATA_USER or not EARTHDATA_PASS:
        log.warning("NASA Earthdata credentials not set — skipping GPM Late")
        return False

    month_str = f"{month:02d}"
    days      = calendar.monthrange(year, month)[1]

    filename = (
        f"3B-MO-L.MS.MRG.3IMERG.{year}{month_str}01"
        f"-S000000-E235959.{month_str}.V07B.HDF5"
    )
    url = (
        f"https://gpm1.gesdisc.eosdis.nasa.gov/data"
        f"/GPM_L3/GPM_3IMERGML.07/{year}/{filename}"
    )

    log.info("Downloading GPM IMERG Late Run %d-%02d...", year, month)
    tmp = os.path.join(DATA_DIR, f"gpm_late_tmp.HDF5")

    try:
        opener = build_earthdata_opener()
        urllib.request.install_opener(opener)
        urllib.request.urlretrieve(url, tmp)
        log.info("Downloaded %.1f MB", os.path.getsize(tmp) / 1024 / 1024)

        data = _parse_gpm_hdf5(tmp, days)
        os.remove(tmp)

        if data is None:
            return False

        write_raster(data, OUTPUT_PATH, "GPM IMERG Late Run V07B", year, month)
        return True

    except urllib.error.HTTPError as e:
        log.warning("GPM Late Run HTTP %s: %s", e.code, e.reason)
        if os.path.exists(tmp):
            os.remove(tmp)
        return False
    except Exception as e:
        log.warning("GPM Late Run failed: %s", e)
        if os.path.exists(tmp):
            os.remove(tmp)
        return False


def _parse_gpm_hdf5(hdf5_path: str, days_in_month: int) -> np.ndarray:
    """
    Parse GPM IMERG HDF5 and return mm/month clipped to Greater Accra.

    GPM HDF5 structure:
      Grid/precipitation — shape (1, lon, lat) — units: mm/hr
      Longitude: -180 to 180 at 0.1 degrees (3600 pixels)
      Latitude:  -90 to 90 at 0.1 degrees  (1800 pixels)

    Steps:
    1. Read Grid/precipitation
    2. Transpose from (lon, lat) to (lat, lon)
    3. Flip vertically — GPM lat goes S to N, rasterio expects N to S
    4. Convert mm/hr to mm/month by multiplying by hours in month
    5. Clip to Greater Accra bounding box
    """
    try:
        import h5py
    except ImportError:
        log.warning("h5py not installed — run: pip install h5py")
        return None

    try:
        with h5py.File(hdf5_path, "r") as f:
            precip = f["Grid/precipitation"][0, :, :]  # (lon, lat)
            fill   = f["Grid/precipitation"].attrs.get("_FillValue", -9999.9)

        # Transpose and flip
        precip = np.flipud(precip.T)  # now (lat, lon), north at top

        # Replace fill values
        precip = precip.astype(np.float32)
        precip[precip == fill] = np.nan
        precip[precip < 0]     = np.nan

        # Convert mm/hr → mm/month
        hours_in_month = days_in_month * 24
        precip = precip * hours_in_month

        log.info("GPM global mean: %.1f mm/month", float(np.nanmean(precip)))

        # Clip to Greater Accra
        # Grid: lat from 90 (top) to -90 (bottom) after flipud
        # lon from -180 (left) to 180 (right)
        lat_min_idx = int((90 - BBOX["north"]) / 0.1)
        lat_max_idx = int((90 - BBOX["south"]) / 0.1)
        lon_min_idx = int((BBOX["west"] + 180) / 0.1)
        lon_max_idx = int((BBOX["east"] + 180) / 0.1)

        clipped = precip[lat_min_idx:lat_max_idx, lon_min_idx:lon_max_idx]
        log.info("Clipped to Greater Accra: %s  mean: %.1f mm/month",
                 clipped.shape, float(np.nanmean(clipped)))

        return clipped

    except Exception as e:
        log.warning("HDF5 parsing failed: %s", e)
        return None


# ── ERA5 Fallback ─────────────────────────────────────────────────────────────

def download_era5(year: int, month: int) -> bool:
    """
    Download ERA5-Land monthly precipitation as fallback.
    Requires ~/.cdsapirc credentials file from cds.climate.copernicus.eu
    """
    try:
        import cdsapi
    except ImportError:
        log.warning("cdsapi not installed — skipping ERA5")
        return False

    if not os.path.exists(os.path.expanduser("~/.cdsapirc")):
        log.warning("CDS credentials not found — skipping ERA5")
        return False

    hours_in_month = 24 * calendar.monthrange(year, month)[1]
    month_str      = f"{month:02d}"
    tmp_nc         = os.path.join(DATA_DIR, "era5_tmp.nc")

    log.info("Downloading ERA5-Land for %d-%02d...", year, month)

    try:
        c = cdsapi.Client(quiet=True)
        c.retrieve(
            "reanalysis-era5-land-monthly-means",
            {
                "product_type": "monthly_averaged_reanalysis",
                "variable":     "total_precipitation",
                "year":         str(year),
                "month":        month_str,
                "time":         "00:00",
                "area":         [
                    BBOX["north"], BBOX["west"],
                    BBOX["south"], BBOX["east"],
                ],
                "format": "netcdf",
            },
            tmp_nc,
        )

        _nc_to_tiff(tmp_nc, OUTPUT_PATH,
                    scale=hours_in_month * 1000,
                    source="ERA5-Land", year=year, month=month)
        os.remove(tmp_nc)
        log.info("ERA5 downloaded ✓")
        return True

    except Exception as e:
        log.warning("ERA5 failed: %s", e)
        if os.path.exists(tmp_nc):
            os.remove(tmp_nc)
        return False


def _nc_to_tiff(nc_path: str, tiff_path: str, scale: float,
                source: str, year: int, month: int) -> None:
    """Convert ERA5 NetCDF to GeoTIFF."""
    import netCDF4 as nc
    import rasterio
    from rasterio.transform import from_bounds

    ds   = nc.Dataset(nc_path)
    data = ds.variables["tp"][0, :, :]
    lats = ds.variables["latitude"][:]
    lons = ds.variables["longitude"][:]
    ds.close()

    data = (np.array(data) * scale).astype(np.float32)
    transform = from_bounds(
        float(lons.min()), float(lats.min()),
        float(lons.max()), float(lats.max()),
        data.shape[1], data.shape[0],
    )

    with rasterio.open(
        tiff_path, "w",
        driver="GTiff",
        height=data.shape[0], width=data.shape[1],
        count=1, dtype="float32",
        crs="EPSG:4326", transform=transform,
        compress="deflate",
    ) as dst:
        dst.write(data, 1)
        dst.update_tags(
            description="ERA5-Land monthly precipitation",
            source=source, units="mm/month",
            year=str(year), month=f"{month:02d}",
        )


# ── CHIRPS Fallback ───────────────────────────────────────────────────────────

def download_chirps(year: int, month: int) -> bool:
    """
    Download CHIRPS v2.0 monthly precipitation — no authentication required.
    5km resolution, 35+ year record. Last resort fallback.
    """
    month_str = f"{month:02d}"
    filename  = f"chirps-v2.0.{year}.{month_str}.tif.gz"
    url = (
        f"https://data.chc.ucsb.edu/products/CHIRPS-2.0"
        f"/global_monthly/tifs/{filename}"
    )

    tmp_gz  = os.path.join(DATA_DIR, f"chirps_tmp.tif.gz")
    tmp_tif = os.path.join(DATA_DIR, f"chirps_tmp_global.tif")

    log.info("Downloading CHIRPS v2.0 for %d-%02d...", year, month)

    try:
        urllib.request.urlretrieve(url, tmp_gz)

        with gzip.open(tmp_gz, "rb") as f_in:
            with open(tmp_tif, "wb") as f_out:
                f_out.write(f_in.read())
        os.remove(tmp_gz)

        _clip_tif(tmp_tif, OUTPUT_PATH,
                  source="CHIRPS v2.0", year=year, month=month)
        os.remove(tmp_tif)
        log.info("CHIRPS downloaded ✓")
        return True

    except Exception as e:
        log.error("CHIRPS failed: %s", e)
        for f in [tmp_gz, tmp_tif]:
            if os.path.exists(f):
                os.remove(f)
        return False


def _clip_tif(src_path: str, dst_path: str,
              source: str, year: int, month: int) -> None:
    """Clip a global GeoTIFF to Greater Accra bounding box."""
    import rasterio
    from rasterio.windows import from_bounds as win_from_bounds

    with rasterio.open(src_path) as src:
        window    = win_from_bounds(
            BBOX["west"], BBOX["south"],
            BBOX["east"], BBOX["north"],
            src.transform,
        )
        data      = src.read(1, window=window).astype(np.float32)
        transform = src.window_transform(window)
        profile   = src.profile.copy()

    profile.update(
        height=data.shape[0], width=data.shape[1],
        transform=transform, dtype="float32", compress="deflate",
    )

    with rasterio.open(dst_path, "w", **profile) as dst:
        dst.write(data, 1)
        dst.update_tags(
            description="CHIRPS v2.0 monthly precipitation — Greater Accra",
            source=source, units="mm/month",
            year=str(year), month=f"{month:02d}",
        )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=== Rainfall Ingest — Year=%d Month=%02d ===", YEAR, MONTH)
    log.info("Priority: GPM Final → GPM Late → ERA5 → CHIRPS")

    os.makedirs(DATA_DIR, exist_ok=True)

    # Check h5py for GPM HDF5 parsing
    try:
        import h5py  # noqa: F401
        log.info("h5py available ✓ — GPM IMERG enabled")
    except ImportError:
        log.warning("h5py not installed — GPM IMERG disabled")
        log.warning("Run: pip install h5py")

    # Skip if already exists
    if os.path.exists(OUTPUT_PATH):
        log.info("Rainfall already exists → %s", OUTPUT_PATH)
        log.info("Delete to force re-download")
        validate(OUTPUT_PATH)
        return

    success = False

    if RAINFALL_SOURCE in ("auto", "gpm_final", "gpm"):
        success = download_gpm_final(YEAR, MONTH)

    if not success and RAINFALL_SOURCE in ("auto", "gpm_late", "gpm"):
        success = download_gpm_late(YEAR, MONTH)

    if not success and RAINFALL_SOURCE in ("auto", "era5"):
        success = download_era5(YEAR, MONTH)

    if not success and RAINFALL_SOURCE in ("auto", "chirps"):
        success = download_chirps(YEAR, MONTH)

    if not success:
        log.error("All rainfall sources failed.")
        log.error("1. Register at https://urs.earthdata.nasa.gov — set EARTHDATA_USER/PASS in .env")
        log.error("2. Run: pip install h5py")
        log.error("3. Or place accra_rainfall.tif manually in %s/", DATA_DIR)
        raise SystemExit(1)

    validate(OUTPUT_PATH)
    log.info("Rainfall ingest complete ✓")


if __name__ == "__main__":
    main()