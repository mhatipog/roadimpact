"""RoadImpact 0.4 | conservative evidence triage. Read-only; NO OSM write code.

Metadata-only. Imagery pixels are not distributed. Reproducible, *not*
evidence of an actual passable road or authority to edit OSM.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


def time(s):
    if not s:
        return None
    try:
        if len(s) == 8 and s.isdigit():
            return datetime.strptime(s, "%Y%m%d").replace(tzinfo=timezone.utc)
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except ValueError:
        return None


def usable_tile(t):
    """Reject flat/placeholder tiles; does NOT assess physical road visibility."""
    return (isinstance(t.get("bytes"), int) and t["bytes"] >= 5000
            and isinstance(t.get("pixel_std"), (int, float))
            and 8 <= t["pixel_std"] < 150 and not t.get("error"))


def mode(tags, name):
    key = {"motorcar": ("motorcar", "motor_vehicle", "vehicle", "access"),
           "emergency": ("emergency", "motorcar", "motor_vehicle", "vehicle", "access"),
           "foot": ("foot", "access")}[name]
    for k in key:
        v = tags.get(k, "")
        if v in ("private", "no", "agricultural", "forestry"):
            return "unknown" if name == "emergency" and k != "emergency" else "deny"
        if v in ("yes", "designated"):
            return "allow" if k == name else "unknown"
    if name == "motorcar" and tags.get("highway") in ("footway", "steps", "cycleway"):
        return "deny"
    return "unknown"


def assess(c, as_of):
    if not isinstance(c.get("case_id"), str) or not c["case_id"]:
        raise ValueError("case_id required")
    o, i = c["osm"], c["imagery"]
    reasons = []
    geometry = (o.get("endpoint_exists") is True
                and o.get("target_exists") is True
                and o.get("shared_node") is False
                and o.get("geometrical_gap") is True)
    if not geometry:
        reasons.append("TOPOLOGY_NOT_REVALIDATED")
    check = time(o.get("checked_at"))
    if not check or (as_of-check).total_seconds() < -86400 or (as_of-check).days > 14:
        reasons.append("OSM_SOURCE_STALE_OR_MISSING")
    capture = time(i.get("acquired_at"))
    if not capture:
        reasons.append("IMAGE_DATE_UNKNOWN")
    elif any(capture < t for x in (o.get("endpoint_last_edit"), o.get("target_last_edit"))
                 if (t := time(x))):
        reasons.append("IMAGERY_PREDATES_OSM_EDIT")
    if i.get("license_for_osm_review") is not True:
        reasons.append("IMAGERY_PERMISSION_NOT_CONFIRMED")
    if i.get("locally_registered") is not True or i.get("control_points", 0) < 3:
        reasons.append("LOCAL_ALIGNMENT_UNVERIFIED")
    quality = {k: sum(usable_tile(t) for t in ts) == len(ts) and bool(ts)
               for k, ts in i.get("zoom_tiles", {}).items()}
    zoom = max((int(k) for k,v in quality.items() if v),default=None)
    if zoom is None:
        reasons.append("NO_USABLE_IMAGE_TILES")
    observation = c.get("visual_observation")
    if observation != "visually_continuous":
        reasons.append("PHYSICAL_CONTINUITY_UNPROVEN")
    if observation == "occluded":
        reasons.append("CORRIDOR_OCCLUDED")
    roads = [o.get("endpoint_tags", {}), o.get("target_tags", {})]
    modes = {}
    for vehicle in ("motorcar", "emergency", "foot"):
        states = [mode(tags,vehicle) for tags in roads]
        modes[vehicle] = "deny" if "deny" in states else "unknown" if "unknown" in states else "allow"
    if modes["motorcar"] != "allow":
        reasons.append("MOTORCAR_CONNECTIVITY_NOT_ESTABLISHED")
    if modes["emergency"] != "allow":
        reasons.append("EMERGENCY_CONNECTIVITY_NOT_ESTABLISHED")
    reasons += ["FIELD_PASSABILITY_UNVERIFIED", "LOCAL_ACCESS_NOT_VERIFIED"]
    score = (2 if geometry and "OSM_SOURCE_STALE_OR_MISSING" not in reasons else 0)
    score += (1 if observation=="possible_passage" else 2 if observation=="visually_continuous"
              else -2 if observation=="occluded" else 0)
    score -= int("IMAGERY_PREDATES_OSM_EDIT" in reasons)
    score -= int("LOCAL_ALIGNMENT_UNVERIFIED" in reasons)
    score -= 2*int("NO_USABLE_IMAGE_TILES" in reasons)
    return {"case_id":c["case_id"],
            "decision":"HUMAN_REVIEW" if geometry and score>=1 and observation!="occluded"
                       else "DEFER_FOR_BETTER_EVIDENCE",
            "score_heuristic_NOT_probability":score,
            "confirmed_connection":False, "eligible_for_osm_edit":False,
            "reasons":sorted(set(reasons)), "tag_based_modes":modes,
            "max_usable_zoom":zoom,"current_topology_gap":geometry,
            "gap_m":o.get("gap_m"),
            "note":"Geometry/imagery do not prove a traversable or legally accessible road."}


def run(source, output, as_of):
    data=json.loads(Path(source).read_text())
    dt=time(as_of)
    if dt is None:
        raise ValueError("use timezone-aware --as-of")
    ids=[r["case_id"] for r in data["cases"]]
    if len(ids)!=len(set(ids)):
        raise ValueError("duplicate case id")
    cases=[assess(r,dt) for r in data["cases"]]
    result={"schema":"roadimpact-stage1-v04","ground_truth_available":False,
            "cases":cases,"confirmed":0,
            "count_human_review":sum(x["decision"]=="HUMAN_REVIEW" for x in cases),
            "count_deferred":sum(x["decision"]=="DEFER_FOR_BETTER_EVIDENCE" for x in cases)}
    p=Path(output);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"real_cases":len(cases),"human_review":result["count_human_review"],
                      "deferred":result["count_deferred"],"confirmed":0}))
    return result


if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--input",default="research/roadimpact-evidence-v04/bunia-cases.json")
    a.add_argument("--output",default="research/roadimpact-evidence-v04/output/triage.json")
    a.add_argument("--as-of",default="2026-10-15T21:30:00+02:00")
    p=a.parse_args()
    run(p.input,p.output,p.as_of)
