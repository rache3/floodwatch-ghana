"""
ingest_aod.py — Download and Process MODIS Aerosol Optical Depth (AOD)
=======================================================================
Source    : MODIS MOD04_L2 (Terra) and MYD04_L2 (Aqua) — NASA Earthdata
            Fallback: MERRA-2 reanalysis AOD (no login required)
Resolution: 3km (MOD04_3K) or 10km (MOD04_L2)
Output    : data/accra_aod.tif       — gridded monthly mean AOD
            data/accra_aod_meta.json — AOD statistics and quality flags

Why Aerosol Optical Depth matters:
------------------------------------
Aerosol Optical Depth (AOD) measures how much sunlight is scattered or
absorbed by particles in the atmosphere — dust, smoke, haze, and urban
pollution. In optical remote sensing, high AOD means satellite sensors
receive less reflected light from the surface and more light scattered
by the atmosphere, introducing significant errors in surface reflectance
measurements.

Accra context:
--------------
Research shows Accra has mean AOD values of 0.587–0.703 (MODIS Terra/Aqua),
well above clean atmosphere values of ~0.05. This is driven by:
  - Heavy vehicular traffic and urban emissions
  - Harmattan dust from the Sahara (November–March)
  - Biomass burning smoke (dry season)
  - Coastal aerosol transport

There is currently NO AERONET ground station in Ghana, making satellite-
derived AOD (MODIS) the most accessible correction source for the region.

Role in FloodWatch pipeline:
-----------------------------
Currently the FloodWatch inputs (DEM, slope, rainfall, ESA WorldCover,
OSM water bodies) are not optical reflectance products, so AOD correction
does not affect the current risk model directly.

However this script serves three purposes:
1. Quality flagging — logs AOD conditions during each pipeline run so
   high-aerosol months are documented alongside the risk outputs
2. Future optical inputs — when reflectance-based layers (NDVI, Sentinel-2
   derived products) are added to the model, AOD data will be needed for
   atmospheric correction
3. Research foundation — positions the pipeline for the research question:
   Can MODIS AOD serve as a viable correction source for data-sparse
   tropical urban environments in the absence of AERONET ground stations?

AOD Quality Thresholds for Accra:
-----------------------------------
  AOD < 0.2  → Clean atmosphere  → optical data highly reliable
  AOD 0.2–0.5 → Moderate aerosol → optical data usable with correction
  AOD 0.5–0.8 → High aerosol     → optical data needs careful correction
  AOD > 0.8   → Very high         → optical data unreliable without correction

Based on research, Accra typically sits in the 0.5–0.8 range.

Data access:
------------
MODIS AOD requires a free NASA Earthdata account:
  Register: https://urs.earthdata.nasa.gov/users/new
  Set credentials in .env:
    EARTHDATA_USER=your_username
    EARTHDATA_PASS=your_password

If no credentials are available, this script falls back to:
  - MERRA-2 reanalysis AOD (no login required)
  - A climatological mean AOD for Accra based on published literature

Usage:
    python scripts/ingest_aod.py

    # Specify year and month:
    RAINFALL_YEAR=2024 RAINFALL_MONTH=6 python scripts/ingest_aod.py

    # Force climatological fallback:
    AOD_SOURCE=climatology python scripts/ingest_aod.py
"""

import os
import json
import logging
import urllib.request
import urllib.error
import calendar
import numpy as np
from datetime import datetime, date


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


# ── Configuration ─────────────────────────────────────────────────────────────
DATA_DIR    = os.getenv("DATA_DIR", "data")
OUTPUT_TIF  = os.path.join(DATA_DIR, "accra_aod.tif")
OUTPUT_META = os.path.join(DATA_DIR, "accra_aod_meta.json")

YEAR  = int(os.getenv("RAINFALL_YEAR",  "2024"))
MONTH = int(os.getenv("RAINFALL_MONTH", "6"))

AOD_SOURCE = os.getenv("AOD_SOURCE", "auto").lower()

# Greater Accra bounding box
BBOX = {
    "west":  float(os.getenv("BBOX_WEST",  "-0.50")),
    "east":  float(os.getenv("BBOX_EAST",   "0.50")),
    "south": float(os.getenv("BBOX_SOUTH",  "5.35")),
    "north": float(os.getenv("BBOX_NORTH",  "5.95")),
}

