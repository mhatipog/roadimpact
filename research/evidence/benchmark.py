"""RoadImpact benchmark harness: data leakage and missing labels are explicit.

Blind adjudication is REQUIRED before any real effectiveness statistic.
"""
import argparse
import json
from pathlib import Path
from collections import Counter

ACCEPTED="accepted_osm_correction"
REJECTED="rejected_connection"
UNKNOWN="unreviewed"
LABELS={ACCEPTED,REJECTED,UNKNOWN,"inconclusive"}


def ensure_labels(rows):
    for r in rows:
        label=r.get("ground_truth",UNKNOWN)
        if label not in LABELS:
            raise ValueError("unknown ground truth label")
        if label!=UNKNOWN:
            reviewers=r.get("independent_reviewers",[])
            if (len(set(reviewers))<2 or not r.get("adjudicator")
                or not str(r.get("evidence_url","")).startswith("https://")
                or not r.get("adjudicated_at")):
                raise ValueError("independent reviews/evidence/adjudication required")
            if label==ACCEPTED and not str(r.get("changeset_url","")).startswith(
                  "https://www.openstreetmap.org/changeset/"):
                raise ValueError("an accepted correction needs an actual OSM changeset")


def precision_at_k(rows,k,score):
    ordered=sorted(rows,key=lambda r:(-r[score],r["case_id"]))[:k]
    labels=[r["ground_truth"] for r in ordered]
    resolved=[l for l in labels if l in (ACCEPTED,REJECTED)]
    full=bool(ordered) and len(resolved)==len(ordered)
    return {"requested_k":k,"inspected":len(ordered),
            "decisively_labelled":len(resolved),
            "accepted":resolved.count(ACCEPTED),
            "precision":len([x for x in labels if x==ACCEPTED])/len(ordered) if full else None,
            "coverage":len(resolved)/len(ordered) if ordered else None}


def benchmark(triage, annotations=None, k=20):
    cases=triage["cases"]
    label_by_id={a["case_id"]:a for a in (annotations or [])}
    unexpected=set(label_by_id)-{c["case_id"] for c in cases}
    if unexpected:
        raise ValueError("annotations contain unknown case IDs")
    joined=[]
    for c in cases:
        label=dict(label_by_id.get(c["case_id"],{}))
        row={"case_id":c["case_id"],
             "heuristic":float(c["score_heuristic_NOT_probability"]),
             "distance_only":-float(c["gap_m"]),
             "ground_truth":label.get("ground_truth",UNKNOWN),**label}
        joined.append(row)
    ensure_labels(joined)
    counts=Counter(row["ground_truth"] for row in joined)
    resolved=counts[ACCEPTED]+counts[REJECTED]
    queue=sorted(joined,key=lambda r:(-r["heuristic"],r["case_id"]))
    # 200 review slots do not mean 200 real observations.
    return {"schema":"roadimpact-benchmark-v04","real_cases":len(joined),
        "adjudicated":resolved,"accepted_osm_edits":counts[ACCEPTED],
        "rejected":counts[REJECTED],"unreviewed":counts[UNKNOWN],
        "confidence":"INSUFFICIENT_INDEPENDENT_LABELS" if resolved<100 or
                     counts[ACCEPTED]<15 or counts[REJECTED]<15 else
                     "REQUIRES_SAMPLING_FRAME_AND_REVIEWER_TRIAL",
        "reportable_real_effectiveness":False,
        "evidence_ranking":precision_at_k(joined,min(k,len(joined)),"heuristic"),
        "distance_baseline":precision_at_k(joined,min(k,len(joined)),"distance_only"),
        "review_queue":[x["case_id"] for x in queue],
        "unfilled_review_slots":max(0,200-len(joined)),
        "scope":"Both algorithms evaluate the SAME candidates. This does not establish causal mapper productivity gains.",
        "note":"NO synthetic labels; NO claims about real roads. Source imagery is not published."}


def main(input_path,output_path,labels=None):
    data=json.loads(Path(input_path).read_text())
    annotations=json.loads(Path(labels).read_text())["annotations"] if labels else []
    report=benchmark(data,annotations)
    p=Path(output_path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"real_cases":report["real_cases"],"adjudicated":report["adjudicated"],
                      "real_precision":report["evidence_ranking"]["precision"],
                      "status":report["confidence"]}))
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--input",default="research/roadimpact-evidence-v04/output/triage.json")
    p.add_argument("--output",default="research/roadimpact-evidence-v04/output/benchmark.json")
    p.add_argument("--labels",default=None)
    args=p.parse_args()
    main(args.input,args.output,args.labels)
