"""Replay the paper's archived CoRe witnesses against the original CoRe graphs."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path, PurePosixPath

import verify_benchmark as verify


def main():
    here=Path(__file__).resolve().parent
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",type=Path,default=here/"data/reproduced-core-693.jsonl")
    parser.add_argument("--inputs",type=Path,default=here/"benchmark/instances")
    parser.add_argument("--manifest",type=Path,default=here/"benchmark/core-693.csv")
    args=parser.parse_args()
    if not __debug__:
        parser.error("Run without Python optimization so assertions are checked.")
    verify.DATA=args.inputs.resolve()
    with args.manifest.open(encoding="utf-8-sig",newline="") as file:
        keys={tuple(PurePosixPath(s).as_posix() for s in row) for row in csv.reader(file)}
    runs=verify.records(args.run)
    assert len(keys)==693 and keys==runs.keys()
    counts=Counter()
    for graph,endpoints in sorted(keys):
        row=runs[graph,endpoints]["run"]
        adj=verify.graph(graph)
        start,goal=verify.endpoint_masks(endpoints,adj)
        if row["status"]=="found" and row["representation"]=="moves":
            verify.explicit(adj,start,goal,row["moves"],row["length"])
            counts["moves"]+=1
        elif row["status"]=="found":
            assert row["representation"]=="compressed"
            verify.compressed(adj,start,goal,row["witness"],row["length"],1)
            counts["compressed"]+=1
        elif row["status"]=="unreachable":
            if row.get("method")=="grid_phase":
                verify.grid_invariant(adj,start,goal)
                counts["grid"]+=1
            elif row.get("method")=="gated_matching":
                verify.pigeonhole_obstruction(PurePosixPath(endpoints).name,adj,start,goal)
                counts["pigeonhole"]+=1
            else:
                assert len(adj)<=20
                verify.enumerate_component(adj,start,goal)
                counts["exhaustive"]+=1
        else:
            raise ValueError(f"No auditable result for {endpoints}")
    assert counts==dict(moves=490,compressed=137,grid=47,pigeonhole=18,exhaustive=1)
    print(json.dumps(counts,indent=2))


if __name__=="__main__":
    main()