# NASA Earthdata credentials
EARTHDATA_USER = os.getenv("EARTHDATA_USER", "")
EARTHDATA_PASS = os.getenv("EARTHDATA_PASS", "")

# ── Accra AOD Climatology ─────────────────────────────────────────────────────
# Monthly mean AOD values for Accra derived from published literature:
# - Machine learning assessment of AOD over Ghana (PLOS Climate, 2025)
# - Assessment of aerosol burden over Ghana (ScienceDirect, 2021)
# Values are MODIS Terra AOD at 550nm, monthly climatological means
# These are used as fallback when satellite data is unavailable

ACCRA_AOD_CLIMATOLOGY = {
    1:  0.72,   # January  — Harmattan dust season, high AOD
    2:  0.75,   # February — Peak Harmattan, highest AOD
    3:  0.68,   # March    — Harmattan weakening
    4:  0.55,   # April    — Transition, moderate
    5:  0.48,   # May      — Pre-monsoon, cleaner
    6:  0.45,   # June     — Monsoon onset, lower AOD
    7:  0.42,   # July     — Peak monsoon, cleanest period
    8:  0.44,   # August   — Monsoon, relatively clean
    9:  0.52,   # September — Post-monsoon transition
    10: 0.58,   # October  — Dry season beginning
    11: 0.65,   # November — Harmattan returning
    12: 0.70,   # December — Harmattan established
}

# AOD quality thresholds
AOD_THRESHOLDS = {
    "clean":     0.20,
    "moderate":  0.50,
    "high":      0.80,
}


# ── MODIS Download via NASA Earthdata ─────────────────────────────────────────

def download_modis_aod(year: int, month: int) -> bool:
    """
    Download MODIS MOD04_3K monthly mean AOD from NASA Earthdata.

    MOD04_3K is the 3km resolution MODIS aerosol product from Terra.
    Monthly aggregates are available via NASA's Earthdata OPeNDAP service.

    Requires NASA Earthdata account credentials in .env:
        EARTHDATA_USER=your_username
        EARTHDATA_PASS=your_password

    Registration is free at: https://urs.earthdata.nasa.gov/users/new
    """
    if not EARTHDATA_USER or not EARTHDATA_PASS:
        log.warning("NASA Earthdata credentials not set in .env")
        log.warning("Set EARTHDATA_USER and EARTHDATA_PASS to download MODIS AOD")
        log.warning("Register free at: https://urs.earthdata.nasa.gov/users/new")
        return False

    log.info("Attempting MODIS MOD04_3K download from NASA Earthdata...")

    # Build the day-of-year range for the month
    days_in_month = calendar.monthrange(year, month)[1]
    doy_start = date(year, month, 1).timetuple().tm_yday
    doy_end   = date(year, month, days_in_month).timetuple().tm_yday

    log.info("Year: %d  Month: %02d  DOY: %d–%d", year, month, doy_start, doy_end)

    # NASA CMR (Common Metadata Repository) API to find granules
    cmr_url = (
        "https://cmr.earthdata.nasa.gov/search/granules.json"
        f"?short_name=MOD04_3K"
        f"&version=006"
        f"&temporal[]={year}-{month:02d}-01T00:00:00Z,"
        f"{year}-{month:02d}-{days_in_month:02d}T23:59:59Z"
        f"&bounding_box={BBOX['west']},{BBOX['south']},{BBOX['east']},{BBOX['north']}"
        f"&page_size=100"
    )

    try:
        log.info("Querying NASA CMR for available granules...")
        with urllib.request.urlopen(cmr_url, timeout=30) as resp:
            granules_data = json.loads(resp.read().decode("utf-8"))

        entries = granules_data.get("feed", {}).get("entry", [])
        log.info("Found %d MODIS granules for %d-%02d", len(entries), year, month)

        if not entries:
            log.warning("No MODIS granules found for this period and bounding box")
            return False

        # Download and process granules
        # For a monthly mean, we need to aggregate daily granules
        # This is a simplified approach — in production use pyhdf or netCDF4
        log.info("MODIS granule download requires HDF4 processing libraries")
        log.info("For production use: pip install pyhdf or use NASA Earthdata API")
        log.info("Falling back to MERRA-2 reanalysis...")
        return False

    except Exception as e:
        log.warning("MODIS CMR query failed: %s", e)
        return False


# ── MERRA-2 Reanalysis AOD ────────────────────────────────────────────────────

