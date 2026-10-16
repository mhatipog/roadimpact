"""Auditable evidence triage for road-topology *hypotheses*, never OSM edits.

Deterministic decision support, not a classifier of real-world road connectivity.
Aerial imagery alone cannot establish legal or vehicle access. Metadata must
remain separate from ground-truth annotations used by the benchmark.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
import argparse
import json
import math

BLOCKED = {"no", "private", "agricultural", "forestry", "delivery"}
PERMISSIVE = {"yes", "designated", "permissive", "official"}
VEHICLE_EXPLICIT = ("motorcar", "motor_vehicle", "vehicle", "access")
ROAD_VEHICLE_AMBIGUOUS = {"service", "track", "path", "road", "living_street"}


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if len(value) == 8 and value.isdigit():
            t = datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc)
        else:
            t = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if t.tzinfo is None:
                return None
        return t.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def valid_image_tiles(records: list[dict]) -> dict[str, Any]:
    """Reject placeholder/blank tiles; tile-byte-size is only a heuristic.

    If a tile has photographic variation, it may still be cloudy/occluded or
    irrelevant to the feature. The result is NOT a road segmentation score.
    """
    good = []
    for tile in records:
        std = tile.get("pixel_std")
        size = tile.get("bytes")
        if not isinstance(std, (int, float)) or not isinstance(size, int):
            continue
        if not (math.isfinite(std) and std >= 0 and size >= 0):
            continue
        if size >= 5_000 and std >= 8 and not tile.get("error"):
            good.append(tile)
    return {"total": len(records), "usable": len(good),
            "all_usable": bool(records) and len(good) == len(records)}


def road_mode(tags: dict[str, str], mode: str) -> str:
    """Tagged eligibility, not proof of passability: allow/deny/unknown."""
    if mode not in {"foot", "bicycle", "motorcar", "emergency"}:
        raise ValueError("unsupported mode")
    highway = tags.get("highway", "")
    if not highway:
        return "unknown"
    keys = {"foot": ("foot", "access"),
            "bicycle": ("bicycle", "vehicle", "access"),
            "motorcar": VEHICLE_EXPLICIT,
            "emergency": ("emergency", "motorcar", "motor_vehicle", "vehicle", "access")}[mode]
    for key in keys:
        tag = tags.get(key, "").lower().strip()
        if tag in BLOCKED:
            # For emergency, common legal vehicle bans do not always apply;
            # never infer that an emergency vehicle can pass from them alone.
            if mode == "emergency" and key != "emergency":
                return "unknown"
            return "deny"
        if tag in PERMISSIVE:
            return "allow" if key == mode or (mode == "motorcar" and key in VEHICLE_EXPLICIT) else "unknown"
    if mode in {"motorcar", "emergency"} and highway in {"footway", "steps", "pedestrian", "cycleway", "bridleway"}:
        return "deny" if mode == "motorcar" else "unknown"
    if mode == "foot" and highway in {"motorway", "motorway_link"}:
        return "deny"
    if mode in {"motorcar", "emergency"}:
        # No assumption that alleys, tracks, or generic services are accessible
        # or wide enough for a car, truck, or emergency vehicle.
        if highway in ROAD_VEHICLE_AMBIGUOUS or tags.get("service") in {
            "alley", "driveway", "parking_aisle", "emergency_access"}:
            return "unknown"
    return "unknown"  # highway type alone is not positive physical evidence


def inspect_case(record: dict[str, Any], as_of: str | None = None) -> dict[str, Any]:
    case_id = record.get("case_id")
    if not isinstance(case_id, str) or not case_id or any(c in case_id for c in "<>\\\n\r"):
        raise ValueError("invalid case_id")
    now = parse_time(as_of) if as_of else datetime.now(timezone.utc)
    if now is None:
        raise ValueError("as_of must be an offset-aware ISO date/time")
    osm = record.get("osm") or {}
    image = record.get("imagery") or {}
    observation = record.get("visual_observation", "not_assessed")
    if observation not in {"possible_passage", "occluded", "no_visible_continuity",
                           "visually_continuous", "not_assessed"}:
        raise ValueError("unrecognized visual observation")
    reasons = []
    source_age = parse_time(osm.get("checked_at"))
    geometry_current = (osm.get("endpoint_exists") is True and
                        osm.get("target_exists") is True and
                        osm.get("shared_node") is False and
                        osm.get("geometrical_gap") is True)
    if not geometry_current:
        reasons.append("TOPOLOGY_NOT_REVALIDATED")
    if not source_age or (now - source_age).total_seconds() < -86400 or (now - source_age).days > 14:
        reasons.append("OSM_SOURCE_STALE_OR_MISSING")

    acquired = parse_time(image.get("acquired_at"))
    if not acquired:
        reasons.append("IMAGE_DATE_UNKNOWN")
    elif acquired > now:
        reasons.append("IMAGE_IN_FUTURE")
    if acquired:
        if any((t := parse_time(value)) is not None and acquired < t for value in
               [osm.get("endpoint_last_edit"), osm.get("target_last_edit")]):
            reasons.append("IMAGERY_PREDATES_OSM_EDIT")
        if (now - acquired).days > 365:
            reasons.append("IMAGERY_OLDER_THAN_ONE_YEAR")
    if image.get("license_for_osm_review") is not True:
        reasons.append("IMAGERY_PERMISSION_NOT_CONFIRMED")
    accuracy = image.get("absolute_accuracy_m")
    if not isinstance(accuracy, (int, float)) or not math.isfinite(accuracy) or accuracy <= 0:
        reasons.append("POSITIONAL_ACCURACY_UNKNOWN")
    if image.get("locally_registered") is not True:
        reasons.append("LOCAL_ALIGNMENT_UNVERIFIED")
    else:
        controls = image.get("control_points", 0)
        residual = image.get("registration_residual_m")
        if not isinstance(controls, int) or controls < 3 or not isinstance(residual, (int, float)) \
                or not math.isfinite(residual) or residual < 0 or residual > 2.0:
            reasons.append("LOCAL_ALIGNMENT_UNVERIFIED")
    zooms = image.get("zoom_tiles", {})
    quality = {str(z): valid_image_tiles(tiles) for z, tiles in zooms.items()}
    usable_levels = [int(z) for z, result in quality.items()
                     if z.isdigit() and result["all_usable"]]
    if not usable_levels:
        reasons.append("NO_USABLE_IMAGE_TILES")
    if observation == "occluded":
        reasons.append("CORRIDOR_OCCLUDED")
    if observation != "visually_continuous":
        reasons.append("PHYSICAL_CONTINUITY_UNPROVEN")
    # Visual continuity alone is never proof of vehicle access or legality.
    reasons.append("FIELD_PASSABILITY_UNVERIFIED")
    if record.get("local_access_verified") is not True:
        reasons.append("LOCAL_ACCESS_NOT_VERIFIED")

    tags_a = osm.get("endpoint_tags") or {}
    tags_b = osm.get("target_tags") or {}
    modes = {}
    for mode in ("foot", "bicycle", "motorcar", "emergency"):
        a, b = road_mode(tags_a, mode), road_mode(tags_b, mode)
        modes[mode] = "deny" if "deny" in (a, b) else "unknown" if "unknown" in (a, b) else "allow"
    if modes["motorcar"] != "allow":
        reasons.append("MOTORCAR_CONNECTIVITY_NOT_ESTABLISHED")
    if modes["emergency"] != "allow":
        reasons.append("EMERGENCY_CONNECTIVITY_NOT_ESTABLISHED")

    # Review priority is a deterministic heuristic, not calibrated probability.
    # Prefer interpretable/human-reviewable evidence, penalize occlusion.
    priority = 0.0
    if geometry_current and source_age and "OSM_SOURCE_STALE_OR_MISSING" not in reasons:
        priority += 2.0
    if observation == "possible_passage":
        priority += 1.0
    if observation == "visually_continuous":
        priority += 2.0
    if observation == "occluded":
        priority -= 2.0
    if "IMAGERY_PREDATES_OSM_EDIT" in reasons:
        priority -= 1.0
    if "LOCAL_ALIGNMENT_UNVERIFIED" in reasons:
        priority -= 1.0
    if "NO_USABLE_IMAGE_TILES" in reasons:
        priority -= 2.0
    # NEVER transition to 'confirmed' through this scoring function.
    action = "HUMAN_REVIEW" if geometry_current and priority >= 1 and observation != "occluded" else "DEFER_FOR_BETTER_EVIDENCE"
    return {
        "case_id": case_id, "decision": action, "confirmed_connection": False,
        "eligible_for_osm_edit": False, "review_priority_heuristic": round(priority, 2),
        "reasons": sorted(set(reasons)), "road_modes_tag_based": modes,
        "imagery": {"acquired_at": image.get("acquired_at"),
                    "declared_resolution_m": image.get("resolution_m"),
                    "declared_absolute_accuracy_m": accuracy,
                    "max_usable_zoom": max(usable_levels) if usable_levels else None,
                    "zoom_quality": quality},
        "osm": {"source_checked_at": osm.get("checked_at"),
                "recorded_gap_m": osm.get("gap_m"), "geometry_confirmed_in_osm": geometry_current},
        "limitation": "OSM geometry, metadata and imagery alone cannot confirm a real-world traversable road or justify a map edit.",
    }


def analyze_file(src: str | Path, dest: str | Path, as_of: str | None = None) -> dict:
    raw = json.loads(Path(src).read_text(encoding="utf-8"))
    cases = raw.get("cases")
    if not isinstance(cases, list):
        raise ValueError("expected cases array")
    ids = [case.get("case_id") for case in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate case_id")
    reviewed = [inspect_case(case, as_of) for case in cases]
    results = {"schema": "roadimpact-evidence-v1", "dataset": raw.get("dataset", "unknown"),
               "ground_truth_provided": False, "cases": reviewed,
               "counts": {"human_review": sum(v["decision"] == "HUMAN_REVIEW" for v in reviewed),
                          "defer": sum(v["decision"] == "DEFER_FOR_BETTER_EVIDENCE" for v in reviewed),
                          "confirmed": 0}}
    target = Path(dest)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return results


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Conservative evidence QA; read-only")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--as-of", default=None, help="ISO timezone-aware reproducibility timestamp")
    args = p.parse_args(argv)
    result = analyze_file(args.input, args.output, args.as_of)
    print(json.dumps(result["counts"], sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
