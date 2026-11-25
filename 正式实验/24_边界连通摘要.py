"""Contract connected components with equal external blockage, then lift witnesses."""
from collections import deque
from itertools import combinations
from pathlib import Path,PurePosixPath
import json
from importlib.util import spec_from_file_location,module_from_spec
from time import perf_counter

HERE=Path(__file__).resolve().parent
spec=spec_from_file_location("core",HERE/"09_CoRe留出评估.py")
ev=module_from_spec(spec)
spec.loader.exec_module(ev)
p=ev.reference.pilot


def route(edges,a,b,allowed):
    prev={a:None}
    queue=deque([a])
    while queue:
        u=queue.popleft()
        if u==b:
            path=[]
            while u is not None:
                path.append(u)
                u=prev[u]
            return path[::-1]
        for v in sorted(edges[u]):
            if v not in prev and allowed(v):
                prev[v]=u
                queue.append(v)
    raise ValueError("Disconnected component")


def shortest_lift(skeleton, pairs, graph, comp, start, target, check=None):
    """Minimize realized moves for a fixed ordered list of boundary crossings."""
    # 展开时在乘积图上做 BFS。二元组记录抽象路径走到哪一步，以及这一层选了哪个具体节点。
    origin=(0,start)
    queue=deque([origin])
    previous={origin:None}
    while queue:
        if check is not None:
            check(len(previous))
        i,u=queue.popleft()
        c,suffix=skeleton[i]
        if i==len(skeleton)-1 and u==target:
            trace=[]
            node=(i,u)
            while node is not None:
                j,v=node
                head,local=pairs[v]
                trace.append((head,local|skeleton[j][1]))
                node=previous[node]
            return trace[::-1]
        # 保持抽象步骤索引不动时，可以在当前连通分量内移动，以衔接下一条抽象边。
        options=[(i,v) for v in graph[u] if comp[v]==c]
        if i+1<len(skeleton):
            next_c,next_suffix=skeleton[i+1]
            if next_c==c:
                assert next_suffix!=suffix
                options.append((i+1,u))
            else:
                assert next_suffix==suffix
                options.extend((i+1,v) for v in graph[u] if comp[v]==next_c)
        for node in options:
            if node not in previous:
                previous[node]=(i,u)
                queue.append(node)
    raise ValueError("A contracted witness must admit a lift")


