"""CLI for read-only humanitarian road topology hypotheses."""
import argparse
import json
import math
from pathlib import Path
import sys

from .core import analyze, write_outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Review-only road-gap prioritizer (never edits OSM)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", type=Path, help="Existing Overpass JSON snapshot")
    group.add_argument("--fetch", action="store_true", help="Make one bounded Overpass query, cache input")
    parser.add_argument("--bbox", nargs=4, type=float, required=True,
                        metavar=("SOUTH", "WEST", "NORTH", "EAST"))
    parser.add_argument("--output", type=Path, default=Path("outputs"))
    parser.add_argument("--max-gap", type=float, default=25.0)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--include-poi-proxies", action="store_true",
                        help="Opt in to sensitive, unvalidated settlement-health graph proxy counts")
    parser.add_argument("--max-source-age-days", type=float, default=14,
                        help="Fail when live Overpass snapshot exceeds this many days (default 14)")
    parser.add_argument("--overpass-url", default="https://overpass-api.de/api/interpreter")
    parser.add_argument("--refresh", action="store_true",
                        help="Re-fetch even when the output already contains a cached snapshot")
    args = parser.parse_args()
    bbox = tuple(args.bbox)
    south, west, north, east = bbox
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        parser.error("Invalid bounding box")
    if (north - south) * 111132 > 10_000 or (east - west) * 111320 * math.cos(math.radians((north + south) / 2)) > 10_000:
        parser.error("Study bbox exceeds 10km; split into smaller runs")
    if not 1 <= args.max_gap <= 60 or args.top < 1:
        parser.error("Use --max-gap between 1 and 60 and --top >= 1")
    if args.fetch:
        import requests
        args.output.mkdir(parents=True, exist_ok=True)
        cached = args.output / "snapshot.overpass.json"
        manifest_file = args.output / "snapshot.manifest.json"
        expected = {"bbox": list(bbox), "include_poi_proxies": args.include_poi_proxies,
                    "overpass_url": args.overpass_url}
        if cached.is_file() and not args.refresh:
            if not manifest_file.is_file():
                parser.error("Snapshot cache has no manifest: choose a new --output or use --refresh")
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            if {key: manifest.get(key) for key in expected} != expected:
                parser.error("Snapshot cache settings don't match bbox, POI policy or API URL; use --refresh or another --output")
            data = json.loads(cached.read_text(encoding="utf-8"))
            source = "cached Overpass API snapshot"
        else:
            data = fetch_snapshot(args, bbox, requests)
            cached.write_text(json.dumps(data), encoding="utf-8")
            from datetime import datetime, timezone
            manifest = {**expected, "created_at": datetime.now(timezone.utc).isoformat()}
            manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            source = "Overpass API"
    else:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        source = str(args.input)
    if args.fetch:
        from datetime import datetime, timezone
        stamp = data.get("osm3s", {}).get("timestamp_osm_base")
        if not stamp:
            raise RuntimeError("Overpass snapshot lacks the OSM replication timestamp")
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(
            stamp.replace("Z", "+00:00"))).total_seconds() / 86400
        if not -1 <= age <= args.max_source_age_days:
            raise RuntimeError(f"OSM data is stale: {age:.2f} days old; "
                               "check a fresher Overpass instance or explicitly raise --max-source-age-days")
    report = analyze(data, bbox, max_gap_m=args.max_gap, top_n=args.top,
                     include_poi_proxies=args.include_poi_proxies)
    report["metadata"]["input_source"] = source
    write_outputs(report, args.output)
    from .viewer import write_viewer
    write_viewer(report, args.output / "review.html")
    print(json.dumps(report["metadata"], indent=2))
    return 0


def fetch_snapshot(args, bbox, requests):
    s, w, n, e = bbox
    # Include 150m around bbox to reduce edge-of-data false positives.
    grow_lat = 150.0 / 111132.0
    grow_lon = 150.0 / (111320.0 * math.cos(math.radians((s + n) / 2)))
    s, w, n, e = s - grow_lat, w - grow_lon, n + grow_lat, e + grow_lon
    query = ('[out:json][timeout:60];('
             f'way["highway"]({s:.7f},{w:.7f},{n:.7f},{e:.7f});')
    # By default do not request health facilities or settlement points in
    # politically sensitive areas. Optional POI proxies require explicit opt-in.
    if args.include_poi_proxies:
        query += (f'node["amenity"~"^(hospital|clinic|doctors|health_post)$"]({s:.7f},{w:.7f},{n:.7f},{e:.7f});'
                  f'node["place"~"^(city|town|village|hamlet)$"]({s:.7f},{w:.7f},{n:.7f},{e:.7f});')
    query += ');(._;>;);out body;'
    response = requests.post(args.overpass_url, data={"data": query}, timeout=95,
                             headers={"User-Agent": "humanitarian-road-impact/0.2 (research; no edits)"})
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("elements"), list):
        raise RuntimeError(f"Unexpected Overpass response: {str(data)[:300]}")
    return data

if __name__ == "__main__":
    sys.exit(main())
