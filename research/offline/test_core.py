import copy
import json
from pathlib import Path

import pytest

from roadimpact.core import analyze, load_overpass, road_allowed, write_outputs

BBOX = (1.560, 30.245, 1.564, 30.249)


def scene():
    """Entirely synthetic OSM-shaped data, NOT a real map of Bunia."""
    ns = [
        (101, 1.562, 30.246, {}), (102, 1.562, 30.247, {}),
        (103, 1.562, 30.248, {}),
        (201, 1.56140, 30.247, {}), (202, 1.56185, 30.247, {}),
        (901, 1.56202, 30.24702, {"amenity": "clinic"}),
        (902, 1.56150, 30.24702, {"place": "village"}),
    ]
    elements = [dict(type="node", id=n, lat=la, lon=lo, tags=t) for n, la, lo, t in ns]
    elements += [
        dict(type="way", id=301, nodes=[101, 102, 103], tags={"highway": "residential"}),
        dict(type="way", id=302, nodes=[201, 202], tags={"highway": "residential"}),
    ]
    return {"version": 0.6, "generator": "SYNTHETIC FIXTURE", "elements": elements}


def test_detects_only_candidate_not_an_edit():
    report = analyze(scene(), BBOX, max_gap_m=25)
    candidates = report["candidates"]
    assert len(candidates) == 1
    found = candidates[0]
    assert found["endpoint_node"] == "202"
    assert found["scenario"] == "disconnected_components"
    assert found["gap_m"] == pytest.approx(16.67, rel=0.04)
    assert found["new_reachable_node_pairs"] == 6
    assert found["new_settlement_health_pairs"] == 0
    assert not report["metadata"]["poi_proxy_metrics_enabled"]
    assert found["review_status"] == "UNVERIFIED"
    assert report["metadata"]["analysis_type"].startswith("Undirected")


def test_bridge_grade_separation_not_flagged():
    data = scene()
    data["elements"][-2]["tags"]["bridge"] = "yes"
    assert analyze(data, BBOX)["candidates"] == []


def test_private_road_excluded():
    data = scene()
    data["elements"][-1]["tags"]["access"] = "private"
    assert analyze(data, BBOX)["candidates"] == []


def test_road_privacy_and_nonroad():
    assert not road_allowed({"highway": "footway"})
    assert not road_allowed({"highway": "residential", "motor_vehicle": "no"})
    assert not road_allowed({"highway": "service", "access": "delivery"})
    assert road_allowed({"highway": "secondary"})


def test_boundary_filter():
    # Place the tip near the bbox border: likely outside study area continuation.
    data = scene()
    tip = next(n for n in data["elements"] if n["type"] == "node" and n["id"] == 202)
    tip["lat"] = 1.56005
    assert all(c["endpoint_node"] != "202" for c in analyze(data, BBOX)["candidates"])


def test_wrong_direction_not_flagged():
    data = scene()
    # Tip physically near east-west road, but points south and away from it.
    start = next(n for n in data["elements"] if n["type"] == "node" and n["id"] == 201)
    start["lat"] = 1.5619
    assert all(c["endpoint_node"] != "202" for c in analyze(data, BBOX)["candidates"])


def test_topological_connection_already_exists():
    data = scene()
    road = next(w for w in data["elements"] if w["type"] == "way" and w["id"] == 302)
    road["nodes"].append(102)
    assert all(c["endpoint_node"] != "202" for c in analyze(data, BBOX)["candidates"])


def test_no_relevant_ways():
    data = scene()
    data["elements"] = [x for x in data["elements"] if x["type"] == "node"]
    assert not analyze(data, BBOX)["candidates"]


def test_outputs_review_only(tmp_path):
    report = analyze(scene(), BBOX)
    write_outputs(report, tmp_path)
    assert len(json.loads((tmp_path / "report.json").read_text())["candidates"]) == 1
    feat = json.loads((tmp_path / "candidates.geojson").read_text())["features"][0]
    assert feat["geometry"]["type"] == "LineString"
    assert feat["properties"]["review_status"] == "UNVERIFIED"
    assert "UNVERIFIED" in (tmp_path / "review.csv").read_text()


