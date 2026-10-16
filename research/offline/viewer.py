"""Generate a local, read-only visual triage page (requires internet for tiles)."""
from __future__ import annotations
import html
import json
from pathlib import Path


def write_viewer(report: dict, path: Path) -> None:
    data = json.dumps(report["candidates"], ensure_ascii=False).replace("<", "\\u003c")
    bbox = json.dumps(report["metadata"].get("bbox", [1.55, 30.235, 1.575, 30.26]))
    summary = html.escape(str(report["metadata"].get("warning", "Unverified candidates only")))
    if report["metadata"].get("synthetic_input"):
        summary = "SYNTHETIC FIXTURE — NOT REAL MAP DATA. " + summary
    page = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>RoadImpact candidate review</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
 integrity="sha256-p4NxAoJBhHIN+hmNHrzRCf9tD/miZyo5pJOZyn7ewFk=" crossorigin="" />
<style>body{font:14px system-ui,sans-serif;margin:0;color:#192333;background:#f6f8fa}
header{padding:16px 22px;background:#14293b;color:white}h1{font-size:19px;margin:0 0 6px}header p{margin:0;color:#dce5f3}
main{display:grid;grid-template-columns:minmax(280px,38%) 1fr;min-height:calc(100vh - 86px)}
#list{overflow:auto;max-height:calc(100vh - 88px);padding:12px}#map{height:calc(100vh - 88px)}
article{padding:12px;margin-bottom:10px;border:1px solid #dbe1e8;background:white;border-radius:8px;cursor:pointer}
article:hover{border-color:#2b6ea6}small{color:#586477}b{color:#122a42}
.tag{display:inline-block;background:#fff0cb;color:#744b00;padding:3px 8px;border-radius:6px}
@media(max-width:760px){main{display:block}#map{height:52vh}#list{max-height:none}}
</style></head><body>
<header><h1>RoadImpact — unverified road-gap hypotheses</h1><p>SUMMARYHERE</p></header>
<main><section id="list"></section><div id="map" role="region" aria-label="Map of unverified candidate gaps"></div></main>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
 integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script>
const data=DATAHERE,bbox=BBOXHERE,box=document.getElementById('list');
const map=L.map('map').fitBounds([[bbox[0],bbox[1]],[bbox[2],bbox[3]]]);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,
 attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'}).addTo(map);
const lines=[];
for(const c of data){
 const line=L.polyline([[c.lat,c.lon],[c.target_lat,c.target_lon]],{color:'#d45a00',weight:5}).addTo(map);
 const locationUrl='https://www.openstreetmap.org/?mlat='+c.lat+'&mlon='+c.lon+'#map=19/'+c.lat+'/'+c.lon;
 const nodeUrl='https://www.openstreetmap.org/node/'+encodeURIComponent(c.endpoint_node);
 const wayUrl='https://www.openstreetmap.org/way/'+encodeURIComponent(c.target_way);
 const popup=document.createElement('div');
 popup.innerHTML='<b>Candidate '+c.rank+'</b> — '+c.scenario+'<hr>Gap: '+c.gap_m+' m; potential newly reachable node pairs: '+c.new_reachable_node_pairs+'<hr><a target="_blank" rel="noopener" href="'+locationUrl+'">Inspect location on OSM</a><br><a target="_blank" rel="noopener" href="'+nodeUrl+'">Endpoint</a> | <a target="_blank" rel="noopener" href="'+wayUrl+'">Target way</a><p><b>UNVERIFIED. Do not edit without imagery and local validation.</b></p>';
 line.bindPopup(popup);lines.push(line);
 const item=document.createElement('article');
 item.innerHTML='<b>#'+c.rank+' — '+c.scenario.replaceAll('_',' ')+'</b><p>'+c.gap_m+' m suspected gap · '+c.new_reachable_node_pairs+' hypothetical reachable node pairs</p><small>OSM node '+c.endpoint_node+' → way '+c.target_way+'</small><p><span class="tag">UNVERIFIED</span></p>';
 item.onclick=()=>{map.setView([c.lat,c.lon],18);line.openPopup()};box.appendChild(item);
}
if(!data.length)box.innerHTML='<article>No candidates found in this run. This does not prove the map is complete.</article>';
</script></body></html>"""
    page = page.replace("DATAHERE", data).replace("BBOXHERE", bbox).replace("SUMMARYHERE", summary)
    path.write_text(page, encoding="utf-8")
