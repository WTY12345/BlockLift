"""Choose a contraction order using the certified block interaction graph."""
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path,PurePosixPath
from time import perf_counter
from collections import deque
from random import Random
import json

HERE=Path(__file__).resolve().parent
spec=spec_from_file_location("packed",HERE/"58_紧凑路径展开.py")
packed=module_from_spec(spec)
spec.loader.exec_module(packed)
latest,p,ev=packed.latest,packed.p,packed.ev


def candidates(blocks,adj,start,goal):
    masks=[p.mask_of(b) for b in blocks]
    outside=[]
    for block,mask in zip(blocks,masks):
        joined=0
        for v in block:
            joined|=adj[v]
        outside.append(joined&~mask)
    connections=[{i for i,m in enumerate(masks) if m&link} for link in outside]
    original=list(range(len(blocks)))
    changed=[i for i,g in enumerate(masks) if g&(start^goal)]
    yield "original",original
    yield "reverse",original[::-1]
    for anchor in (None,*(changed[:2]),max(original,key=lambda i:len(connections[i]))):
        available=set(original)
        chosen=[]
        inside=frontier=0
        if anchor is not None:
            chosen.append(anchor)
            available.remove(anchor)
            inside=masks[anchor]
            frontier=outside[anchor]
        while available:
            nxt=min(available,key=lambda i:(((outside[i]|frontier)&~(inside|masks[i])).bit_count(),
                                           -(frontier&masks[i]).bit_count(),len(connections[i]),i))
            chosen.append(nxt)
            available.remove(nxt)
            inside|=masks[nxt]
            frontier=(frontier|outside[nxt])&~inside
        yield f"greedy-{anchor}",chosen
        yield f"reverse-greedy-{anchor}",chosen[::-1]
    # Repeatedly eliminate low-degree vertices, adding fill edges.
    live=set(original)
    link=[a.copy() for a in connections]
    order=[]
    while live:
        def cost(i):
            neighbors=sorted(link[i]&live)
            missing=sum(b not in link[a] for j,a in enumerate(neighbors) for b in neighbors[j+1:])
            return missing,len(neighbors),i
        i=min(live,key=cost)
        order.append(i)
        live.remove(i)
        neighbors=link[i]&live
        for a in neighbors:
            link[a].update(neighbors-{a})
    yield "minfill",order
    yield "minfill-reverse",order[::-1]


def main():
    wanted={r["name"]:r["length"] for r in json.loads((HERE/"CoRe官方赛道与新版结果交叉核验.json").read_bytes())["only_others"]}
    records=[]
    source=(HERE/"CoRe最新结构算法15秒全量.jsonl").read_bytes().splitlines()
    for line in source:
        row=json.loads(line)
        g,d=map(PurePosixPath,(row["graph"],row["endpoints"]))
        if d.name not in wanted or row["family"]!="exp_instance":
            continue
        case=ev.reference.load_case((row["family"],g,d))
        adj=case.adjacency()
        start,goal=map(p.mask_of,(case.start,case.target))
        partitions,_=latest.alg.assess(case,adj,start,goal,perf_counter()+1)
        blocks=partitions[0]
        tried=[]
        seen=set()
        for name,order in candidates(blocks,adj,start,goal):
            if tuple(order) in seen:
                continue
            seen.add(tuple(order))
            result=packed.solve(case,[blocks[i] for i in order],seconds=30,pair_cap=180_000)
            path=result.pop("path")
            result.update(order=name,length=len(path)-1 if path else None)
            tried.append(result)
            print(d.name,name,result["status"],result["length"],len(result["merges"]),result.get("detail"),
                  round(result["seconds"],3),flush=True)
            if path:
                ev.validate(case,{"path":path,"length":len(path)-1},10**9,None,adj)
                result["moves"]=[[(a&~b).bit_length(),(b&~a).bit_length()] for a,b in zip(path,path[1:])]
                break
        records.append(dict(name=d.name,reference=wanted[d.name],runs=tried))
        ev.write_json(HERE/"稀疏约束分块顺序试验.json",records)


if __name__=="__main__":
    main()
