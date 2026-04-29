# FloodWatch Ghana: Risk Methodology & Model Validation (v0.1)

*Greater Accra Region, Ghana · Updated April 2026*

This document provides a comprehensive overview of the FloodWatch Ghana risk model, the district risk leaderboard, engineering history, and a full quantitative and qualitative validation of both model versions against the May 18, 2025 Greater Accra flood event.

---

## 1. The Risk Model (v0.1)

FloodWatch Ghana v0.1 is a **structural baseline** model. It identifies areas chronically prone to flooding based on their physical and environmental characteristics — terrain, drainage, land cover, and rainfall patterns.

### 1.1 Weighted Composite Formula

Each 30m pixel is assigned a risk score from 0 (Low) to 1 (High) using a weighted combination of five input layers:

| Component | Weight | Direction | Source | Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **Elevation** | 30% | Inverted | NASA SRTM (30m) | Low-lying areas are natural catchments for surface runoff. |
| **Precipitation** | 25% | Normal | GPM IMERG Final Run (0.1°) | Actual observed monthly rainfall drives runoff volume. |
| **Terrain Slope** | 20% | Inverted | Derived from SRTM | Flat terrain cannot drain quickly and pools surface water. |
| **Imperviousness** | 15% | Normal | ESA WorldCover (10m) | Paved and urban surfaces prevent infiltration into soil. |
| **Water Proximity** | 10% | Inverted | OpenStreetMap | Proximity to rivers and drainage channels increases inundation risk. |

**Formula:**
```
Risk = 0.30×(1−DEM_norm) + 0.25×Rain_norm + 0.20×(1−Slope_norm) + 0.15×Imperv_norm + 0.10×(1−Water_norm)
```

All input layers are min-max normalised to [0, 1] before compositing. The final composite is reclassified using **percentile-based stretching** (p25 and p75 breakpoints) to distribute risk scores across the full [0, 1] range and avoid compression in the middle.

### 1.2 Rainfall Data Source — Why GPM IMERG over ERA5/CHIRPS

The rainfall layer is the most operationally significant input to update. Two approaches have been used across model versions:

| Source | Type | Latency | Accuracy | Used in |
| :--- | :--- | :--- | :--- | :--- |
| CHIRPS v2.0 | Climatological mean | Days | Moderate | v0.1 original |
| ERA5-Land | Reanalysis mean | Days | Good | v0.1 original fallback |
| GPM IMERG Final Run | Actual monthly observed | ~3.5 months | Best (gauge-corrected) | v0.1 recalculated |
| GPM IMERG Late Run | Near real-time | ~12 hours | Good | v0.1 recalculated fallback |

CHIRPS and ERA5 return the same climatological average for June regardless of the year — June 2019 and June 2024 produce identical values. GPM IMERG returns the **actual measured precipitation** for that specific month, making the model genuinely responsive to real rainfall conditions. The v0.1 recalculated model uses GPM IMERG Final Run for June 2024 (198 mm/month mean over Greater Accra).

---

## 2. District Risk Leaderboard

### 2.1 Original Model (CHIRPS/ERA5 rainfall, no percentile reclassification)

Mean risk scores computed per district from the original pipeline run.

| Rank | District | Mean Risk | Max Risk | Flooded May 2025 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | Ablekuma West | 0.8398 | 0.9928 | No |
| 2 | Weija Gbawe | 0.8123 | 0.9957 | **Yes** |
| 3 | Ga Central | 0.7258 | 0.9796 | No |
| 4 | Accra Metropolis | 0.7170 | 0.8681 | **Yes** |
| 5 | Ga West | 0.7063 | 0.9091 | No |
| 6 | Ga South | 0.7035 | 0.9168 | No |
| 7 | Ablekuma North | 0.6922 | 0.9129 | No |
| 8 | Ablekuma Central | 0.6876 | 0.9673 | No |
| 9 | Ayawaso East | 0.6741 | 0.8010 | No |
| 10 | Korle-Klottey | 0.6708 | 0.8220 | No |
| 11 | La-Dade-Kotopon | 0.6665 | 0.8261 | No |
| 12 | Ayawaso North | 0.6428 | 0.7923 | No |
| 13 | Okaikwei North | 0.6216 | 0.7901 | No |
| 14 | Ayawaso Central | 0.6024 | 0.7815 | No |
| 15 | Krowor | 0.5994 | 0.7714 | No |
| 16 | Ledzokuku | 0.5633 | 0.7841 | No |
| 17 | Ayawaso West | 0.5555 | 0.7763 | No |
| 18 | Ga East | 0.5529 | 0.8011 | **Yes** |
| 19 | Ga North | 0.5399 | 0.8156 | No |
| 20 | Tema | 0.5215 | 0.7691 | **Yes** |
| 21 | Tema West | 0.4887 | 0.7598 | **Yes** |
| 22 | Ningo-Prampram | 0.4646 | 1.0000 | No |
| 23 | Ada East | 0.4635 | 0.8083 | No |
| 24 | La-Nkwantanang-Madina | 0.4619 | 0.7043 | **Yes** |
| 25 | Adenta | 0.4610 | 0.7331 | **Yes** |
| 26 | Kpone-Katamanso | 0.4507 | 0.7605 | No |
| 27 | Ada West | 0.4376 | 0.7787 | No |
| 28 | Shai Osudoku | 0.4223 | 0.9061 | No |
| 29 | Ashaiman | 0.3654 | 0.6527 | No |

