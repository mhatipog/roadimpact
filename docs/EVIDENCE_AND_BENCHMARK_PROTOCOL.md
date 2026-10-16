# RoadImpact 0.4 | Evidence and benchmark protocol

**Read-only, no OSM edits, no automatic validation of map connections.**

## Practical result (15 October 2026)

The 2026-10-15 Bunia investigation provides **two actual road-topology
hypotheses**, checked independently against the main OSM API. It does *not*
provide two confirmed physical connections.

| Case | Actual OSM gap | Source | Imagery | Stage-1 triage |
| --- | ---: | --- | --- | --- |
| Bunia A | 20.96 m | OSM main API, October 2026 | Esri/Vantor, 2025-06-14 | HUMAN_REVIEW |
| Bunia B | 20.17 m | OSM main API, October 2026 | Same; obstructed by vegetation | DEFER_FOR_BETTER_EVIDENCE |

Both cases use June 2025 imagery older than nearby OSM revisions in July or
September 2026. Esri advertises 0.34 m pixel resolution and 5 m absolute
positional accuracy, *not* a locally calibrated 0.34 m alignment.
Zoom levels 19–20 returned 2,521-byte placeholder tiles; zoom 18 is the
highest usable tile level in the actual acquired set. All satellite imagery
remains outside this distributed repository. The use of Esri for OSM editing
must comply with the imagery provider's current OSM licensing terms.

```bash
pip install -e '.[test]'
pytest -q
roadimpact-evidence --input evidence/bunia-evidence-metadata.json \
  --output evidence/bunia-assessment.json --as-of 2026-10-15T21:30:00+02:00
roadimpact-benchmark --input benchmark/evaluation-input.json \
  --output benchmark/evaluation.json --review-budget 200
```

## Evidence gates

1. **Live topology / provenance:** no point is accepted because old imagery
   appears continuous. OSM object versions, current node/way existence and a
   fresh API timestamp must be recorded.
2. **Temporal comparison:** captured satellite imagery older than either OSM
   object's latest edit is flagged, never used as negative ground truth.
3. **Image validity:** reject blank/placeholder tiles using byte size and
   pixel variation; this does not establish legibility, road presence or access.
4. **Spatial alignment:** satellite ground sampling distance and absolute
   positional accuracy are separate. Local registration requires at least
   three independent controls and a reported residual; neither Bunia case
   has this verification.
5. **Mode-specific tags:** OSM access tags are *not* evidence of vehicle width,
   barriers under canopy, local access permissions or emergency routing.
   Tag-unknown is not considered allowed.
6. **Visual and local observations:** both can be inconclusive. The model must
   abstain. Stage 1 cannot authorize an edit, even with favorable indicators.

The evidence heuristic is explicitly **not a calibrated probability** and
must not be called one. It determines what to show a trained mapper, not what
to upload to OSM.

## Benchmark design — real world

Pre-register the protocol **before** looking at adjudicated outcomes. Obtain a
pool of 200 independently sampled sites, incorporating hypotheses from
RoadImpact, a pure distance-based baseline, existing QA tools, and random
road endpoints/intentional dead ends. Stratify by road class, region, feature
ambiguity and network scenario. Do not select only high-scoring RoadImpact
hits (spectrum bias). Keep an explicit negative-control stratum and locations
with absent/inconclusive imagery.

For every selected site:

- Two qualified reviewers independently inspect the **same source evidence**,
  blinded to detector identity and the score ordering. Collect their separate
  judgements, modes of possible travel, evidence provenance and minutes spent.
- Resolve disagreement with a third independent adjudicator and document why.
- Distinguish `inconclusive`, `rejected_connection`, and
  `accepted_osm_correction`. The latter requires an actual accepted OSM
  changeset URL, not an optimistic mapper note.
- Check review reliability, unresolved cases and hours per accepted correction.
  Report unsafe false-connection proposals separately.
- Apply distance-only and evidence ranking to **the exact same population**;
  compare precision@20 and accepted corrections/reviewer-hour. An operational
  test with random assignment or counterbalanced ordering is required to
  establish causal reviewer productivity gains.
- Do not release coordinates without HOT/local OSM mapping coordination or
  permission. No automatic MapRoulette challenge or automated edits.

`benchmark/evaluation-input.json` contains two **unreviewed** real Bunia cases
and 12 explicitly **synthetic** labelled examples, only to regression-test the
metric implementation. Synthetic metrics are never merged into the real metric
and do not count as evidence of effectiveness.

A credible comparison requires an independently labelled, sufficiently diverse
pool; current real sample n=2 and adjudicated n=0. The benchmark appropriately
returns `INSUFFICIENT_INDEPENDENT_LABELS`, `precision=null` and 198 empty
review-queue slots. This is deliberate rather than an implementation failure.

## Licensing, hazards, and scope

- Code MIT; OSM geometry © OpenStreetMap contributors, ODbL 1.0.
- Imagery content deliberately excluded from distributed artifacts; only
  provenance, capture metadata and image-quality summary statistics retained.
- Published outputs cannot confirm a physical road nor enable ambulance
  routing. The graph model remains undirected and topological.
- Real imagery used for evidence must be approved by OSM/licensor and checked
  for current terms before any edit is proposed.
- HOT validation permission and conflict-area sensitivity take precedence.
