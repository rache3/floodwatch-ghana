# Contributing to FloodWatch Ghana

Thank you for your interest in contributing to FloodWatch Ghana. This document explains how to set up your environment, understand the codebase, and submit contributions.

FloodWatch Ghana is an open source flood risk intelligence pipeline for Greater Accra, Ghana, built by GeoBuilders Africa. We welcome contributions from developers, data scientists, and geospatial engineers.

---

## Table of contents

- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Environment setup](#environment-setup)
- [Running the pipeline](#running-the-pipeline)
- [Code standards](#code-standards)
- [Branching and pull requests](#branching-and-pull-requests)
- [CI checks](#ci-checks)
- [Areas where we need help](#areas-where-we-need-help)
- [Contact](#contact)

---

## Project structure

```
floodwatch-ghana/
├── scripts/               # Pipeline scripts — one file per data layer
│   ├── ingest.py          # Orchestrator — runs all ingest scripts in order
│   ├── ingest_dem.py      # SRTM 30m elevation data
│   ├── ingest_slope.py    # Slope derived from DEM
│   ├── ingest_rainfall.py # GPM IMERG / CHIRPS precipitation
│   ├── ingest_landcover.py# ESA WorldCover land cover
│   ├── ingest_waterbodies.py # OSM water features
│   ├── ingest_aod.py      # Aerosol optical depth quality flagging
│   ├── flood_risk.py      # Risk model — combines all layers into COG
│   ├── upload_gcs.py      # Uploads outputs to Google Cloud Storage
│   └── validate_flood_risk.py # Qualitative validation against flood events
├── docs/
│   └── index.html         # MapLibre GL JS web map (GitHub Pages)
├── terraform/             # GCP infrastructure as code
├── data/                  # Downloaded input data (gitignored)
├── output/                # Generated rasters and reports (gitignored)
├── .env.example           # Configuration template
└── requirements.txt       # Python dependencies
```

Each ingest script is independent — you can run any one of them individually without running the full pipeline.

---

## Getting started

**Prerequisites:**
- Python 3.11+
- Git
- A free NASA Earthdata account — [register here](https://urs.earthdata.nasa.gov/users/new)
- Google Cloud SDK (optional — only needed for GCS upload)

**Clone the repo:**
```bash
git clone https://github.com/rache3/floodwatch-ghana.git
cd floodwatch-ghana
```

---

## Environment setup

**Create a virtual environment:**
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

**Install dependencies:**
```bash
pip install -r requirements.txt
pip install h5py  # Required for GPM IMERG HDF5 parsing
```

**Configure environment variables:**
```bash
cp .env.example .env
```

Open `.env` and fill in your values. The minimum required to run the pipeline locally:

```env
BBOX_WEST=-0.50
BBOX_EAST=0.50
BBOX_SOUTH=5.35
BBOX_NORTH=5.95
OPENTOPO_API_KEY=demoapikeyot2022
EARTHDATA_USER=your_nasa_earthdata_username
EARTHDATA_PASS=your_nasa_earthdata_password
```

**Note:** Never commit your `.env` file. It is listed in `.gitignore`.

---

## Running the pipeline

**Run a single layer (recommended for development):**
```bash
python scripts/ingest_dem.py
python scripts/ingest_rainfall.py
python scripts/ingest_landcover.py
python scripts/ingest_waterbodies.py
python scripts/ingest_slope.py
```

**Run all layers in order:**
```bash
python scripts/ingest.py
```

**Generate the risk map:**
```bash
python scripts/flood_risk.py
```

**Run validation:**
```bash
python scripts/validate_flood_risk.py
```

**Upload to GCS (requires GCP credentials):**
```bash
python scripts/upload_gcs.py
```

---

## Code standards

We use **ruff** for linting. All contributions must pass the linter before merging.

**Install ruff:**
```bash
pip install ruff
```

**Run the linter:**
```bash
ruff check scripts/
```

**Auto-fix fixable issues:**
```bash
ruff check scripts/ --fix
```

**Key style rules:**
- No unused imports
- No unused variables
- No f-strings without placeholders
- Every script must have the PROJ conflict fix at the top:

```python
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)
```

This prevents conflicts with PostgreSQL/PostGIS PROJ installations on Windows.

---

## Branching and pull requests

**Branch naming:**
```
feature/description     # New features
fix/description         # Bug fixes
data/description        # Data layer additions or changes
docs/description        # Documentation only
```

**Workflow:**
1. Fork the repository
2. Create a branch from `main`
3. Make your changes
4. Run `ruff check scripts/` — fix any errors
5. Open a pull request against `main`
6. Describe what you changed and why

**Pull request checklist:**
- [ ] Ruff lint passes with zero errors
- [ ] New scripts follow the existing structure (logging, PROJ fix, dotenv)
- [ ] `.env.example` updated if new environment variables were added
- [ ] `requirements.txt` updated if new packages were added

---

## CI checks

Every push and pull request runs three automated checks:

**1. Lint** — ruff checks all Python scripts in `scripts/`  
**2. Validate structure** — confirms all required scripts and files exist  
**3. Syntax check** — parses all scripts to catch syntax errors without running the pipeline

All three must pass before a PR can be merged.

---

## Areas where we need help

**Frontend:**
- Improve the MapLibre GL JS web map UX
- Add mobile-responsive design
- District comparison feature

**Data science:**
- Improve model weights using AHP or PCA
- Add SCS Curve Number runoff estimation
- Integrate soil permeability data from ISRIC SoilGrids

**Backend:**
- Build a REST API for property-level risk scoring
- Add real-time GPM IMERG Late Run integration
- Improve Cloud Run job efficiency

**Validation:**
- Sentinel-1 SAR flood extent validation via Google Earth Engine
- Compare against NADMO historical flood records
- ROC curve and confusion matrix analysis

**Expansion:**
- Adapt the pipeline for other Ghana regions
- Test on other West African cities

---

## Contact

**Rachel Atia** — Founder, GeoBuilders Africa  
Email: rachelatia@geobuildersafrica.com  
GitHub: [@rache3](https://github.com/rache3)  
Website: [geobuildersafrica.com](https://geobuildersafrica.com)

For questions about the pipeline, open a GitHub issue. For partnership or collaboration enquiries, email directly.

---

*GeoBuilders Africa · Greater Accra, Ghana · 2025–2026*