# 适用前提是所有块在起点就达到独立数。令牌总数守恒使得每一步都发生在某一个块内。
def solve(case,blocks,optimize_lift=False,observe=None,restrict_local=False,restrict_prefix=False,check=None,*,lift_solver=None,witness_builder=None):
    adj=case.adjacency()
    start,goal=map(p.mask_of,(case.start,case.target))
    # future 保存尚未合并的顶点。labels[q] 是摘要分量 q 封锁的外部顶点位集。
    future=(1<<case.n)-1
    labels=[0]
    edges=[set()]
    initial=target=0
    stages=[]
    for block in blocks:
        if check is not None:
            check(len(labels))
        mask=p.mask_of(block)
        future &= ~mask
        k=(start&mask).bit_count()
        assert (goal&mask).bit_count()==k
        def blocked(state):
            result=0
            for v in p.vertices(state):
                result |= adj[v]
            return result
        # 若块内存在更大的独立集，则一定含有一个大小 k+1 的独立子集。这个检查验证饱和容量。
        # Certify alpha(block)=k using the start and exclusion of size k+1.
        assert all(blocked(m)&m for m in map(p.mask_of,combinations(block,k+1)))
        local={m:blocked(m) for m in map(p.mask_of,combinations(block,k)) if not blocked(m)&m}
        if restrict_local:
            origin=start & mask
            reachable={origin}
            stack=[origin]
            while stack:
                state=stack.pop()
                for neighbor in local:
                    if neighbor not in reachable and (state^neighbor).bit_count()==2:
                        reachable.add(neighbor)
                        stack.append(neighbor)
            if goal & mask not in reachable:
                return None,[]
            local={state:external for state,external in local.items() if state in reachable}
        # 只组合互相兼容的旧前缀分量 u 和新块配置 s。位集相交表示新块令牌落在被封锁的位置。
        if witness_builder is None or check is None:
            if check is not None:
                check(len(labels)*len(local))
            pairs=[(u,s) for u,label in enumerate(labels) for s in local if not s&label]
        else:
            pairs=[]
            for u,label in enumerate(labels):
                if u%2048==0:
                    check(len(pairs))
                pairs.extend((u,s) for s in local if not s&label)
            check(len(pairs))
        index={pair:i for i,pair in enumerate(pairs)}
        graph=[set() for _ in pairs]
        signatures=[]
        for i,(u,s) in enumerate(pairs):
            # 合并后的阻挡标签是两部分邻域的并集，只保留通往未处理顶点的部分。
            signatures.append((labels[u]|local[s])&future)
            # 两类边分别对应旧前缀移动和新块移动。满载证书排除了二者之间的跨块跳跃。
            graph[i].update(index[v,s] for v in edges[u] if (v,s) in index)
            graph[i].update(index[u,t] for t in local if (s^t).bit_count()==2 and (u,t) in index)
        a,b=index[initial,start&mask],index[target,goal&mask]
        if restrict_prefix:
            # 全局路径投影到前缀后仍是一条从前缀起点出发的走法，所以前缀不可达的状态可以删掉。
            # A global witness projects to a walk from a in the prefix product.
            reached={a}
            pending=[a]
            while pending:
                i=pending.pop()
                for j in graph[i]:
                    if j not in reached:
                        reached.add(j)
                        pending.append(j)
            if b not in reached:
                return None,[]
            if len(reached)<len(pairs):
                kept=sorted(reached)
                index_in_kept={old:new for new,old in enumerate(kept)}
                graph=[{index_in_kept[j] for j in graph[i]} for i in kept]
                pairs=[pairs[i] for i in kept]
                signatures=[signatures[i] for i in kept]
                a,b=index_in_kept[a],index_in_kept[b]
        # 只合并同一标签下连通的节点。同一标签的不同连通分量必须分别保留。
        comp=[-1]*len(pairs)
        labels=[]
        for i,signature in enumerate(signatures):
            if comp[i]>=0:
                continue
            c=len(labels)
            labels.append(signature)
            comp[i]=c
            stack=[i]
            while stack:
                j=stack.pop()
                for h in graph[j]:
                    if comp[h]<0 and signatures[h]==signature:
                        comp[h]=c
                        stack.append(h)
        if observe is not None:
            observe(len(pairs), len(set(signatures)), len(labels))
        edges=[set() for _ in labels]
        # 跨分量边保存一条真实的乘积图边，供反向展开时选取可执行的见证。
        bridges={}
        for i,neighbors in enumerate(graph):
            for j in neighbors:
                if comp[i]!=comp[j]:
                    edges[comp[i]].add(comp[j])
                    bridges.setdefault((comp[i],comp[j]),(i,j))
        stages.append((pairs,graph,comp,bridges,a,b,len(labels)))
        initial,target=comp[a],comp[b]
    # 所有顶点处理完之后，对外标签都为空。此时分量是否相同就决定端点是否可达。
    if initial!=target:
        return None,[]
    if witness_builder is not None:
        return witness_builder(stages), [[len(pairs),ncomponents] for pairs,_,_,_,_,_,ncomponents in stages]
    # 逆序展开每一层收缩，恢复全局状态。分层 BFS 只优化给定抽象顺序下的展开，通常不保证全局最短。
    # Reverse each contraction. A skeleton step changes either the prefix or the last block.
    skeleton=[(initial,0)]
    sizes=[]
    for pairs,graph,comp,bridges,a,b,ncomponents in reversed(stages):
        sizes.append([len(pairs),ncomponents])
        if optimize_lift:
            expand=shortest_lift if lift_solver is None else lift_solver
            skeleton=expand(skeleton,pairs,graph,comp,a,b,check)
            continue
        expanded=[]
        current=a
        for i,(c,suffix) in enumerate(skeleton):
            following=skeleton[i+1][0] if i+1<len(skeleton) else None
            if following is None:
                end=b
            elif c==following:
                end=current
            else:
                end,_=bridges[c,following]
            for j in route(graph,current,end,lambda j:comp[j]==c):
                u,s=pairs[j]
                entry=(u,s|suffix)
                if not expanded or expanded[-1]!=entry:
                    expanded.append(entry)
            current=end if following is None or c==following else bridges[c,following][1]
        skeleton=expanded
    return [s for _,s in skeleton],sizes[::-1]


def main():
    rows=json.loads((HERE/"LLM实验/精确宏动作1.5B/CoRe_beam_全量.json").read_bytes())["rows"]
    results=[]
    for r in rows:
        name=PurePosixPath(r["endpoint_file"]).name
        if name not in {"hc-square-008-002_01.dat","hc-power-004-002_01.dat"}:
            continue
        case=ev.reference.load_case((r["family"],PurePosixPath(r["graph_file"]),PurePosixPath(r["endpoint_file"])))
        blocks=[list(range(4))]+[list(range(i,i+5)) for i in range(4,case.n,5)]
        for order,sequence in [("forward",blocks),("reverse",blocks[::-1])]:
            began=perf_counter()
            path,sizes=solve(case,sequence)
            result=dict(instance=name,order=order,path=path,length=len(path)-1 if path else None,layers=sizes)
            ev.validate(case,result,10**9,r["author_length"],case.adjacency())
            result["seconds"]=perf_counter()-began
            print(name,order,result["length"],max((x[0] for x in sizes),default=0),result["seconds"],flush=True)
            results.append(result)
            ev.write_json(HERE/"边界连通摘要结果.json",results)


if __name__=="__main__":
    main()
