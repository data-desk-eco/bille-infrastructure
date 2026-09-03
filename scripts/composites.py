#!/usr/bin/env python3
"""seasonal composites, change overlays and per-site series from the sentinel caches.

reads data/s2/cache and data/s1/cache (written by s2.py and s1.py), then writes:
  data/s2/summary.parquet      per-scene mean ndvi and water reflectance near the seeps and in a control ring
  data/s1/wells.parquet        per-scene peak vv backscatter at each well and facility
  data/overlays.json           bounds for the png overlays in docs/assets
  docs/assets/s2_dndvi.png     dry-season ndvi change, 2025-26 against 2023-25
  docs/assets/s1_dvv.png       vv backscatter change, oct 2025-mar 2026 against the same months a year earlier
  data/s2/hotspots.geojson     clusters of ndvi loss
  data/s1/targets.geojson      clusters of new bright radar targets

usage: uv run --with rasterio,numpy,pillow,scipy,pyarrow scripts/composites.py
"""
import glob, json, os, numpy as np, pyarrow as pa, pyarrow.parquet as pq
from PIL import Image
from scipy import ndimage
from rasterio.warp import transform

R = os.path.join(os.path.dirname(__file__), "..")
S1 = json.load(open(f"{R}/data/s1/scenes.json"))
S2 = json.load(open(f"{R}/data/s2/scenes.json")) if os.path.exists(f"{R}/data/s2/scenes.json") else {**S1, "scenes": []}
W, S, E, N = S2["bounds"]; RES = 20
SEEP = (6.8855, 4.5770)  # centre of the surveyed seep cluster (numbere et al., may 2026)

def grid(bounds):
    w, s, e, n = bounds; h, wd = int(round((n - s) / RES)), int(round((e - w) / RES))
    xs, ys = np.meshgrid(w + (np.arange(wd) + .5) * RES, n - (np.arange(h) + .5) * RES)
    return xs, ys

def to_utm(lon, lat):
    x, y = transform("EPSG:4326", S2["crs"], [lon], [lat]); return x[0], y[0]

def to_ll(x, y):
    lon, lat = transform(S2["crs"], "EPSG:4326", [x], [y]); return lon[0], lat[0]

def png(arr, path, lo, hi, neg="#d62728", pos="#1f77b4", floor=0.0):
    """diverging overlay: negative values in neg, positive in pos, transparent inside ±floor."""
    c = {k: np.array([int(v[i:i + 2], 16) for i in (1, 3, 5)]) for k, v in [("n", neg), ("p", pos)]}
    v = np.clip(np.abs(arr) / hi, 0, 1); a = np.where(np.isfinite(arr) & (np.abs(arr) > floor), (0.3 + 0.7 * v) * 255, 0)
    rgb = np.where(arr[..., None] < 0, c["n"], c["p"]) * np.ones_like(v)[..., None]
    Image.fromarray(np.dstack([rgb, a]).astype(np.uint8), "RGBA").save(path)

def clusters(mask, values, minpx, xs, ys):
    lab, n = ndimage.label(mask); feats = []
    for i in range(1, n + 1):
        m = lab == i
        if m.sum() < minpx: continue
        lon, lat = to_ll(xs[m].mean(), ys[m].mean())
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                      "properties": {"pixels": int(m.sum()), "ha": round(m.sum() * RES * RES / 1e4, 2), "mean": round(float(values[m].mean()), 3),
                                     "km_from_seeps": round(float(np.hypot(xs[m].mean() - sx, ys[m].mean() - sy)) / 1000, 2)}})
    return {"type": "FeatureCollection", "features": sorted(feats, key=lambda f: f["properties"]["km_from_seeps"])}

xs, ys = grid(S2["bounds"]); sx, sy = to_utm(*SEEP); dist = np.hypot(xs - sx, ys - sy)
overlays = {}

# sentinel-2: per-scene summary and dry-season ndvi composites
rows, seasons = [], {}
for sc in S2["scenes"]:
    d = np.load(f"{R}/data/s2/cache/{sc['id']}.npz"); ok = d["ok"]; water = d["water"] & ok
    veg = ok & ~water & (d["ndvi"].astype(np.float32) > 0.2)
    if ok.mean() < 0.05: continue
    ndvi, red = d["ndvi"].astype(np.float32), d["red"].astype(np.float32)
    near, ctrl = dist < 1500, (dist > 4000) & (dist < 6000)
    rows.append({"date": sc["date"], "cloud": sc["cloud"], "valid": sc["valid"],
                 "ndvi_near": float(np.nanmean(ndvi[veg & near])) if (veg & near).sum() > 200 else None,
                 "ndvi_control": float(np.nanmean(ndvi[veg & ctrl])) if (veg & ctrl).sum() > 200 else None,
                 "red_water_near": float(np.nanmean(red[water & near])) if (water & near).sum() > 200 else None,
                 "red_water_control": float(np.nanmean(red[water & ctrl])) if (water & ctrl).sum() > 200 else None})
    y, m = int(sc["date"][:4]), int(sc["date"][5:7])
    if m >= 11 or m <= 4:
        key = f"{y}-{y + 1}" if m >= 11 else f"{y - 1}-{y}"
        seasons.setdefault(key, []).append(np.where(ok, ndvi, np.nan))
