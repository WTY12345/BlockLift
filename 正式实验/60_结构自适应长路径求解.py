"""Integrated long-path solver built on certified contractions and compact lifting."""
from itertools import combinations
from pathlib import Path,PurePosixPath
from importlib.util import module_from_spec,spec_from_file_location
from time import perf_counter
import json

HERE=Path(__file__).resolve().parent
spec=spec_from_file_location("ordering",HERE/"59_块交互顺序选择.py")
ordering=module_from_spec(spec)
spec.loader.exec_module(ordering)
packed,latest,p,ev=ordering.packed,ordering.latest,ordering.p,ordering.ev


def saturated(case,blocks,adj):
    if {v for block in blocks for v in block}!=set(range(case.n)):
        return False
    if sum(map(len,blocks))!=case.n:
        return False
    start=p.mask_of(case.start)
    for block in blocks:
        count=(start&p.mask_of(block)).bit_count()
        for group in combinations(block,count+1):
            if not any(adj[u]&(1<<v) for u,v in combinations(group,2)):
                return False
    return True


def solve(case,family,budget=300):
    began=perf_counter()
    deadline=began+budget
    # Preserve the fast path for instances already covered by the earlier solver.
    fast=latest.solve(case,family,budget=min(1.0,budget*0.2))
    if fast["status"] in ("found","unreachable"):
        return dict(fast,method="earlier_fast_path",seconds=perf_counter()-began)
    if family not in {"sp","power","power_wide","power_wider","exp_instance"}:
        if perf_counter()>=deadline:
            return dict(fast,method="fast_budget",seconds=perf_counter()-began)
        result=latest.solve(case,family,budget=deadline-perf_counter())
        return dict(result,method="earlier_fallback",seconds=perf_counter()-began)

    compact,classes,index=latest.twins.quotient(case)
    adj=compact.adjacency()
    start,goal=map(p.mask_of,(compact.start,compact.target))
    choices=[]
    if family=="sp":
        blocks=latest.twins.capacity_two_partition(compact,adj)
        if blocks is not None:
            blocks,probe=packed.choose_direction(compact,blocks)
            choices=[(probe["order"],blocks)]
    elif family=="exp_instance":
        options,_=latest.alg.assess(compact,adj,start,goal,min(deadline,perf_counter()+1))
        original_blocks=options.get(0)
        if original_blocks is not None:
            choices=((name,[original_blocks[i] for i in order])
                     for name,order in ordering.candidates(original_blocks,adj,start,goal))
    else:
        try:
            choices=[("recognized",latest.alg.core.structure.recognize(compact))]
        except ValueError:
            pass
    runs=[]
    seen=set()
    for name,blocks in choices:
        identity=tuple(map(tuple,blocks))
        if identity in seen:
            continue
        seen.add(identity)
        remaining=deadline-perf_counter()
        if remaining<=0:
            break
        if not saturated(compact,blocks,adj):
            continue
        pair_cap=180_000 if family=="exp_instance" else 250_000
        result=packed.solve(compact,blocks,seconds=min(30,remaining),pair_cap=pair_cap)
        path=result.pop("path")
        runs.append(dict(order=name,**result))
        if result["status"]=="unreachable" or path is not None:
            if path is not None:
                path=latest.twins.lift(case,path,index,[g[0] for g in classes])
            elapsed=perf_counter()-began
            if elapsed>budget:
                break
            return dict(status=result["status"],path=path,method="compact_contraction",
                        branch=family,order=name,seconds=elapsed,attempts=runs)
    remaining=deadline-perf_counter()
    if remaining>0:
        fallback=latest.solve(case,family,budget=remaining)
        return dict(fallback,method="earlier_fallback",seconds=perf_counter()-began,structural_attempts=runs)
    return dict(status="budget",path=None,method="long_path_budget",seconds=perf_counter()-began,attempts=runs)


def main():
    official=json.loads((HERE/"CoRe官方赛道与新版结果交叉核验.json").read_bytes())
    known={r["name"]:r["length"] for r in official["only_others"]}
    prior=json.loads((HERE/"ddreconf十五例官方日志耗时.json").read_bytes())
    ddreconf={r["name"]:r.get("wall") for r in prior}
    suite={}
    for line in (HERE/"CoRe最新结构算法15秒全量.jsonl").read_bytes().splitlines():
        row=json.loads(line)
        g,d=map(PurePosixPath,(row["graph"],row["endpoints"]))
        if d.name in known:
            suite[d.name]=(row["family"],g,d)
    assert len(suite)==15
    records=[]
    output=HERE/"CoRe十五个漏解优化后结果.jsonl"
    with output.open("w",encoding="utf-8",buffering=1) as out:
        for name in sorted(suite,key=lambda n:known[n]):
            family,g,d=suite[name]
            case=ev.reference.load_case((family,g,d))
            result=solve(case,family)
            path=result.pop("path")
            length=len(path)-1 if path is not None else None
            if path is not None:
                ev.validate(case,{"path":path,"length":length},10**9,None,case.adjacency())
                result["moves"]=[[(a&~b).bit_length(),(b&~a).bit_length()] for a,b in zip(path,path[1:])]
            row=dict(name=name,family=family,reference=known[name],ddreconf_seconds=ddreconf[name],
                     length=length,budget_seconds=300,**result)
            out.write(json.dumps(row,ensure_ascii=False)+"\n")
            records.append(row)
            print(name,length,known[name],round(row["seconds"],3),row.get("order"),flush=True)
    assert len(records)==15
    print("solved",sum(r["status"]=="found" for r in records),"/",len(records),flush=True)


if __name__=="__main__":
    main()
