"""Recognize the benchmark's five-vertex blocks from edges; test random relabeling."""
from dataclasses import replace
from itertools import combinations
from random import Random
from pathlib import Path,PurePosixPath
from importlib.util import spec_from_file_location,module_from_spec
from time import perf_counter
import json

HERE=Path(__file__).resolve().parent
spec=spec_from_file_location("contract",HERE/"24_边界连通摘要.py")
m=module_from_spec(spec)
spec.loader.exec_module(m)
p=m.p


def recognize(case):
    adj=case.adjacency()
    blocks=set()
    for a in range(case.n):
        for b,c in combinations(p.vertices(adj[a]),2):
            if not adj[b]&(1<<c):
                continue
            triangle=(1<<a)|(1<<b)|(1<<c)
            for x in p.vertices(adj[b]&~triangle):
                for y in p.vertices(adj[x]&adj[c]&~triangle):
                    mask=triangle|(1<<x)|(1<<y)
                    if sum((adj[v]&mask).bit_count() for v in p.vertices(mask))==12:
                        blocks.add(mask)
    covered=0
    for mask in blocks:
        if mask&covered:
            raise ValueError("overlapping candidate blocks")
        covered|=mask
    universe=(1<<case.n)-1
    prefix=universe^covered
    if prefix.bit_count()!=4:
        raise ValueError("unrecognized remainder")
    order=[list(p.vertices(prefix))]
    def neighbors(mask):
        joined=0
        for v in p.vertices(mask):
            joined|=adj[v]
        return joined
    frontier=neighbors(prefix)&~prefix
    while blocks:
        def score(mask):
            new_boundary=(frontier|neighbors(mask))&~(prefix|mask)
            return new_boundary.bit_count(),-(frontier&mask).bit_count(),mask
        mask=min(blocks,key=score)
        prefix|=mask
        frontier=(frontier|neighbors(mask))&~prefix
        blocks.remove(mask)
        order.append(list(p.vertices(mask)))
    return order


def main():
    reference=json.loads((HERE/"分层最短展开结果.json").read_bytes())
    chosen={r["name"] for r in reference}
    source=json.loads((HERE/"LLM实验/精确宏动作1.5B/CoRe_beam_全量.json").read_bytes())["rows"]
    out=[]
    for row in source:
        name=PurePosixPath(row["endpoint_file"]).name
        if name not in chosen:
            continue
        case=m.ev.reference.load_case((row["family"],PurePosixPath(row["graph_file"]),PurePosixPath(row["endpoint_file"])))
        for seed in (17,23,41):
            permutation=list(range(case.n))
            Random(seed).shuffle(permutation)
            relabeled=replace(case,edges=tuple((permutation[u],permutation[v]) for u,v in case.edges),
                              start=tuple(permutation[v] for v in case.start),target=tuple(permutation[v] for v in case.target))
            began=perf_counter()
            blocks=recognize(relabeled)
            path,layers=m.solve(relabeled,blocks,optimize_lift=True)
            assert path
            check={"path":path,"length":len(path)-1}
            m.ev.validate(relabeled,check,10**9,row["author_length"],relabeled.adjacency())
            out.append(dict(name=name,seed=seed,length=len(path)-1,peak=max(n for n,c in layers),
                            seconds=perf_counter()-began))
        print(name,[(r["length"],r["peak"]) for r in out[-3:]],flush=True)
    m.ev.write_json(HERE/"结构识别重编号结果.json",out)


if __name__=="__main__":
    main()
