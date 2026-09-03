#!/usr/bin/env python3
"""true-colour sentinel-2 crops of bille town for the clearest dry-season scene each year.

writes docs/assets/rgb_<date>.png at 10 m and their corner coordinates into data/rgb.json.

usage: uv run --with rasterio,numpy,requests,pillow scripts/rgb.py
"""
import json, os, numpy as np, rasterio, requests
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds
from PIL import Image

R = os.path.join(os.path.dirname(__file__), "..")
W, S, E, N = 6.862, 4.560, 6.912, 4.595
out = {}
for year in (2024, 2025, 2026):
    r = requests.post("https://earth-search.aws.element84.com/v1/search", json={
        "collections": ["sentinel-2-l2a"], "bbox": [W, S, E, N], "datetime": f"{year - 1}-11-15T00:00:00Z/{year}-03-31T00:00:00Z",
        "query": {"eo:cloud_cover": {"lt": 60}, "grid:code": {"eq": "MGRS-32NKL"}}, "limit": 50}, timeout=60).json()
    best = None
    for it in sorted(r["features"], key=lambda f: f["properties"]["eo:cloud_cover"]):
        bands = {}
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
            for k in ("red", "green", "blue"):
                with rasterio.open(it["assets"][k]["href"]) as src:
                    b = transform_bounds("EPSG:4326", src.crs, W, S, E, N)
                    bands[k] = src.read(1, window=from_bounds(*b, src.transform), boundless=True, fill_value=0).astype(np.float32)
        cloud = (bands["blue"] / 10000 > 0.12).mean()  # bright pixels are cloud; skip partial tiles too
        if (bands["red"] > 0).mean() > 0.95 and (best is None or cloud < best[0]): best = (cloud, it, bands)
        if best and best[0] < 0.02: break
    if not best: continue
    cloud, it, bands = best
    rgb = np.dstack([np.clip(bands[k] / 10000 / 0.25, 0, 1) ** 0.7 for k in ("red", "green", "blue")])
    Image.fromarray((rgb * 255).astype(np.uint8)).save(f"{R}/docs/assets/rgb_{it['properties']['datetime'][:10]}.png")
    out[it["properties"]["datetime"][:10]] = {"bounds": [[W, N], [E, N], [E, S], [W, S]], "cloud": round(float(cloud), 3), "id": it["id"]}
    print(it["id"], round(float(cloud), 3))
json.dump(out, open(f"{R}/data/rgb.json", "w"))
