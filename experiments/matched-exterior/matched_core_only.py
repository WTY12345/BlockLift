"""Same-objective comparison for the fixed-core experiment."""
import argparse
from collections import deque
from heapq import heappop, heappush
import json
from pathlib import Path

from matched_exterior_experiment import cases, implicit, trial
from time import perf_counter


def core_only(case, deadline, cap):
    """Concrete-state A* with exterior cost zero and core cost one."""
    target_core,target_word = case.goal
    conflicts = [[0,0] for _ in range(2*case.pairs)]
    for u,v in case.conflicts:
        conflicts[u][v&1] |= 1 << (v//2)
        conflicts[v][u&1] |= 1 << (u//2)
    required = []
    for ban in case.forbidden:
        required.append(tuple(sum(1<<(u//2) for u in ban if (u&1)!=bit) for bit in (0,1)))

    # Relax to pairwise consistency of the required values, dropping cross-pair conflicts.
    edges = [[] for _ in required]
    for x,(zx,ox) in enumerate(required):
        for y,(zy,oy) in enumerate(required):
            if x!=y and not ((zx|zy)&(ox|oy)):
                edges[x].append(y)
    heuristic = {target_core:0}
    pending = deque([target_core])
    while pending:
        x=pending.popleft()
        for y in edges[x]:
            if y not in heuristic:
                heuristic[y]=heuristic[x]+1
                pending.append(y)
    if case.start[0] not in heuristic:
        return None,0,"complete"
    next_cores = {x:tuple(y for y in edges[x] if heuristic[y]<h) for x,h in heuristic.items()}

    def violations(x,word):
        z,o = required[x]
        return (word&z)|(~word&o)

    def enqueue(state,g):
        x,word=state
        h=heuristic[x]
        # Guide ties toward a core crossing, then toward the target exterior.
        blockers=min((violations(y,word).bit_count() for y in next_cores[x]),default=0)
        heappush(queue,(g+h,h,blockers,(word^target_word).bit_count(),g,x,word))

    queue, cost, parent = [], {case.start:0}, {case.start:None}
    enqueue(case.start,0)
    while queue:
        if perf_counter()>=deadline:
            return None,len(parent),"time_cap"
        _,_,_,_,g,x,word=heappop(queue)
        state=x,word
        if g!=cost[state]:
            continue
        if state==case.goal:
            path=[]
            while state is not None:
                path.append(state)
                state=parent[state]
            return path[::-1],len(parent),"complete"
        moves=[(y,word,1) for y in edges[x] if not violations(y,word)]
        for i in range(case.pairs):
            bit=1-(word>>i&1)
            z,o=conflicts[2*i+bit]
            if ((required[x][1-bit]>>i)&1) or (~word&z) or (word&o):
                continue
            moves.append((x,word^(1<<i),0))
        for y,mask,fee in moves:
            other,ng=(y,mask),g+fee
            if other in cost and cost[other]<=ng:
                continue
            if other not in cost and len(parent)>=cap:
                return None,len(parent),"state_cap"
            cost[other],parent[other]=ng,state
            enqueue(other,ng)
    return None,len(parent),"complete"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--seconds",type=float,default=1)
    parser.add_argument("--repeats",type=int,default=3)
    parser.add_argument("--caps",type=int,nargs="+",default=[20000,200000])
    parser.add_argument("--select",nargs="+",help="Only run listed family:size groups")
    args=parser.parse_args()
    with args.output.open("x",encoding="utf-8",buffering=1) as file:
        for i,case in enumerate(cases()):
            if args.select and f"{case.family}:{case.pairs}" not in args.select:
                continue
            a=trial(implicit,case,args.seconds,args.caps[0],args.repeats)
            assert a["core_jumps"]==(None if case.family=="frozen" else 2)
            baselines={}
            for cap in (args.caps if i%2==0 else args.caps[::-1]):
                b=trial(core_only,case,args.seconds,cap,args.repeats)
                for result in b["repeat_results"]:
                    if result["status"]=="complete":
                        assert result["core_jumps"]==a["core_jumps"]
                baselines[str(cap)]=b
            row=dict(family=case.family,pairs=case.pairs,seed=case.seed,seconds=args.seconds,
                     repeats=args.repeats,implicit=a,core_only=baselines)
            file.write(json.dumps(row)+"\n")
            print(case.family,case.pairs,{k:b["status"] for k,b in baselines.items()},flush=True)


if __name__=="__main__":
    main()
