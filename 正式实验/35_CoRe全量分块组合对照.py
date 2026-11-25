"""Run the complete official CoRe list under a fixed local comparison protocol."""
import argparse
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import csv
from itertools import combinations
import json
from pathlib import Path, PurePosixPath
from time import perf_counter
from urllib.error import URLError
from importlib.util import module_from_spec, spec_from_file_location

HERE=Path(__file__).resolve().parent
spec=spec_from_file_location("pilot",HERE/"33_CoRe非饱和分块对照.py")
pilot=module_from_spec(spec)
spec.loader.exec_module(pilot)
ev,p=pilot.ev,pilot.p
structure=pilot.load("26_结构识别重编号.py")
MODES=("beam8","full","face","new")
BUDGET=1.0
EDGE_CAP=1_000_000


def partition(case):
    if case.n <= 500 and len(case.edges) <= 2*case.n and case.n % 5 == 4:
        try:
            groups=structure.recognize(case)
        except ValueError:
            groups=None
        if groups is not None:
            return groups,"recognized"
    if 5*len(case.start) < case.n:
        # Every nonempty block has capacity at least one.
        return None,"capacity_lower_bound"
    groups=[list(range(i,min(i+5,case.n))) for i in range(0,case.n,5)]
    return groups,"consecutive"


def certified(groups,adj,start,deadline):
    if groups is None:
        return False
    for group in groups:
        k=(start&p.mask_of(group)).bit_count()
        for vertices in combinations(group,k+1):
            mask=p.mask_of(vertices)
            if not any(adj[v]&mask for v in vertices):
                return False
        if perf_counter()>=deadline:
            raise p.SearchTimeout(0,0)
    return True


