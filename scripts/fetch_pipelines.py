#!/usr/bin/env python3
"""Fetch Nigerian pipeline vector data from MapStand WMS via KML tiles.

MapStand's GeoServer doesn't expose pipelines via WFS, and KML output
only works with EPSG:3857 for this layer. We tile Nigeria in Web Mercator,
request KML from WMS GetMap, parse line geometries, and deduplicate into
GeoJSON (coordinates are returned as WGS84 lon/lat in the KML).

Usage: uv run scripts/fetch_pipelines.py
"""

import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.join(PROJECT_ROOT, "data", "pipelines.geojson")

WMS_BASE = "https://app.mapstand.com/geoserver/ows/mps"
LAYER = "mps_mapping_pipeline"
HEADERS = {"Referer": "https://app.mapstand.com/"}
APIKEY = "63abb313-a3ce-4dd8-b4de-d093f897018a"

# Nigeria bbox in EPSG:4326 (lon_min, lat_min, lon_max, lat_max)
BBOX_4326 = (2.5, 3.0, 15.0, 14.5)
TILE_SIZE_M = 120_000  # ~120km tiles in meters
WORKERS = 8


def lonlat_to_3857(lon, lat):
    x = lon * 20037508.34 / 180.0
    lat_rad = lat * math.pi / 180.0
    y = math.log(math.tan(math.pi / 4 + lat_rad / 2)) * 20037508.34 / math.pi
    return x, y


def generate_tiles_3857(lon_min, lat_min, lon_max, lat_max, step_m):
    """Generate tiles in EPSG:3857 covering a WGS84 bbox."""
    x_min, y_min = lonlat_to_3857(lon_min, lat_min)
    x_max, y_max = lonlat_to_3857(lon_max, lat_max)
    tiles = []
    y = y_min
    while y < y_max:
        x = x_min
        while x < x_max:
            tiles.append((x, y, min(x + step_m, x_max), min(y + step_m, y_max)))
            x += step_m
        y += step_m
    return tiles


def parse_props(desc_html):
    """Extract key/value pairs from KML description HTML."""
    props = {}
    for m in re.finditer(
        r'class="atr-name">(.*?)</span>.*?class="atr-value">(.*?)</span>',
        desc_html, re.DOTALL,
    ):
        props[m.group(1).strip()] = m.group(2).strip()
    return props


def parse_coords(text):
    """Parse KML coordinate string to [[lon, lat], ...] list."""
    coords = []
    for triplet in text.strip().split():
        parts = triplet.split(",")
        coords.append([float(parts[0]), float(parts[1])])
    return coords


def parse_geometry(placemark):
    """Extract GeoJSON geometry from a KML Placemark (lines or polygons)."""
    mg = placemark.find(".//kml:MultiGeometry", KML_NS)
    if mg is not None:
        lines = []
        polys = []
        for ls in mg.findall(".//kml:LineString/kml:coordinates", KML_NS):
            lines.append(parse_coords(ls.text))
        for poly in mg.findall("kml:Polygon", KML_NS):
            outer = poly.find(
                ".//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", KML_NS
            )
            if outer is not None:
                polys.append([parse_coords(outer.text)])
        if lines:
            if len(lines) == 1:
                return {"type": "LineString", "coordinates": lines[0]}
            return {"type": "MultiLineString", "coordinates": lines}
        if polys:
            if len(polys) == 1:
                return {"type": "Polygon", "coordinates": polys[0]}
            return {"type": "MultiPolygon", "coordinates": polys}
        return None

    ls = placemark.find(".//kml:LineString/kml:coordinates", KML_NS)
    if ls is not None:
        return {"type": "LineString", "coordinates": parse_coords(ls.text)}

    poly = placemark.find(".//kml:Polygon", KML_NS)
    if poly is not None:
        outer = poly.find(
            ".//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", KML_NS
        )
        if outer is not None:
            return {"type": "Polygon", "coordinates": [parse_coords(outer.text)]}

    return None


def fetch_tile(x_min, y_min, x_max, y_max):
    """Fetch a single EPSG:3857 tile as KML and return parsed features."""
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "FORMAT": "application/vnd.google-earth.kml+xml",
        "LAYERS": LAYER,
        "SRS": "EPSG:3857",
        "BBOX": f"{x_min},{y_min},{x_max},{y_max}",
        "WIDTH": "256",
        "HEIGHT": "256",
        "apikey": APIKEY,
    }
    url = WMS_BASE + "?" + urlencode(params)
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=60) as resp:
            kml = ET.parse(resp)
    except (URLError, HTTPError, ET.ParseError) as e:
        return [], str(e)

    features = []
    for pm in kml.findall(".//kml:Placemark", KML_NS):
        fid = pm.get("id", "")
        desc = pm.find("kml:description", KML_NS)
        props = parse_props(desc.text) if desc is not None and desc.text else {}
        geom = parse_geometry(pm)
        if geom:
            features.append({
                "type": "Feature",
                "id": fid,
                "geometry": geom,
                "properties": props,
            })
    return features, None


def simplify_props(props):
    """Keep useful pipeline properties."""
    skip = {"attribution"}
    return {k: v for k, v in props.items() if v and k not in skip}


def main():
    tiles = generate_tiles_3857(*BBOX_4326, TILE_SIZE_M)
    print(f"Fetching {LAYER} across Nigeria: {len(tiles)} tiles")

    all_features = {}
    errors = 0
    done = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(fetch_tile, *t): t for t in tiles}
        for future in as_completed(futures):
            done += 1
            features, err = future.result()
            if err:
                errors += 1
            for feat in features:
                fid = feat["id"]
                if fid not in all_features:
                    all_features[fid] = feat
            if done % 10 == 0 or done == len(tiles):
                sys.stdout.write(
                    f"\r  {done}/{len(tiles)} tiles, "
                    f"{len(all_features)} unique features"
                )
                sys.stdout.flush()

    print()
    if errors:
        print(f"  {errors} tile errors")

    output_features = []
    for fid, feat in all_features.items():
        output_features.append({
            "type": "Feature",
            "id": fid,
            "geometry": feat["geometry"],
            "properties": simplify_props(feat.get("properties", {})),
        })

    geojson = {"type": "FeatureCollection", "features": output_features}
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(geojson, f)

    size_kb = os.path.getsize(OUTPUT) / 1024
    print(f"Wrote {len(output_features)} features to {OUTPUT} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
