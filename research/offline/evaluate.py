"""Evaluate independent blinded mapping reviews without inventing missing labels."""
from __future__ import annotations
from collections import defaultdict
import argparse
import csv
import json
from pathlib import Path

VALID = {"actionable", "not_actionable", "inconclusive"}

def read_rows(path):
    with open(path, encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))

def evaluate(allocation, reviews, adjudications):
    sites = {row["blind_id"]: row for row in allocation}
    if len(sites) != len(allocation):
        raise ValueError("Duplicate blind identifier")
    grouped = defaultdict(set)
    for row in reviews:
        key, person = row.get("blind_id"), row.get("reviewer_id")
        if key not in sites or not person or person in grouped[key]:
            raise ValueError("Unknown site, missing reviewer or duplicate assessment")
        grouped[key].add(person)
    decision = {}
    for row in adjudications:
        key = row.get("blind_id")
        if key not in sites or key in decision:
            raise ValueError("Unknown or duplicate adjudication")
        if len(grouped[key]) < 2:
            raise ValueError("Two independent reviews required")
        if not row.get("adjudicator_id") or row["adjudicator_id"] in grouped[key]:
            raise ValueError("Independent adjudicator required")
        if row.get("final_outcome") not in VALID or not row.get("evidence_link"):
            raise ValueError("Outcome and supporting evidence required")
        decision[key] = row
    result = {"sites": len(sites), "adjudicated": len(decision), "complete": len(decision) == len(sites),
              "ranking_comparison": {}, "real_precision": None,
              "accepted_osm_edits_confirmed": 0,
              "notice": "An actionable review does not prove an accepted OSM change."}
    arms = sorted({row["sampling_arm"] for row in allocation})
    for arm in arms:
        ids = [row["blind_id"] for row in allocation if row["sampling_arm"] == arm]
        matched = [decision[key] for key in ids if key in decision]
        rate = sum(x["final_outcome"] == "actionable" for x in matched) / len(ids) if len(matched) == len(ids) and ids else None
        result["ranking_comparison"][arm] = {"assigned": len(ids), "adjudicated": len(matched), "actionable_rate": rate}
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--allocation", required=True)
    parser.add_argument("--reviews", required=True)
    parser.add_argument("--adjudications", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = evaluate(read_rows(args.allocation), read_rows(args.reviews), read_rows(args.adjudications))
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))

if __name__ == "__main__":
    main()
