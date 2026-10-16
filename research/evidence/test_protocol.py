"""Unittest suite for the GitHub-runnable RoadImpact evidence pilot."""
import copy
import json
from pathlib import Path
import unittest

from triage import assess, run, time, usable_tile, mode
from benchmark import benchmark, ensure_labels

DIR=Path(__file__).parent
NOW=time("2026-10-15T21:30:00+02:00")


class TestEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=json.loads((DIR/"bunia-cases.json").read_text())["cases"]

    def test_bunia_what_is_really_known(self):
        a,b=(assess(c,NOW) for c in self.raw)
        self.assertEqual(a["decision"],"HUMAN_REVIEW")
        self.assertEqual(b["decision"],"DEFER_FOR_BETTER_EVIDENCE")
        self.assertEqual(a["max_usable_zoom"],18)
        self.assertEqual(b["max_usable_zoom"],18)
        for c in (a,b):
            self.assertFalse(c["confirmed_connection"])
            self.assertFalse(c["eligible_for_osm_edit"])
            self.assertTrue(c["current_topology_gap"])
            self.assertIn("IMAGERY_PREDATES_OSM_EDIT",c["reasons"])
            self.assertIn("LOCAL_ALIGNMENT_UNVERIFIED",c["reasons"])
            self.assertIn("EMERGENCY_CONNECTIVITY_NOT_ESTABLISHED",c["reasons"])
        self.assertIn("CORRIDOR_OCCLUDED",b["reasons"])

    def test_empty_placeholder_is_not_evidence(self):
        self.assertFalse(usable_tile({"bytes":2521,"pixel_std":5.37}))
        self.assertTrue(usable_tile({"bytes":18000,"pixel_std":42}))
        self.assertFalse(usable_tile({"bytes":20000,"pixel_std":0}))

    def test_unknown_vehicle_access_is_not_allowed(self):
        tags={"highway":"service","service":"alley"}
        self.assertEqual(mode(tags,"motorcar"),"unknown")
        self.assertEqual(mode(tags,"emergency"),"unknown")
        self.assertEqual(mode({"highway":"footway"},"motorcar"),"deny")

    def test_missing_reference_causes_defer(self):
        c=copy.deepcopy(self.raw[0])
        c["osm"]["target_exists"]=False
        self.assertEqual(assess(c,NOW)["decision"],"DEFER_FOR_BETTER_EVIDENCE")

    def test_better_imagery_does_not_prove_vehicle_passage(self):
        c=copy.deepcopy(self.raw[0])
        c["imagery"].update(acquired_at="20261014",locally_registered=True,control_points=4)
        c["visual_observation"]="visually_continuous"
        r=assess(c,NOW)
        self.assertNotIn("IMAGERY_PREDATES_OSM_EDIT",r["reasons"])
        self.assertFalse(r["eligible_for_osm_edit"])

    def test_not_an_impact_benchmark(self):
        cases=[assess(c,NOW) for c in self.raw]
        report=benchmark({"cases":cases})
        self.assertEqual(report["real_cases"],2)
        self.assertEqual(report["adjudicated"],0)
        self.assertIsNone(report["evidence_ranking"]["precision"])
        self.assertIsNone(report["distance_baseline"]["precision"])
        self.assertFalse(report["reportable_real_effectiveness"])
        self.assertEqual(report["unfilled_review_slots"],198)
        self.assertEqual(report["review_queue"][0],"bunia-20261015-a")

    def test_cannot_invent_confirmed_osm_correction(self):
        labels=[{"case_id":"bunia-20261015-a","ground_truth":"accepted_osm_correction"}]
        with self.assertRaisesRegex(ValueError,"independent"):
            benchmark({"cases":[assess(c,NOW) for c in self.raw]},labels)

    def test_label_needs_osm_changeset(self):
        labels=[{"case_id":"bunia-20261015-a","ground_truth":"accepted_osm_correction",
                 "independent_reviewers":["one","two"],"adjudicator":"three",
                 "evidence_url":"https://www.openstreetmap.org/way/1",
                 "adjudicated_at":"2026-10-15T22:00:00Z"}]
        with self.assertRaisesRegex(ValueError,"changeset"):
            benchmark({"cases":[assess(c,NOW) for c in self.raw]},labels)

    def test_partial_labels_not_precision(self):
        labels=[{"case_id":"bunia-20261015-a","ground_truth":"accepted_osm_correction",
                 "independent_reviewers":["one","two"],"adjudicator":"three",
                 "evidence_url":"https://www.openstreetmap.org/way/1",
                 "adjudicated_at":"2026-10-15T22:00:00Z",
                 "changeset_url":"https://www.openstreetmap.org/changeset/42"}]
        r=benchmark({"cases":[assess(c,NOW) for c in self.raw]},labels)
        self.assertIsNone(r["evidence_ranking"]["precision"])


if __name__=="__main__":
    unittest.main()
