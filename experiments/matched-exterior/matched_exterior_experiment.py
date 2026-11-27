"""Benchmark the matched-exterior theorem against explicit solution-graph search."""
from collections import deque
from dataclasses import dataclass
from heapq import heappop, heappush
from pathlib import Path
import argparse
import json
import platform
import random
from statistics import median
from time import perf_counter
import tracemalloc


@dataclass(frozen=True)
class Case:
    # The core is a supplied triangle. Literal 2*i+j selects endpoint j of pair i.
    family: str
    pairs: int
    seed: int
    conflicts: tuple
    forbidden: tuple
    start: tuple
    goal: tuple


def cases():
    for b in (4, 8, 12, 16, 24, 64, 256, 1024):
        for family in ("path", "sparse"):
            for seed in ((0,) if family == "path" else (11, 29, 47)):
                rng = random.Random(seed)
                edges = {(2*i+1, 2*i+3) for i in range(b-1)}
                if family == "sparse":
                    for i in range(b):
                        for j in rng.sample(range(b), min(3,b)):
                            if i != j:
                                edges.add(tuple(sorted((2*i+1, 2*j+1))))
                yield Case(family,b,seed,tuple(sorted(edges)),((1,),(),(0,)),(0,0),(2,1))
    # The two first variables must agree. Their joint flip is forbidden.
    for b in (8, 256):
        yield Case("frozen",b,0,((0,3),(1,2)),((1,),(),(0,)),(0,0),(2,3))
    for b in (8, 16, 24, 64, 256, 1024):
        conflicts = tuple((2*i+1,2*i+3) for i in range(b-1))
        yield Case("detour",b,0,conflicts,((1,),tuple(2*i for i in range(2,b,2)),(0,)),
                   (0,0),(2,1))


def implications(b, conflicts, units=()):
    graph = [[] for _ in range(2*b)]
    for u,v in conflicts:
        graph[u].append(v^1)
        graph[v].append(u^1)
    for u in units:
        graph[u^1].append(u)
    return graph


def scc(graph):
    reverse = [[] for _ in graph]
    for u, row in enumerate(graph):
        for v in row:
            reverse[v].append(u)
    seen, order = set(), []
    for root in range(len(graph)):
        if root in seen:
            continue
        seen.add(root)
        stack = [(root, iter(graph[root]))]
        while stack:
            u, children = stack[-1]
            v = next(children, None)
            if v is None:
                order.append(u)
                stack.pop()
            elif v not in seen:
                seen.add(v)
                stack.append((v,iter(graph[v])))
    rank = [-1]*len(graph)
    sizes = []
    for root in reversed(order):
        if rank[root] != -1:
            continue
        rank[root] = len(sizes)
        stack, size = [root], 0
        while stack:
            size += 1
            for v in reverse[stack.pop()]:
                if rank[v] == -1:
                    rank[v] = len(sizes)
                    stack.append(v)
        sizes.append(size)
    return rank, sizes