def test_input_guard():
    for bbox in ((1.56, 30.25, 1.55, 30.27), (1.5, 30.0, 1.8, 30.5)):
        with pytest.raises(ValueError):
            analyze(scene(), bbox)
    with pytest.raises(ValueError):
        analyze(scene(), BBOX, max_gap_m=100)


def test_barrier_at_endpoint_excluded():
    data = scene()
    tip = next(n for n in data["elements"] if n["type"] == "node" and n["id"] == 202)
    tip["tags"]["barrier"] = "gate"
    assert all(c["endpoint_node"] != "202" for c in analyze(data, BBOX)["candidates"])


def test_sensible_detour_only_if_existing_connection():
    data = scene()
    data["elements"][-1]["nodes"] = [201, 202]
    data["elements"].extend([
        {"type": "node", "id": 208, "lat": 1.56090, "lon": 30.2465},
        {"type": "node", "id": 209, "lat": 1.56120, "lon": 30.2460},
        {"type": "way", "id": 303, "nodes": [201, 208, 209, 101],
         "tags": {"highway": "unclassified"}},
    ])
    cands = analyze(data, BBOX)["candidates"]
    target = [c for c in cands if c["endpoint_node"] == "202"]
    assert len(target) == 1
    assert target[0]["scenario"] == "potential_detour"
    assert target[0]["detour_m"] > 250
    assert target[0]["new_reachable_node_pairs"] == 0
    assert target[0]["new_settlement_health_pairs"] == 0


def test_html_report_no_fake_verification(tmp_path):
    from roadimpact.viewer import write_viewer
    report = analyze(scene(), BBOX)
    write_viewer(report, tmp_path / "review.html")
    contents = (tmp_path / "review.html").read_text()
    assert "UNVERIFIED" in contents
    assert "OpenStreetMap contributors" in contents
    assert "https://www.openstreetmap.org/" in contents


def test_explicit_poi_proxy_opt_in():
    result = analyze(scene(), BBOX, include_poi_proxies=True)
    assert result["candidates"][0]["new_settlement_health_pairs"] == 1
    assert result["metadata"]["poi_proxy_metrics_enabled"]


def test_turning_circle_and_noexit_suppressed():
    data = scene()
    tip = next(n for n in data["elements"] if n["type"] == "node" and n["id"] == 202)
    tip["tags"]["highway"] = "turning_circle"
    assert analyze(data, BBOX)["candidates"] == []
    data = scene()
    tip = next(n for n in data["elements"] if n["type"] == "node" and n["id"] == 202)
    tip["tags"]["noexit"] = "yes"
    assert analyze(data, BBOX)["candidates"] == []


def test_driveway_and_parking_aisle_are_suppressed():
    for service in ("driveway", "parking_aisle"):
        assert not road_allowed({"highway": "service", "service": service})
    assert road_allowed({"highway": "service", "service": "alley"})


def test_target_barrier_suppressed():
    data = scene()
    target = next(n for n in data["elements"] if n["type"] == "node" and n["id"] == 102)
    target["tags"]["barrier"] = "gate"
    assert analyze(data, BBOX)["candidates"] == []


def test_review_ledger_reviewer_evidence_and_non_destructive(tmp_path):
    import csv
    from roadimpact.review import review_ledger
    report = analyze(scene(), BBOX)
    dest = tmp_path / "decisions.csv"
    summary = review_ledger(report, dest, initialize=True)
    assert summary["decision_counts"]["UNREVIEWED"] == 1
    with pytest.raises(FileExistsError):
        review_ledger(report, dest, initialize=True)
    with dest.open(newline="") as f:
        rows = list(csv.DictReader(f))
    rows[0]["decision"] = "CONFIRMED_MAPPING_ERROR"
    with dest.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
    with pytest.raises(ValueError, match="missing evidence_url"):
        review_ledger(report, dest)
    rows[0].update(evidence_url="https://www.openstreetmap.org/way/301", reviewer="local mapper",
                   reviewed_at="2026-10-15T14:00:00+02:00", notes="Reviewed approved imagery")
    with dest.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
    assert review_ledger(report, dest)["decision_counts"]["CONFIRMED_MAPPING_ERROR"] == 1


