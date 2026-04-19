# Technical Bug Report & Methodology Transparency (v0.1)

This document provides a transparent overview of the critical bugs identified during the development of FloodWatch Ghana v0.1 and the engineering decisions made to resolve them.

## 1. The "Global Average" Bug (0.508)

### Description
Users reported that every district on the map displayed the exact same **Mean Risk Score of 0.508**, regardless of its actual terrain or rainfall data.

### Root Cause Analysis
The issue was identified in the `script.js` frontend logic. The application was attempting to fetch district-specific statistics from an external TiTiler API using the following URL structure:
`.../cog/statistics?url=[raster_url]&bbox=undefined,undefined,undefined,undefined`

Because the source GeoJSON data did not include pre-defined bounding boxes (`bbox`) for each district, the frontend was sending `undefined` coordinates. The TiTiler API, receiving no specific area of interest, defaulted to calculating the statistics for the **entire raster image** (the whole of Greater Accra), resulting in the global average being shown for every district.

### Attempted Fix (Dynamic API)
We attempted to resolve this by dynamically calculating the bounding box for each district on-the-fly using the **Turf.js** library.
*   **Action**: Modified `script.js` to use `turf.bbox(feature)` before making the API call.
*   **Result**: While the API calls were then correctly formatted with precise coordinates, the external service continued to return the global average (0.508), indicating a backend configuration issue or a service-side limitation in handling complex dynamic requests.

---

## 2. Methodology Shift: Static Pre-calculation

### The Decision
To ensure 100% accuracy and remove dependency on a brittle external API, we shifted the methodology from **Dynamic (Runtime) Calculation** to **Static (Pre-calculated) Statistics** for v0.1.

### New Methodology
We implemented a Python-based pre-processing pipeline:
1.  **Extraction**: For each district polygon, we "masked" the High-Resolution Flood Risk Raster.
2.  **Zonal Statistics**: Using `rasterio` and `numpy`, we calculated the true Mean, Max, Median, and Standard Deviation for only the pixels within each district.
3.  **Histogram Generation**: We calculated a 10-bin risk distribution histogram for each district to show the spread of risk (Low to High).
4.  **Data Injection**: These statistics were injected directly into the district properties within the `gadm41_GHA_accra.json` file.

### Impact
*   **Accuracy**: Scores are now verified against the raw raster data using industry-standard Python libraries.
*   **Reliability**: The application no longer relies on a backend API to show statistics; the data is "baked in."
*   **Performance**: Popups now load instantly without waiting for a network request.

## 3. Future Outlook (v1.1)
While the static approach is superior for the current fixed-raster model, we plan to re-evaluate the dynamic approach in v1.1 when we introduce multi-temporal data (comparing risk across different years/months), which may require a more robust backend infrastructure.
