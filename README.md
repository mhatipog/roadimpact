# RoadImpact

[![Offline tests](https://github.com/mhatipog/roadimpact/actions/workflows/ci.yml/badge.svg)](https://github.com/mhatipog/roadimpact/actions/workflows/ci.yml)

**Open-source, read-only research for evidence-aware OpenStreetMap road-network quality assurance.**

RoadImpact generates **unverified** road-topology hypotheses for trained mappers. It does not edit OpenStreetMap or establish whether roads are physically passable, legally accessible, or safe for ambulances.

## Install and test

```bash
python -m pip install -e '.[test]'
python -m unittest discover -s research/evidence -p 'test_*.py' -v
python -m pytest -q research/offline/test_core.py research/offline/test_experiment.py
roadimpact --help
roadimpact-review --help
roadimpact-evidence --help
roadimpact-benchmark --help
```

The GitHub workflow checks all four CLI commands, **27 package/offline tests** and **9 independent evidence protocol tests**, with no network access or real-world OSM modifications required.

The installable `roadimpact` package is currently mapped to `research/offline` in `pyproject.toml`. The separate historical comparative detector is `research/offline/experiment.py` (use `--help`).

## Real research results, not validated defects

The historical **2026-10-12** Geofabrik DRC snapshot, buffered around Bunia, contained 41,655 eligible road nodes. The offline comparison generated **312 directional road-continuation hypotheses** and **172 endpoint-distance baseline hypotheses**. A proposed blinded validation queue contains 60 locations (25/20/10/5 across selection arms and controls).

**Confirmed physical road connections: 0. Accepted OSM corrections: 0. Demonstrated humanitarian benefit: none yet.** Comparison with established production QA systems remains necessary; the simple distance baseline is not MapRoulette or Osmose.

The original two highlighted Bunia locations remain inconclusive. Available imagery was acquired in June 2025 before later OSM edits, and one gap was obscured by vegetation.

## Reproduce the historical experiment

Obtain the date-pinned DRC PBF from [Geofabrik](https://download.geofabrik.de/africa/congo-democratic-republic-261012.osm.pbf), verify its published MD5, then:

```bash
osmium extract --bbox 30.19,1.50,30.31,1.63 --strategy complete_ways drc-20261012.osm.pbf -o bunia.osm.pbf
osmium cat bunia.osm.pbf -o bunia.osm
python research/offline/experiment.py --osm bunia.osm --output local-review
```

The OSM source snapshot is not committed to git; the derived XML SHA-256 and successful extraction provenance are recorded in [docs/DATA_PROVENANCE.md](docs/DATA_PROVENANCE.md). Code, methods, tests and numerical claims are public; **real unreviewed candidate rankings, reviewer allocations, and licensed satellite imagery are not**.

Read the [independent validation plan](docs/VALIDATION_PLAN.md), [evidence and benchmark protocol](docs/EVIDENCE_AND_BENCHMARK_PROTOCOL.md) and [research status](docs/RESEARCH_STATUS.md).

## Safety, coordination and licensing

Do not treat hypotheses as mapping instructions. Coordinate with local OSM validators or HOT before creating OSM tasks or edits, especially in sensitive areas. This repository contains no OSM write integration and does not publish medical facility locations.

Code is **Apache 2.0** (see LICENSE). OSM source/derived geographic data are © OpenStreetMap contributors, licensed separately under **ODbL 1.0**. Imagery has distinct license terms and is not redistributed.
