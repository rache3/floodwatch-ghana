# Flood Risk Pipeline — Greater Accra Region
**Author:** Rachel Atia  
**Stack:** GitHub Actions · Google Cloud Run · Cloudflare R2 · Supabase · TiTiler · MapLibre

---

## Architecture

```
Data Sources (Copernicus DEM, ERA5 rainfall)
       │
       ▼
GitHub Actions  ──► builds & triggers ──► Google Cloud Run (processing job)
                                                   │
                              ┌────────────────────┴───────────────────┐
                              ▼                                         ▼
                    Cloudflare R2                                 (optional)
                    - flood_risk_map.cog.tif                  Supabase PostGIS
                    - gadm41_GHA_2.json                       - district stats
                              │
                              ▼
                    Google Cloud Run (TiTiler)
                    - serves XYZ tiles from COG
                              │
                              ▼
                    GitHub Pages (frontend)
                    - MapLibre GL JS web map
```

**Monthly cost: $0** — all services stay within free tiers for this workload.

---

## Free Tier Summary

| Service | What it does | Free limit |
|---|---|---|
| GitHub Actions | Runs the pipeline monthly | 2,000 min/month (public repo) |
| Google Cloud Run | Processing job + TiTiler tile server | 2M req/month, 180K vCPU-sec/month |
| Cloudflare R2 | Stores COG rasters + GeoJSON | 10 GB storage, **zero egress fees** |
| Supabase | PostGIS for district stats (optional) | 500 MB database |
| GitHub Pages | Hosts the web map | Unlimited (public repo) |

---

## Setup (one-time)

### 1. Cloudflare R2

1. Go to [dash.cloudflare.com](https://dash.cloudflare.com) → R2
2. Create a bucket named `accra-flood-risk`
3. Enable **Public Access** on the bucket (for TiTiler to read the COG)
4. Create an API token with **Object Read & Write** permissions
5. Note your **Account ID**, **Access Key ID**, and **Secret Access Key**

### 2. Google Cloud Run

```bash
# Install gcloud CLI, then:
gcloud auth login
gcloud projects create accra-flood-risk --name="Accra Flood Risk"
gcloud config set project accra-flood-risk

# Enable required APIs
gcloud services enable run.googleapis.com containerregistry.googleapis.com secretmanager.googleapis.com

# Create a service account for GitHub Actions
gcloud iam service-accounts create github-pipeline \
  --display-name="GitHub Actions Pipeline"

gcloud projects add-iam-policy-binding accra-flood-risk \
  --member="serviceAccount:github-pipeline@accra-flood-risk.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding accra-flood-risk \
  --member="serviceAccount:github-pipeline@accra-flood-risk.iam.gserviceaccount.com" \
  --role="roles/storage.admin"

# Download the key (you'll add this to GitHub secrets)
gcloud iam service-accounts keys create gcp-key.json \
  --iam-account=github-pipeline@accra-flood-risk.iam.gserviceaccount.com
```

### 3. Store R2 credentials in GCP Secret Manager

```bash
echo -n "YOUR_R2_ACCOUNT_ID" | gcloud secrets create r2-account-id --data-file=-
echo -n "YOUR_R2_ACCESS_KEY"  | gcloud secrets create r2-access-key  --data-file=-
echo -n "YOUR_R2_SECRET_KEY"  | gcloud secrets create r2-secret-key  --data-file=-
echo -n "accra-flood-risk"    | gcloud secrets create r2-bucket       --data-file=-
```

### 4. GitHub Secrets

In your repo → Settings → Secrets → Actions, add:

| Secret | Value |
|---|---|
| `GCP_PROJECT_ID` | `accra-flood-risk` |
| `GCP_SA_KEY` | Contents of `gcp-key.json` |

### 5. Deploy TiTiler to Cloud Run

```bash
cd titiler
docker build -t gcr.io/accra-flood-risk/titiler .
docker push gcr.io/accra-flood-risk/titiler

gcloud run deploy titiler \
  --image=gcr.io/accra-flood-risk/titiler \
  --region=us-central1 \
  --allow-unauthenticated \
  --set-env-vars="R2_PUBLIC_URL=https://pub-YOURPUBID.r2.dev" \
  --memory=512Mi \
  --min-instances=0
```

### 6. Update frontend config

Edit `frontend/index.html` and replace:
- `https://YOUR-TITILER-SERVICE-URL.run.app` → your Cloud Run URL
- `https://pub-YOURPUBID.r2.dev` → your R2 public URL

Then push to GitHub. GitHub Pages will serve it automatically from the `frontend/` folder.

---

## Running the pipeline manually

```bash
# Local run (with your data files in data/)
export DATA_DIR=data
export OUTPUT_DIR=output
python scripts/ingest.py --year 2024 --month 6
python scripts/flood_risk.py

# Or trigger via GitHub Actions UI:
# Actions → Flood Risk Pipeline → Run workflow
```

---

## File structure

```
flood_pipeline/
├── .github/
│   └── workflows/
│       └── pipeline.yml      # Monthly scheduler + Cloud Run trigger
├── docker/
│   ├── Dockerfile            # Processing container (rasterio + GDAL)
│   └── requirements.txt
├── scripts/
│   ├── ingest.py             # Download DEM, rainfall, derive slope
│   ├── flood_risk.py         # Core processing: normalise + score + COG
│   └── upload_r2.py          # Upload outputs to Cloudflare R2
├── titiler/
│   ├── Dockerfile            # TiTiler tile server
│   └── main.py               # FastAPI app with COG tile endpoints
└── frontend/
    └── index.html            # MapLibre GL JS web map (deploy to GitHub Pages)
```

---

## Risk score methodology

The flood risk score is a **weighted composite** of three normalised layers:

| Layer | Weight | Direction | Rationale |
|---|---|---|---|
| DEM (elevation) | 40% | Inverted (low elev = high risk) | Low-lying areas flood first |
| Rainfall | 35% | Normal (high rain = high risk) | Precipitation intensity |
| Slope | 25% | Inverted (flat = high risk) | Flat terrain = poor drainage |

Score range: **0 (low risk) → 1 (high risk)**

To adjust the model, edit `WEIGHTS` in `scripts/flood_risk.py`.
