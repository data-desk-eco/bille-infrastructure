#!/usr/bin/env python3
"""fetch mapstand wellheads with attributes for the bille area as geojson.

the wms kml encoder returns the stored attributes in the placemark description.

usage: uv run scripts/fetch_wells.py
"""
import json, re, os, xml.etree.ElementTree as ET
from urllib.request import Request, urlopen
from urllib.parse import urlencode

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "wells.geojson")
NS = {"k": "http://www.opengis.net/kml/2.2"}
q = {"SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap", "FORMAT": "application/vnd.google-earth.kml+xml",
     "LAYERS": "mps_mapping_wellheader", "SRS": "EPSG:4326", "BBOX": "6.55,4.35,7.2,4.85", "WIDTH": "256", "HEIGHT": "256",
     "format_options": "extendedData:true", "apikey": "63abb313-a3ce-4dd8-b4de-d093f897018a"}
r = Request("https://app.mapstand.com/geoserver/ows/mps?" + urlencode(q), headers={"Referer": "https://app.mapstand.com/"})
kml = ET.parse(urlopen(r, timeout=120))
keep = ["well_name", "well_status", "well_result", "well_type", "completion_date", "total_depth", "optr_name", "accumulation_accumulation_name", "current_lc_area_phase_nm", "uwi"]
feats = []
for pm in kml.findall(".//k:Placemark", NS):
    d = pm.find("k:description", NS)
    p = {m.group(1).strip(): m.group(2).strip() for m in re.finditer(r'class="atr-name">(.*?)</span>.*?class="atr-value">(.*?)</span>', d.text or "", re.S)} if d is not None else {}
    lon, lat = map(float, pm.find(".//k:coordinates", NS).text.strip().split(",")[:2])
    feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": {k: p.get(k) or None for k in keep}})
json.dump({"type": "FeatureCollection", "features": feats}, open(OUT, "w"))
print(len(feats), "wells")
