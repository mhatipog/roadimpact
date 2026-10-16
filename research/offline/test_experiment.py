import csv, json, tempfile, unittest, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import experiment as e


def fixture():
    # Artificial candidate geometries: never asserted to be real-world errors.
    nodes={};ways=[]
    nid=100
    for row in range(3):
        for col in range(4):
            lat=1.556 + row*.0034
            lon=30.242 + col*.0034
            # first way: eastward 20m, next: north/south 20m away
            ids=[]
            for la,lo in ((lat,lon),(lat,lon+.00012)):
                nodes[nid]=(la,lo);ids.append(nid);nid+=1
            ways.append((nid+10000,ids,{'highway':'residential'}))
            ids=[]
            for la,lo in ((lat-.00012,lon+.00026),(lat+.00012,lon+.00026)):
                nodes[nid]=(la,lo);ids.append(nid);nid+=1
            ways.append((nid+10000,ids,{'highway':'residential'}))
    return nodes,ways


class ExperimentTests(unittest.TestCase):
    def test_directional_detector_and_baseline(self):
        nodes,ways=fixture()
        found=e.discover(nodes,ways,set(),set())
        self.assertGreaterEqual(len(found['roadimpact']),8)
        self.assertGreaterEqual(len(found['distance_only']),8)
        self.assertEqual(found['road_nodes'],48)
        self.assertTrue(all(x['generator']=='roadimpact' for x in found['roadimpact']))
        self.assertTrue(all(x['orientation']>=.45 for x in found['roadimpact']))

    def test_nonpublic_ways_are_excluded(self):
        self.assertFalse(e.allowed({'highway':'service','access':'private'}))
        self.assertFalse(e.allowed({'highway':'service','service':'driveway'}))
        self.assertFalse(e.allowed({'highway':'footway'}))
        self.assertTrue(e.allowed({'highway':'residential'}))

    def test_grade_separation(self):
        self.assertIsNone(e.grade({'bridge':'yes'}))
        self.assertIsNone(e.grade({'layer':'1'}))
        self.assertEqual(e.grade({'highway':'residential'}),0)

    def test_blind_queue_no_leak_and_deterministic(self):
        nodes,ways=fixture()
        quotas={'roadimpact':6,'distance_only':4,'random_endpoint':2,'junction_control':1}
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/'a'; b=Path(d)/'b'
            x=e.produce(nodes,ways,set(),set(),a,'hash',targets=quotas)
            y=e.produce(nodes,ways,set(),set(),b,'hash',targets=quotas)
            self.assertEqual((a/'BLIND_review_queue.csv').read_bytes(),(b/'BLIND_review_queue.csv').read_bytes())
            self.assertEqual(x,y)
            self.assertEqual(x['ground_truth_count'],0)
            reviewer=(a/'BLIND_review_queue.csv').read_text()
            self.assertNotIn('roadimpact',reviewer.lower())
            self.assertNotIn('distance_only',reviewer.lower())
            self.assertNotIn('target_way',reviewer.lower())
            self.assertIn('sampling_arm',(a/'PRIVATE_allocation.csv').read_text())
            ids=[r['blind_id'] for r in csv.DictReader(reviewer.splitlines())]
            self.assertEqual(len(ids),len(set(ids)))
            self.assertGreater(len(ids),7)

    def test_xml_offline_parser(self):
        text='''<osm version="0.6"><node id="1" lat="1.558" lon="30.249"/>
        <node id="2" lat="1.558" lon="30.2491"><tag k="barrier" v="gate"/></node>
        <way id="4"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/></way></osm>'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'f.osm';p.write_text(text)
            nodes,ways,barriers,noexit=e.parse_osm(p)
            self.assertEqual(len(nodes),2)
            self.assertEqual(len(ways),1)
            self.assertIn(2,barriers)

if __name__=='__main__':unittest.main()
