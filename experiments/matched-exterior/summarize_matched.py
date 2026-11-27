"""Recompute the matched-exterior coverage and scale comparison from raw logs."""
import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import median


def key(row):
    return row["family"],row["pairs"],row["seed"]


def load(path):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    index = {key(row):row for row in rows}
    assert len(index)==len(rows)
    return index


def metrics(rows):
    statuses=Counter(r["status"] for r in rows)
    for r in rows:
        assert all(s==r["status"] for s in r["statuses"])
    return dict(statuses=statuses,median_ms=1000*median(r["seconds"] for r in rows),
                median_peak_kib=median(r["peak_python_bytes"] for r in rows)/1024,
                lengths=sorted({r["length"] for r in rows if r["length"] is not None}),
                profiling_statuses=Counter(r["memory_status"] for r in rows))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original",type=Path,required=True)
    p.add_argument("--same-objective",type=Path,required=True)
    p.add_argument("--large-cap",type=Path)
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    original,same=load(args.original),load(args.same_objective)
    assert len(original)==40 and original.keys()==same.keys()
    for k,row in same.items():
        a=row["implicit"]
        prior=original[k]["solvers"]["implicit"]
        assert (a["core_jumps"],a["length"])==(prior["core_jumps"],prior["length"])
        for b in row["core_only"].values():
            if b["status"]=="complete":
                assert b["core_jumps"]==a["core_jumps"]
    scopes=(("path",4),("path",16),("path",1024),("sparse",24),("sparse",1024),
            ("detour",256),("detour",1024),("frozen",256))
    totals={
        "original":{name:metrics([r["solvers"][name] for r in original.values()])
                    for name in ("implicit","explicit","astar")},
        "same_objective":{cap:metrics([r["core_only"][cap] for r in same.values()])
                          for cap in ("20000","200000")},
        "selected":[dict(family=f,pairs=b,implicit=metrics([r["implicit"] for r in same.values()
                         if key(r)[:2]==(f,b)]),
                         core_only=metrics([r["core_only"]["200000"] for r in same.values()
                         if key(r)[:2]==(f,b)])) for f,b in scopes],
    }
    if args.large_cap:
        totals["large_cap"]=list(load(args.large_cap).values())
    report=json.dumps(totals,indent=2)+"\n"
    if args.output is not None:
        args.output.write_text(report,encoding="utf-8")
    print(report)


if __name__=="__main__":
    main()