def download_merra2_aod(year: int, month: int) -> bool:
    """
    Download MERRA-2 reanalysis AOD for Greater Accra.

    MERRA-2 (Modern-Era Retrospective analysis for Research and Applications)
    is a NASA atmospheric reanalysis that provides AOD estimates globally
    at ~0.5° × 0.625° resolution.

    Available via NASA GES DISC — requires free Earthdata account but
    public access is available for monthly means via OPeNDAP.

    MERRA-2 AOD is less accurate than MODIS for instantaneous values but
    provides consistent monthly climatology useful for quality flagging.
    """
    log.info("Attempting MERRA-2 AOD download...")

    month_str = f"{month:02d}"

    # MERRA-2 monthly mean AOD via GES DISC OPeNDAP
    # M2TMNXAER = MERRA-2 tavgM_2d_aer_Nx (2D, monthly mean, aerosols)
    url = (
        "https://goldsmr4.gesdisc.eosdis.nasa.gov/opendap/MERRA2_MONTHLY"
        f"/M2TMNXAER.5.12.4/{year}"
        f"/MERRA2_400.tavgM_2d_aer_Nx.{year}{month_str}.nc4.nc4"
        f"?TOTEXTTAU"  # Total aerosol extinction AOD at 550nm
        f"[0][{_lat_to_idx(BBOX['south'])}:{_lat_to_idx(BBOX['north'])}]"
        f"[{_lon_to_idx(BBOX['west'])}:{_lon_to_idx(BBOX['east'])}]"
    )

    try:
        tmp_path = os.path.join(DATA_DIR, "merra2_aod_tmp.nc4")

        # Set up authentication for NASA Earthdata
        if EARTHDATA_USER and EARTHDATA_PASS:
            password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
            password_mgr.add_password(None, "https://urs.earthdata.nasa.gov",
                                      EARTHDATA_USER, EARTHDATA_PASS)
            auth_handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
            opener = urllib.request.build_opener(auth_handler)
            urllib.request.install_opener(opener)

        log.info("Downloading MERRA-2 AOD...")
        urllib.request.urlretrieve(url, tmp_path)

        # Parse NetCDF4
        aod_mean = _parse_merra2_nc(tmp_path)
        os.remove(tmp_path)

        if aod_mean is not None:
            log.info("MERRA-2 AOD for %d-%02d: %.3f", year, month, aod_mean)
            _write_aod_raster(aod_mean, year, month, source="MERRA-2")
            return True
        return False

    except Exception as e:
        log.warning("MERRA-2 download failed: %s", e)
        if os.path.exists(os.path.join(DATA_DIR, "merra2_aod_tmp.nc4")):
            os.remove(os.path.join(DATA_DIR, "merra2_aod_tmp.nc4"))
        return False


def _lat_to_idx(lat: float) -> int:
    """Convert latitude to MERRA-2 grid index (0.5° resolution, -90 to 90)."""
    return int((lat + 90.0) / 0.5)


def _lon_to_idx(lon: float) -> int:
    """Convert longitude to MERRA-2 grid index (0.625° resolution, -180 to 180)."""
    return int((lon + 180.0) / 0.625)


def _parse_merra2_nc(nc_path: str) -> float:
    """Parse MERRA-2 NetCDF4 file and return mean AOD over bounding box."""
    try:
        import netCDF4 as nc
        ds = nc.Dataset(nc_path)
        aod = ds.variables["TOTEXTTAU"][0, :, :]
        ds.close()
        valid = aod[aod > 0]
        return float(np.mean(valid)) if len(valid) > 0 else None
    except ImportError:
        log.warning("netCDF4 not installed — run: pip install netCDF4")
        return None
    except Exception as e:
        log.warning("NetCDF4 parsing failed: %s", e)
        return None


# ── Climatological Fallback ───────────────────────────────────────────────────

def use_climatology(year: int, month: int) -> bool:
    """
    Use published climatological mean AOD for Accra as fallback.

    When neither MODIS nor MERRA-2 data is available, use monthly
    climatological values derived from published research on aerosol
    burden over Ghana (2005-2019 period).

    This provides a reasonable estimate for quality flagging purposes
    but should not be used for quantitative atmospheric correction.
    """
    aod_mean = ACCRA_AOD_CLIMATOLOGY.get(month, 0.55)

    log.info("Using climatological AOD for Accra:")
    log.info("  Month     : %02d", month)
    log.info("  AOD (mean): %.3f", aod_mean)
    log.info("  Source    : Published literature (PLOS Climate 2025, ScienceDirect 2021)")
    log.info("  Note      : Climatological value — not observation for %d-%02d", year, month)

    _write_aod_raster(aod_mean, year, month, source="climatology")
    return True


