const TITILER_URL = "https://titiler-z2qegb4nha-uc.a.run.app";
const R2_PUBLIC = "https://storage.googleapis.com/accra-flood-risk";
const COG_URL = `${R2_PUBLIC}/rasters/flood_risk_map.cog.tif?v=4`;
const GEOJSON_URL = "./gadm41_GHA_accra.json";

const TILE_URL = `${TITILER_URL}/cog/tiles/{z}/{x}/{y}` +
  `?url=${encodeURIComponent(COG_URL)}` +
  "&colormap_name=plasma" +
  "&rescale=0,1";

const map = new maplibregl.Map({
  container: "map",
  style: {
    version: 8,
    sources: {
      osm: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: "© OpenStreetMap contributors",
      },
    },
    layers: [{ id: "osm", type: "raster", source: "osm", paint: { "raster-opacity": 0.35 } }],
  },
  center: [0.10, 5.78],
  zoom: 8,
  maxZoom: 14,
});

const aboutButton = document.getElementById("btn-about");
const aboutOverlay = document.getElementById("about-overlay");
const aboutCloseButton = document.getElementById("about-close");
const toggleRisk = document.getElementById("toggle-risk");
const toggleBoundaries = document.getElementById("toggle-boundaries");
const opacitySlider = document.getElementById("opacity");
const opacityValue = document.getElementById("opacity-val");

map.addControl(new maplibregl.NavigationControl(), "top-right");
map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");

map.on("load", () => {
  map.addSource("flood-risk", {
    type: "raster",
    tiles: [TILE_URL],
    tileSize: 256,
  });

  map.addLayer({
    id: "flood-risk-layer",
    type: "raster",
    source: "flood-risk",
    paint: { "raster-opacity": 0.8 },
  });

  map.addSource("boundaries", {
    type: "geojson",
    data: GEOJSON_URL,
  });

  map.addLayer({
    id: "boundaries-line",
    type: "line",
    source: "boundaries",
    paint: {
      "line-color": "#ffffff",
      "line-width": 1.5,
      "line-opacity": 0.9,
    },
  });

  map.addLayer({
    id: "boundaries-fill",
    type: "fill",
    source: "boundaries",
    paint: { "fill-color": "transparent" },
  });

  map.addLayer({
    id: "boundaries-labels",
    type: "symbol",
    source: "boundaries",
    minzoom: 8,
    layout: {
      "text-field": ["get", "NAME_2"],
      "text-size": 11,
      "text-anchor": "center",
      "text-max-width": 8,
    },
    paint: {
      "text-color": "#ffffff",
      "text-halo-color": "#000000",
      "text-halo-width": 1.5,
    },
  });

  map.on("click", "boundaries-fill", async (e) => {
    const props = e.features[0].properties;
    const name = props.NAME_2 || props.NAME_1 || "Unknown";

    const popup = new maplibregl.Popup({ offset: 8, maxWidth: "280px" })
      .setLngLat(e.lngLat)
      .setHTML(`
        <strong>${name}</strong><br/>
        <span style="color:#7a7870;font-size:11px">Loading statistics...</span>
      `)
      .addTo(map);

    try {
      const s = typeof props.stats === "string" ? JSON.parse(props.stats) : props.stats;

      if (!s) {
        throw new Error("No statistics available for this district");
      }

      const riskLevel = s.mean > 0.7 ? "High" : s.mean > 0.4 ? "Moderate" : "Low";
      const riskColor = s.mean > 0.7 ? "#fca5a5" : s.mean > 0.4 ? "#fcd34d" : "#86efac";
      const riskBg = s.mean > 0.7 ? "#7c1d1d" : s.mean > 0.4 ? "#78350f" : "#14532d";

      popup.setHTML(`
        <div style="font-family:sans-serif;min-width:220px">
          <div style="font-weight:600;font-size:13px;margin-bottom:6px">${name}</div>
          <div style="margin-bottom:8px">
            <span style="background:${riskBg};color:${riskColor};padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600">
              ${riskLevel} Risk
            </span>
          </div>
          <table style="width:100%;font-size:12px;border-collapse:collapse">
            <tr><td style="color:#7a7870;padding:2px 0">Mean risk score</td>
                <td style="text-align:right;font-weight:600">${s.mean.toFixed(3)}</td></tr>
            <tr><td style="color:#7a7870;padding:2px 0">Max risk score</td>
                <td style="text-align:right">${s.max.toFixed(3)}</td></tr>
            <tr><td style="color:#7a7870;padding:2px 0">Median</td>
                <td style="text-align:right">${s.median.toFixed(3)}</td></tr>
            <tr><td style="color:#7a7870;padding:2px 0">Std deviation</td>
                <td style="text-align:right">${s.std.toFixed(3)}</td></tr>
            <tr><td style="color:#7a7870;padding:2px 0">Valid pixels</td>
                <td style="text-align:right">${s.valid_percent.toFixed(1)}%</td></tr>
          </table>
          <div style="margin-top:8px">
            <div style="font-size:11px;color:#7a7870;margin-bottom:3px">Risk distribution</div>
            <div style="display:flex;align-items:flex-end;gap:1px;height:30px">
              ${s.histogram[0].map((count, i) => {
                const maxCount = Math.max(...s.histogram[0]);
                const height = Math.round((count / maxCount) * 30);
                const plasmaColors = ['#0d0887','#4b03a1','#7d03a8','#a82296','#cb4679','#e56b5d','#f89441','#fdc328','#f0f921'];
                const colorIdx = Math.round((i / (s.histogram[0].length - 1)) * (plasmaColors.length - 1));
                const color = plasmaColors[colorIdx];
                return `<div style="flex:1;height:${height}px;background:${color};border-radius:1px 1px 0 0"></div>`;
              }).join("")}
            </div>
            <div style="display:flex;justify-content:space-between;font-size:10px;color:#7a7870;margin-top:2px">
              <span>Low</span><span>High</span>
            </div>
          </div>
        </div>
      `);
    } catch (err) {
      popup.setHTML(`
        <strong>${name}</strong><br/>
        <span style="color:#7a7870;font-size:11px">Statistics not found for this district.</span>
      `);
    }
  });

  map.on("mouseenter", "boundaries-fill", () => {
    map.getCanvas().style.cursor = "pointer";
  });

  map.on("mouseleave", "boundaries-fill", () => {
    map.getCanvas().style.cursor = "";
  });
});