pq.write_table(pa.Table.from_pylist(rows or [{"date": None, "cloud": None, "valid": None, "ndvi_near": None, "ndvi_control": None, "red_water_near": None, "red_water_control": None}]), f"{R}/data/s2/summary.parquet")
if not rows: json.dump({"type": "FeatureCollection", "features": []}, open(f"{R}/data/s2/hotspots.geojson", "w"))
med = {k: np.nanmedian(np.stack(v), 0) for k, v in seasons.items() if len(v) >= 3}
cnt = {k: np.isfinite(np.stack(v)).sum(0) for k, v in seasons.items() if len(v) >= 3}
print({k: len(v) for k, v in seasons.items()})
if "2025-2026" in med:
    prior = [k for k in ("2023-2024", "2024-2025") if k in med]
    base = np.nanmean(np.stack([med[k] for k in prior]), 0)
    dndvi = np.where((cnt["2025-2026"] >= 2) & (base > 0.3), med["2025-2026"] - base, np.nan)
    dndvi -= np.nanmedian(dndvi)  # centre on the scene so haze and phenology between seasons drop out
    png(dndvi, f"{R}/docs/assets/s2_dndvi.png", 0, 0.4, floor=0.1)
    ll = [to_ll(W, N), to_ll(E, N), to_ll(E, S), to_ll(W, S)]; overlays["s2_dndvi"] = {"bounds": ll, "seasons": prior + ["2025-2026"]}
    json.dump(clusters(dndvi < -0.15, dndvi, 6, xs, ys), open(f"{R}/data/s2/hotspots.geojson", "w"))

# sentinel-1: per-well peak backscatter and a change overlay
wells = json.load(open(f"{R}/data/wells.geojson"))["features"]
infra = [(f["properties"]["well_name"], *f["geometry"]["coordinates"]) for f in wells]
infra += [("Krakama flow station", 6.9001, 4.5556), ("Awoba flow station", 6.8200, 4.5345)]
sites = [(n, *to_utm(lo, la)) for n, lo, la in infra if W < to_utm(lo, la)[0] < E and S < to_utm(lo, la)[1] < N]
rows, before, after = [], {}, {}
for sc in S1["scenes"]:
    vv = np.load(f"{R}/data/s1/cache/{sc['id']}.npz")["vv"].astype(np.float32)
    if np.isfinite(vv).mean() < 0.5: continue
    for n, x, y in sites:
        j, i = int((x - W) / RES), int((N - y) / RES)
        win = vv[max(i - 2, 0):i + 3, max(j - 2, 0):j + 3]; bg = vv[max(i - 12, 0):i + 13, max(j - 12, 0):j + 13]
        if np.isfinite(win).sum() < 10: continue
        rows.append({"site": n, "date": sc["date"], "orbit": sc["orbit"], "vv_max": float(np.nanmax(win)), "vv_bg": float(np.nanmedian(bg))})
    d = sc["date"]
    if "2025-10-01" <= d <= "2026-03-31": after.setdefault(sc["orbit"], []).append(vv)
    if "2024-10-01" <= d <= "2025-03-31": before.setdefault(sc["orbit"], []).append(vv)
pq.write_table(pa.Table.from_pylist(rows), f"{R}/data/s1/wells.parquet")
orbits = [o for o in after if o in before and len(after[o]) >= 3 and len(before[o]) >= 3]
dvv = np.nanmean(np.stack([np.nanmedian(np.stack(after[o]), 0) - np.nanmedian(np.stack(before[o]), 0) for o in orbits]), 0)
png(dvv, f"{R}/docs/assets/s1_dvv.png", 0, 8, neg="#1f77b4", pos="#ff7f0e", floor=3)
overlays["s1_dvv"] = {"bounds": [to_ll(W, N), to_ll(E, N), to_ll(E, S), to_ll(W, S)], "orbits": orbits}
json.dump(clusters(dvv > 5, dvv, 4, xs, ys), open(f"{R}/data/s1/targets.geojson", "w"))
json.dump(overlays, open(f"{R}/data/overlays.json", "w"))
