import json
import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.features import geometry_mask

with open("gadm41_GHA_2.json") as f:
    gj = json.load(f)

shapes = [f["geometry"] for f in gj["features"] 
          if f["properties"].get("NAME_1") == "GreaterAccra"]

with rasterio.open("output/flood_risk_map.tif") as src:
    out_image, out_transform = mask(
        src, shapes, 
        crop=True, 
        nodata=np.nan,
        all_touched=False,
        invert=False
    )
    out_meta = src.meta.copy()
    out_meta.update({
        "driver": "GTiff",
        "height": out_image.shape[1],
        "width": out_image.shape[2],
        "transform": out_transform,
        "nodata": np.nan,
        "dtype": "float32"
    })
    with rasterio.open("output/flood_risk_masked.tif", "w", **out_meta) as dst:
        dst.write(out_image)

print("Masked raster saved!")