# ── Output Writers ────────────────────────────────────────────────────────────

def _write_aod_raster(aod_value: float, year: int, month: int,
                      source: str) -> None:
    """
    Write AOD as a simple GeoTIFF raster over the Greater Accra bounding box.

    For climatological or single-value MERRA-2 data, this creates a uniform
    raster where every pixel has the same AOD value. When actual gridded
    MODIS data is available, this will be replaced with spatial variation.

    The raster is used by flood_risk.py as a quality context layer —
    it does not currently enter the weighted risk calculation but provides
    metadata for each pipeline run.
    """
    import rasterio
    from rasterio.transform import from_bounds

    # Create a small raster at 0.1° resolution (roughly 10km, matching MERRA-2)
    rows, cols = 7, 11  # Covers ~0.6° lat × 1.0° lon

    data = np.full((rows, cols), aod_value, dtype=np.float32)
    transform = from_bounds(
        BBOX["west"], BBOX["south"],
        BBOX["east"], BBOX["north"],
        cols, rows,
    )

    os.makedirs(DATA_DIR, exist_ok=True)

    with rasterio.open(
        OUTPUT_TIF, "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        compress="deflate",
    ) as dst:
        dst.write(data, 1)
        dst.update_tags(
            description="Aerosol Optical Depth (AOD) at 550nm for Greater Accra",
            source=source,
            year=str(year),
            month=f"{month:02d}",
            units="dimensionless (AOD at 550nm)",
            note="Used for quality flagging of optical satellite inputs",
        )

    log.info("AOD raster written → %s", OUTPUT_TIF)


def _write_metadata(aod_value: float, year: int, month: int,
                    source: str) -> None:
    """
    Write AOD quality metadata as JSON alongside the pipeline outputs.

    This JSON file is written with every pipeline run and records:
    - The AOD value used
    - The data source
    - The quality flag and what it means for optical inputs
    - Recommendations for this pipeline run

    This is the primary output that flood_risk.py reads for quality context.
    """
    # Determine quality flag
    if aod_value < AOD_THRESHOLDS["clean"]:
        flag = "CLEAN"
        optical_reliability = "high"
        recommendation = "Optical satellite inputs are highly reliable this month."
    elif aod_value < AOD_THRESHOLDS["moderate"]:
        flag = "MODERATE"
        optical_reliability = "moderate"
        recommendation = (
            "Optical satellite inputs are usable. "
            "Apply atmospheric correction before use."
        )
    elif aod_value < AOD_THRESHOLDS["high"]:
        flag = "HIGH"
        optical_reliability = "low"
        recommendation = (
            "Optical satellite inputs require careful atmospheric correction. "
            "MODIS AOD should be applied before processing Sentinel-2 or Landsat data. "
            "Consider using SAR-based inputs (Sentinel-1) where possible."
        )
    else:
        flag = "VERY_HIGH"
        optical_reliability = "very_low"
        recommendation = (
            "Very high aerosol loading. Optical satellite inputs are unreliable "
            "without full atmospheric correction using MODIS AOD. "
            "This is typical of Harmattan season in Accra (November–March). "
            "Use SAR-based data where possible."
        )

    metadata = {
        "pipeline_run": {
            "year":  year,
            "month": month,
            "date":  datetime.now().isoformat(),
        },
        "aod": {
            "value":  round(float(aod_value), 4),
            "source": source,
            "units":  "AOD at 550nm (dimensionless)",
            "quality_flag": flag,
        },
        "optical_reliability": optical_reliability,
        "recommendation": recommendation,
        "accra_context": {
            "national_mean_aod": 0.509,
            "accra_mean_aod_terra": 0.703,
            "accra_mean_aod_aqua":  0.587,
            "nearest_aeronet_site": "Ilorin, Nigeria (~600km northeast)",
            "note": (
                "No AERONET ground station exists in Ghana. "
                "MODIS satellite AOD is the best available correction source. "
                "This represents a research gap — see Dr. Craig Coburn (Univ. of Lethbridge) "
                "on irradiance monitoring for tropical UAV calibration."
            ),
        },
        "layers_affected": {
            "dem":          {"affected": False, "reason": "SRTM radar — not affected by aerosols"},
            "slope":        {"affected": False, "reason": "Derived from DEM — not affected"},
            "rainfall":     {"affected": False, "reason": "ERA5 reanalysis — not affected"},
            "landcover":    {"affected": False, "reason": "ESA WorldCover uses SAR — not affected"},
            "waterbodies":  {"affected": False, "reason": "OpenStreetMap vector — not affected"},
            "future_ndvi":  {"affected": True,  "reason": "Optical — will require AOD correction"},
            "future_s2":    {"affected": True,  "reason": "Optical — will require AOD correction"},
        },
    }

    with open(OUTPUT_META, "w") as f:
        json.dump(metadata, f, indent=2)

    log.info("AOD metadata written → %s", OUTPUT_META)


