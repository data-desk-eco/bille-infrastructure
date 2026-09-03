#!/usr/bin/env python3
"""sentinel-2 l2a windows around bille from the public aws cog archive.

for every scene since october 2022 with tile cloud below 85%, read a 20 m
window over the bille / krakama / awoba area, mask with the scene
classification layer, and cache ndvi, ndwi, red, swir16, swir22 per scene.
then write seasonal (nov-apr) median composites and a per-scene summary.

usage: uv run --with rasterio,numpy,requests scripts/s2.py
"""
import json, os, sys, numpy as np, rasterio, requests
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds

W, S, E, N = 6.80, 4.50, 6.96, 4.64
CRS = "EPSG:32632"
RES = 20
ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "s2")
CACHE = os.path.join(ROOT, "cache")
os.makedirs(CACHE, exist_ok=True)
BANDS = ["red", "green", "nir", "swir16", "swir22", "scl"]

def search():
    url = "https://earth-search.aws.element84.com/v1/search"
    body = {"collections": ["sentinel-2-l2a"], "bbox": [W, S, E, N],
            "datetime": "2022-10-01T00:00:00Z/2026-12-31T00:00:00Z",
            "query": {"eo:cloud_cover": {"lt": 85}, "grid:code": {"eq": "MGRS-32NKL"}}, "limit": 200}
    items = []
    while url:
        r = requests.post(url, json=body, timeout=60).json()
        items += r["features"]
        nxt = [l for l in r.get("links", []) if l["rel"] == "next"]
        url, body = (nxt[0]["href"], nxt[0].get("body", body)) if nxt else (None, None)
    return sorted(items, key=lambda i: i["properties"]["datetime"])

def bounds():
    return transform_bounds("EPSG:4326", CRS, W, S, E, N)

def read(item):
    out = os.path.join(CACHE, item["id"] + ".npz")
    if os.path.exists(out):
        return out
    b = bounds()
    arrs = {}
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.jp2"):
        for k in BANDS:
            href = item["assets"][k]["href"]
            with rasterio.open(href) as src:
                bb = transform_bounds(CRS, src.crs, *b) if str(src.crs) != CRS else b
                win = from_bounds(*bb, src.transform)
                h = int(round((b[3] - b[1]) / RES)); w = int(round((b[2] - b[0]) / RES))
                arrs[k] = src.read(1, window=win, out_shape=(h, w), resampling=rasterio.enums.Resampling.nearest if k == "scl" else rasterio.enums.Resampling.average, boundless=True, fill_value=0)
    scl = arrs["scl"]
    ok = np.isin(scl, [4, 5, 6, 7]) & (arrs["red"] > 0)
    f = lambda k: arrs[k].astype(np.float32) / 10000  # earth-search cogs already carry the boa offset
    red, green, nir, s16, s22 = (f(k) for k in ["red", "green", "nir", "swir16", "swir22"])
    ndvi = np.clip((nir - red) / np.maximum(nir + red, 1e-3), -1, 1)
    ndwi = np.clip((green - nir) / np.maximum(green + nir, 1e-3), -1, 1)
    np.savez_compressed(out, ok=ok, water=scl == 6, ndvi=ndvi.astype(np.float16), ndwi=ndwi.astype(np.float16),
                        red=red.astype(np.float16), nir=nir.astype(np.float16), s16=s16.astype(np.float16), s22=s22.astype(np.float16))
    return out

def main():
    items = search()
    if os.environ.get("S2_SHARD"):  # "i/n": worker i of n takes every nth scene first; each writes the same complete scenes.json at the end
        i, n = map(int, os.environ["S2_SHARD"].split("/")); items = [it for j, it in enumerate(items) if j % n == i] + [it for j, it in enumerate(items) if j % n != i]
    print(len(items), "scenes", file=sys.stderr)
    meta = []
    for i, it in enumerate(items):
        try:
            p = read(it)
        except Exception as e:
            print("fail", it["id"], e, file=sys.stderr); continue
        d = np.load(p)
        meta.append({"id": it["id"], "date": it["properties"]["datetime"][:10],
                     "cloud": it["properties"]["eo:cloud_cover"], "valid": float(d["ok"].mean())})
        print(i, it["id"], f'{d["ok"].mean():.2f}', file=sys.stderr)
    meta.sort(key=lambda m: m["date"])
    json.dump({"bounds": bounds(), "crs": CRS, "res": RES, "scenes": meta}, open(os.path.join(ROOT, "scenes.json"), "w"))

if __name__ == "__main__":
    main()
