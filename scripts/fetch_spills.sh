#!/usr/bin/env bash
set -euo pipefail

# Fetch NOSDRA oil spill data and filter to Niger Delta region around Bille
OUTFILE="data/spills.json"

curl -sS --compressed \
  "https://oilspillmonitor.ng/api/spill-data.php?dataset=nosdra&format=json" \
  | jq '[.[] | select(
      .latitude != null and .latitude != "" and
      .longitude != null and .longitude != "" and
      (.latitude | tonumber? // 0) >= 4.0 and (.latitude | tonumber? // 0) <= 6.0 and
      (.longitude | tonumber? // 0) >= 6.0 and (.longitude | tonumber? // 0) <= 7.5
    ) | {
      lat: (.latitude | tonumber),
      lon: (.longitude | tonumber),
      date: .incidentdate,
      company: .company,
      cause: .cause,
      contaminant: .contaminant,
      quantity: .estimatedquantity,
      location: .sitelocationname,
      status: .status
    }]' > "$OUTFILE"

echo "Saved $(jq 'length' "$OUTFILE") spills to $OUTFILE"
