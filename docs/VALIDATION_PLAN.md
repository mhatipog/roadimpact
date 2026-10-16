# Humanitarian validation protocol — Bunia research pilot

**Current status: SOFTWARE TESTED ON SYNTHETIC NETWORKS. ZERO real Bunia
candidate corrections have been verified or accepted.**

## Pilot run

Small illustrative bounding rectangle: south 1.553, west 30.239,
north 1.571, east 30.257 (WGS84). This is NOT an official response area;
confirm humanitarian partners' priorities before releasing a QA task list.

One bounded live query (network access required; POI proxies disabled by default):

```sh
pip install -e '.[test]'
roadimpact --fetch --bbox 1.553 30.239 1.571 30.257 --output outputs/bunia-pilot
```

## Reviewer ledger

Create a separately maintained evidence ledger (does not overwrite the
machine-generated candidate file):

```sh
roadimpact-review --report outputs/bunia-pilot/report.json \
  --decisions outputs/bunia-pilot/decisions.csv --init
```

Allowed states are `UNREVIEWED`, `NEEDS_LOCAL_REVIEW`, `DISMISSED`, and
`CONFIRMED_MAPPING_ERROR`; a confirmed record requires an evidence URL,
reviewer, ISO timestamp, and explanatory notes. A verified geometric
observation alone does not authorise a map edit. Reviewers should record
imagery licensing/age, historical OSM edits, barriers, terrain, access and
possible hazards in non-sensitive notes, without introducing patient data.

## Independent validation conditions

A confirmed case requires (a) publicly usable mapping evidence and
(b) an authorized mapper's review of physical connectivity and access; false
positives must be saved as negative examples to tune the detector.

Actual map improvement needs accepted local/OSM community action, not just a
candidate flag. Any network simulation should compare audited OSM snapshots
before/after and use consistent routing rules. Present **estimated** accessibility
changes with uncertainty, not clinical response outcomes.

## Prepublication ethical gate

OpenStreetMap DRC Ebola activation documents a data protection assessment in
conflict-affected Ituri. Avoid medical case locations, personal datasets,
non-public supply routes, sensitive facilities, exact patient origins and
other information that could cause physical harm. Involve the HOT mapping hub,
OSM DRC, or other official mapping coordinators before making an aggregated
issue list public; they may prefer private triage or a different focus region.

## Go / no-go

- Do 20 best-ranked hypotheses produce at least 3 defensible real errors after
  independent review? If not, stop/pivot the algorithm.
- Is routing impact meaningful **after** actual edits are reviewed, not only in
  the simulated structural graph?
- Are operators actually asking for this QA information, rather than generic
  extra validation work? If not, stop.

Not an official HOT/MSF project, medical navigation system, or emergency service.
