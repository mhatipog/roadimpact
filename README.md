# RoadImpact

**Open-source, read-only research into evidence-aware OpenStreetMap road-network quality assurance.**

RoadImpact evaluates whether geographically plausible but **unverified** network disconnections can be prioritized for independent human review. It does not modify OpenStreetMap, prove vehicle passability, recommend emergency routes or claim confirmed humanitarian benefit.

## What exists

- A conservative, provenance-aware evidence triage tool (`research/evidence/triage.py`) that refuses to label ambiguous road gaps as confirmed defects.
- A blinded-evaluation harness (`research/evidence/benchmark.py`), with tests requiring independent evidence and no manufactured precision.
- An offline, pinned-snapshot road-graph experiment (`research/offline/experiment.py`) comparing directional endpoint-to-segment hypotheses against an intentionally simple endpoint-to-endpoint baseline.
- Reproducible setup and test instructions in `research/` and `docs/`.

## Actual research results (15 October 2026)

A historical Geofabrik DRC snapshot from **2026-10-12**, spatially extracted for Bunia with Osmium, yielded 41,655 eligible road nodes, **312** directional hypotheses and **172** distance-baseline hypotheses. The blinded review sample contains 60 locations (25/20/10/5 across detector arms and controls).

**Zero independently verified physical connections; zero accepted OSM changesets; no demonstrated superiority over existing mapping QA tools.** Earlier satellite evidence for two candidate locations was inconclusive. The ranking is an experiment, not an instruction to edit OSM.

This repository does not publish the real Bunia ranking, detailed unpublished reviewer allocations, licensed satellite imagery or any patient/medical facilities.

## Try the source

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s research/evidence -p 'test_*.py' -v
python research/evidence/triage.py --help
python research/evidence/benchmark.py --help
python research/offline/experiment.py --help
```

The offline experiment requires an **OSM XML extract**, not a PBF as CLI input. See [how to get the pinned OSM data](docs/DATA_PROVENANCE.md). All repeated analysis should run offline rather than against public OSM APIs.

The evidence input is historical and carries only coarse map metadata; this code is **not** a finished humanitarian routing product. A real reviewer study and comparison with production tools (e.g. MapRoulette/Osmose) are the next gates.

## Community, safety and attribution

Please coordinate with the relevant local OSM community or HOT before publishing detailed real-site QA challenges or considering systematic edits. The code does not have OSM write functions. Code uses **Apache-2.0** (see `LICENSE`). OSM-derived geographical data remain © OpenStreetMap contributors, **ODbL 1.0**. Imagery licensing is separate; images are not shipped.

See [research integrity](docs/RESEARCH_STATUS.md) and [review protocol](research/evidence/README.md).