### 2.2 Recalculated Model (GPM IMERG rainfall + percentile reclassification, April 2026)

| Rank | District | Mean Risk | Max Risk | Flooded May 2025 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | Ayawaso North | 0.9301 | — | No |
| 2 | Ledzokuku | 0.9204 | — | No |
| 3 | Krowor | 0.9181 | — | No |
| 4 | Tema West | 0.8956 | — | **Yes** |
| 5 | Ashaiman | 0.8941 | — | No |
| 6 | La-Dade-Kotopon | 0.8910 | — | No |
| 7 | Ga Central | 0.8814 | — | No |
| 8 | Ablekuma North | 0.8734 | — | No |
| 9 | Ayawaso West | 0.8686 | — | No |
| 10 | Ayawaso East | 0.8682 | — | No |
| 11 | Okaikwei North | 0.8570 | — | No |
| 12 | Ayawaso Central | 0.8525 | — | No |
| 13 | Korle-Klottey | 0.8525 | — | No |
| 14 | Adenta | 0.8408 | — | **Yes** |
| 15 | Tema | 0.8357 | — | **Yes** |
| 16 | Ga West | 0.8160 | — | No |
| 17 | Ablekuma Central | 0.8157 | — | No |
| 18 | Ga East | 0.8114 | — | **Yes** |
| 19 | Accra Metropolis | 0.7847 | — | **Yes** |
| 20 | Weija Gbawe | 0.7570 | — | **Yes** |
| 21 | La-Nkwantanang-Madina | 0.7531 | — | **Yes** |
| 22 | Ga South | 0.7523 | — | No |
| 23 | Ga North | 0.7507 | — | No |
| 24 | Kpone-Katamanso | 0.7430 | — | No |
| 25 | Ablekuma West | 0.7418 | — | No |
| 26 | Ningo-Prampram | 0.4870 | — | No |
| 27 | Ada East | 0.4747 | — | No |
| 28 | Shai Osudoku | 0.4541 | — | No |
| 29 | Ada West | 0.3971 | — | No |

---

## 3. Validation — May 18, 2025 Flood Event

### 3.1 Event Summary

On **May 18, 2025**, Greater Accra experienced a severe flash flooding event following approximately **132mm of rainfall** in a short period — roughly the equivalent of a full month's rain in a single day. The event caused widespread flooding across multiple districts. Reported flooded districts (sourced from The Watchers, GDACS, and Copernicus EMS):

**Flooded (7 of 29 districts):** Weija Gbawe · Accra Metropolis · Ga East · Tema · Tema West · La-Nkwantanang-Madina · Adenta

**Not flooded (22 districts):** All remaining districts.

### 3.2 Quantitative Metrics — Model Comparison

#### Mean Risk Score by Flood Status

| Metric | Original Model | Recalculated Model | Verdict |
| :--- | :--- | :--- | :--- |
| Mean risk — flooded districts | 0.5736 | **0.8112** | Recalc higher ✓ |
| Mean risk — non-flooded districts | 0.5953 | **0.7745** | — |
| Difference (flooded − non-flooded) | **−0.0217** | **+0.0367** | Recalc correct direction ✓ |
| % flooded districts flagged High Risk (≥0.70) | 28.6% (2/7) | **100% (7/7)** | Recalc better ✓ |
| % non-flooded districts flagged High Risk (≥0.70) | 18.2% (4/22) | 81.8% (18/22) | Original more precise |

