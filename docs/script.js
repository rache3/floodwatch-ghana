const TITILER_URL = "https://titiler-z2qegb4nha-uc.a.run.app";
const R2_PUBLIC = "https://storage.googleapis.com/accra-flood-risk";
const COG_URL = `${R2_PUBLIC}/rasters/flood_risk_map.cog.tif?v=4`;
const GEOJSON_URL = `${R2_PUBLIC}/vectors/gadm41_GHA_accra.json`;

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
    id: "flood-risk-mask",
    type: "fill",
    source: "boundaries",
    paint: { "fill-color": "#1a1d26", "fill-opacity": 1 },
    filter: ["!=", ["get", "NAME_1"], "GreaterAccra"],
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
      const bbox = e.features[0].bbox || turf.bbox(e.features[0]);
      const res = await fetch(
        `${TITILER_URL}/cog/statistics?url=${encodeURIComponent(COG_URL)}` +
        `&bbox=${bbox[0]},${bbox[1]},${bbox[2]},${bbox[3]}`
      );
      const data = await res.json();
      const s = data.b1;

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
        <span style="color:#7a7870;font-size:11px">Statistics temporarily unavailable. Click district again to retry.</span>
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

setTimeout(() => {
  fetch(`${TITILER_URL}/cog/info?url=${encodeURIComponent(COG_URL)}`).catch(() => {});
}, 1500);
