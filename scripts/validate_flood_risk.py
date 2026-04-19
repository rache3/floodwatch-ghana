"""
validate_flood_risk.py — Qualitative Validation Against May 2025 Accra Floods
==============================================================================
Validates FloodWatch Ghana risk scores against documented flood locations
from the May 18, 2025 Greater Accra flood event.

Event summary:
--------------
Heavy rainfall of 132.20mm hit Greater Accra on May 18, 2025.
4 people died, 3,000+ displaced.
Source: The Watchers, GDACS/Copernicus EMS

Documented flooded areas:
--------------------------
- Weija
- Kaneshie
- Adabraka
- Adentan / Adentan-Dodowa
- Oyarifa
- Tema
- Abokobi
- Adenta

Validation method:
------------------
1. Load FloodWatch risk raster
2. Load Greater Accra district boundaries (GADM)
3. Extract mean risk score per district using zonal statistics
4. Flag districts that were documented as flooded
5. Compare risk scores of flooded vs non-flooded districts
6. Report validation metrics

Usage:
    python scripts/validate_flood_risk.py
"""

import os
import json
import logging
import numpy as np

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

# ── Paths ─────────────────────────────────────────────────────────────────────
RISK_RASTER   = os.getenv("RISK_RASTER",   "output/flood_risk_map.cog.tif")
DISTRICTS_JSON = os.getenv("DISTRICTS_JSON", "data/gadm41_GHA_accra.json")
OUTPUT_DIR    = os.getenv("OUTPUT_DIR",    "output")

# ── May 2025 Flood Event Documentation ───────────────────────────────────────
# Districts/areas documented as flooded during May 18 2025 event
# Source: The Watchers, GDACS, local media reports
FLOODED_AREAS = [
    "weija",                 # Matches WeijaGbawe
    "accra",                 # Matches Accra Metropolis (Kaneshie, Adabraka)
    "gaeast",                # Matches Ga East (Abokobi)
    "la-nkwantanang-madina", # Matches La-Nkwantanang-Madina (Oyarifa)
    "adenta",                # Matches Adenta
    "tema",                  # Matches Tema and TemaWest
    "kaneshie",              # Substring backup
    "adabraka",              # Substring backup
]

# ── Zonal Statistics ──────────────────────────────────────────────────────────

def extract_district_stats(risk_path: str, districts_path: str) -> list:
    """
    Extract flood risk statistics for each district using zonal statistics.
    Returns a list of dicts with district name and risk metrics.
    """
    import rasterio
    from rasterio.mask import mask as rio_mask

    log.info("Loading risk raster: %s", risk_path)
    log.info("Loading districts: %s", districts_path)

    with open(districts_path) as f:
        districts = json.load(f)

    features = districts.get("features", [])
    log.info("Found %d districts", len(features))

    results = []

    with rasterio.open(risk_path) as src:
        log.info("Risk raster CRS   : %s", src.crs)
        log.info("Risk raster shape : %s x %s", src.height, src.width)
        log.info("Risk raster bounds: %s", src.bounds)

        for feature in features:
            props    = feature.get("properties", {})
            geometry = feature.get("geometry", {})

            # Get district name from GADM properties
            name = (
                props.get("NAME_2") or
                props.get("NAME_1") or
                props.get("name")   or
                props.get("NAME")   or
                "Unknown"
            )

            try:
                # Mask raster to district boundary
                masked, _ = rio_mask(
                    src,
                    [geometry],
                    crop=True,
                    nodata=np.nan,
                    filled=True,
                )

                data = masked[0].astype(float)
                data[data == src.nodata] = np.nan
                data[data < 0] = np.nan

                valid = data[~np.isnan(data)]

                if len(valid) == 0:
                    log.warning("No valid pixels for district: %s", name)
                    continue

                mean_risk = float(np.mean(valid))
                max_risk  = float(np.max(valid))
                high_risk_pct = float(np.sum(valid > 0.67) / len(valid) * 100)

                # Check if this district matches a flooded area
                name_lower = name.lower()
                flooded = any(area in name_lower for area in FLOODED_AREAS)

                results.append({
                    "district":      name,
                    "mean_risk":     round(mean_risk, 4),
                    "max_risk":      round(max_risk, 4),
                    "high_risk_pct": round(high_risk_pct, 1),
                    "pixel_count":   len(valid),
                    "flooded_may2025": flooded,
                })

            except Exception as e:
                log.warning("Could not process district %s: %s", name, e)
                continue

    return results


# ── Validation Analysis ───────────────────────────────────────────────────────

def analyse_results(results: list) -> dict:
    """
    Compare risk scores of flooded vs non-flooded districts.
    Returns validation metrics.
    """
    flooded     = [r for r in results if r["flooded_may2025"]]
    not_flooded = [r for r in results if not r["flooded_may2025"]]

    if not flooded or not not_flooded:
        log.warning("Could not split districts into flooded/not flooded")
        return {}

    flooded_mean     = np.mean([r["mean_risk"] for r in flooded])
    not_flooded_mean = np.mean([r["mean_risk"] for r in not_flooded])

    flooded_high_pct     = np.mean([r["high_risk_pct"] for r in flooded])
    not_flooded_high_pct = np.mean([r["high_risk_pct"] for r in not_flooded])

    # Rank all districts by mean risk
    ranked = sorted(results, key=lambda x: x["mean_risk"], reverse=True)
    total  = len(ranked)

    # Check what percentile flooded districts sit at
    for r in ranked:
        r["rank"] = ranked.index(r) + 1
        r["percentile"] = round((1 - r["rank"] / total) * 100, 1)

    return {
        "total_districts":         total,
        "flooded_districts":       len(flooded),
        "not_flooded_districts":   len(not_flooded),
        "flooded_mean_risk":       round(float(flooded_mean), 4),
        "not_flooded_mean_risk":   round(float(not_flooded_mean), 4),
        "risk_difference":         round(float(flooded_mean - not_flooded_mean), 4),
        "flooded_high_risk_pct":   round(float(flooded_high_pct), 1),
        "not_flooded_high_risk_pct": round(float(not_flooded_high_pct), 1),
        "ranked_districts":        ranked,
    }