#### Confusion Matrix at 0.70 Threshold

| | Original Model | Recalculated Model |
| :--- | :--- | :--- |
| True Positives (flooded, flagged high) | 2 | **7** |
| False Positives (not flooded, flagged high) | 4 | 18 |
| True Negatives (not flooded, flagged low) | 18 | 4 |
| False Negatives (flooded, missed) | **5** | 0 |
| **Precision** | 0.33 | 0.28 |
| **Recall** | 0.29 | **1.00** |
| **F1 Score** | 0.31 | **0.44** |

### 3.3 Qualitative Assessment

#### Original Model
The original model correctly placed two of the most historically flood-prone districts — **Weija Gbawe (rank 2)** and **Accra Metropolis (rank 4)** — in its top tier. These are well-known chronic flood zones in Greater Accra and their high ranking reflects genuine structural risk (low elevation, dense impervious surfaces, proximity to the Odaw River and Korle Lagoon drainage system).

However, the model **missed five flooded districts entirely** at the 0.70 threshold:
- **Ga East (rank 18), Tema (rank 20), Tema West (rank 21)** — ranked mid-table, well below the high-risk cutoff
- **La-Nkwantanang-Madina (rank 24), Adenta (rank 25)** — ranked near the bottom

This is the model's most significant qualitative failure. Adenta and La-Nkwantanang-Madina are peri-urban and inland districts that were overwhelmed by the volume of the May 2025 event — their structural characteristics (moderate slope, mixed land cover) do not mark them as chronic flood zones, but a 132mm single-day rainfall event overloaded their drainage regardless. The original model, built on climatological rainfall averages, had no mechanism to capture this.

The mean risk of flooded districts (0.574) was actually **lower** than non-flooded districts (0.595) — the model ranked flooded areas as marginally safer on average. This is a fundamental failure of direction.

#### Recalculated Model
The recalculated model shows a meaningful improvement. With GPM IMERG actual rainfall (June 2024, 198 mm/month mean) and percentile reclassification applied:

- **All 7 flooded districts score above 0.70** — recall is perfect (1.00)
- The mean risk of flooded districts (0.811) now correctly **exceeds** non-flooded districts (0.774)
- **Tema West rises to rank 4**, reflecting its genuine vulnerability to both structural factors and rainfall exposure
- **Adenta (rank 14) and Tema (rank 15)** move into the top half of the risk distribution, better reflecting their susceptibility to high-rainfall events

The main weakness of the recalculated model is **low precision (0.28)**: 18 of 22 non-flooded districts also score above 0.70. The score distribution is compressed into a narrow high band (most districts fall between 0.74–0.93), making it difficult to discriminate flooded from non-flooded at the district mean level alone. The bottom four districts — Ningo-Prampram, Ada East, Shai Osudoku, Ada West — are correctly identified as low risk; these are predominantly rural and coastal areas with very different terrain and land cover.

### 3.4 Overall Verdict — Which Model Performs Better?

**The recalculated model is the stronger performer.**

| Criterion | Original | Recalculated | Winner |
| :--- | :--- | :--- | :--- |
| Direction of risk signal | Wrong (flooded < non-flooded) | Correct (flooded > non-flooded) | Recalculated |
| Recall — flooded districts caught | 0.29 | **1.00** | Recalculated |
| F1 Score | 0.31 | **0.44** | Recalculated |
| Precision | **0.33** | 0.28 | Original (marginally) |
| Qualitative alignment (known flood zones) | Partial (2/7) | Strong (7/7) | Recalculated |
| Score discrimination across districts | Better spread | Compressed mid-high | Original |
| Rainfall data quality | Climatological average | Actual observed | Recalculated |

The recalculated model wins on every meaningful criterion except precision. Its near-zero false negative rate is critical for a flood risk application — **missing a flooded district is a worse failure than over-flagging a safe one**. The original model's apparent precision advantage is misleading: it achieved it by simply scoring most districts as moderate risk, meaning it also missed five of the seven districts that actually flooded.

The precision gap (0.28 vs 0.33) is a known structural limitation of both models. A static weighted composite applied at the district mean level will always have difficulty separating flash-flood-driven events from structural risk — the underlying issue is that the May 2025 event was an extreme single-day episode, while the model represents chronic susceptibility. Improving precision requires dynamic, event-driven inputs.

---

## 4. Engineering History & Bug Resolutions

### 4.1 The "Global Average" Bug (0.508)

