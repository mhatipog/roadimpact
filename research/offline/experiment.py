#!/usr/bin/env python3
"""RoadImpact: offline, read-only, blinded comparison of two OSM topology heuristics.

Neither algorithm establishes a physical road connection or vehicle passability.
All network findings are HYPOTHESES. No OSM edits are made.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math, random, sys, xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
import networkx as nx
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

# LONGITUDE, LATITUDE. Core study extent and wider collection/routing buffer.
CORE = (30.215, 1.53, 30.285, 1.605)
EXTRACT = (30.19, 1.50, 30.31, 1.63)
ROAD_TYPES = {'motorway','trunk','primary','secondary','tertiary','unclassified',
              'residential','living_street','service','track','road',
              'primary_link','secondary_link','tertiary_link','trunk_link','motorway_link'}
NONPUBLIC={'private','no','agricultural','forestry'}
SERVICE_SKIP={'driveway','parking_aisle','drive-through','emergency_access'}
BARRIER={'gate','lift_gate','swing_gate','bollard','block','cycle_barrier','fence','yes'}


def meters(lat,lon):
    # accurate enough at ~20m near equator; coordinates are for geometric ranking only
    ref_lat=(CORE[1]+CORE[3])/2
    return (lon*111320*math.cos(math.radians(ref_lat)),lat*111132)


def allowed(tags):
    return (tags.get('highway') in ROAD_TYPES and tags.get('area')!='yes'
            and not (tags.get('highway')=='service' and tags.get('service') in SERVICE_SKIP)
            and all(tags.get(t,'') not in NONPUBLIC for t in ('motor_vehicle','motorcar','vehicle','access'))
            and tags.get('impassable')!='yes')


def grade(tags):
    if tags.get('bridge','no') not in ('no','') or tags.get('tunnel','no') not in ('no',''):
        return None
    try:
        layer=int(tags.get('layer','0'))
    except ValueError:
        return None
    return layer if layer==0 else None


def parse_osm(filename):
    """Load an already bounded, complete-ways OSM XML. Does NOT access APIs."""
    nodes={}; ways=[]; barrier=set(); noexit=set()
    for _,el in ET.iterparse(filename,events=('end',)):
        if el.tag=='node':
            tags={t.get('k'):t.get('v') for t in el.findall('tag')}
            if el.get('lat') and el.get('lon'):
                nid=int(el.get('id')); nodes[nid]=(float(el.get('lat')),float(el.get('lon')))
                if tags.get('barrier') in BARRIER:barrier.add(nid)
                if tags.get('noexit')=='yes':noexit.add(nid)
        elif el.tag=='way':
            tags={t.get('k'):t.get('v') for t in el.findall('tag')}
            if allowed(tags):
                ways.append((int(el.get('id')),[int(n.get('ref')) for n in el.findall('nd')],tags))
        if el.tag in ('node','way','relation'):
            el.clear()
    return nodes,ways,barrier,noexit


def build_graph(nodes,ways):
    G=nx.Graph(); seg=[]; roads=defaultdict(set); endpoint_way=defaultdict(set)
    way_info={}; ground_nodes=set()
    for way_id,refs,tags in ways:
        refs=[ref for ref in refs if ref in nodes]
        if len(refs)<2:continue
        way_info[way_id]=tags
        for ref in (refs[0],refs[-1]):endpoint_way[ref].add(way_id)
        for a,b in zip(refs,refs[1:]):
            if a==b:continue
            p,q=meters(*nodes[a]),meters(*nodes[b]); d=math.dist(p,q)
            if not .1<d<3000:continue
            G.add_edge(a,b,weight=d)
            roads[a].add(way_id);roads[b].add(way_id)
            seg.append({'way':way_id,'a':a,'b':b,'geom':LineString([p,q]),'tags':tags})
            if grade(tags) is None:ground_nodes.update((a,b))
    return G,seg,roads,endpoint_way,way_info,ground_nodes


def in_core(lat,lon,margin=60):
    left,bottom,right,top=CORE
    dlon=margin/(111320*math.cos(math.radians((bottom+top)/2)))
    dlat=margin/111132
    return left+dlon<lon<right-dlon and bottom+dlat<lat<top-dlat


def orientation(nodes,G,node,point):
    near=next(iter(G.neighbors(node)))
    p=meters(*nodes[node]); prev=meters(*nodes[near])
    incoming=(p[0]-prev[0],p[1]-prev[1])
    vector=(point.x-p[0],point.y-p[1]); norm=math.hypot(*incoming)*math.hypot(*vector)
    return (incoming[0]*vector[0]+incoming[1]*vector[1])/norm if norm else -1


def candidate_record(node, target_way, target, dist, source, nodes, segment=None, cos=None):
    lat,lon=nodes[node]
    # Use source endpoint/node ID and nearest target OSM way; hash stable across repeats.
    identity=f'{node}:{target_way}:{round(target.x,1)}:{round(target.y,1)}'
    return {'candidate_id':'ra-'+hashlib.sha256(identity.encode()).hexdigest()[:14],
            'osm_node_id':node,'target_way_id':target_way,'lat':lat,'lon':lon,
            'gap_m':round(dist,2),'generator':source,
            'orientation':round(cos,3) if cos is not None else None,
            'target_metric':[round(target.x,2),round(target.y,2)]}


def discover(nodes,ways,barrier,noexit,max_gap=30):
    G,segments,roads,endpoint_ways,way_info,grade_nodes=build_graph(nodes,ways)
    if not segments:raise ValueError('Empty eligible road network')
    geoms=[s['geom'] for s in segments]
    spatial=STRtree(geoms)
    endpoints=[nid for nid in G if G.degree(nid)==1 and in_core(*nodes[nid])]
    endpoints.sort()
    base=[];priority=[]; endpoint_pts=[Point(meters(*nodes[n])) for n in endpoints]
    tip_tree=STRtree(endpoint_pts)
    for idx,nid in enumerate(endpoints):
        pt=endpoint_pts[idx]
        if nid in noexit or nid in barrier:continue
        # BASELINE B: naive endpoint-to-other-endpoint geometric closeness, no topology impact.
        for ix in tip_tree.query(pt.buffer(max_gap)):
            other=endpoints[int(ix)]
            if other<=nid or other in barrier or other in noexit:continue
            if other in G[nid]:continue
            gap=pt.distance(endpoint_pts[int(ix)])
            if .5<=gap<=max_gap:
                w=min(endpoint_ways.get(other,{0}))
                rec=candidate_record(nid,w,endpoint_pts[int(ix)],gap,'distance_only',nodes)
                rec['baseline_score']=-gap
                base.append(rec)
        # ROADIMPACT A: projected endpoint-to-segment with continuation/grade/barrier guards.
        if nid in grade_nodes:continue
        for si in spatial.query(pt.buffer(max_gap)):
            s=segments[int(si)]
            if nid in (s['a'],s['b']) or s['way'] in endpoint_ways.get(nid,set()):continue
            if (grade(s['tags']) is None or s['a'] in barrier or s['b'] in barrier
                or s['a'] in grade_nodes or s['b'] in grade_nodes):continue
            q=s['geom'].interpolate(s['geom'].project(pt));gap=pt.distance(q)
            if not .5<=gap<=max_gap:continue
            cos=orientation(nodes,G,nid,q)
            if cos<.45:continue
            rec=candidate_record(nid,s['way'],q,gap,'roadimpact',nodes,cos=cos)
            # No invented benefit probability. Pure evidence-review heuristic.
            rec['priority_score']=round(2*cos+1/(1+gap/10),5)
            priority.append(rec)
    # Remove duplicate hypotheses from same source very near each other; OSM may split ways.
    def collapse(rows,score):
        rows=sorted(rows,key=lambda x:(-x[score],x['candidate_id']))
        taken=[]
        for r in rows:
            if any(math.dist(meters(r['lat'],r['lon']),meters(q['lat'],q['lon']))<20 for q in taken):continue
            taken.append(r)
        return taken
    priority=collapse(priority,'priority_score')
    base=collapse(base,'baseline_score')
    controls=[]
    for nid in sorted(G):
        if G.degree(nid)>=3 and in_core(*nodes[nid]) and nid not in barrier:
            lat,lon=nodes[nid]
            controls.append({'candidate_id':'control-'+str(nid), 'osm_node_id':nid,
                'lat':lat,'lon':lon,'gap_m':None,'generator':'mapped_junction_control',
                'target_way_id':None})
    return {'roadimpact':priority,'distance_only':base,'junction_control':controls,
            'endpoints':endpoints,'road_nodes':G.number_of_nodes(),
            'road_segments':len(segments),'graph_components':nx.number_connected_components(G)}


def cell(r, width=4):
    left,bottom,right,top=CORE
    x=min(width-1,max(0,int((r['lon']-left)/(right-left)*width)))
    y=min(width-1,max(0,int((r['lat']-bottom)/(top-bottom)*width)))
    return (x,y)


def spaced_pick(pool,count,existing,rng,min_separation=35):
    """Grid-stratified, deterministic and spatially diverse; never pad with invented cases."""
    buckets=defaultdict(list)
    for r in pool:buckets[cell(r)].append(r)
    keys=sorted(buckets);rng.shuffle(keys)
    for k in keys:rng.shuffle(buckets[k])
    selected=[]
    while len(selected)<count and any(buckets.values()):
        progressed=False
        for k in keys:
            if not buckets[k]:continue
            r=buckets[k].pop(0)
            if any(math.dist(meters(r['lat'],r['lon']),meters(q['lat'],q['lon']))<min_separation for q in existing+selected):continue
            selected.append(r);progressed=True
            if len(selected)>=count:break
        if not progressed and not any(buckets.values()):break
    return selected


def produce(nodes,ways,barrier,noexit,out,source_sha,seed=20261015,targets=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    found=discover(nodes,ways,barrier,noexit)
    rng=random.Random(seed)
    quotas=targets or {'roadimpact':25,'distance_only':20,'random_endpoint':10,'junction_control':5}
    selected=[]
    for name in ('roadimpact','distance_only'):
        selected.extend(spaced_pick(found[name],quotas[name],selected,rng))
    random_endpoints=[{'candidate_id':f'rand-{nid}','osm_node_id':nid,'lat':nodes[nid][0],
                       'lon':nodes[nid][1],'gap_m':None,'generator':'random_endpoint'}
                      for nid in found['endpoints']]
    rng.shuffle(random_endpoints)
    selected.extend(spaced_pick(random_endpoints,quotas['random_endpoint'],selected,rng))
    selected.extend(spaced_pick(found['junction_control'],quotas['junction_control'],selected,rng))
    # Blind IDs unrelated to location/source; shuffle AFTER balanced selection.
    ordered=selected[:];rng.shuffle(ordered)
    for i,r in enumerate(ordered):r['blind_id']=f'R{(i+1):03d}-{rng.randrange(0,16**5):05x}'
    mapids={r['candidate_id']:r['blind_id'] for r in ordered}
    private=[]
    for r in ordered:
        sources=[]
        for method in ('roadimpact','distance_only'):
            if any(math.dist(meters(r['lat'],r['lon']),meters(x['lat'],x['lon']))<25
                   for x in found[method]):sources.append(method)
        private.append({**r,'matched_generators':sources,
                        'sampling_arm':r['generator'],'ground_truth':'UNREVIEWED'})
    def dump_csv(name,rows,fields):
        with (out/name).open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
    # Reviewer file cannot reveal the detector, classification, estimated gap, priority or score.
    public=[]
    for r in ordered:
        public.append({'blind_id':r['blind_id'],'latitude':f"{r['lat']:.7f}",
                       'longitude':f"{r['lon']:.7f}",
                       'osm_link':f"https://www.openstreetmap.org/#map=19/{r['lat']:.7f}/{r['lon']:.7f}",
                       'road_connection':'', 'motorcar_access':'','evidence_link':'',
                       'imagery_date':'','uncertain_reason':'','minutes_spent':'','reviewer_id':''})
    dump_csv('BLIND_review_queue.csv',public,list(public[0]) if public else ['blind_id'])
    dump_csv('PRIVATE_allocation.csv',private,['blind_id','candidate_id','osm_node_id','target_way_id',
               'lat','lon','generator','sampling_arm','matched_generators','gap_m',
               'orientation','priority_score','baseline_score','ground_truth'])
    universe={key:found[key] for key in ('roadimpact','distance_only')}
    (out/'candidate_universe.json').write_text(json.dumps(universe,indent=2,sort_keys=True)+'\n')
    snapshot={'osm_xml_sha256':source_sha,'seed':seed,'study_core_lonlat':CORE,
              'extract_extent_lonlat':EXTRACT,'node_count':found['road_nodes'],
              'road_segment_count':found['road_segments'],'components':found['graph_components'],
              'number_unfiltered_endpoints':len(found['endpoints']),
              'candidate_universe_counts':{k:len(v) for k,v in universe.items()},
              'sampling_targets':quotas,'selected_counts':dict(Counter(r['generator'] for r in selected)),
              'selected_total':len(selected),
              'design':'Topologically screened endpoint-to-segment vs naive endpoint-to-endpoint; spatially stratified controls',
              'blinding':'Reviewers receive only BLIND_review_queue.csv, never allocation or candidate_universe.',
              'ground_truth_count':0,
              'warning':'NO VERIFIED DEFECTS, NO REAL PRECISION CLAIM, NO AUTOMATED OSM EDITS'}
    (out/'manifest.json').write_text(json.dumps(snapshot,indent=2,sort_keys=True)+'\n')
    print(json.dumps(snapshot,sort_keys=True))
    return snapshot


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--osm',required=True,help='bounded complete-ways OSM XML snapshot')
    ap.add_argument('--output',default='outputs/bunia-v1')
    ap.add_argument('--seed',type=int,default=20261015)
    args=ap.parse_args()
    data=Path(args.osm).read_bytes();source_hash=hashlib.sha256(data).hexdigest()
    nodes,ways,barrier,noexit=parse_osm(args.osm)
    produce(nodes,ways,barrier,noexit,args.output,source_hash,args.seed)

if __name__=='__main__':main()
