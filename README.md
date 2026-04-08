# FloodWatch Ghana — Flood Risk Intelligence Pipeline
### Greater Accra Region

**Author:** Rachel Atia · GeoBuilders Africa  
**Live map:** https://floodwatch.geobuildersafrica.com  
**Company:** https://geobuildersafrica.com  
**GitHub:** https://github.com/rache3/flood-risk-mapping-greater-accra

---

## Overview

An automated flood risk mapping pipeline for Greater Accra, Ghana. The system ingests five geospatial datasets, normalises and combines them into a weighted composite risk score, and serves the output as a live interactive web map updated monthly.

Greater Accra is the pilot region. The pipeline is designed to scale across all regions of Ghana and other African cities.

---

## Live map

> **https://floodwatch.geobuildersafrica.com**

- Flood risk raster rendered with plasma colormap (0 = low risk, 1 = high risk)
- All 29 districts of Greater Accra with boundary overlays
- Click any district for mean, max, median, std deviation, and risk distribution
- Layer toggles and opacity control
- Validation badge — validated against May 18, 2025 Greater Accra floods

---

## Validation

FloodWatch Ghana v1.0 underwent **qualitative validation** against the **May 18, 2025 Greater Accra flood event** — 132.20mm of rainfall, 4 deaths, 3,000+ displaced (Source: The Watchers, GDACS, Copernicus EMS).

Qualitative validation compares the model's district-level risk rankings against documented flood locations from news reports and official sources. It does not use satellite-derived flood extent maps — that quantitative validation is planned for v1.1 using Sentinel-1 SAR imagery via Google Earth Engine.

**Result: MODERATE ✓**

Flooded districts mean risk score: **0.5983** vs non-flooded: **0.5874** (+0.0109)

All 3 chronically high-risk flood zones correctly ranked in the top 4 districts. The 4 districts that were missed (Adenta, La-Nkwantanang-Madina, Tema, TemaWest) experienced flash flooding driven by extreme rainfall (132mm) — a separate risk category not captured by the static structural model. This is an expected limitation of v1.0 and informs the roadmap for v1.1.

| District | Rank | Percentile | Flooded May 2025 |
|---|---|---|---|
| WeijaGbawe | 2 of 29 | top 93% | 🔴 YES |
| GaCentral (Kaneshie) | 3 of 29 | top 90% | 🔴 YES |
| Accra (Adabraka) | 4 of 29 | top 86% | 🔴 YES |
| Tema | 20 of 29 | top 31% | 🔴 YES |
| TemaWest | 21 of 29 | top 28% | 🔴 YES |
| La-Nkwantanang-Madina (Oyarifa/Abokobi) | 24 of 29 | top 17% | 🔴 YES |
| Adenta | 25 of 29 | top 14% | 🔴 YES |

**Flooded districts mean risk: 0.5983 vs non-flooded: 0.5874**

3 of 7 flooded districts ranked in the top 4 risk zones. Districts that ranked lower but flooded (Adenta, La-Nkwantanang-Madina) experienced **flash flooding** driven by extreme rainfall rather than chronic structural vulnerability — a known limitation of the current static model.

Validation script: `scripts/validate_flood_risk.py`  
Full results: `output/validation_may2025.json`

---

## Risk model

```
Risk = 0.30 × (1 − norm_DEM)
     + 0.25 × norm_Rainfall
     + 0.20 × (1 − norm_Slope)
     + 0.15 × norm_Landcover
     + 0.10 × (1 − norm_Waterbodies)
```

| Layer | Weight | Direction | Source | Rationale |
|---|---|---|---|---|
| Elevation (SRTM DEM) | 30% | Inverted | OpenTopography | Low-lying areas accumulate water |
| Precipitation | 25% | Normal | CHIRPS v2.0 / GPM IMERG | Higher rainfall increases runoff |
| Terrain slope | 20% | Inverted | Derived from SRTM | Flat terrain drains poorly |
| Land cover imperviousness | 15% | Normal | ESA WorldCover 2021 | Impervious surfaces increase runoff |
| Distance to water bodies | 10% | Inverted | OpenStreetMap | Proximity to rivers increases risk |

Each layer is min-max normalised to [0, 1]. The composite score uses percentile-based reclassification at p25/p75, producing three risk tiers: low (0–0.33), moderate (0.33–0.67), and high (0.67–1.0).

---

## Pipeline architecture

