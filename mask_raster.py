import rasterio
from rasterio.mask import mask
import json

with open("gadm41_GHA_2.json") as f:
    gj = json.load(f)

shapes = [f["geometry"] for f in gj["features"] 
          if f["properties"].get("NAME_1") == "GreaterAccra"]

with rasterio.open("flood_risk_map.tif") as src:
    out_image, out_transform = mask(src, shapes, crop=True, nodata=-9999)
    out_meta = src.meta.copy()
    out_meta.update({
        "driver": "GTiff",
        "height": out_image.shape[1],
        "width": out_image.shape[2],
        "transform": out_transform,
        "nodata": -9999
    })
    with rasterio.open("flood_risk_masked.tif", "w", **out_meta) as dst:
        dst.write(out_image)

print("Masked raster saved!")


