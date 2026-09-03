#!/usr/bin/env python3
"""sentinel-1 rtc backscatter windows around bille from microsoft planetary computer.

reads a 20 m vv/vh window for every scene since 2024-01-01, caches it, and
writes a per-scene summary. a swamp rig, barge or new structure at a well
shows as a bright, persistent vv target; the notebook reads the cache.

usage: uv run --with rasterio,numpy,requests scripts/s1.py
"""
import json, os, sys, numpy as np, rasterio, requests
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds

W, S, E, N = 6.80, 4.50, 6.96, 4.64
CRS, RES = "EPSG:32632", 20
ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "s1")
CACHE = os.path.join(ROOT, "cache")
os.makedirs(CACHE, exist_ok=True)
PC = "https://planetarycomputer.microsoft.com/api"

def search():
    url, body = PC + "/stac/v1/search", {"collections": ["sentinel-1-rtc"], "bbox": [W, S, E, N],
        "datetime": "2024-01-01T00:00:00Z/2026-12-31T00:00:00Z", "limit": 250}
    items = []
    while url:
        r = requests.post(url, json=body, timeout=60).json()
        items += r["features"]
        nxt = [l for l in r.get("links", []) if l["rel"] == "next"]
        url, body = (nxt[0]["href"], nxt[0].get("body", body)) if nxt else (None, None)
    return sorted(items, key=lambda i: i["properties"]["datetime"])

def token():
    return requests.get(PC + "/sas/v1/token/sentinel-1-rtc", timeout=30).json()["token"]

def read(item, tok, b):
    out = os.path.join(CACHE, item["id"] + ".npz")
    if os.path.exists(out):
        return out
    arrs = {}
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        for k in ["vv", "vh"]:
            with rasterio.open(item["assets"][k]["href"] + "?" + tok) as src:
                bb = transform_bounds(CRS, src.crs, *b) if str(src.crs) != CRS else b
                h = int(round((b[3] - b[1]) / RES)); w = int(round((b[2] - b[0]) / RES))
                a = src.read(1, window=from_bounds(*bb, src.transform), out_shape=(h, w),
                             resampling=rasterio.enums.Resampling.average, boundless=True, fill_value=0)
                arrs[k] = (10 * np.log10(np.where(a > 0, a, np.nan))).astype(np.float16)
    np.savez_compressed(out, **arrs)
    return out

def main():
    items = search(); b = transform_bounds("EPSG:4326", CRS, W, S, E, N)
    print(len(items), "scenes", file=sys.stderr)
    tok, meta = token(), []
    for i, it in enumerate(items):
        try:
            p = read(it, tok, b)
        except Exception as e:
            if "403" in str(e) or "401" in str(e):
                tok = token(); p = read(it, tok, b)
            else:
                print("fail", it["id"], e, file=sys.stderr); continue
        d = np.load(p)
        meta.append({"id": it["id"], "date": it["properties"]["datetime"][:10], "orbit": it["properties"]["sat:relative_orbit"],
                     "pass": it["properties"]["sat:orbit_state"], "valid": float(np.isfinite(d["vv"]).mean())})
        print(i, it["id"], meta[-1]["valid"], file=sys.stderr)
    json.dump({"bounds": list(b), "crs": CRS, "res": RES, "scenes": meta}, open(os.path.join(ROOT, "scenes.json"), "w"))

if __name__ == "__main__":
    main()
