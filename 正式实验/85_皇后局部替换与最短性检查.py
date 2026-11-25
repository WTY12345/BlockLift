"""Try shorter queen subpaths and test a length bound by complete bounded search."""
import argparse
import csv
from heapq import heappop, heappush
import json
from math import isqrt
from pathlib import Path
import runpy
from time import perf_counter

HERE=Path(__file__).resolve().parent
def shorten(path,side,deadline,queen):
    for width in (6,10,16,24):
        i=0
        while i<len(path)-2:
            j=min(i+width,len(path)-1)
            now=perf_counter()
            if now>=deadline:
                return path
            if (path[j]&~path[i]).bit_count()<j-i:
                board=queen.Board(side,path[j])
                improved,_=queen.search(board,path[i],24,24,min(deadline,now+0.075),5,
                                        bool(i%2),depth_limit=j-i-1)
                if improved:
                    path=path[:i]+improved+path[j+1:]
            i+=2
    return path


def bounded(board,start,limit,deadline,cap=180_000):
    """Complete when exhausted. The mismatch count is an admissible lower bound."""
    g={start:0}
    parent={start:None}
    h=lambda s:(board.goal&~s).bit_count()
    queue=[(h(start),0,start)]
    expanded=0
    while queue:
        if perf_counter()>=deadline or len(g)>=cap:
            return None,False,expanded
        _,cost,state=heappop(queue)
        if cost!=g[state]:
            continue
        if state==board.goal:
            path=[]
            while state is not None:
                path.append(state)
                state=parent[state]
            return path[::-1],True,expanded
        expanded+=1
        for u,v in board.moves(state):
            nxt=state^(1<<u)^(1<<v)
            if cost+1>=g.get(nxt,limit+1) or cost+1+h(nxt)>limit:
                continue
            g[nxt]=cost+1
            parent[nxt]=state
            heappush(queue,(cost+1+h(nxt),cost+1,nxt))
    return None,True,expanded


def main():
    evaluation=runpy.run_path(str(HERE/"72_未判定与偏长实例复测.py"))
    solver=evaluation["solver"]
    queen=solver["latest"].queen
    parser=argparse.ArgumentParser()
    parser.add_argument("--seconds",type=float,default=8)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    with (HERE/"CoRe最终693例结论.csv").open(encoding="utf-8-sig",newline="") as f:
        manifest={r["实例"]:r for r in csv.DictReader(f)}
    best={}
    for source in ("CoRe冻结版15秒全量.jsonl","CoRe偏长25例优化.jsonl",
                   "CoRe偏长皇后续改.jsonl","CoRe皇后逐例改短.jsonl"):
        with (HERE/source).open(encoding="utf-8") as f:
            for line in f:
                r=json.loads(line)
                name=Path(r["endpoints"]).name if "endpoints" in r else r["name"]
                r=r.get("run",r)
                if manifest[name]["图族"]!="queen" or not r.get("moves"):
                    continue
                if name not in best or r["length"]<best[name]["length"]:
                    best[name]=r
    with args.output.open("w",encoding="utf-8",buffering=1) as out:
        for row in evaluation["suite"]:
            name=row["实例"]
            if name not in best:
                continue
            incumbent=best[name]
            ref=manifest[name]["作者精确参照"]
            if ref and incumbent["length"]==int(ref):
                continue
            case=evaluation["load_case"](row)
            p=solver["p"]
            start,goal=map(p.mask_of,(case.start,case.target))
            gap=(goal&~start).bit_count()
            if gap==incumbent["length"]:
                continue
            n=isqrt(case.n)
            if n*n!=case.n or len(case.start)!=n-1:
                continue
            began=perf_counter()
            path=solver["path_from_moves"](start,incumbent["moves"])
            path=shorten(path,n,began+args.seconds*0.45,queen)
            expanded=0
            exact=len(path)-1==gap
            if not exact:
                choice,complete,expanded=bounded(queen.Board(n,goal),start,len(path)-2,
                                                 began+args.seconds)
                if choice:
                    path=choice
                exact=complete
            length=len(path)-1
            assert length<=incumbent["length"]
            solver["ev"].validate(case,dict(path=path,length=length),10**9,int(ref) if ref else None,
                                  case.adjacency(),materialize=False)
            r=dict(name=name,status="found",length=length,before=incumbent["length"],optimal=exact,expanded=expanded,
                   seconds=perf_counter()-began,budget_seconds=args.seconds,
                   moves=[[(a&~b).bit_length(),(b&~a).bit_length()] for a,b in zip(path,path[1:])])
            out.write(json.dumps(r,ensure_ascii=False)+"\n")
            print(name,r["before"],length,exact,expanded,round(r["seconds"],3),flush=True)


if __name__=="__main__":
    main()
