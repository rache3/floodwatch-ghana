# FloodWatch Ghana — Flood Risk Intelligence Pipeline
### Greater Accra Region

**Author:** Rachel Atia · GeoBuilders Africa  
**Live map:** https://floodwatch.geobuildersafrica.com  
**Company:** https://geobuildersafrica.com

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

---

## Risk model

```
Risk = 0.30 × (1 − norm_DEM)
     + 0.25 × norm_Rainfall
     + 0.20 × (1 − norm_Slope)
     + 0.15 × norm_Landcover
     + 0.10 × (1 − norm_Waterbodies)
```

| Layer | Weight | Direction | Rationale |
|---|---|---|---|
| Elevation (SRTM DEM) | 30% | Inverted | Low-lying areas accumulate water |
| Precipitation (ERA5) | 25% | Normal | Higher rainfall increases runoff |
| Terrain slope | 20% | Inverted | Flat terrain drains poorly |
| Land cover imperviousness | 15% | Normal | Impervious surfaces increase runoff |
| Distance to water bodies | 10% | Inverted | Proximity to rivers and lagoons increases risk |

Each layer is min-max normalised to [0, 1] before combination. The composite score is reclassified into percentile-based risk tiers using the 25th and 75th percentiles of the local distribution, producing three categories: low (0–0.33), moderate (0.33–0.67), and high (0.67–1.0).

Output range: **0 (low risk) → 1 (high risk)**

---

## Pipeline architecture

```
Input data sources
(OpenTopography · ERA5 · ESA S3 · OpenStreetMap Overpass API)
              │
              ▼
    scripts/ingest.py
    ├── ingest_dem.py          ← SRTM 30m DEM via OpenTopography API
    ├── ingest_slope.py        ← Slope derived from DEM using NumPy gradient
    ├── ingest_rainfall.py     ← ERA5-Land monthly precipitation (GPM fallback)
    ├── ingest_landcover.py    ← ESA WorldCover 2021 → imperviousness fraction
    └── ingest_waterbodies.py  ← OSM water features → distance raster
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

Orchestrated by **GitHub Actions** on a monthly cron schedule. Authentication uses **Workload Identity Federation** — no API keys or secrets stored in the repository.

---

## Repository structure

```
flood-risk-mapping-greater-accra/
├── .github/
│   └── workflows/
│       └── pipeline.yml       # GitHub Actions — monthly + manual trigger
├── scripts/
│   ├── ingest.py              # Orchestrator — runs all ingest scripts in order
│   ├── ingest_dem.py          # SRTM DEM download
│   ├── ingest_slope.py        # Slope derivation from DEM
│   ├── ingest_rainfall.py     # ERA5 / GPM precipitation download
│   ├── ingest_landcover.py    # ESA WorldCover download and processing
│   ├── ingest_waterbodies.py  # OSM water features and distance raster
│   ├── flood_risk.py          # Risk model — normalise, score, mask, COG
│   └── upload_gcs.py          # Upload outputs to Google Cloud Storage
├── titiler/
│   └── main.py                # TiTiler FastAPI tile server
├── terraform/
│   ├── main.tf                # GCP infrastructure as code
│   ├── variables.tf
│   ├── outputs.tf
│   └── terraform.tfvars       # Gitignored
├── docs/
│   └── index.html             # MapLibre GL JS web map
├── data/                      # Input rasters (auto-downloaded, gitignored)
├── output/                    # Generated outputs (gitignored)
├── .env.example               # Configuration template
└── PIPELINE_GUIDE.md          # Full setup and deployment guide
```

---

## Quickstart — run locally

```bash
# Clone
git clone https://github.com/rache3/flood-risk-mapping-greater-accra.git
cd flood-risk-mapping-greater-accra

# Install dependencies
pip install rasterio numpy scipy shapely python-dotenv google-cloud-storage

# Configure
cp .env.example .env
# Edit .env with your GCP project ID, bucket name, bounding box

# Run the full pipeline
python scripts/ingest.py        # Download all input data
python scripts/flood_risk.py    # Process, mask, and write COG
python scripts/upload_gcs.py    # Upload to GCS
```

---

## Data sources

| Dataset | Source | Resolution | Licence |
|---|---|---|---|
| Elevation (DEM) | SRTM GL1 via OpenTopography | 30m | Free, no API key |
| Precipitation | ERA5-Land via ECMWF CDS | ~9km | Free research use |
| Slope | Derived from SRTM DEM | 30m | — |
| Land cover | ESA WorldCover 2021 | 10m | Free |
| Water bodies | OpenStreetMap Overpass API | Variable | Open |
| District boundaries | GADM v4.1 | — | Free research use |

---

## Infrastructure

| Service | Role |
|---|---|
| Google Cloud Run | TiTiler tile server |
| Google Cloud Storage | COG raster and GeoJSON storage |
| GitHub Actions | Pipeline orchestration |
| GitHub Pages | Web map hosting |
| Terraform | Infrastructure as code |
| Workload Identity Federation | Keyless GCP authentication |

---

## Deployment

See [PIPELINE_GUIDE.md](PIPELINE_GUIDE.md) for the full setup guide including Terraform infrastructure provisioning, GitHub Actions configuration, and Workload Identity Federation setup.

---

*Greater Accra Region, Ghana · EPSG:4326 · Rachel Atia · GeoBuilders Africa · 2025–2026*
