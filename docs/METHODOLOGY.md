# FloodWatch Ghana: Risk Methodology & Project History (v0.1)

This document provides a comprehensive overview of the FloodWatch Ghana risk model, the Greater Accra district leaderboard, and the technical engineering decisions made during the development of v0.1.

---

## 1. The Risk Model (v0.1)

FloodWatch Ghana v0.1 is a **structural baseline** model. It identifies areas chronically prone to flooding based on their physical and environmental characteristics.

### Weighted Composite Formula
Each 30m pixel is assigned a value from 0 (Low) to 1 (High) using the following weights:

| Component | Weight | Direction | Source | Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **Elevation** | 30% | Inverted | NASA SRTM | Low-lying areas are natural catchments for runoff. |
| **Precipitation** | 25% | Normal | CHIRPS / GPM | Areas with higher historical rainfall intensity. |
| **Terrain Slope** | 20% | Inverted | Derived from SRTM | Flat terrain drains significantly slower than slopes. |
| **Imperviousness** | 15% | Normal | ESA WorldCover | Paved/urban surfaces prevent water infiltration. |
| **Water Proximity**| 10% | Inverted | OpenStreetMap | Proximity to known rivers and drainage channels. |

**Formula:**
`Risk = 0.30*(1-DEM) + 0.25*Rain + 0.20*(1-Slope) + 0.15*Imperv + 0.10*(1-Water)`

---

## 2. District Risk Leaderboard

Mean risk scores calculated across every 30m pixel within each district boundary.

| Rank | District | Mean Risk | Max Risk | Tier |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **Ablekuma West** | 0.8398 | 0.9928 | 🔴 High |
| 2 | **Weija Gbawe** | 0.8123 | 0.9957 | 🔴 High |
| 3 | **Ga Central** | 0.7258 | 0.9796 | 🔴 High |
| 4 | **Accra Metropolis** | 0.7170 | 0.8681 | 🔴 High |
| 5 | **Ga West** | 0.7063 | 0.9091 | 🔴 High |
| ... | ... | ... | ... | ... |
| 29 | **Ashaiman** | 0.3654 | 0.6527 | 🟢 Low |

*(See [output/validation_may2025.json](../output/validation_may2025.json) for the full 29-district dataset.)*

---

## 3. Engineering History & Bug Resolutions

### The "Global Average" Bug (0.508)
During early development, every district incorrectly displayed a uniform Mean Risk Score of **0.508**. 
*   **Cause**: The frontend was sending undefined bounding boxes to the TiTiler API, causing it to default to the global average of the entire region.
*   **Resolution**: We shifted from **Dynamic (Runtime) Calculation** to **Static (Pre-calculated) Statistics**. The zonal statistics (Mean, Max, Median) are now "baked" into the GeoJSON district properties using a Python pre-processing pipeline (`scripts/precalculate_stats.py`). This ensures 100% accuracy and instant loading.

### Validation Mapping
Validation against the May 18, 2025 flood event (132mm rainfall) showed that while the model is **qualitatively strong** (identifying the most famous flood zones in the Top 4), real-world flooding is often driven by event-specific flash flood dynamics not captured by a static structural model. This informs the roadmap for v1.1.

---

## 4. Future Roadmap (v1.1)

*   **Dynamic Risk Layer**: Real-time GPM IMERG rainfall thresholds.
*   **Quantitative Validation**: Sentinel-1 SAR flood extent mapping via Google Earth Engine.
*   **Property-Level API**: Moving back to a robust dynamic backend for individual property risk lookups.

*Greater Accra Region, Ghana · v0.1 · 2026*
