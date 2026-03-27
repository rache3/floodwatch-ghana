# Flood Risk Mapping Pipeline — User Guide

**Project:** Cloud-Native Flood Risk Mapping Pipeline, Greater Accra Region  
**Author:** Rachel Atia  
**Repo:** [rache3/flood-risk-mapping-greater-accra](https://github.com/rache3/flood-risk-mapping-greater-accra)  
**Live map:** https://rache3.github.io/flood-risk-mapping-greater-accra

---

## Table of Contents

1. [Pipeline Overview](#1-pipeline-overview)
2. [Prerequisites & Setup](#2-prerequisites--setup)
3. [Running the Pipeline Locally](#3-running-the-pipeline-locally)
4. [Deploying to GCP](#4-deploying-to-gcp)
5. [Infrastructure as Code (HCL)](#5-infrastructure-as-code-hcl)
6. [Updating the Data](#6-updating-the-data)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Pipeline Overview

This pipeline takes three geospatial raster inputs — elevation (DEM), rainfall, and slope — and combines them into a weighted flood risk score for Greater Accra. The output is served as an interactive web map.

### How it flows

```
Input rasters (DEM, rainfall, slope)
          │
          ▼
  scripts/ingest.py          ← downloads/prepares data
          │
          ▼
  scripts/flood_risk.py      ← normalises, scores, writes COG
          │
          ▼
  scripts/upload_gcs.py      ← uploads COG to GCS bucket
          │
          ▼
  Google Cloud Storage       ← stores flood_risk_map.cog.tif
          │
          ▼
  TiTiler on Cloud Run       ← serves the COG as XYZ map tiles
          │
          ▼
  docs/index.html            ← MapLibre web map (GitHub Pages)
```

### Risk score formula

```
Risk = 0.40 × (1 - norm_DEM) + 0.35 × norm_Rainfall + 0.25 × (1 - norm_Slope)
```

- **DEM** is inverted — low elevation = high risk
- **Rainfall** is normal — high rainfall = high risk
- **Slope** is inverted — flat terrain = high risk (poor drainage)
- Output range: **0 (low risk) → 1 (high risk)**

---

## 2. Prerequisites & Setup

### What you need installed

| Tool | Purpose | Install guide |
|------|---------|---------------|
| Python 3.11+ | Run processing scripts | [python.org](https://www.python.org/downloads/) |
| Git | Version control | [git-scm.com](https://git-scm.com/) |
| Docker Desktop | Build containers | [docker.com](https://www.docker.com/products/docker-desktop/) |
| Google Cloud SDK | GCP CLI tools | [cloud.google.com/sdk](https://cloud.google.com/sdk/docs/install) |

### Step 1 — Clone the repository

Open your terminal and run:

```bash
git clone https://github.com/rache3/flood-risk-mapping-greater-accra.git
cd flood-risk-mapping-greater-accra
```

### Step 2 — Install Python dependencies

```bash
pip install rasterio numpy boto3 gdal
```

> **Note:** On Windows, if `pip install` gives an error about system packages, add `--break-system-packages` to the command.

### Step 3 — Place your input data

Put these files in the root of the project folder:

```
flood-risk-mapping-greater-accra/
├── accra_dem.tif          ← elevation raster (int16, EPSG:4326)
├── accra_rainfall.tif     ← rainfall raster (float64, EPSG:4326)
├── accra_slope.tif        ← slope raster (float32, EPSG:4326)
└── gadm41_GHA_2.json      ← Ghana district boundaries (GADM v4.1)
```

All rasters must share the same CRS (EPSG:4326) and ideally the same grid dimensions. The pipeline uses the DEM as the reference grid and reprojects the other layers to match.

### Step 4 — Set up Google Cloud SDK

If you haven't already authenticated:

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

Replace `YOUR_PROJECT_ID` with your GCP project ID.

---

## 3. Running the Pipeline Locally

You can run each script individually from the project root folder.

### Step 1 — Ingest data

This script checks if your input files exist. If the slope raster is missing, it derives one from the DEM using GDAL.

```bash
python scripts/ingest.py
```

Expected output:
```
2026-03-26 10:00:00  INFO      DEM already exists, skipping download.
2026-03-26 10:00:00  INFO      Slope already exists, skipping derivation.
2026-03-26 10:00:00  INFO      Rainfall already exists, skipping download.
2026-03-26 10:00:00  INFO      Ingestion complete ✓
```

### Step 2 — Process and generate flood risk map

This is the core script. It normalises the three input layers, applies the weighted formula, and writes two output files:

```bash
python scripts/flood_risk.py
```

Expected output:
```
2026-03-26 10:00:05  INFO      Loading DEM as reference grid …
2026-03-26 10:00:06  INFO      Aligning rainfall to DEM grid …
2026-03-26 10:00:07  INFO      Aligning slope to DEM grid …
2026-03-26 10:00:08  INFO      Normalising layers …
2026-03-26 10:00:09  INFO      Computing weighted flood risk score …
2026-03-26 10:00:09  INFO      Risk stats  min=0.0000  max=1.0000  mean=0.2496
2026-03-26 10:00:10  INFO      Writing GeoTIFF → output/flood_risk_map.tif
2026-03-26 10:00:12  INFO      Building Cloud-Optimised GeoTIFF …
2026-03-26 10:00:14  INFO      COG written → output/flood_risk_map.cog.tif
2026-03-26 10:00:14  INFO      Pipeline complete ✓
```

Two files will appear in the `output/` folder:
- `flood_risk_map.tif` — standard GeoTIFF
- `flood_risk_map.cog.tif` — Cloud-Optimised GeoTIFF (for TiTiler)

### Step 3 — Mask raster to Greater Accra boundary

This removes the rectangular bounding box that appears around the raster on the map.

```bash
python mask_raster.py
```

Expected output:
```
Masked raster saved!
```

This creates `flood_risk_masked.tif` in your project folder.

### Step 4 — Upload to GCS

```bash
gsutil cp flood_risk_masked.tif gs://accra-flood-risk/rasters/flood_risk_map.cog.tif
gsutil cp gadm41_GHA_2.json gs://accra-flood-risk/vectors/gadm41_GHA_2.json
```

### Adjusting the risk model weights

To change how much each layer contributes, open `scripts/flood_risk.py` and find this section near the top:

```python
WEIGHTS = {
    "dem":      0.40,
    "rainfall": 0.35,
    "slope":    0.25,
}
```

Change the numbers — they must always add up to **1.0**. For example, to give rainfall more influence:

```python
WEIGHTS = {
    "dem":      0.35,
    "rainfall": 0.45,
    "slope":    0.20,
}
```

Save the file and re-run `python scripts/flood_risk.py`.

---

## 4. Deploying to GCP

### 4.1  First-time GCP setup

Run these commands once in the Google Cloud SDK Shell:

```bash
# Enable required APIs
gcloud services enable run.googleapis.com containerregistry.googleapis.com secretmanager.googleapis.com storage.googleapis.com

# Create GCS bucket
gsutil mb -l us-central1 gs://accra-flood-risk

# Make bucket publicly readable
gsutil iam ch allUsers:objectViewer gs://accra-flood-risk

# Set CORS policy (allows the web map to fetch files from GCS)
echo '[{"origin":["*"],"method":["GET"],"responseHeader":["Content-Type"],"maxAgeSeconds":3600}]' > cors.json
gsutil cors set cors.json gs://accra-flood-risk

# Create service account for GitHub Actions
gcloud iam service-accounts create github-pipeline --display-name="GitHub Actions Pipeline"

# Grant permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:github-pipeline@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:github-pipeline@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.admin"
```

### 4.2  Set up Workload Identity Federation

This allows GitHub Actions to authenticate to GCP without storing any keys or secrets.

```bash
# Create identity pool
gcloud iam workload-identity-pools create github-pool \
  --location="global" \
  --display-name="GitHub Actions Pool"

# Add GitHub as a provider (replace YOUR_GITHUB_USERNAME)
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository_owner=='YOUR_GITHUB_USERNAME'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# Bind the service account to your GitHub repo
gcloud iam service-accounts add-iam-policy-binding \
  github-pipeline@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/YOUR_PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME"
```

> **Where to find your project number:**  
> Run `gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)"`

### 4.3  Deploy TiTiler tile server

TiTiler reads the COG from GCS and serves it as map tiles.

```bash
# Build the Docker image
docker build -f docker/Dockerfile -t gcr.io/YOUR_PROJECT_ID/titiler .

# Configure Docker to push to GCR
gcloud auth configure-docker

# Push the image
docker push gcr.io/YOUR_PROJECT_ID/titiler

# Deploy to Cloud Run
gcloud run deploy titiler \
  --image gcr.io/YOUR_PROJECT_ID/titiler \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 512Mi \
  --min-instances 0 \
  --project YOUR_PROJECT_ID
```

This gives you a URL like `https://titiler-XXXXXXXXX-uc.a.run.app`. Copy it.

### 4.4  Update the frontend config

Open `docs/index.html` and update these two lines with your actual URLs:

```javascript
const TITILER_URL = "https://titiler-XXXXXXXXX-uc.a.run.app";
const R2_PUBLIC   = "https://storage.googleapis.com/accra-flood-risk";
```

### 4.5  Enable GitHub Pages

1. Go to your repo on GitHub
2. Click **Settings → Pages**
3. Under **Source**, select branch `master`, folder `/docs`
4. Click **Save**

Your map will be live at `https://YOUR_GITHUB_USERNAME.github.io/YOUR_REPO_NAME` within 1-2 minutes.

### 4.6  Shut down Cloud Run (to avoid charges)

When you are not actively using the map:

```bash
gcloud run services delete titiler --region us-central1 --project YOUR_PROJECT_ID
```

To bring it back, just re-run the deploy command in section 4.3.

---

## 5. Infrastructure as Code (HCL)

HCL (HashiCorp Configuration Language) is used with Terraform to define and provision cloud infrastructure as code rather than clicking through the console. The configuration below provisions all GCP resources needed for this pipeline.

### Why use HCL/Terraform?

- **Reproducible** — rebuild the entire infrastructure from scratch with one command
- **Version controlled** — infrastructure changes are tracked in Git just like code
- **Documented** — the `.tf` files describe exactly what exists in your cloud account

### Install Terraform

Download from [terraform.io](https://developer.hashicorp.com/terraform/downloads) and add it to your PATH.

Verify:
```bash
terraform --version
```

### Project structure for Terraform

Create a `terraform/` folder in your project:

```
terraform/
├── main.tf          ← GCP resources
├── variables.tf     ← input variables
├── outputs.tf       ← output values
└── terraform.tfvars ← your actual values (DO NOT commit this file)
```

### `terraform/variables.tf`

```hcl
variable "project_id" {
  description = "Your GCP project ID"
  type        = string
}

variable "project_number" {
  description = "Your GCP project number"
  type        = string
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "us-central1"
}

variable "github_username" {
  description = "Your GitHub username"
  type        = string
}

variable "github_repo" {
  description = "Your GitHub repository name"
  type        = string
}

variable "bucket_name" {
  description = "Name for the GCS bucket"
  type        = string
  default     = "accra-flood-risk"
}

variable "titiler_image" {
  description = "Full GCR image path for TiTiler"
  type        = string
}
```

### `terraform/terraform.tfvars`

> ⚠️ Add `terraform.tfvars` to your `.gitignore` — never commit this file.

```hcl
project_id      = "project-a93d8eb8-d695-49f7-857"
project_number  = "244163528833"
region          = "us-central1"
github_username = "rache3"
github_repo     = "flood-risk-mapping-greater-accra"
bucket_name     = "accra-flood-risk"
titiler_image   = "gcr.io/project-a93d8eb8-d695-49f7-857/titiler:latest"
```

### `terraform/main.tf`

```hcl
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── Enable required APIs ──────────────────────────────────────────────────────

resource "google_project_service" "run_api" {
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "registry_api" {
  service            = "containerregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "storage_api" {
  service            = "storage.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iam_api" {
  service            = "iam.googleapis.com"
  disable_on_destroy = false
}

# ── GCS Bucket ───────────────────────────────────────────────────────────────

resource "google_storage_bucket" "flood_risk" {
  name          = var.bucket_name
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  cors {
    origin          = ["*"]
    method          = ["GET"]
    response_header = ["Content-Type"]
    max_age_seconds = 3600
  }
}

# Make bucket publicly readable
resource "google_storage_bucket_iam_member" "public_read" {
  bucket = google_storage_bucket.flood_risk.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# ── Service Account for GitHub Actions ───────────────────────────────────────

resource "google_service_account" "github_pipeline" {
  account_id   = "github-pipeline"
  display_name = "GitHub Actions Pipeline"
}

resource "google_project_iam_member" "run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.github_pipeline.email}"
}

resource "google_project_iam_member" "storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.github_pipeline.email}"
}

resource "google_project_iam_member" "secretmanager_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.github_pipeline.email}"
}

# ── Workload Identity Federation ─────────────────────────────────────────────

resource "google_iam_workload_identity_pool" "github_pool" {
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions Pool"
  description               = "Identity pool for GitHub Actions OIDC"
}

resource "google_iam_workload_identity_pool_provider" "github_provider" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_pool.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub Provider"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }

  attribute_condition = "assertion.repository_owner == '${var.github_username}'"
}

resource "google_service_account_iam_member" "workload_identity_binding" {
  service_account_id = google_service_account.github_pipeline.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool.name}/attribute.repository/${var.github_username}/${var.github_repo}"
}

# ── Cloud Run — TiTiler Tile Server ──────────────────────────────────────────

resource "google_cloud_run_v2_service" "titiler" {
  name     = "titiler"
  location = var.region

  depends_on = [google_project_service.run_api]

  template {
    containers {
      image = var.titiler_image

      resources {
        limits = {
          memory = "512Mi"
          cpu    = "1"
        }
      }

      env {
        name  = "GCS_BUCKET"
        value = var.bucket_name
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
  }
}

# Allow unauthenticated access to TiTiler
resource "google_cloud_run_service_iam_member" "titiler_public" {
  location = google_cloud_run_v2_service.titiler.location
  service  = google_cloud_run_v2_service.titiler.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
```

### `terraform/outputs.tf`

```hcl
output "bucket_name" {
  description = "GCS bucket name"
  value       = google_storage_bucket.flood_risk.name
}

output "bucket_url" {
  description = "Public GCS bucket URL"
  value       = "https://storage.googleapis.com/${google_storage_bucket.flood_risk.name}"
}

output "titiler_url" {
  description = "TiTiler Cloud Run service URL"
  value       = google_cloud_run_v2_service.titiler.uri
}

output "workload_identity_provider" {
  description = "Workload identity provider path for GitHub Actions"
  value       = google_iam_workload_identity_pool_provider.github_provider.name
}

output "service_account_email" {
  description = "GitHub Actions service account email"
  value       = google_service_account.github_pipeline.email
}
```

### Running Terraform

```bash
# Navigate to the terraform folder
cd terraform

# Initialise — downloads the Google provider plugin
terraform init

# Preview what will be created (no changes made yet)
terraform plan

# Apply — creates all resources in GCP
terraform apply
```

When `terraform apply` finishes it will print your TiTiler URL and bucket URL as outputs. Copy the TiTiler URL into `docs/index.html`.

To **destroy all resources** when done:

```bash
terraform destroy
```

> ⚠️ `terraform destroy` permanently deletes everything including your GCS bucket and all files in it. Only run this if you want to tear everything down completely.

---

## 6. Updating the Data

### Update the flood risk raster

When you have new DEM, rainfall, or slope data:

1. Replace the relevant `.tif` file in your project folder
2. Re-run the processing script:
   ```bash
   python scripts/flood_risk.py
   ```
3. Re-run the masking script:
   ```bash
   python mask_raster.py
   ```
4. Upload the new masked raster to GCS:
   ```bash
   gsutil cp flood_risk_masked.tif gs://accra-flood-risk/rasters/flood_risk_map.cog.tif
   ```
5. Hard refresh the map in your browser with `Ctrl + Shift + R`

### Update the district boundaries

If you have an updated GeoJSON:

```bash
gsutil cp gadm41_GHA_2.json gs://accra-flood-risk/vectors/gadm41_GHA_2.json
```

### Change the map colormap

Open `docs/index.html` and find:

```javascript
`&colormap_name=plasma`
```

Replace `plasma` with any of these options:
- `viridis` — blue to yellow (colourblind-friendly)
- `reds` — white to red
- `blues` — white to blue
- `rdylgn` — red to yellow to green
- `turbo` — full spectrum

Save and push to GitHub.

### Trigger the pipeline manually via GitHub Actions

1. Go to your repo on GitHub
2. Click **Actions**
3. Select **Flood Risk Pipeline**
4. Click **Run workflow → Run workflow**

This builds and deploys everything from scratch.

---

## 7. Troubleshooting

### Map tiles not showing (blank raster layer)

**Check 1** — Is TiTiler running?
```bash
curl https://titiler-XXXXXXXXX-uc.a.run.app/health
```
Should return `{"status":"ok"}`. If it fails, redeploy TiTiler (see section 4.3).

**Check 2** — Is the COG in GCS?
```bash
gsutil ls -l gs://accra-flood-risk/rasters/
```
Should show `flood_risk_map.cog.tif`. If not, re-upload it.

**Check 3** — Open browser DevTools (`F12`) → Console. Look for red errors.

---

### District boundaries not showing

This is a CORS issue. Fix it by running:

```bash
echo '[{"origin":["*"],"method":["GET"],"responseHeader":["Content-Type"],"maxAgeSeconds":3600}]' > cors.json
gsutil cors set cors.json gs://accra-flood-risk
```

Then hard refresh the map with `Ctrl + Shift + R`.

---

### TiTiler returning 404 errors

The COG URL may have extra characters appended. Open `docs/index.html` and make sure the COG URL is clean:

```javascript
const COG_URL = `${R2_PUBLIC}/rasters/flood_risk_map.cog.tif`;
```

No `?v=2` or other query parameters.

---

### `gcloud` not recognised in PowerShell

Use the **Google Cloud SDK Shell** from the Windows Start menu instead of PowerShell or the VSCode terminal. The SDK Shell has the correct PATH pre-configured.

---

### Docker build fails with `libexpat.so.1` error

Your Dockerfile is using `python:3.11-slim` which is missing system libraries. Change the first line of `docker/Dockerfile` to:

```dockerfile
FROM python:3.11
```

Then rebuild:
```bash
docker build -f docker/Dockerfile -t gcr.io/YOUR_PROJECT_ID/titiler .
```

---

### Raster bounding box showing as blue rectangle on map

The raster needs to be masked to the Greater Accra boundary. Run:

```bash
python mask_raster.py
```

Then upload the masked output:
```bash
gsutil cp flood_risk_masked.tif gs://accra-flood-risk/rasters/flood_risk_map.cog.tif
```

---

### Service account key creation blocked

Your GCP organisation policy may block service account key creation. Use Workload Identity Federation instead — see section 4.2. This is more secure than key-based authentication anyway.

---

### GitHub Actions workflow fails with authentication error

Make sure the `permissions` block is present in your workflow file:

```yaml
permissions:
  contents: read
  id-token: write
```

Both jobs (`build` and `process`) need this block.

---

### Old tiles still showing after uploading new raster

TiTiler caches tiles. Force a refresh by temporarily adding a version parameter to the COG URL in `docs/index.html`:

```javascript
const COG_URL = `${R2_PUBLIC}/rasters/flood_risk_map.cog.tif?v=3`;
```

Increment the number each time you update the raster. Then commit and push.

---

## Free Tier Reference

| Service | Free limit | Notes |
|---------|-----------|-------|
| Google Cloud Run | 2M requests/month | Scales to zero — no charge when idle |
| Google Cloud Storage | 5 GB storage | No egress fees within GCP |
| GitHub Actions | 2,000 min/month | Public repos only |
| GitHub Pages | Unlimited | Public repos only |
| Workload Identity | Always free | No limits |
| **Total monthly cost** | **$0.00** | Within free tier for this workload |

---

*Guide generated: March 2026 | Rachel Atia | github.com/rache3/flood-risk-mapping-greater-accra*
