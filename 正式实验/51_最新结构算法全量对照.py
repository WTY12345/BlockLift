"""Integrated structural Token Jumping solver and a paired CoRe experiment."""
import argparse
import csv
import json
from collections import Counter
from importlib.util import module_from_spec, spec_from_file_location
from math import isqrt
from pathlib import Path, PurePosixPath
from time import perf_counter

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "CoRe最新结构算法全量.jsonl"
MODES = ("beam", "previous", "latest")
BUDGET = 1.0
PUBLIC = ("v47-d1-d2", "nuasp", "paris", "reconfaigeration")


def load(filename):
    path = HERE / filename
    spec = spec_from_file_location(path.stem, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


twins = load("46_闭邻域等价压缩.py")
queen = load("49_皇后图空行空列搜索.py")
gate = load("50_鸽笼中转点分解.py")
alg, ev, p = twins.alg, twins.ev, twins.p


def solve(case, family, budget=BUDGET, *, beam_limit=alg.DEFAULT_BEAM_LIMIT):
    started = perf_counter()
    deadline = started + budget
    start, goal = map(p.mask_of, (case.start,case.target))
    attempts = []
    if (goal & ~start).bit_count() <= 1:
        path = [start] if start == goal else [start, goal]
        return dict(status="found",path=path,seconds=perf_counter()-started,branch="direct",attempts=attempts)
    n = isqrt(case.n)
    if family == "queen" and n*n == case.n and len(case.start) == n-1:
        board = queen.Board(n,goal)
        strategies = [(32,True),(16,False)] if n<=20 else [(16,False),(48,True)]
        for width, reverse in strategies:
            now = perf_counter()
            if now >= deadline:
                break
            share = 0.75 if width == strategies[0][0] else 0.5
            path, work = queen.search(board,start,width,width,now+share*(deadline-now),4,reverse)
            attempts.append(dict(method="queen",work=work,width=width,reverse=reverse))
            if path is not None:
                board.validate(path,start)
                if perf_counter()<=deadline:
                    return dict(status="found",path=path,seconds=perf_counter()-started,branch="queen",attempts=attempts)
                break
    elif family == "ph-isr" and case.n<=500:
        result = gate.solve(case,max_assignments=512)
        attempts.append(dict(method="gateway",status=result["status"]))
        if result["status"] in ("found","unreachable") and perf_counter()<=deadline:
            return dict(status=result["status"],path=result["path"],seconds=perf_counter()-started,
                        branch="gateway",attempts=attempts)
    elif case.n<=500 or (case.n<=2000 and len(case.edges)<=20*case.n):
        # Avoid constructing a replacement instance on the common no-equivalent-vertices path.
        adj = case.adjacency()
        closed = {values | (1<<v) for v,values in enumerate(adj)}
        wider_block = twins.capacity_two_partition(case,adj)
        if len(closed)<case.n or wider_block is not None:
            remaining = deadline-perf_counter()
            if remaining>0:
                result=twins.solve(case,budget=remaining,beam_limit=beam_limit)
                attempts.append(dict(method=result["method"],classes=result["classes"]))
                if result["status"] in ("found","unreachable") and perf_counter()<=deadline:
                    return dict(status=result["status"],path=result["path"],seconds=perf_counter()-started,
                                branch=result["method"],attempts=attempts)
    remaining = deadline-perf_counter()
    if remaining<=0:
        return dict(status="budget",path=None,seconds=perf_counter()-started,branch="adaptive",attempts=attempts)
    result=alg.solve(case,"rule",budget=remaining,beam_limit=beam_limit)
    elapsed=perf_counter()-started
    return dict(status=result["status"] if elapsed<=budget else "budget",
                path=result["path"] if elapsed<=budget else None,seconds=elapsed,
                branch="adaptive",attempts=attempts+result["attempts"])


def public_records():
    records={}
    with (ev.DATA/"作者完整结果.csv").open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            if row["solver"] in PUBLIC:
                records.setdefault((row["col_file"],row["dat_file"]),{})[row["solver"]]=row
    return records


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--budget",type=float,default=BUDGET)
    parser.add_argument("--output",type=Path,default=OUTPUT)
    parser.add_argument("--uncapped-beam",action="store_true",help="remove the beam depth limit")
    args=parser.parse_args()
    beam_limit=None if args.uncapped_beam else alg.DEFAULT_BEAM_LIMIT
    if args.uncapped_beam and args.output==OUTPUT:
        parser.error("use a separate output file when changing the beam limit")
    if args.budget<=0:
        parser.error("budget must be positive")
    if args.budget!=BUDGET and args.output==OUTPUT:
        parser.error("use a separate output file for another budget")
    refs=public_records()
    with (ev.DATA/"official_693.csv").open(encoding="utf-8-sig",newline="") as f:
        suite=[tuple(map(PurePosixPath,row)) for row in csv.reader(f)]
    assert len(suite)==len(set(suite))==693
    developed={(str(g),str(d)) for _,g,d in ev.reference.selection()}
    tuned=set()
    for name in ("CoRe已知漏解放宽时间.jsonl",):
        for line in (HERE/name).read_bytes().splitlines():
            previous=json.loads(line)
            if previous["result"]["status"]!="found":
                tuned.add((previous["graph"],previous["endpoints"]))
    done=set()
    if args.output.is_file():
        for line in args.output.read_bytes().splitlines():
            previous=json.loads(line)
            if previous.get("beam_limit",alg.DEFAULT_BEAM_LIMIT)!=beam_limit:
                raise ValueError("An existing result has a different beam limit")
            if previous.get("budget_seconds",BUDGET)!=args.budget:
                raise ValueError("An existing result has a different budget")
            done.add((previous["graph"],previous["endpoints"]))
    totals={name:Counter() for name in MODES}
    with args.output.open("a",encoding="utf-8",buffering=1) as dest:
        for index,(g,d) in enumerate(suite):
            key=(str(g),str(d))
            if key in done:
                continue
            source=refs[g.name,d.name]
            family=g.parent.name
            case=(alg.core.load_large_case(g,d)[0] if int(source[PUBLIC[0]]["edges"] or 0)>1_000_000
                  else ev.reference.load_case((family,g,d)))
            public={}
            for name,row in source.items():
                length=(int(row["transition_length"]) if row["result"]=="YES" and row["transition_length"] else None)
                public[name]=dict(status=row["status"],decision=row["result"],length=length,
                                  cpu_seconds=float(row["cpu_time_s"]) if row["cpu_time_s"] else None)
            exact={r["length"] for name,r in public.items()
                   if name!="paris" and r["length"] is not None and r["status"]=="OK"}
            assert len(exact)<=1
            known=next(iter(exact),None)
            shift=index%len(MODES)
            results={}
            for name in MODES[shift:]+MODES[:shift]:
                results[name]=(solve(case,family,budget=args.budget,beam_limit=beam_limit) if name=="latest" else
                               alg.solve(case,"rule" if name=="previous" else "beam",budget=args.budget,beam_limit=beam_limit))
            if any(r["path"] is not None for r in results.values()):
                adj=case.adjacency()
            for name,result in results.items():
                path=result.pop("path")
                result["length"]=len(path)-1 if path is not None else None
                if path is not None:
                    ev.validate(case,{"path":path,"length":result["length"]},10**9,known,adj)
                    result["moves"]=[[(a&~b).bit_length(),(b&~a).bit_length()] for a,b in zip(path,path[1:])]
                totals[name][result["status"]]+=1
            dest.write(json.dumps(dict(graph=key[0],endpoints=key[1],family=family,n=case.n,k=len(case.start),
                                       original_development=key in developed,targeted_development=key in tuned,
                                       reference_exact=known,public=public,runs=results,budget_seconds=args.budget,beam_limit=beam_limit),ensure_ascii=False)+"\n")
            if (index+1)%25==0 or index+1==len(suite):
                print(index+1,{name:dict(v) for name,v in totals.items()},flush=True)


if __name__ == "__main__":
    main()
