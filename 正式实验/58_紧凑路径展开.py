"""Restore long contracted witnesses with compact, separately bounded path records."""
from array import array
from bisect import bisect_right
from collections import deque
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path,PurePosixPath
from time import perf_counter
import json

HERE=Path(__file__).resolve().parent
spec=spec_from_file_location("latest",HERE/"51_最新结构算法全量对照.py")
latest=module_from_spec(spec)
spec.loader.exec_module(latest)
p,ev=latest.p,latest.ev
contract=latest.alg.core.structure.m


def packed_lift(skeleton,pairs,graph,comp,start,target,*,deadline,record_cap,statistics):
    """BFS for a fixed abstract trajectory, with four bytes per possible predecessor."""
    members={}
    position=[]
    for u,c in enumerate(comp):
        group=members.setdefault(c,[])
        position.append(len(group))
        group.append(u)
    offsets=array("Q",[0])
    for i,(c,_) in enumerate(skeleton):
        if i%2048==0 and perf_counter()>=deadline:
            raise p.SearchTimeout(0,0)
        offsets.append(offsets[-1]+len(members[c]))
        if offsets[-1]>record_cap:
            raise OverflowError("lift table",offsets[-1])
    statistics.append(offsets[-1])
    previous=array("i",[-2])*offsets[-1]
    origin=position[start]
    previous[origin]=-1
    queue=deque([(0,start)])
    fixed_neighbors=[sorted(v for v in graph[u] if comp[v]==comp[u]) for u in range(len(graph))]
    steps=0
    while queue:
        i,u=queue.popleft()
        node=offsets[i]+position[u]
        steps+=1
        if steps%2048==0 and perf_counter()>=deadline:
            raise p.SearchTimeout(steps,0)
        if i==len(skeleton)-1 and u==target:
            path=[]
            while node>=0:
                i=bisect_right(offsets,node)-1
                c,suffix=skeleton[i]
                u=members[c][node-offsets[i]]
                head,local=pairs[u]
                path.append((head,local|suffix))
                node=previous[node]
            return path[::-1]
        for v in fixed_neighbors[u]:
            key=offsets[i]+position[v]
            if previous[key]==-2:
                previous[key]=node
                queue.append((i,v))
        if i+1==len(skeleton):
            continue
        c,suffix=skeleton[i]
        next_c,next_suffix=skeleton[i+1]
        if c==next_c:
            assert suffix!=next_suffix
            forward=(u,)
        else:
            assert suffix==next_suffix
            forward=(v for v in sorted(graph[u]) if comp[v]==next_c)
        for v in forward:
            key=offsets[i+1]+position[v]
            if previous[key]==-2:
                previous[key]=node
                queue.append((i+1,v))
    raise ValueError("A contracted witness must admit a lift")


class ProbeComplete(Exception):
    pass


def choose_direction(case, blocks, *, stages=6):
    """Measure actual compatible pairs before choosing which end of a chain to process."""
    measurements=[]
    for name,order in (("forward",blocks),("reverse",blocks[::-1])):
        sizes=[]
        stopped=False
        def observe(pairs,labels,components):
            sizes.append(pairs)
            if len(sizes)>=min(stages,len(order)):
                raise ProbeComplete()
        def guard(size):
            if size>20_000:
                raise OverflowError()
        try:
            contract.solve(case,order,observe=observe,restrict_local=True,restrict_prefix=True,check=guard)
        except ProbeComplete:
            pass
        except OverflowError:
            stopped=True
        measurements.append((stopped,max(sizes,default=0),sum(sizes),name,order,sizes))
    chosen=min(measurements,key=lambda item:item[:3])
    return chosen[4],dict(order=chosen[3],probes={x[3]:x[5] for x in measurements})


def solve(case,blocks,*,seconds=30,pair_cap=250_000,record_cap=16_000_000):
    began=perf_counter()
    deadline=began+seconds
    merges=[]
    tables=[]
    phase="contract"
    def check(size):
        if perf_counter()>=deadline:
            raise p.SearchTimeout(0,0)
        if size>pair_cap:
            raise OverflowError("pair upper bound",size)
    def expand(skeleton,pairs,graph,comp,a,b,unused):
        nonlocal phase
        phase="lift"
        return packed_lift(skeleton,pairs,graph,comp,a,b,deadline=deadline,record_cap=record_cap,statistics=tables)
    try:
        path,_=contract.solve(case,blocks,True,observe=lambda *v:merges.append(v),
                              restrict_local=True,restrict_prefix=True,check=check,lift_solver=expand)
    except OverflowError as e:
        return dict(status="resource_limit",path=None,phase=phase,detail=list(e.args),
                    merges=merges,lift_tables=tables,seconds=perf_counter()-began)
    except p.SearchTimeout:
        return dict(status="wall_budget",path=None,phase=phase,
                    merges=merges,lift_tables=tables,seconds=perf_counter()-began)
    return dict(status="found" if path else "unreachable",path=path,phase=phase,
                merges=merges,lift_tables=tables,seconds=perf_counter()-began)


def main():
    only_others=json.loads((HERE/"CoRe官方赛道与新版结果交叉核验.json").read_bytes())["only_others"]
    targets={r["name"]:r["length"] for r in only_others}
    rows=[json.loads(line) for line in (HERE/"CoRe最新结构算法15秒全量.jsonl").read_bytes().splitlines()]
    out=[]
    for row in rows:
        g,d=map(PurePosixPath,(row["graph"],row["endpoints"]))
        if d.name not in targets or row["family"] not in ("power","power_wide","power_wider","sp"):
            continue
        began=perf_counter()
        case=ev.reference.load_case((row["family"],g,d))
        compact,classes,index=latest.twins.quotient(case)
        blocks=(latest.twins.capacity_two_partition(compact,compact.adjacency()) if row["family"]=="sp"
                else latest.alg.core.structure.recognize(compact))
        assert blocks
        order=None
        if row["family"]=="sp":
            blocks,order=choose_direction(compact,blocks)
        result=solve(compact,blocks)
        if order is not None:
            result.update(order)
        path=result.pop("path")
        if path:
            path=latest.twins.lift(case,path,index,[g[0] for g in classes])
        result.update(name=d.name,family=row["family"],reference=targets[d.name],
                      length=len(path)-1 if path else None,seconds_with_input=perf_counter()-began)
        if path:
            ev.validate(case,{"path":path,"length":result["length"]},10**9,None,case.adjacency())
            result["moves"]=[[(a&~b).bit_length(),(b&~a).bit_length()] for a,b in zip(path,path[1:])]
        out.append(result)
        print(d.name,result["status"],result["length"],result.get("detail"),round(result["seconds"],3),flush=True)
        ev.write_json(HERE/"紧凑展开长路径试验.json",out)


if __name__=="__main__":
    main()
