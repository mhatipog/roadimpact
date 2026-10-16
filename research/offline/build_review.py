#!/usr/bin/env python3
"""Produce review UI from BLINDED queue only. No privileged files loaded."""
import argparse, csv, json, html
from pathlib import Path


def run(source, output):
    with open(source,newline='',encoding='utf-8') as file:cases=list(csv.DictReader(file))
    safe=[{'id':case['blind_id'],'lat':float(case['latitude']),
           'lon':float(case['longitude']),'link':case['osm_link']} for case in cases]
    encoded=json.dumps(safe,ensure_ascii=True)
    page='''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><title>Bunia blinded road review</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzxCAnJOdXbRxy0AW2LGUz1hQ=" crossorigin="">
    <style>body{font-family:system-ui,sans-serif;margin:0;background:#f8fafc;color:#172033}header{padding:16px 20px}h1{margin:0 0 6px}p{margin:4px 0;color:#475569}#map{height:75vh}footer{padding:12px 20px}a{color:#0c6596}small{color:#607080}</style>
    </head><body><header><h1>Bunia — independent, blinded map review</h1>
    <p>Each pin is a review location, NOT a verified mapping defect. No generator identity or model scores are shown.</p></header>
    <div id="map" role="application" aria-label="Map of anonymous OSM review sites"></div><footer>
    <small>© OpenStreetMap contributors, ODbL · Review only. Verify evidence, physical continuity, permitted travel modes and local context; do not edit based on pins alone.</small>
    </footer><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
    <script>const sites=__DATA__;const map=L.map('map').setView([1.568,30.249],13);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(map);
    const bounds=[];for(const p of sites){const pin=L.circleMarker([p.lat,p.lon],{radius:6,color:'#10647d',fillOpacity:.72});
    const a=document.createElement('a');a.href=p.link;a.target='_blank';a.rel='noopener';a.textContent='Inspect in OpenStreetMap';
    const box=document.createElement('div');const strong=document.createElement('strong');strong.textContent=p.id;
    box.append(strong,document.createElement('br'),a);pin.bindPopup(box).addTo(map);bounds.push([p.lat,p.lon]);}
    if(bounds.length)map.fitBounds(bounds,{padding:[25,25]});</script></body></html>'''
    Path(output).write_text(page.replace('__DATA__',encoded),encoding='utf-8')
    print(f'{len(safe)} anonymous pins written to {output}')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--queue',required=True);p.add_argument('--output',required=True)
    x=p.parse_args();run(x.queue,x.output)