# ── Reporting ─────────────────────────────────────────────────────────────────

def print_report(metrics: dict) -> None:
    """Print a human readable validation report."""

    ranked = metrics.get("ranked_districts", [])

    log.info("")
    log.info("═" * 65)
    log.info("  FLOODWATCH GHANA — VALIDATION REPORT")
    log.info("  Event: Greater Accra Floods — May 18, 2025")
    log.info("═" * 65)
    log.info("")
    log.info("  SUMMARY")
    log.info("  -------")
    log.info("  Total districts analysed : %d", metrics["total_districts"])
    log.info("  Documented flooded areas : %d", metrics["flooded_districts"])
    log.info("")
    log.info("  RISK SCORE COMPARISON")
    log.info("  ---------------------")
    log.info("  Flooded districts mean risk     : %.4f",
             metrics["flooded_mean_risk"])
    log.info("  Non-flooded districts mean risk : %.4f",
             metrics["not_flooded_mean_risk"])
    log.info("  Difference                      : %.4f  %s",
             metrics["risk_difference"],
             "✓ Flooded areas scored HIGHER" if metrics["risk_difference"] > 0
             else "✗ Flooded areas scored LOWER — model needs review")
    log.info("")
    log.info("  HIGH RISK PIXEL PERCENTAGE (score > 0.67)")
    log.info("  ------------------------------------------")
    log.info("  Flooded districts     : %.1f%%",
             metrics["flooded_high_risk_pct"])
    log.info("  Non-flooded districts : %.1f%%",
             metrics["not_flooded_high_risk_pct"])
    log.info("")
    log.info("  DISTRICT RANKINGS (highest risk first)")
    log.info("  ----------------------------------------")
    log.info("  %-4s  %-30s  %-10s  %-10s  %-8s  %s",
             "Rank", "District", "Mean Risk", "Max Risk", "High%", "Flooded?")
    log.info("  %s", "-" * 75)

    for r in ranked:
        flooded_marker = "🔴 YES" if r["flooded_may2025"] else "   no"
        log.info("  %-4d  %-30s  %-10.4f  %-10.4f  %-8.1f  %s",
                 r["rank"],
                 r["district"][:30],
                 r["mean_risk"],
                 r["max_risk"],
                 r["high_risk_pct"],
                 flooded_marker)

    log.info("")
    log.info("  FLOODED DISTRICT RANKINGS")
    log.info("  --------------------------")
    flooded = [r for r in ranked if r["flooded_may2025"]]
    total   = metrics["total_districts"]
    for r in flooded:
        log.info("  %s — Rank %d of %d (top %.0f%%)",
                 r["district"], r["rank"], total, r["percentile"])

    log.info("")

    # Overall assessment
    diff = metrics["risk_difference"]
    if diff > 0.05:
        assessment = "STRONG — Flooded areas consistently scored higher risk"
        symbol     = "✓✓"
    elif diff > 0:
        assessment = "MODERATE — Flooded areas scored slightly higher risk"
        symbol     = "✓"
    else:
        assessment = "WEAK — Model did not correctly rank flooded areas higher"
        symbol     = "✗"

    log.info("  OVERALL ASSESSMENT: %s %s", symbol, assessment)
    log.info("═" * 65)
    log.info("")


def save_results(results: list, metrics: dict) -> None:
    """Save validation results as JSON."""
    output = {
        "event":       "Greater Accra Floods — May 18 2025",
        "sources":     ["The Watchers", "GDACS", "Copernicus EMS"],
        "methodology": "Zonal statistics — mean risk score per district",
        "metrics":     {k: v for k, v in metrics.items()
                        if k != "ranked_districts"},
        "districts":   metrics.get("ranked_districts", []),
    }

    path = os.path.join(OUTPUT_DIR, "validation_may2025.json")
    with open(path, "w") as f:
        json.dump(output, f, indent=2)

    log.info("Validation results saved → %s", path)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=== FloodWatch Validation — May 2025 Accra Floods ===")

    # Check files exist
    for path in [RISK_RASTER, DISTRICTS_JSON]:
        if not os.path.exists(path):
            log.error("File not found: %s", path)
            raise SystemExit(1)

    # Check dependencies
    try:
        import shapely  # noqa: F401
    except ImportError:
        log.error("shapely not installed — run: pip install shapely")
        raise SystemExit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Extract zonal statistics
    log.info("Extracting risk scores per district...")
    results = extract_district_stats(RISK_RASTER, DISTRICTS_JSON)

    if not results:
        log.error("No results extracted — check raster and district files")
        raise SystemExit(1)

    log.info("Extracted stats for %d districts", len(results))

    # Analyse
    metrics = analyse_results(results)

    # Report
    print_report(metrics)

    # Save
    save_results(results, metrics)

    log.info("Validation complete ✓")


if __name__ == "__main__":
    main()
