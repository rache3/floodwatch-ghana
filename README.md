# Flood Risk Mapping Pipeline — Greater Accra Region

**Author:** Rachel Atia  
**Live map:** https://rache3.github.io/flood-risk-mapping-greater-accra  
**TiTiler API:** https://titiler-244163528833.us-central1.run.app/health  
**Stack:** GEE · Python · Docker · GCP Cloud Run · GCS · TiTiler · MapLibre · GitHub Actions

---

## What this is

A cloud-native, automated flood risk mapping pipeline for Greater Accra, Ghana. It takes three geospatial raster inputs — elevation (DEM), rainfall, and slope — normalises them, applies a weighted risk model, and serves the output as a live interactive web map.

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
Input rasters (DEM · rainfall · slope)
              │
              ▼
    scripts/ingest.py          ← auto-downloads data from Copernicus + ERA5
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
Risk = 0.40 × (1 - norm_DEM) + 0.35 × norm_Rainfall + 0.25 × (1 - norm_Slope)
```

| Layer | Weight | Direction | Rationale |
|---|---|---|---|
| DEM / Elevation | 40% | Inverted | Low-lying areas flood first |
| ERA5 Rainfall | 35% | Normal | Higher rainfall = higher risk |
| Terrain Slope | 25% | Inverted | Flat terrain = poor drainage |

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

## Adapting to a different study area

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

| Dataset | Source | Resolution | License |
|---|---|---|---|
| DEM | Copernicus GLO-30 via OpenTopography | 30m | Free |
| Rainfall | ERA5-Land via ECMWF CDS | ~9km | Free (research) |
| Slope | Derived from DEM via GDAL | 30m | — |
| Boundaries | GADM v4.1 | — | Free (research) |

---

*Greater Accra Region, Ghana · EPSG:4326 · Rachel Atia · 2024–2026*
