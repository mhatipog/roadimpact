# RoadImpact offline comparison (research only)

One-off, offline data acquisition for the proposed RoadImpact vs endpoint-distance comparison.

Source: pinned Geofabrik DRC OSM PBF 2026-10-12, not the changeable latest link. Reuse the extracted Bunia OSM XML offline for all experiments. Do not use OSM editing API as a bulk provider.

- Input bounding box: longitude 30.19–30.31, latitude 1.50–1.63, intentionally larger than the comparison core.
- OSM Osmium 'complete_ways' keeps nodes referenced by partially included ways; connections outside even this buffer are not guaranteed.
- Output: bounded PBF, bounded OSM XML, SHA-256 and original MD5 verification, source manifest.
- No imagery downloads, medical site data, or automated OSM edits.
- These extracts contain only OpenStreetMap data © OpenStreetMap contributors, ODbL 1.0; source https://download.geofabrik.de/africa/congo-democratic-republic.html.
- Designed for a single run. GHA hosted minutes and artifact storage may count against account free-tier quotas.

The evaluator source and test suite are distributed separately in the RoadImpact experiment package; this workflow provides a reproducible *real* local dataset for that evaluator, not validated defects.

Use the private workflow **RoadImpact pinned offline Bunia extract** and download its artifact.