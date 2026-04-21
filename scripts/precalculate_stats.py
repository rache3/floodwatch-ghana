import json
import numpy as np
import rasterio
from rasterio.mask import mask
import os

geojson_path = "data/gadm41_GHA_accra.json"
raster_path = "output/flood_risk_masked.tif"
output_path = "docs/gadm41_GHA_accra.json"

if not os.path.exists("docs"):
    os.makedirs("docs")

with open(geojson_path) as f:
    gj = json.load(f)

with rasterio.open(raster_path) as src:
    for feature in gj["features"]:
        geometry = feature["geometry"]
        name = feature["properties"].get("NAME_2", "Unknown")
        try:
            # Mask the raster with the polygon
            out_image, out_transform = mask(src, [geometry], crop=True, nodata=np.nan)
            data = out_image[0]
            # Filter out NaNs and nodata
            valid_data = data[~np.isnan(data)]
            valid_data = valid_data[valid_data >= 0] # Assuming risk is 0-1
            
            if valid_data.size > 0:
                stats = {
                    "mean": float(np.mean(valid_data)),
                    "max": float(np.max(valid_data)),
                    "median": float(np.median(valid_data)),
                    "std": float(np.std(valid_data)),
                    "valid_percent": float(valid_data.size / data.size * 100)
                }
                
                # Calculate histogram (10 bins)
                counts, bin_edges = np.histogram(valid_data, bins=10, range=(0, 1))
                stats["histogram"] = [counts.tolist(), bin_edges.tolist()]
                
                feature["properties"]["stats"] = stats
                print(f"Processed {name}: mean={stats['mean']:.3f}")
            else:
                feature["properties"]["stats"] = None
                print(f"No valid data for {name}")
                
        except Exception as e:
            print(f"Error processing {name}: {e}")
            feature["properties"]["stats"] = None

with open(output_path, "w") as f:
    json.dump(gj, f)

print(f"\nUpdated GeoJSON with stats saved to {output_path}")
