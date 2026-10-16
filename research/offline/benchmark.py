"""Strict label-isolated review benchmark. No inference from unreviewed candidates.

The tool never invents ground truth. A labelled record requires independent
reviewer evidence and adjudication. Synthetic tests are reported separately.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

VALID_LABELS = {"accepted_osm_correction", "rejected_connection", "inconclusive", "unreviewed"}


def validate_case(row: dict) -> None:
    if row.get("source_type") not in {"real", "synthetic"}:
        raise ValueError("source_type must be real or synthetic")
    if row.get("ground_truth", "unreviewed") not in VALID_LABELS:
        raise ValueError("unsupported ground_truth")
    label = row.get("ground_truth", "unreviewed")
    if row.get("source_type") == "real" and label != "unreviewed":
        reviewers = row.get("independent_reviewers", [])
        if (not isinstance(reviewers, list) or len(set(reviewers)) < 2 or
            not row.get("adjudicator") or not row.get("evidence_url") or
            not str(row.get("evidence_url")).startswith("https://") or
            not row.get("adjudicated_at") or
            (label == "accepted_osm_correction" and
             not str(row.get("accepted_changeset_url", "")).startswith("https://www.openstreetmap.org/changeset/"))):
            raise ValueError("real labels require two independent reviewers, evidence URL and adjudication")
    for metric in ("gap_m", "heuristic_score", "baseline_score"):
        value = row.get(metric)
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"invalid {metric}")
    if not row.get("case_id"):
        raise ValueError("case_id required")


def precision_at_k(records: list[dict], order: str, k: int) -> dict:
    ranked = sorted(records, key=lambda c: (-c[order], c["case_id"]))[:k]
    labelled = [r for r in ranked if r.get("ground_truth") in {
        "accepted_osm_correction", "rejected_connection"}]
    positive = sum(r["ground_truth"] == "accepted_osm_correction" for r in labelled)
    # Do not silently hide the unknowns and call the labelled subset precision@k.
    fully_labelled = bool(ranked) and len(labelled) == len(ranked)
    return {"requested_k": k, "inspected": len(ranked), "decisively_adjudicated": len(labelled),
            "accepted_corrections": positive,
            "precision": positive / len(labelled) if fully_labelled else None,
            "coverage": len(labelled) / len(ranked) if ranked else None}


def stratified_queue(cases: list[dict], budget: int = 200) -> list[dict]:
    """Deterministic round-robin queue across geography/type/uncertainty strata.

    Coverage is bounded by actual supplied candidates; never invents cases.
    """
    if budget < 1:
        raise ValueError("budget must be positive")
    buckets = defaultdict(list)
    for row in cases:
        if row["ground_truth"] != "unreviewed":
            continue
        key = (row.get("region", "unknown"), row.get("road_type", "unknown"),
               row.get("scenario", "unknown"), row.get("uncertainty", "unknown"))
        buckets[key].append(row)
    for bucket in buckets.values():
        bucket.sort(key=lambda r: (-r["heuristic_score"], r["case_id"]))
    result = []
    # Actionable human-review cases first; also retain deferred cases as negative
    # controls once the main queue has been considered.
    keys = sorted(buckets, key=lambda k: (
        min(0 if r.get("evidence_review_status") == "HUMAN_REVIEW" else 1
            for r in buckets[k]), k))
    while len(result) < budget and keys:
        next_round = []
        for key in keys:
            if buckets[key]:
                result.append(buckets[key].pop(0))
                if len(result) >= budget:
                    break
            if buckets[key]:
                next_round.append(key)
        keys = sorted(next_round, key=lambda k: (
            min(0 if r.get("evidence_review_status") == "HUMAN_REVIEW" else 1
                for r in buckets[k]), k))
    return result


def evaluate(rows: list[dict], review_budget: int = 200) -> dict:
    unique = set()
    for row in rows:
        validate_case(row)
        identity = (row["source_type"], row["case_id"])
        if identity in unique:
            raise ValueError("duplicate case ID")
        unique.add(identity)
    sources = {}
    for source in ("real", "synthetic"):
        subset = [r for r in rows if r["source_type"] == source]
        counts = Counter(r.get("ground_truth", "unreviewed") for r in subset)
        adjudicated = counts["accepted_osm_correction"] + counts["rejected_connection"]
        sample_origins = {r.get("sampling_origin") for r in subset if r.get("ground_truth") != "unreviewed"}
        enough = (source == "real" and adjudicated >= 100 and
                  counts["accepted_osm_correction"] >= 15 and
                  counts["rejected_connection"] >= 15 and
                  {"roadimpact", "random_endpoint", "external_qa"}.issubset(sample_origins))
        queue = stratified_queue(subset, review_budget)
        sources[source] = {
            "candidates": len(subset), "label_counts": dict(counts),
            "independently_adjudicated": adjudicated,
            "adjudicated_sampling_origins": sorted(v for v in sample_origins if v is not None),
            "benchmark_status": "READY_FOR_VALIDATION" if enough else "INSUFFICIENT_INDEPENDENT_LABELS",
            "reportable_real_effectiveness": bool(enough),
            "ranking": {
                "evidence_heuristic": precision_at_k(subset, "heuristic_score", min(20, len(subset))),
                "distance_only_baseline": precision_at_k(subset, "baseline_score", min(20, len(subset))),
            },
            "queue": [r["case_id"] for r in queue],
            "queue_unfilled_capacity": max(0, review_budget - len(queue)),
        }
    return {"schema": "roadimpact-benchmark-v1", "source_segregation": True,
            "important": "Synthetic evaluation tests software only; never combine it with real-world effectiveness.",
            "sources": sources}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Offline, label-isolated RoadImpact QA benchmarking")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--review-budget", type=int, default=200)
    args = p.parse_args(argv)
    rows = json.loads(Path(args.input).read_text(encoding="utf-8"))["cases"]
    report = evaluate(rows, args.review_budget)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({s: {"candidates": v["candidates"], "status": v["benchmark_status"]}
                      for s, v in report["sources"].items()}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