def test_full_cli_fetch_caches_exact_settings(tmp_path, monkeypatch):
    """End-to-end network stub exercises fetch, snapshot, JSON, map, reviewer ledger."""
    from roadimpact import __main__ as cli
    from roadimpact.review import review_ledger
    import sys

    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            from datetime import datetime, timezone
            payload = scene()
            payload["osm3s"] = {"timestamp_osm_base": datetime.now(timezone.utc).isoformat()}
            return payload

    def fake_post(url, data, **kwargs):
        calls.append((url, data["data"]))
        assert "node[\"amenity\"" not in data["data"]
        assert "node[\"place\"" not in data["data"]
        return Response()

    import requests
    monkeypatch.setattr(requests, "post", fake_post)
    args = ["roadimpact", "--fetch", "--bbox", *map(str, BBOX), "--output", str(tmp_path)]
    monkeypatch.setattr(sys, "argv", args)
    assert cli.main() == 0
    assert len(calls) == 1
    assert (tmp_path / "snapshot.manifest.json").exists()
    assert (tmp_path / "review.html").exists()
    assert review_ledger(json.loads((tmp_path / "report.json").read_text()),
                         tmp_path / "decisions.csv", initialize=True)["total_candidates"] == 1
    assert cli.main() == 0
    assert len(calls) == 1  # second run reuses snapshot, no new API call
    monkeypatch.setattr(sys, "argv", args + ["--refresh"])
    assert cli.main() == 0
    assert len(calls) == 2
    monkeypatch.setattr(sys, "argv", args + ["--include-poi-proxies"])
    with pytest.raises(SystemExit):
        cli.main()  # no silently reusing snapshot from a different query policy


def test_synthetic_warning_present_in_view(tmp_path):
    from roadimpact.viewer import write_viewer
    report = analyze(scene(), BBOX)
    assert report["metadata"]["synthetic_input"]
    write_viewer(report, tmp_path / "map.html")
    assert "SYNTHETIC FIXTURE" in (tmp_path / "map.html").read_text()


def test_untrusted_osm_ids_cannot_inject_html(tmp_path):
    from roadimpact.viewer import write_viewer
    data = scene()
    # Invalid fake way ID must not be included, and never written into the HTML.
    data["elements"][-1]["id"] = '<img src=x onerror=alert(1)>'
    result = analyze(data, BBOX)
    write_viewer(result, tmp_path / "safe.html")
    assert "<img src=x" not in (tmp_path / "safe.html").read_text()
    assert not result["candidates"]


def test_reciprocal_links_deduplicated():
    """Two dangling tips pointing at each other describe one physical gap."""
    data = {"generator": "SYNTHETIC FIXTURE", "elements": [
        {"type": "node", "id": 101, "lat": 1.562, "lon": 30.246},
        {"type": "node", "id": 102, "lat": 1.562, "lon": 30.247},
        {"type": "node", "id": 201, "lat": 1.562, "lon": 30.24718},
        {"type": "node", "id": 202, "lat": 1.562, "lon": 30.248},
        {"type": "way", "id": 301, "nodes": [101, 102], "tags": {"highway": "residential"}},
        {"type": "way", "id": 302, "nodes": [201, 202], "tags": {"highway": "residential"}},
    ]}
    result = analyze(data, BBOX)
    assert result["metadata"]["possible_matches"] == 2
    assert result["metadata"]["candidates"] == 1
