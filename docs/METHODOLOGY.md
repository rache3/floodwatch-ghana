# FloodWatch Ghana: Risk Methodology & Scorecard (v0.1)

FloodWatch Ghana v0.1 provides a **high-resolution structural baseline** of flood vulnerability across the Greater Accra Region. This model is optimized for long-term urban planning and infrastructure resilience.

## The Risk Model

The "Risk Score" is a weighted composite of five normalized geospatial datasets. Each pixel (30m resolution) is assigned a value from 0 (Low Risk) to 1 (High Risk).

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

## Greater Accra District Leaderboard (v0.1)

Based on the **Mean Risk Score** calculated across every 30m pixel within each district boundary.

| Rank | District | Mean Risk | Max Risk | Tier |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **Ablekuma West** | 0.8398 | 0.9928 | 🔴 High |
| 2 | **Weija Gbawe** | 0.8123 | 0.9957 | 🔴 High |
| 3 | **Ga Central** | 0.7258 | 0.9796 | 🔴 High |
| 4 | **Accra Metropolis** | 0.7170 | 0.8681 | 🔴 High |
| 5 | **Ga West** | 0.7063 | 0.9091 | 🔴 High |
| 6 | **Ga South** | 0.7035 | 0.9168 | 🔴 High |
| 7 | **Ablekuma North** | 0.6922 | 0.9129 | 🔴 High |
| 8 | **Ablekuma Central**| 0.6876 | 0.9673 | 🔴 High |
| 9 | **Ayawaso East** | 0.6741 | 0.8010 | 🔴 High |
| 10 | **Korle-Klottey** | 0.6708 | 0.8220 | 🔴 High |
| 11 | **La-Dade-Kotopon** | 0.6665 | 0.8261 | 🟡 Moderate |
| 12 | **Ayawaso North** | 0.6428 | 0.7923 | 🟡 Moderate |
| 13 | **Okaikwei North** | 0.6216 | 0.7901 | 🟡 Moderate |
| 14 | **Ayawaso Central** | 0.6024 | 0.7815 | 🟡 Moderate |
| 15 | **Krowor** | 0.5994 | 0.7714 | 🟡 Moderate |
| 16 | **Ledzokuku** | 0.5633 | 0.7841 | 🟡 Moderate |
| 17 | **Ayawaso West** | 0.5555 | 0.7763 | 🟡 Moderate |
| 18 | **Ga East** | 0.5529 | 0.8011 | 🟡 Moderate |
| 19 | **Ga North** | 0.5399 | 0.8156 | 🟡 Moderate |
| 20 | **Tema** | 0.5215 | 0.7691 | 🟡 Moderate |
| 21 | **Tema West** | 0.4887 | 0.7598 | 🟡 Moderate |
| 22 | **Ningo-Prampram** | 0.4646 | 1.0000 | 🟡 Moderate |
| 23 | **Ada East** | 0.4635 | 0.8083 | 🟡 Moderate |
| 24 | **La-Nkwantanang** | 0.4619 | 0.7043 | 🟡 Moderate |
| 25 | **Adenta** | 0.4610 | 0.7331 | 🟡 Moderate |
| 26 | **Kpone-Katamanso**| 0.4507 | 0.7605 | 🟡 Moderate |
| 27 | **Ada West** | 0.4376 | 0.7787 | 🟡 Moderate |
| 28 | **Shai Osudoku** | 0.4223 | 0.9061 | 🟡 Moderate |
| 29 | **Ashaiman** | 0.3654 | 0.6527 | 🟢 Low |

---

## Planning Implications

*   **High Risk (0.67 - 1.0)**: Districts in this category are structurally prone to flooding. New developments here must incorporate significant drainage infrastructure and flood-resistant building codes.
*   **Moderate Risk (0.33 - 0.67)**: Vulnerability is localized. Flash flooding is the primary threat during extreme rainfall events.
*   **Low Risk (0.0 - 0.33)**: Generally safe baseline, though localized poor drainage can still cause minor flooding.

---

## Search & Geocoding

To allow users to find specific neighborhoods (e.g., Kaneshie, Dansoman) that may not be district names, FloodWatch v0.1 uses the **Photon API** (built by Komoot on top of OpenStreetMap data). 

*   **Logic**: Searches are biased towards the Greater Accra coordinates (`5.6N, -0.18E`).
*   **Privacy**: No user data is stored; requests are sent directly to the open Photon endpoint.

*Greater Accra Region, Ghana · v0.1 · 2026*