def run(case,mode,start,goal):
    began=perf_counter()
    deadline=began+BUDGET
    branch=mode
    try:
        if (goal & ~start).bit_count() <= 1:
            path=[start] if start==goal else [start,goal]
            result=dict(status="found",path=path,length=len(path)-1,candidates=0)
        elif mode=="beam8":
            path,count,expanded,_=p.solve(case,2048,"llm_rule",8,772,deadline=deadline)
            result=dict(status="found" if path else "no_path_found",path=path,
                        length=len(path)-1 if path else None,candidates=count,expanded=expanded)
        else:
            adj=case.adjacency()
            # Bound bigint storage as well as the number of configurations.
            state_limit=min(100000,32*1024**2//(128+(case.n+7)//8))
            residual_limit=state_limit
            if mode=="new":
                groups,group_method=partition(case)
                if certified(groups,adj,start,deadline):
                    branch="contract"
                    def check(states):
                        if states>=state_limit or perf_counter()>=deadline:
                            raise p.SearchTimeout(0,0)
                    path,layers=structure.m.solve(case,groups,optimize_lift=True,restrict_local=True,
                                                  restrict_prefix=True,check=check)
                    result=dict(status="found" if path else "unreachable",path=path,
                                length=len(path)-1 if path else None,layers=layers)
                    result["partition"]=group_method
                else:
                    branch="face"
                    result=pilot.exact(case,"face",None,adj,deadline=deadline,state_limit=state_limit,
                                       residual_limit=residual_limit)
                    result["partition"]=group_method
            else:
                result=pilot.exact(case,mode,None,adj,deadline=deadline,state_limit=state_limit,
                                   residual_limit=residual_limit)
    except p.SearchTimeout as error:
        result=dict(status="budget",path=None,length=None,candidates=error.checked)
    elapsed=perf_counter()-began
    if elapsed>BUDGET and result["status"]!="budget":
        result.update(status="budget",path=None,length=None)
    result.update(seconds=elapsed,branch=branch)
    return result


@dataclass(frozen=True)
class CompactCase:
    n: int
    start: tuple
    target: tuple
    neighbors: tuple

    def adjacency(self):
        return self.neighbors


@lru_cache(maxsize=1)
def load_compact_graph(path):
    # Pack rows into bytes during parsing, avoiding large tuples of Python edge objects.
    with path.open("rb") as source:
        header=next(line.split() for line in source if line.startswith(b"p "))
        n,expected=map(int,header[-2:])
        masks=[bytearray((n+7)//8) for _ in range(n)]
        count=0
        for line in source:
            if not line.startswith(b"e "):
                continue
            _,a,b=line.split()
            u,v=int(a)-1,int(b)-1
            assert 0<=u<n and 0<=v<n and u!=v
            masks[u][v//8] |= 1<<(v%8)
            masks[v][u//8] |= 1<<(u%8)
            count+=1
        assert count==expected
        adj=tuple(int.from_bytes(row,"little") for row in masks)
        assert sum(row.bit_count() for row in adj)==2*expected
        return adj,count


def load_large_case(g,d):
    adj,edge_count=load_compact_graph(ev.reference.download(g))
    ends={}
    for line in ev.reference.download(d).read_text(encoding="utf-8-sig").splitlines():
        values=line.split()
        if values and values[0] in ("s","t"):
            ends[values[0]]=tuple(int(v)-1 for v in values[1:])
    assert len(ends["s"])==len(ends["t"])
    for group in ends.values():
        assert len(group)==len(set(group)) and all(0<=i<len(adj) for i in group)
        state=p.mask_of(group)
        assert all(not adj[i]&state for i in group)
    return CompactCase(len(adj),ends["s"],ends["t"],adj),edge_count


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--edge-cap",type=int,default=EDGE_CAP)
    parser.add_argument("--output",type=Path,default=HERE/"CoRe全量分块组合对照.jsonl")
    parser.add_argument("--only-oversized",action="store_true")
    args=parser.parse_args()
    author=ev.reference.author_results()
    with (ev.DATA/"official_693.csv").open(encoding="utf-8-sig",newline="") as file:
        suite=[tuple(map(PurePosixPath,row)) for row in csv.reader(file)]
    assert len(set(suite))==len(suite)==693
    developed={(str(g),str(d)) for _,g,d in ev.reference.selection()}
    completed=set()
    if args.output.exists():
        with args.output.open(encoding="utf-8") as file:
            for line in file:
                previous=json.loads(line)
                assert previous["edge_cap"]==args.edge_cap and previous["budget"]==BUDGET
                completed.add((previous["graph"],previous["endpoints"]))
    counts=Counter()
    with args.output.open("a",encoding="utf-8",buffering=1) as out:
        for index,(graph,ends) in enumerate(suite):
            key=(str(graph),str(ends))
            if key in completed:
                continue
            row=author[graph.name,ends.name]
            oversized=bool(row["edges"]) and int(row["edges"])>EDGE_CAP
            if args.only_oversized and not oversized:
                continue
            ref=int(row["transition_length"]) if row["status"]=="OK" and row["result"]=="YES" and row["transition_length"] else None
            record=dict(graph=key[0],endpoints=key[1],family=graph.parent.name,development=key in developed,
                        srip_status=row["status"],srip_length=ref,edge_cap=args.edge_cap,budget=BUDGET,runs={})
            try:
                if row["edges"] and int(row["edges"])>args.edge_cap:
                    raise ev.reference.EdgeLimitExceeded(row["edges"])
                if args.only_oversized:
                    case,edge_count=load_large_case(graph,ends)
                    assert edge_count==int(row["edges"])
                else:
                    case=ev.reference.load_case((graph.parent.name,graph,ends),args.edge_cap)
                    edge_count=len(case.edges)
            except ev.reference.EdgeLimitExceeded as error:
                record.update(input_status="edge_cap",detail=str(error))
            except (OSError,URLError,UnicodeError) as error:
                record.update(input_status="input_error",detail=str(error))
            else:
                start,goal=map(p.mask_of,(case.start,case.target))
                record.update(input_status="ready",n=case.n,k=len(case.start),edges=edge_count)
                shift=index%len(MODES)
                for mode in MODES[shift:]+MODES[:shift]:
                    record["runs"][mode]=run(case,mode,start,goal)
                if any(r["path"] for r in record["runs"].values()):
                    adj=case.adjacency()
                    for result in record["runs"].values():
                        path=result["path"]
                        if path is not None:
                            ev.validate(case,result,10**9,ref,adj)
                            result["moves"]=[[(a&~b).bit_length(),(b&~a).bit_length()] for a,b in zip(path,path[1:])]
                        del result["path"]
            out.write(json.dumps(record,ensure_ascii=False)+"\n")
            counts[record["input_status"]]+=1
            if (index+1)%25==0 or index+1==len(suite):
                print(f"{index+1}/{len(suite)} {dict(counts)}",flush=True)


if __name__=="__main__":
    main()