During early development, every district incorrectly displayed a uniform Mean Risk Score of **0.508**.

- **Cause**: The frontend was sending undefined bounding boxes to the TiTiler API, which defaulted to computing the global average of the entire raster.
- **Resolution**: Shifted from dynamic runtime calculation to static pre-calculated statistics. Zonal statistics (mean, max, median, std, histogram) are now baked into the GeoJSON district properties via `scripts/precalculate_stats.py` at pipeline time. This ensures 100% accuracy and instant loading with no API dependency at render time.

### 4.2 Rainfall Source Upgrade (CHIRPS → GPM IMERG)

The original model ingested rainfall from CHIRPS v2.0 or ERA5-Land — both climatological products that return the same historical average regardless of the actual year processed. This meant the model could not respond to unusually wet or dry months.

The pipeline was upgraded to use **NASA GPM IMERG** as the primary source, with a 4-tier fallback chain:

```
GPM IMERG Final Run  →  GPM IMERG Late Run  →  ERA5-Land  →  CHIRPS v2.0
```

GPM IMERG Final Run is bias-corrected against ground rain gauges and available with approximately 3.5 months latency. For June 2024, the actual observed mean rainfall over Greater Accra was 198 mm/month (range: 126–300 mm/month across the region), compared to the climatological average which does not vary by event.

### 4.3 Percentile Reclassification

The original pipeline applied min-max normalisation directly to the composite score, which resulted in compressed mid-range scores across most districts. The recalculated model adds a **percentile-based reclassification step** using the 25th and 75th percentile breakpoints of the pixel-level risk distribution:

```
score < p25  →  mapped to [0.00, 0.33]   (low tier)
p25 ≤ score < p75  →  mapped to [0.33, 0.67]   (moderate tier)
score ≥ p75  →  mapped to [0.67, 1.00]   (high tier)
```

This better utilises the full output range and sharpens the separation between low, moderate, and high risk areas at the pixel level — though district mean compression remains at the 0.70+ band for most urban districts.

### 4.4 COG Pipeline & Tile Serving

All risk outputs are served as Cloud-Optimised GeoTIFFs (COG) from Google Cloud Storage, rendered via TiTiler. Previous versions encountered issues with:
- **Pixel bleeding at district edges** — resolved by removing a boundary buffer that was clipping edge pixels
- **nodata=nan tile blanking** — resolved by removing the `&nodata=nan` TiTiler parameter
- **COG version cache** — managed via `?v=N` query string versioning on the COG URL

---

## 5. Limitations & Roadmap

### 5.1 Current Limitations

- **Static structural model**: Cannot capture event-specific dynamics. A 132mm single-day rainfall will overwhelm peri-urban districts regardless of their chronic risk score.
- **District-level aggregation**: Mean risk at the district level conceals localised hotspots. High-risk pixels within a nominally moderate district are invisible in the leaderboard.
- **Rainfall temporal mismatch**: The June 2024 GPM data does not correspond to the May 2025 validation event. A proper temporal validation would require running the model with May 2025 GPM data specifically.
- **No drainage infrastructure data**: The model has no representation of storm drain capacity, culvert blockages, or drainage network connectivity — a major driver of urban flash flooding in Accra.
- **Score compression**: The percentile reclassification improves pixel-level spread but most urban districts still cluster in the 0.74–0.93 band at the mean level, limiting district-level discrimination.

### 5.2 Future Roadmap (v1.1)

| Feature | Description | Impact |
| :--- | :--- | :--- |
| **Dynamic risk layer** | Real-time GPM IMERG rainfall thresholds triggering risk score adjustments on the day of an event | High — addresses the core precision gap |
| **Sentinel-1 SAR validation** | Flood extent mapping via Google Earth Engine for quantitative spatial accuracy metrics beyond district means | High — enables pixel-level validation |
| **Drainage infrastructure layer** | OSM and NADMO drainage network data as an additional composite input | Medium |
| **Property-level API** | Dynamic backend for individual parcel risk queries | Medium |
| **Temporal validation** | Rerun model with May 2025 GPM data to validate under event-matched rainfall | Medium |

---

*FloodWatch Ghana · Greater Accra Region · v0.1 · April 2026*
*Data sources: NASA SRTM, NASA GPM IMERG, ESA WorldCover, OpenStreetMap, GADM*
*Validation event: Greater Accra Floods, May 18 2025 — sources: The Watchers, GDACS, Copernicus EMS*
