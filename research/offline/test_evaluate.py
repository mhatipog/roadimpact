"""Synthetic-only regression tests for independent mapping QA adjudication."""
import pytest
from evaluate import evaluate

ALLOCATION = [
    {"blind_id": "blind-001", "sampling_arm": "roadimpact"},
    {"blind_id": "blind-002", "sampling_arm": "distance_only"},
]

REVIEWS = [
    {"blind_id": "blind-001", "reviewer_id": "mapper-a"},
    {"blind_id": "blind-001", "reviewer_id": "mapper-b"},
]

ADJUDICATIONS = [
    {"blind_id": "blind-001", "adjudicator_id": "mapper-c",
     "final_outcome": "actionable", "evidence_link": "https://example.org/example-evidence"}
]

def test_partial_annotations_do_not_turn_unknowns_into_negative_labels():
    r = evaluate(ALLOCATION, REVIEWS, ADJUDICATIONS)
    assert r["adjudicated"] == 1
    assert not r["complete"]
    assert r["ranking_comparison"]["roadimpact"]["actionable_rate"] == 1.0
    assert r["ranking_comparison"]["distance_only"]["actionable_rate"] is None
    assert r["accepted_osm_edits_confirmed"] == 0

def test_unreviewed_queue_does_not_claim_precision():
    r = evaluate(ALLOCATION, [], [])
    assert r["adjudicated"] == 0
    assert r["real_precision"] is None
    assert all(group["actionable_rate"] is None for group in r["ranking_comparison"].values())

def test_independent_reviewers_required():
    with pytest.raises(ValueError, match="Two independent"):
        evaluate(ALLOCATION, REVIEWS[:1], ADJUDICATIONS)

def test_independent_adjudicator_required():
    invalid = [dict(ADJUDICATIONS[0], adjudicator_id="mapper-a")]
    with pytest.raises(ValueError, match="Independent adjudicator"):
        evaluate(ALLOCATION, REVIEWS, invalid)

def test_unknown_outcome_rejected():
    invalid = [dict(ADJUDICATIONS[0], final_outcome="definitely_real")]
    with pytest.raises(ValueError, match="Outcome"):
        evaluate(ALLOCATION, REVIEWS, invalid)
