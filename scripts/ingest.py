"""
ingest.py — Pipeline Orchestrator
===================================
Runs all data ingest scripts in the correct order.
Each script can also be run independently for testing or debugging.

Execution order:
1. ingest_dem.py        — SRTM 30m elevation (must run first)
2. ingest_slope.py      — derived from DEM (requires DEM)
3. ingest_rainfall.py   — ERA5 or GPM monthly precipitation
4. ingest_landcover.py  — ESA WorldCover (requires DEM for resampling)
5. ingest_waterbodies.py — OSM water features (requires DEM for grid)

After all scripts complete, the data/ folder will contain:
- accra_dem.tif           ← elevation
- accra_slope.tif         ← terrain slope in degrees
- accra_rainfall.tif      ← monthly precipitation in mm
- accra_landcover.tif     ← imperviousness fraction (0-1)
- accra_waterbodies.tif   ← distance to nearest water body in metres

Usage:
    # Run full ingest:
    python scripts/ingest.py

    # Run with custom year/month for rainfall:
    RAINFALL_YEAR=2024 RAINFALL_MONTH=9 python scripts/ingest.py

    # Force re-download of everything (delete existing files first):
    python scripts/ingest.py --force

    # Run only specific scripts:
    python scripts/ingest_dem.py
    python scripts/ingest_slope.py
"""

import os
import sys
import logging
import argparse
import importlib
import time

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

# ── Script definitions ────────────────────────────────────────────────────────
# Order matters — DEM must come before slope, landcover, and waterbodies
SCRIPTS = [
    {
        "name":        "ingest_dem",
        "description": "SRTM 30m Digital Elevation Model",
        "output":      "accra_dem.tif",
        "required":    True,   # Pipeline cannot continue without this
    },
    {
        "name":        "ingest_slope",
        "description": "Terrain slope (derived from DEM)",
        "output":      "accra_slope.tif",
        "required":    True,
    },
    {
        "name":        "ingest_rainfall",
        "description": "Monthly precipitation (ERA5 / GPM)",
        "output":      "accra_rainfall.tif",
        "required":    True,
    },
    {
        "name":        "ingest_landcover",
        "description": "ESA WorldCover land cover",
        "output":      "accra_landcover.tif",
        "required":    True,  # Now required for enhanced flood risk model
    },
    {
        "name":        "ingest_waterbodies",
        "description": "OpenStreetMap water bodies",
        "output":      "accra_waterbodies.tif",
        "required":    True,  # Now required for enhanced flood risk model
    },
]

DATA_DIR = os.getenv("DATA_DIR", "data")


def run_script(script_name: str) -> bool:
    """
    Dynamically import and run a script's main() function.
    Returns True on success, False on failure.
    """
    # Add scripts directory to path
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    try:
        module = importlib.import_module(script_name)
        # Reload in case it was already imported (useful during testing)
        importlib.reload(module)
        module.main()
        return True
    except SystemExit as e:
        # Script called sys.exit(1) — treat as failure
        if e.code != 0:
            log.error("Script %s exited with code %s", script_name, e.code)
            return False
        return True
    except Exception as e:
        log.error("Script %s raised an exception: %s", script_name, e)
        return False


def force_delete_outputs() -> None:
    """Delete all existing output files to force re-download."""
    log.info("Force mode: deleting existing data files...")
    for script in SCRIPTS:
        path = os.path.join(DATA_DIR, script["output"])
        if os.path.exists(path):
            os.remove(path)
            log.info("  Deleted: %s", path)


def check_existing(script: dict) -> bool:
    """Check if a script's output already exists."""
    path = os.path.join(DATA_DIR, script["output"])
    return os.path.exists(path)


def print_summary(results: dict) -> None:
    """Print a summary table of all script results."""
    log.info("")
    log.info("═" * 60)
    log.info("  INGEST SUMMARY")
    log.info("═" * 60)

    all_required_ok = True
    for script in SCRIPTS:
        name   = script["name"]
        output = script["output"]
        req    = "required" if script["required"] else "optional"

        status = results.get(name)
        path   = os.path.join(DATA_DIR, output)
        exists = os.path.exists(path)

        if status == "skipped":
            icon = "⏭"
            msg  = "skipped (already exists)"
        elif status == "success":
            size_mb = os.path.getsize(path) / 1024 / 1024 if exists else 0
            icon = "✓"
            msg  = f"OK ({size_mb:.1f} MB)"
        elif status == "failed":
            icon = "✗"
            msg  = "FAILED"
            if script["required"]:
                all_required_ok = False
        else:
            icon = "?"
            msg  = "unknown"

        log.info("  %s  %-25s [%s]  %s", icon, output, req, msg)

    log.info("═" * 60)

    if all_required_ok:
        log.info("  All required data ready — run flood_risk.py next")
    else:
        log.info("  Some required data is missing — check errors above")

    log.info("")


def main():
    parser = argparse.ArgumentParser(
        description="GeoBuilders Africa — Data Ingest Pipeline"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Delete existing files and re-download everything"
    )
    parser.add_argument(
        "--skip-optional", action="store_true",
        help="Skip optional scripts (none currently - all required for flood risk model)"
    )
    args = parser.parse_args()

    log.info("═" * 60)
    log.info("  GeoBuilders Africa — Data Ingest Pipeline")
    log.info("  Year: %s  Month: %s",
             os.getenv("RAINFALL_YEAR", "2024"),
             os.getenv("RAINFALL_MONTH", "6"))
    log.info("═" * 60)
    log.info("")

    os.makedirs(DATA_DIR, exist_ok=True)

    # Force re-download if requested
    if args.force:
        force_delete_outputs()

    results = {}
    start_time = time.time()

    for script in SCRIPTS:
        name = script["name"]

        # Skip optional scripts if flag is set
        if args.skip_optional and not script["required"]:
            log.info("Skipping optional: %s", name)
            results[name] = "skipped"
            continue

        # Skip if output already exists (and not in force mode)
        if check_existing(script):
            log.info("Already exists: %s — skipping", script["output"])
            results[name] = "skipped"
            continue

        log.info("")
        log.info("─── Running: %s (%s) ───", name, script["description"])

        t0 = time.time()
        success = run_script(name)
        elapsed = time.time() - t0

        if success:
            log.info("Completed in %.1fs: %s", elapsed, name)
            results[name] = "success"
        else:
            log.error("Failed: %s", name)
            results[name] = "failed"

            # Stop pipeline if a required script fails
            if script["required"]:
                log.error("Required script failed — stopping pipeline")
                break

    total_elapsed = time.time() - start_time
    log.info("")
    log.info("Total ingest time: %.1fs", total_elapsed)

    print_summary(results)

    # Exit with error code if any required script failed
    failed_required = [
        s["name"] for s in SCRIPTS
        if s["required"] and results.get(s["name"]) == "failed"
    ]
    if failed_required:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
