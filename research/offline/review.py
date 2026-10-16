"""Human-reviewed QA ledger. Generates templates; cannot upload OSM changes."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

DECISIONS = {"UNREVIEWED", "NEEDS_LOCAL_REVIEW", "DISMISSED", "CONFIRMED_MAPPING_ERROR"}
HEADERS = ("candidate_id", "decision", "evidence_url", "reviewer", "reviewed_at", "notes")


def review_ledger(report: dict, path: Path, *, initialize: bool = False) -> dict:
    """Validate a reviewer ledger tied to the immutable OSM source fingerprint.

    CONFIRMED_MAPPING_ERROR requires nonempty reviewer, evidence URL, timestamp,
    and narrative notes. This does not imply it is safe to make an OSM edit.
    """
    report_ids = {str(c["candidate_id"]) for c in report["candidates"]}
    if len(report_ids) != len(report["candidates"]):
        raise ValueError("Duplicate candidate IDs; do not initialize ledger")
    if initialize:
        if path.exists():
            raise FileExistsError(f"Review ledger exists, refusing overwrite: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=HEADERS)
            writer.writeheader()
            for c in report["candidates"]:
                writer.writerow({"candidate_id": c["candidate_id"], "decision": "UNREVIEWED"})
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != list(HEADERS):
            raise ValueError(f"Ledger columns must be exactly: {', '.join(HEADERS)}")
        rows = list(reader)
    seen = set()
    counts = {key: 0 for key in DECISIONS}
    for row in rows:
        cid = row["candidate_id"]
        if cid in seen or cid not in report_ids:
            raise ValueError(f"Unknown/duplicate candidate ID: {cid}")
        seen.add(cid)
        decision = row["decision"]
        if decision not in DECISIONS:
            raise ValueError(f"Invalid decision {decision!r} for {cid}")
        if decision == "CONFIRMED_MAPPING_ERROR":
            for field in ("evidence_url", "reviewer", "reviewed_at", "notes"):
                if not row[field].strip():
                    raise ValueError(f"Confirmed case {cid} missing {field}")
            if not row["evidence_url"].startswith(("https://", "http://")):
                raise ValueError(f"Evidence URL must be an explicit HTTP(S) link for {cid}")
            try:
                datetime.fromisoformat(row["reviewed_at"].replace("Z", "+00:00"))
            except ValueError as e:
                raise ValueError(f"Date format must be ISO 8601 for {cid}") from e
        counts[decision] += 1
    if seen != report_ids:
        raise ValueError(f"Ledger missing {len(report_ids - seen)} candidate rows")
    return {
        "input_sha256": report.get("metadata", {}).get("input_sha256"),
        "total_candidates": len(report_ids),
        "decision_counts": {k: counts[k] for k in sorted(counts)},
        "note": "Even confirmed mapping errors require mapper permission, coordination and editor validation before editing OSM",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Offline, reviewer-controlled triage ledger (no uploads)")
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--decisions", type=Path, required=True)
    p.add_argument("--init", action="store_true", help="Create a blank review ledger without overwriting")
    p.add_argument("--summary", type=Path, help="Optional local JSON summary file")
    a = p.parse_args()
    report = json.loads(a.report.read_text(encoding="utf-8"))
    result = review_ledger(report, a.decisions, initialize=a.init)
    if a.summary:
        a.summary.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
