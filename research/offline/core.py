"""Read-only OSM road-gap candidate analysis.

Outputs hypotheses for mapper review, NEVER changes OSM. Measures topological
counterfactuals, not proven vehicle travel or real-world medical outcomes.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import networkx as nx
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

DRIVABLE = frozenset({
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "living_street", "service", "track", "road",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
})
BLOCKED_ACCESS = frozenset({"no", "private", "agricultural", "forestry", "delivery"})
POI_PLACE = frozenset({"city", "town", "village", "hamlet"})
POI_HEALTH = frozenset({"hospital", "clinic", "doctors", "health_post"})


def road_allowed(tags: dict[str, str]) -> bool:
    if tags.get("highway") not in DRIVABLE:
        return False
    # These service road types are commonly private parking or driveway stubs.
    if tags.get("highway") == "service" and tags.get("service") in {
        "driveway", "parking_aisle", "drive-through", "emergency_access"
    }:
        return False
    if tags.get("noexit") == "yes" or tags.get("construction"):
        return False
    for tag in ("access", "motor_vehicle", "motorcar", "vehicle"):
        if tags.get(tag, "").strip().lower() in BLOCKED_ACCESS:
            return False
    if tags.get("area") == "yes" or tags.get("impassable") == "yes":
        return False
    return True


def ground_level(tags: dict[str, str]) -> bool:
    # Never flag a connection involving elevated, underground or special layers.
    if tags.get("bridge", "no") not in ("no", ""):
        return False
    if tags.get("tunnel", "no") not in ("no", ""):
        return False
    if tags.get("covered", "no") not in ("no", ""):
        return False
    try:
        return int(tags.get("layer", "0")) == 0
    except ValueError:
        return False


def valid_osm_id(value: Any) -> bool:
    """Reject fabricated non-numeric identifiers before embedding into HTML."""
    return type(value) is int and 0 < value < 2**63


def load_overpass(data: dict[str, Any]) -> tuple[dict[str, tuple[float, float]], list[dict], list[dict]]:
    """Parse Overpass JSON 'out body; >; out skel qt;' output."""
    nodes: dict[str, tuple[float, float]] = {}
    ways: list[dict] = []
    pois: list[dict] = []
    for item in data.get("elements", []):
        kind = item.get("type")
        if kind == "node" and valid_osm_id(item.get("id")) and "lat" in item and "lon" in item:
            nid = str(item["id"])
            nodes[nid] = (float(item["lat"]), float(item["lon"]))
            tags = item.get("tags", {})
            if tags.get("amenity") in POI_HEALTH:
                pois.append({"id": nid, "kind": "health", "lat": nodes[nid][0], "lon": nodes[nid][1]})
            if tags.get("place") in POI_PLACE:
                pois.append({"id": nid, "kind": "settlement", "lat": nodes[nid][0], "lon": nodes[nid][1]})
        if kind == "way" and valid_osm_id(item.get("id")) and isinstance(item.get("nodes"), list):
            if not all(valid_osm_id(n) for n in item["nodes"]):
                continue
            ways.append({"id": str(item["id"]), "nodes": [str(n) for n in item["nodes"]], "tags": item.get("tags", {})})
    return nodes, ways, pois


def xy(lat: float, lon: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    # Local planar metric approximation intended for <= 10 km across near Bunia.
    return ((lon - origin_lon) * 111320.0 * math.cos(math.radians(origin_lat)),
            (lat - origin_lat) * 111132.0)


def latlon(x: float, y: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    return (origin_lat + y / 111132.0,
            origin_lon + x / (111320.0 * math.cos(math.radians(origin_lat))))


@dataclass(frozen=True)
class Segment:
    way_id: str
    a: str
    b: str
    geom: LineString
    tags: dict


@dataclass
class Candidate:
    rank: int
    candidate_id: str
    lat: float
    lon: float
    target_lat: float
    target_lon: float
    endpoint_node: str
    endpoint_way: str
    target_way: str
    gap_m: float
    scenario: str
    component_nodes_a: int
    component_nodes_b: int
    new_reachable_node_pairs: int
    new_settlement_health_pairs: int
    detour_m: float | None
    score: float
    review_status: str = "UNVERIFIED"
    review_note: str = "Requires imagery/local mapper validation; do not auto-edit."


def analyze(data: dict, bbox: tuple[float, float, float, float],
            max_gap_m: float = 25.0, boundary_margin_m: float = 70.0,
            top_n: int = 20, include_poi_proxies: bool = False) -> dict[str, Any]:
    """Detect near misses at dangling road endpoints; never equate proximity with truth.

    bbox: (south, west, north, east). Input must cover bbox *plus an external
    buffer*, since otherwise cut edges may look like missing road connections.
    """
    if not (1 <= max_gap_m <= 60):
        raise ValueError("max_gap_m must be between 1 and 60 meters")
    if boundary_margin_m < max_gap_m:
        raise ValueError("boundary_margin_m must be >= max_gap_m")
    south, west, north, east = bbox
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise ValueError("invalid bounding box")
    if (north - south) * 111132 > 10_000 or (east - west) * 111320 * math.cos(math.radians((north + south) / 2)) > 10_000:
        raise ValueError("Study region exceeds 10km: use smaller regional runs")
    origin_lat, origin_lon = (south + north) / 2, (west + east) / 2
    nodes, ways, pois = load_overpass(data)
    # Health/settlement linkage is opt-in: location-sensitive, unverified proxy.
    if not include_poi_proxies:
        pois = []
    graph = nx.Graph()
    restricted_nodes = {str(x["id"]) for x in data.get("elements", []) if x.get("type") == "node"
                        and (x.get("tags", {}).get("barrier") in {
                            "gate", "bollard", "block", "lift_gate", "swing_gate", "border_control",
                            "fence", "jersey_barrier", "yes", "cycle_barrier"
                        } or x.get("tags", {}).get("noexit") == "yes"
                        or x.get("tags", {}).get("highway") in {"turning_circle", "turning_loop"})}
    segments: list[Segment] = []
    endpoint_way_ids: dict[str, set[str]] = defaultdict(set)
    used_ways = 0
    nonground_incident_nodes: set[str] = set()
    for way in ways:
        tags = way["tags"]
        if not road_allowed(tags):
            continue
        used_ways += 1
        ids = way["nodes"]
        for nid in (ids[:1] + ids[-1:]):
            endpoint_way_ids[nid].add(way["id"])
        for a, b in zip(ids, ids[1:]):
            if a not in nodes or b not in nodes or a == b:
                continue
            p = xy(*nodes[a], origin_lat, origin_lon)
            q = xy(*nodes[b], origin_lat, origin_lon)
            length = math.dist(p, q)
            if not (0.1 <= length <= 3000):
                continue
            if graph.has_edge(a, b):
                if length < graph[a][b]["weight"]:
                    graph[a][b]["weight"] = length
            else:
                graph.add_edge(a, b, weight=length)
            segments.append(Segment(way["id"], a, b, LineString([p, q]), tags))
            if not ground_level(tags):
                nonground_incident_nodes.update((a, b))
    if not segments:
        return {"metadata": {"analyzed_at": datetime.now(timezone.utc).isoformat(), "road_ways": 0, "nodes": 0, "candidates": 0, "bbox": bbox, "warning": "No road geometries found: check input coverage and query."}, "candidates": []}

    component_of: dict[str, int] = {}
    size_of: dict[int, int] = {}
    for comp_id, component in enumerate(nx.connected_components(graph)):
        size_of[comp_id] = len(component)
        for nid in component:
            component_of[nid] = comp_id

    poi_components: dict[int, dict[str, int]] = defaultdict(lambda: {"health": 0, "settlement": 0})
    if pois:
        roadids = sorted(graph.nodes())
        roadpoints = [Point(xy(*nodes[n], origin_lat, origin_lon)) for n in roadids]
        pt_tree = STRtree(roadpoints)
        for poi in pois:
            p = Point(xy(poi["lat"], poi["lon"], origin_lat, origin_lon))
            nearest = pt_tree.nearest(p)
            if nearest is not None and roadpoints[int(nearest)].distance(p) <= 150:
                component_id = component_of[roadids[int(nearest)]]
                poi_components[component_id][poi["kind"]] += 1

    tree = STRtree([s.geom for s in segments])
    west_x, south_y = xy(south, west, origin_lat, origin_lon)
    east_x, north_y = xy(north, east, origin_lat, origin_lon)
    proposals = []
    inspected = 0
    for nid in sorted(graph.nodes()):
        if graph.degree(nid) != 1 or nid in restricted_nodes:
            continue
        pos = Point(xy(*nodes[nid], origin_lat, origin_lon))
        if (pos.x - west_x < boundary_margin_m or east_x - pos.x < boundary_margin_m or
                pos.y - south_y < boundary_margin_m or north_y - pos.y < boundary_margin_m):
            continue
        if nid in nonground_incident_nodes:
            continue
        neighbor = next(iter(graph.neighbors(nid)))
        back = Point(xy(*nodes[neighbor], origin_lat, origin_lon))
        forward = (pos.x - back.x, pos.y - back.y)
        fmag = math.hypot(*forward)
        if fmag < 0.1:
            continue
        inspected += 1
        # A disconnected tip close to another road is only a hypothesis.
        for idx in tree.query(pos.buffer(max_gap_m)):
            segment = segments[int(idx)]
            if nid in (segment.a, segment.b):
                continue
            if segment.a in restricted_nodes or segment.b in restricted_nodes:
                continue
            if not ground_level(segment.tags):
                continue
            target_geom = segment.geom
            projection = target_geom.interpolate(target_geom.project(pos))
            gap = pos.distance(projection)
            if not (0.5 <= gap <= max_gap_m):
                continue
            direction = (projection.x - pos.x, projection.y - pos.y)
            cos = (direction[0] * forward[0] + direction[1] * forward[1]) / (gap * fmag)
            if cos < 0.5:
                continue
            a_comp, b_comp = component_of[nid], component_of[segment.a]
            if component_of[segment.b] != b_comp:
                continue  # consistency guard
            detour = None
            new_pairs = 0
            new_sh = 0
            if a_comp != b_comp:
                new_pairs = size_of[a_comp] * size_of[b_comp]
                pa, pb = poi_components[a_comp], poi_components[b_comp]
                new_sh = pa["settlement"] * pb["health"] + pb["settlement"] * pa["health"]
                scenario = "disconnected_components"
                score = (math.log1p(new_pairs) * 3 + math.log1p(new_sh) * 4 - gap / 20)
            else:
                # Compare current graph path against hypothetical direct link.
                # The projected spot isn't an existing node; approximate via segment endpoints.
                dist_a = nx.shortest_path_length(graph, nid, segment.a, weight="weight")
                dist_b = nx.shortest_path_length(graph, nid, segment.b, weight="weight")
                detour = min(dist_a + projection.distance(Point(target_geom.coords[0])),
                             dist_b + projection.distance(Point(target_geom.coords[-1])))
                if detour < max(250, 7 * gap):
                    continue
                scenario = "potential_detour"
                score = math.log1p(detour - gap) * 2 - gap / 20
            lat2, lon2 = latlon(projection.x, projection.y, origin_lat, origin_lon)
            proposal = Candidate(
                rank=0, candidate_id=f"tip-{nid}-way-{segment.way_id}",
                lat=round(nodes[nid][0], 7), lon=round(nodes[nid][1], 7),
                target_lat=round(lat2, 7), target_lon=round(lon2, 7),
                endpoint_node=nid, endpoint_way=next(iter(sorted(endpoint_way_ids.get(nid, []))), "unknown"),
                target_way=segment.way_id, gap_m=round(gap, 2), scenario=scenario,
                component_nodes_a=size_of[a_comp], component_nodes_b=size_of[b_comp],
                new_reachable_node_pairs=new_pairs, new_settlement_health_pairs=new_sh,
                detour_m=round(detour, 2) if detour is not None else None,
                score=round(score, 3))
            proposals.append(proposal)

    # Keep only strongest target for each tip, for actionable manual review.
    best: dict[str, Candidate] = {}
    for candidate in proposals:
        key = candidate.endpoint_node
        existing = best.get(key)
        if existing is None or (candidate.score, -candidate.gap_m) > (existing.score, -existing.gap_m):
            best[key] = candidate
    # A pair of dangling road tips may identify the same missing segment twice.
    # Deduplicate physical links independently of which tip suggested the join.
    physical: dict[tuple, Candidate] = {}
    for c in best.values():
        corners = tuple(sorted(((round(c.lat, 6), round(c.lon, 6)),
                                (round(c.target_lat, 6), round(c.target_lon, 6)))))
        existing = physical.get(corners)
        if existing is None or (c.score, -c.gap_m) > (existing.score, -existing.gap_m):
            physical[corners] = c
    ranked = sorted(physical.values(), key=lambda c: (-c.score, c.gap_m, c.candidate_id))[:top_n]
    for ix, cand in enumerate(ranked, 1):
        cand.rank = ix
    return {
        "metadata": {
            "input_sha256": hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "dataset_attribution": "© OpenStreetMap contributors, ODbL 1.0",
            "synthetic_input": str(data.get("generator", "")).upper().startswith("SYNTHETIC"),
            "osm_timestamp": data.get("osm3s", {}).get("timestamp_osm_base"),
            "bbox": bbox, "road_ways": used_ways, "road_nodes": graph.number_of_nodes(),
            "road_segments": len(segments), "components": len(size_of),
            "dangling_endpoints_reviewed": inspected, "possible_matches": len(proposals),
            "candidates": len(ranked), "max_gap_m": max_gap_m,
            "poi_proxy_metrics_enabled": bool(include_poi_proxies),
            "analysis_type": "Undirected structural connectivity, not navigable routing",
            "warning": "All candidates UNVERIFIED; no road connections or medical accessibility claims",
        },
        "candidates": [asdict(c) for c in ranked],
    }


def write_outputs(report: dict, output_dir: str | Path) -> None:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    cs = report["candidates"]
    fields = list(Candidate.__dataclass_fields__)
    with (folder / "review.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(cs)
    features = []
    for c in cs:
        features.append({"type": "Feature", "geometry": {
            "type": "LineString", "coordinates": [[c["lon"], c["lat"]], [c["target_lon"], c["target_lat"]]]},
            "properties": {k: v for k, v in c.items() if k not in ("lat", "lon", "target_lat", "target_lon")}})
    geojson = {"type": "FeatureCollection", "name": "Unverified road-gap candidates", "features": features}
    (folder / "candidates.geojson").write_text(json.dumps(geojson, indent=2), encoding="utf-8")
