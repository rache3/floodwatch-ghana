# Flood Risk Mapping Pipeline — Greater Accra Region

**Author:** Rachel Atia  
**Live map:** https://rache3.github.io/flood-risk-mapping-greater-accra  
**TiTiler API:** https://titiler-z2qegb4nha-uc.a.run.app/health  
**Stack:** GEE · Python · Docker · GCP Cloud Run · GCS · TiTiler · MapLibre · GitHub Actions

---

## What this is

A cloud-native, automated flood risk mapping pipeline for Greater Accra, Ghana. It takes five geospatial raster inputs — elevation (DEM), rainfall, slope, land cover, and water proximity — normalises them, applies a weighted risk model, and serves the output as a live interactive web map.

This is a **Digital Twin prototype** — a living system that updates on a schedule and serves results via a public web map, rather than a static GIS output.

---

## Live map

> https://rache3.github.io/flood-risk-mapping-greater-accra

Features:
- Flood risk raster rendered with plasma colormap (0 = low risk, 1 = high risk)
- District boundary overlay (GADM v4.1)
- Layer visibility toggles and opacity slider
- Click on any district for details

---

## Architecture

```
Input rasters (DEM · rainfall · slope · landcover · water proximity)
              │
              ▼
    scripts/ingest.py          ← auto-downloads data from Copernicus + ESA + OSM
              │
              ▼
    scripts/flood_risk.py      ← normalises, scores, writes COG
              │
              ▼
    scripts/upload_gcs.py      ← uploads COG to GCS bucket
              │
              ▼
    Google Cloud Storage       ← stores flood_risk_map.cog.tif + GeoJSON
              │
              ▼
    TiTiler on Cloud Run       ← serves COG as XYZ map tiles
              │
              ▼
    docs/index.html            ← MapLibre web map (GitHub Pages)
```

Orchestrated by **GitHub Actions** — runs monthly on a cron schedule or manually via the Actions UI. Authentication uses **Workload Identity Federation** — no API keys or secrets stored anywhere.

---

## Risk model

```
Risk = 0.30 × (1 - norm_DEM) + 0.25 × norm_Rainfall + 0.20 × (1 - norm_Slope) + 0.15 × norm_Landcover + 0.10 × (1 - norm_Waterbodies)
```

| Layer | Weight | Direction | Rationale |
|---|---|---|---|
| DEM / Elevation | 30% | Inverted | Low-lying areas flood first |
| ERA5 Rainfall | 25% | Normal | Higher rainfall = higher risk |
| Terrain Slope | 20% | Inverted | Flat terrain = poor drainage |
| Land Cover | 15% | Normal | Impervious surfaces increase runoff |
| Water Proximity | 10% | Inverted | Closer to water bodies = higher risk |

**Enhanced Classification**: The model now uses percentile-based risk tiers (25th/75th percentiles) for adaptive classification that adapts to local data distribution rather than absolute thresholds. This provides three distinct risk categories: low (0-0.33), moderate (0.33-0.67), and high (0.67-1.0).

Output range: **0 (low risk) → 1 (high risk)**

---

## Free tier cost breakdown

| Service | Role | Free limit | Monthly cost |
|---|---|---|---|
| Google Earth Engine | Satellite data processing | Free (research) | $0 |
| GCP Cloud Run | TiTiler tile server + processing job | 2M req/month | $0 |
| Google Cloud Storage | COG rasters + GeoJSON | 5 GB | $0 |
| GitHub Actions | Pipeline orchestration | 2,000 min/month | $0 |
| GitHub Pages | Web map hosting | Unlimited | $0 |
| Workload Identity | Keyless GCP auth | Always free | $0 |
| **Total** | | | **$0.00** |

---

## Repository structure

```
flood-risk-mapping-greater-accra/
├── .github/
│   └── workflows/
│       └── pipeline.yml       # GitHub Actions — monthly cron + manual trigger
├── docker/
│   ├── Dockerfile             # Processing container (Python + rasterio + GDAL)
│   └── requirements.txt
├── scripts/
│   ├── ingest.py              # Auto-downloads DEM, derives slope, fetches rainfall
│   ├── flood_risk.py          # Core processing — normalise, score, write COG
│   ├── mask_raster.py         # Boundary masking to hide bleeding tiles
│   └── upload_gcs.py          # Upload outputs to Google Cloud Storage
├── titiler/
│   └── main.py                # TiTiler FastAPI tile server
├── docs/
│   └── index.html             # MapLibre GL JS web map (served by GitHub Pages)
├── terraform/
│   ├── main.tf                # GCP infrastructure as code
│   ├── variables.tf           # Terraform variables
│   ├── outputs.tf             # Terraform outputs
│   └── terraform.tfvars       # Actual values (gitignored)
├── data/                      # Input rasters (auto-downloaded)
├── output/                    # Generated flood risk maps
├── .env.example               # Configuration template
├── mask_raster.py             # Boundary masking script (root level)
├── PIPELINE_GUIDE.md          # Full user guide with HCL/Terraform section
└── README.md
```
│   ├── ingest.py              # Auto-downloads DEM, derives slope, fetches rainfall
│   ├── flood_risk.py          # Core processing — normalise, score, write COG
│   └── upload_gcs.py          # Upload outputs to Google Cloud Storage
├── titiler/
│   └── main.py                # TiTiler FastAPI tile server
├── docs/
│   └── index.html             # MapLibre GL JS web map (served by GitHub Pages)
├── .env.example               # Configuration template — copy to .env and fill in
├── setup.sh                   # One-time GCP infrastructure setup script
├── PIPELINE_GUIDE.md          # Full user guide with HCL/Terraform section
└── README.md
```

---

## Quickstart — run locally

### 1. Clone the repo

```bash
git clone https://github.com/rache3/flood-risk-mapping-greater-accra.git
cd flood-risk-mapping-greater-accra
```

### 2. Install dependencies

```bash
pip install rasterio numpy python-dotenv google-cloud-storage
```

### 3. Configure

```bash
cp .env.example .env
# Open .env and fill in your GCP project ID, bucket name, bounding box etc.
```

### 4. Run the pipeline

```bash
# Download input data
python scripts/ingest.py