toggleRisk.addEventListener("change", (e) => {
  map.setLayoutProperty("flood-risk-layer", "visibility", e.target.checked ? "visible" : "none");
});

toggleBoundaries.addEventListener("change", (e) => {
  const visibility = e.target.checked ? "visible" : "none";
  map.setLayoutProperty("boundaries-line", "visibility", visibility);
  map.setLayoutProperty("boundaries-fill", "visibility", visibility);
  map.setLayoutProperty("boundaries-labels", "visibility", visibility);
});

opacitySlider.addEventListener("input", (e) => {
  const value = parseFloat(e.target.value);
  map.setPaintProperty("flood-risk-layer", "raster-opacity", value);
  opacityValue.textContent = `${Math.round(value * 100)}%`;
});

aboutButton.addEventListener("click", () => {
  aboutOverlay.classList.add("open");
});

aboutCloseButton.addEventListener("click", () => {
  aboutOverlay.classList.remove("open");
});

aboutOverlay.addEventListener("click", (event) => {
  if (event.target === aboutOverlay) {
    aboutOverlay.classList.remove("open");
  }
});

// --- Search Logic ---
let searchMarker = null;
const searchInput = document.getElementById("search-input");
const searchResults = document.getElementById("search-results");

function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

const handleSearch = debounce(async (query) => {
  if (query.length < 3) {
    searchResults.classList.remove("active");
    return;
  }

  try {
    const res = await fetch(`https://photon.komoot.io/api/?q=${encodeURIComponent(query)}&lat=5.6037&lon=-0.1870&bbox=-0.5,5.4,0.6,6.2&limit=5`);
    const data = await res.json();
    
    searchResults.innerHTML = "";
    if (data.features.length === 0) {
      searchResults.classList.remove("active");
      return;
    }

    data.features.forEach(f => {
      const item = document.createElement("div");
      item.className = "search-result-item";
      const name = f.properties.name || f.properties.street || "Unknown location";
      const sub = [f.properties.district, f.properties.city].filter(Boolean).join(", ") || "Ghana";
      
      item.innerHTML = `
        <span class="result-name">${name}</span>
        <span class="result-sub">${sub}</span>
      `;
      
      item.onclick = () => {
        const [lon, lat] = f.geometry.coordinates;
        map.flyTo({ center: [lon, lat], zoom: 13, essential: true });
        
        if (searchMarker) searchMarker.remove();
        searchMarker = new maplibregl.Marker({ color: "#f59e0b" })
          .setLngLat([lon, lat])
          .addTo(map);

        searchResults.classList.remove("active");
        searchInput.value = name;
      };
      searchResults.appendChild(item);
    });
    searchResults.classList.add("active");
  } catch (err) {
    console.error("Geocoding error:", err);
  }
}, 300);

searchInput.addEventListener("input", (e) => handleSearch(e.target.value));

document.addEventListener("click", (e) => {
  if (!document.getElementById("search-container").contains(e.target)) {
    searchResults.classList.remove("active");
  }
});

setTimeout(() => {
  fetch(`${TITILER_URL}/cog/info?url=${encodeURIComponent(COG_URL)}`).catch(() => {});
}, 1500);
