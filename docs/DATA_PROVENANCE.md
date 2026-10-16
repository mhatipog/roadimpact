# Reproducing the dated Bunia offline dataset

Upstream data: https://download.geofabrik.de/africa/congo-democratic-republic-261012.osm.pbf

Use its companion `.md5` to verify the downloaded file before extraction.

```bash
osmium extract --bbox 30.19,1.50,30.31,1.63 --strategy complete_ways drc-20261012.osm.pbf -o bunia-20261012.osm.pbf
osmium cat bunia-20261012.osm.pbf -o bunia-20261012.osm
python research/offline/experiment.py --osm bunia-20261012.osm --output local-review
```

Validated historical bounded XML SHA-256: `8d11f45e706c810c4acbe4e87177a5c0e7c480528c76d43f70aa21d54897bd49`.

The archive contained 975,764 OSM nodes and 204,121 ways (10,993 highway-tagged). The eligible road graph contained 41,655 nodes and 46,280 segments. The historical source cannot prove the current state of the roads. No real-site candidate list is part of the public repository.

Credit: © OpenStreetMap contributors, ODbL 1.0. Geofabrik distributes the extracts. Do not use OSM main API for bulk analysis.