# Process and generate flood risk COG
python scripts/flood_risk.py

# Mask to Greater Accra boundary (removes rectangular bounding box)
python mask_raster.py

# Upload to GCS
python scripts/upload_gcs.py
```

---

## Quickstart — deploy to GCP

### 1. Set up GCP infrastructure (one time only)

```bash
# Fill in .env first, then:
bash setup.sh
```

### 2. Build and deploy TiTiler

```bash
docker build -f docker/Dockerfile -t gcr.io/YOUR_PROJECT_ID/titiler .
gcloud auth configure-docker
docker push gcr.io/YOUR_PROJECT_ID/titiler
gcloud run deploy titiler \
  --image gcr.io/YOUR_PROJECT_ID/titiler \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 512Mi \
  --min-instances 0
```

### 3. Add GitHub repository variables

Go to **Settings → Secrets and variables → Actions → Variables** and add:

| Variable | Value |
|---|---|
| `GCP_PROJECT_ID` | your GCP project ID |
| `GCP_PROJECT_NUMBER` | your GCP project number |
| `GCP_REGION` | `us-central1` |
| `GCS_BUCKET` | your bucket name |
| `WORKLOAD_IDENTITY_PROVIDER` | your WIF provider path |
| `SERVICE_ACCOUNT` | your service account email |

### 4. Enable GitHub Pages

**Settings → Pages → Source:** branch `main`, folder `/docs`

---

## Trigger the pipeline manually

Go to **Actions → Flood Risk Pipeline → Run workflow** and optionally set the rainfall year and month.

---

## Recent Improvements (March 2026)

- **Boundary Masking**: Added `mask_raster.py` to clip flood risk map to Greater Accra boundary, eliminating rectangular tile bleeding
- **Percentile-Based Classification**: Implemented adaptive risk tiers using 25th/75th percentiles for better score distribution
- **Enhanced NoData Handling**: Improved handling of missing data throughout the pipeline
- **Pure NumPy Slope Derivation**: Removed GDAL dependency for slope calculation using NumPy operations
- **Infrastructure as Code**: Complete Terraform setup for GCP resources with proper lifecycle management
- **Workload Identity Federation**: Secure GitHub Actions authentication without service account keys

---

1. Update the bounding box in `.env` — use your area's extent from QGIS
2. Replace `gadm41_GHA_2.json` with the GADM boundary for your country/region
3. Update the `NAME_1` filter in `mask_raster.py` to match your region name
4. Run `bash setup.sh` to provision GCP resources
5. Deploy and push

---

## Documentation

See [PIPELINE_GUIDE.md](PIPELINE_GUIDE.md) for the full user guide including:
- Step-by-step setup instructions
- HCL / Terraform infrastructure as code
- Troubleshooting common errors
- How to update the data

---

## Data sources

| Dataset | Source | Resolution | License | Processing |
|---|---|---|---|---|
| DEM | SRTM GL1 via OpenTopography | 30m | Free | Direct download, no API key |
| Rainfall | ERA5-Land via CDS | ~9km | Research free | Monthly aggregation |
| Slope | Derived from SRTM DEM | 30m | — | Pure NumPy calculation |
| Boundaries | GADM v4.1 | — | Research free | GeoJSON masking |
| Land Cover | ESA WorldCover 2021 | 10m | Free | Imperviousness fraction |
| Water Bodies | OpenStreetMap | Variable | Open | Distance calculation |

**Recent Improvements:**
- Pure NumPy slope derivation (no GDAL dependency)
- Enhanced nodata handling throughout pipeline
- Boundary masking to prevent tile bleeding
- Percentile-based adaptive risk classification

---

*Greater Accra Region, Ghana · EPSG:4326 · Rachel Atia · 2025–2026*