def lift(graph, start, goal, core):
    changed = {2*i+1 if goal>>i&1 else 2*i for i in range(len(graph)//2)
               if (start^goal)>>i&1}
    incoming = dict.fromkeys(changed,0)
    for u in changed:
        for v in graph[u]:
            if v in changed and v != u:
                incoming[v] += 1
    queue = deque(u for u in sorted(changed) if incoming[u]==0)
    order = []
    while queue:
        u = queue.popleft()
        order.append(u)
        for v in graph[u]:
            if v in changed and v != u:
                incoming[v] -= 1
                if incoming[v]==0:
                    queue.append(v)
    assert len(order)==len(changed)
    for u in reversed(order):
        start ^= 1 << (u//2)
        yield core,start


def implicit(case, deadline, cap):
    b = case.pairs
    start_core, start = case.start
    end_core, end = case.goal
    graph = implications(b,case.conflicts)
    rank,sizes = scc(graph)
    frozen = [i for i in range(b) if sizes[rank[2*i]]>1 or sizes[rank[2*i+1]]>1]
    if any((start^end)>>i&1 for i in frozen):
        return None,0,"complete"
    units = [2*i+(start>>i&1) for i in frozen]
    blocked = [tuple(u^1 for u in row) for row in case.forbidden]
    edges = [[] for _ in blocked]
    count = 0
    for x in range(3):
        for y in range(x+1,3):
            ranks,_ = scc(implications(b,case.conflicts,(*units,*blocked[x],*blocked[y])))
            count += 1
            if any(ranks[2*i]==ranks[2*i+1] for i in range(b)):
                continue
            witness = sum((ranks[2*i+1]>ranks[2*i])<<i for i in range(b))
            edges[x].append((y,witness))
            edges[y].append((x,witness))
    queue, parent = deque([start_core]), {start_core:None}
    while queue:
        x=queue.popleft()
        for y,witness in edges[x]:
            if y not in parent:
                parent[y]=(x,witness)
                queue.append(y)
    if end_core not in parent:
        return None,count,"complete"
    route, x = [], end_core
    while parent[x] is not None:
        previous,witness=parent[x]
        route.append((x,witness))
        x=previous
    path=[case.start]
    for y,witness in reversed(route):
        path.extend(lift(graph,start,witness,x))
        path.append((y,witness))
        x,start=y,witness
    path.extend(lift(graph,start,end,x))
    return path,count,"complete"


def explicit(case, deadline, cap):
    # Generate only feasible exterior assignments via prefix pruning.
    b = case.pairs
    forbidden = [0]*(2*b)
    for u,v in case.conflicts:
        forbidden[u] |= 1<<v
        forbidden[v] |= 1<<u
    stack, valid = [(0,0,0)], {}
    while stack:
        if perf_counter()>=deadline:
            return None,len(valid),"time_cap"
        i,word,blocked = stack.pop()
        if i==b:
            if len(valid)>=cap:
                return None,len(valid),"assignment_cap"
            # Each vertex in masks is an exterior literal. Test its truth directly.
            valid[word] = tuple(c for c,row in enumerate(case.forbidden)
                                if all((word>>(u//2)&1)!=(u&1) for u in row))
            continue
        for bit in (1,0):
            literal=2*i+bit
            if not (blocked>>literal&1):
                stack.append((i+1,word|(bit<<i),blocked|forbidden[literal]))
    # Lexicographic Dijkstra chooses the shortest witness among minimum-core-jump paths.
    pending = [(0,0,*case.start)]
    costs, parent = {case.start:(0,0)}, {case.start:None}
    while pending:
        if perf_counter()>=deadline:
            return None,len(valid),"time_cap"
        jumps,length,x,word=heappop(pending)
        current=(x,word)
        if costs[current]!=(jumps,length):
            continue
        if current==case.goal:
            path=[]
            while current is not None:
                path.append(current)
                current=parent[current]
            return path[::-1],len(valid),"complete"
        moves=[(1,y,word) for y in valid[word] if y!=x]
        for i in range(b):
            other=word^(1<<i)
            if x in valid.get(other,()):
                moves.append((0,x,other))
        for fee,y,other in moves:
            state,distance=(y,other),(jumps+fee,length+1)
            if state not in costs or distance<costs[state]:
                costs[state],parent[state]=distance,current
                heappush(pending,(*distance,*state))
    return None,len(valid),"complete"


def astar(case, deadline, cap):
    """Search concrete states on demand with two consistent distance lower bounds."""
    target_core,target_word = case.goal
    adj = [[] for _ in range(2*case.pairs)]
    for u,v in case.conflicts:
        adj[u].append(v)
        adj[v].append(u)

    def key(state, cost):
        core,word = state
        h = int(core!=target_core)
        return cost[0]+h,cost[1]+h+(word^target_word).bit_count(),*cost,*state

    def occupied(word,u):
        return (word>>(u//2)&1)==(u&1)

    parent, costs = {case.start:None}, {case.start:(0,0)}
    queue = [key(case.start,(0,0))]
    while queue:
        if perf_counter()>=deadline:
            return None,len(parent),"time_cap"
        _,_,d,length,core,word = heappop(queue)
        state = core,word
        if costs[state]!=(d,length):
            continue
        if state==case.goal:
            path=[]
            while state is not None:
                path.append(state)
                state=parent[state]
            return path[::-1],len(parent),"complete"
        moves=[(1,c,word) for c in range(3) if c!=core
               and not any(occupied(word,u) for u in case.forbidden[c])]
        for i in range(case.pairs):
            u=2*i+1-(word>>i&1)
            if u not in case.forbidden[core] and not any(occupied(word,v) for v in adj[u]):
                moves.append((0,core,word^(1<<i)))
        for fee,c,w in moves:
            other,cost=(c,w),(d+fee,length+1)
            if other not in costs or cost<costs[other]:
                if other not in costs and len(parent)>=cap:
                    return None,len(parent),"state_cap"
                costs[other],parent[other]=cost,state
                heappush(queue,key(other,cost))
    return None,len(parent),"complete"


def replay(case, path):
    if path is None:
        return None,None
    assert (path[0],path[-1])==(case.start,case.goal)
    def occupied(word,u):
        return word>>(u//2)&1 == u&1
    for core,word in path:
        assert 0<=core<3 and 0<=word<1<<case.pairs
        assert not any(occupied(word,u) for u in case.forbidden[core])
        assert not any(occupied(word,u) and occupied(word,v) for u,v in case.conflicts)
    for (x,a),(y,b) in zip(path,path[1:]):
        assert int(x!=y)+(a^b).bit_count()==1
    return sum(x!=y for (x,_),(y,_) in zip(path,path[1:])),len(path)-1


def trial(fn,case,seconds,cap,repeats):
    times, statuses, repeat_results = [], [], []
    for _ in range(repeats):
        start=perf_counter()
        path,work,status=fn(case,start+seconds,cap)
        times.append(perf_counter()-start)
        statuses.append(status)
        jumps,length=replay(case,path)
        if jumps is not None and fn==implicit:
            assert length<=jumps+(jumps+1)*case.pairs
        repeat_results.append(dict(status=status, seconds=times[-1],work=work,
                                   core_jumps=jumps,length=length))
    if fn==implicit:
        assert status=="complete"
    # Keep tracing overhead out of runtime measurements. Give profiling its own larger deadline.
    tracemalloc.start()
    _,_,memory_status=fn(case,perf_counter()+2*seconds,cap)
    _,peak=tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return dict(status=status,statuses=statuses,seconds=median(times),peak_python_bytes=peak,
                memory_status=memory_status,work=work,core_jumps=jumps,length=length,
                repeat_results=repeat_results)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--seconds",type=float,default=1)
    p.add_argument("--assignment-cap",type=int,default=20000)
    p.add_argument("--repeats",type=int,default=3)
    args=p.parse_args()
    with args.output.open("x",encoding="utf8",buffering=1) as file:
        for i,c in enumerate(cases()):
            solvers=(implicit,explicit,astar)
            offset=i%len(solvers)
            order=solvers[offset:]+solvers[:offset]
            result={f.__name__:trial(f,c,args.seconds,args.assignment_cap,args.repeats) for f in order}
            a,b = result["implicit"],result["explicit"]
            expected=None if c.family=="frozen" else 2
            assert a["core_jumps"]==expected
            for other in (b,result["astar"]):
                if other["status"]=="complete":
                    assert a["core_jumps"]==other["core_jumps"]
                    if a["length"] is not None:
                        assert other["length"]<=a["length"]
            if b["status"]==result["astar"]["status"]=="complete":
                assert b["length"]==result["astar"]["length"]
            row=dict(family=c.family,pairs=c.pairs,seed=c.seed,vertices=2*c.pairs+3,
                     cross_conflicts=len(c.conflicts),budget=args.seconds,assignment_cap=args.assignment_cap,
                     repeats=args.repeats,python=platform.python_version(),solvers=result)
            file.write(json.dumps(row)+"\n")
            print(c.family,c.pairs,c.seed,a["status"],b["status"],flush=True)


if __name__=="__main__":
    main()