```
Input data sources
(OpenTopography · CHIRPS/GPM · ESA S3 · OpenStreetMap Overpass API)
              │
              ▼
    scripts/ingest.py
    ├── ingest_dem.py          ← SRTM 30m DEM via OpenTopography API
    ├── ingest_slope.py        ← Slope derived from DEM using NumPy gradient
    ├── ingest_rainfall.py     ← GPM IMERG Final → Late → ERA5 → CHIRPS fallback
    ├── ingest_landcover.py    ← ESA WorldCover 2021 → imperviousness fraction
    ├── ingest_waterbodies.py  ← OSM water features → distance raster
    └── ingest_aod.py          ← MODIS/MERRA-2 AOD → quality flagging (optional)
              │
              ▼
    scripts/flood_risk.py
    ├── Align all layers to DEM reference grid
    ├── Min-max normalisation per layer
    ├── Weighted composite risk score
    ├── Percentile-based reclassification
    ├── Mask to Greater Accra boundary
    └── Write Cloud-Optimised GeoTIFF (COG)
              │
              ▼
    scripts/upload_gcs.py      ← Upload COG and GeoJSON to GCS
              │
              ▼
    Google Cloud Storage       ← flood_risk_map.cog.tif + district GeoJSON
              │
              ▼
    TiTiler on Cloud Run       ← Serves COG as XYZ tiles
              │
              ▼
    docs/index.html            ← MapLibre GL JS web map (GitHub Pages)
```

Orchestrated by **GitHub Actions** on a monthly cron schedule. Authentication uses **Workload Identity Federation** — no API keys stored in the repository.

---

## Repository structure

```
flood-risk-mapping-greater-accra/
├── .github/
│   └── workflows/
│       ├── ci.yml             # Lint, structure validation, syntax checks
│       └── pipeline.yml       # Monthly pipeline — build, process, upload
├── scripts/
│   ├── ingest.py              # Orchestrator
│   ├── ingest_dem.py          # SRTM DEM download
│   ├── ingest_slope.py        # Slope derivation
│   ├── ingest_rainfall.py     # GPM IMERG / CHIRPS precipitation
│   ├── ingest_landcover.py    # ESA WorldCover
│   ├── ingest_waterbodies.py  # OSM water features
│   ├── ingest_aod.py          # AOD quality flagging
│   ├── flood_risk.py          # Risk model
│   ├── upload_gcs.py          # GCS upload
│   └── validate_flood_risk.py # Validation against historical flood events
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
├── docs/
│   └── index.html             # MapLibre GL JS web map
├── output/
│   └── validation_may2025.json # Validation results
├── data/
│   └── gadm41_GHA_accra.json  # District boundaries
├── .env.example               # Configuration template
├── requirements.txt
└── README.md
```

---

## Quickstart — run locally

```bash
git clone https://github.com/rache3/flood-risk-mapping-greater-accra.git
cd flood-risk-mapping-greater-accra

pip install -r requirements.txt

cp .env.example .env
# Edit .env with your credentials

python scripts/ingest.py        # Download all input data
python scripts/flood_risk.py    # Process and write COG
python scripts/upload_gcs.py    # Upload to GCS

# Optional: run validation
python scripts/validate_flood_risk.py
```

---

## Data sources

| Dataset | Source | Resolution | Auth |
|---|---|---|---|
| Elevation (DEM) | SRTM GL1 via OpenTopography | 30m | Free API key |
| Precipitation | CHIRPS v2.0 / GPM IMERG | 5km / 10km | Free / Earthdata |
| Slope | Derived from SRTM | 30m | — |
| Land cover | ESA WorldCover 2021 | 10m | Free |
| Water bodies | OpenStreetMap Overpass API | Variable | Open |
| District boundaries | GADM v4.1 | — | Free |

---

## Infrastructure

| Service | Role |
|---|---|
| Google Cloud Run | TiTiler tile server |
| Google Cloud Storage | COG raster and GeoJSON |
| GitHub Actions | CI and monthly pipeline |
| GitHub Pages | Web map hosting |
| Terraform | Infrastructure as code |
| Workload Identity Federation | Keyless GCP authentication |

---

## Known limitations

- **Validation is qualitative** — district risk rankings compared against news-reported flood locations. Quantitative validation using Sentinel-1 SAR flood extent maps is planned for v1.1
- Static risk model captures chronic structural vulnerability — not event-driven flash flooding
- Districts like Adenta and La-Nkwantanang-Madina may flood under extreme rainfall events not predicted by the static model
- Real-time rainfall thresholds via GPM IMERG Late Run are planned for v1.1
- Greater Accra pilot only — expansion to other Ghana regions in progress

---

*Greater Accra Region, Ghana · EPSG:4326 · Rachel Atia · GeoBuilders Africa · 2025–2026*