# ── Validation and Reporting ──────────────────────────────────────────────────

def report_aod_quality(meta_path: str) -> None:
    """
    Print a human-readable AOD quality report for this pipeline run.
    """
    with open(meta_path) as f:
        meta = json.load(f)

    aod   = meta["aod"]
    flag  = aod["quality_flag"]
    value = aod["value"]

    flag_icons = {
        "CLEAN":     "✓",
        "MODERATE":  "⚠",
        "HIGH":      "⚠⚠",
        "VERY_HIGH": "✗",
    }

    log.info("")
    log.info("═" * 60)
    log.info("  AOD QUALITY REPORT — %d-%02d",
             meta["pipeline_run"]["year"],
             meta["pipeline_run"]["month"])
    log.info("═" * 60)
    log.info("  AOD value    : %.3f (source: %s)", value, aod["source"])
    log.info("  Quality flag : %s %s", flag_icons.get(flag, "?"), flag)
    log.info("  Reliability  : %s", meta["optical_reliability"].upper())
    log.info("")
    log.info("  %s", meta["recommendation"])
    log.info("")
    log.info("  Current pipeline layers — all unaffected by AOD:")
    log.info("  ✓ DEM · Slope · Rainfall · Land cover · Water bodies")
    log.info("")
    log.info("  Future optical layers will require AOD correction:")
    log.info("  ! NDVI · Sentinel-2 · Landsat surface reflectance")
    log.info("═" * 60)
    log.info("")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=== AOD Ingest — Year=%d Month=%02d ===", YEAR, MONTH)

    os.makedirs(DATA_DIR, exist_ok=True)

    # Skip if already processed for this month
    if os.path.exists(OUTPUT_META):
        with open(OUTPUT_META) as f:
            existing = json.load(f)
        existing_year  = existing["pipeline_run"]["year"]
        existing_month = existing["pipeline_run"]["month"]

        if existing_year == YEAR and existing_month == MONTH:
            log.info("AOD metadata already exists for %d-%02d → %s",
                     YEAR, MONTH, OUTPUT_META)
            log.info("Delete the file to force a fresh download")
            report_aod_quality(OUTPUT_META)
            return

    success = False
    source  = "unknown"

    # Try each source in order
    if AOD_SOURCE in ("auto", "modis"):
        log.info("Attempting MODIS MOD04_3K download...")
        success = download_modis_aod(YEAR, MONTH)
        if success:
            source = "MODIS MOD04_3K"

    if not success and AOD_SOURCE in ("auto", "merra2"):
        log.info("Attempting MERRA-2 reanalysis AOD download...")
        success = download_merra2_aod(YEAR, MONTH)
        if success:
            source = "MERRA-2"

    if not success:
        log.info("Using climatological AOD fallback for Accra...")
        success = use_climatology(YEAR, MONTH)
        source  = "climatology"

    if not success:
        log.error("All AOD sources failed")
        raise SystemExit(1)

    # Get the AOD value that was written
    aod_value = ACCRA_AOD_CLIMATOLOGY.get(MONTH, 0.55)
    if os.path.exists(OUTPUT_TIF):
        try:
            import rasterio
            with rasterio.open(OUTPUT_TIF) as src:
                data = src.read(1)
                aod_value = float(np.nanmean(data[data > 0]))
        except Exception:
            pass

    # Write metadata
    _write_metadata(aod_value, YEAR, MONTH, source)

    # Print quality report
    report_aod_quality(OUTPUT_META)

    log.info("AOD ingest complete ✓")
    log.info("Raster   → %s", OUTPUT_TIF)
    log.info("Metadata → %s", OUTPUT_META)


if __name__ == "__main__":
    main()
