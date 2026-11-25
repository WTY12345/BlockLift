"""Compose structure certificates, proven compressed paths, and bounded improvement."""
from math import isqrt
from pathlib import Path
import re
import runpy
from time import perf_counter

HERE = Path(__file__).resolve().parent
old = runpy.run_path(str(HERE/"long_path_search.py"))
structures = runpy.run_path(str(HERE/"compressed_witness.py"))
ph = runpy.run_path(str(HERE/"pigeonhole_matching.py"))
sat = runpy.run_path(str(HERE/"sat_projection.py"))
packed, latest, p, ev = (old[k] for k in ("packed","latest","p","ev"))


def path_from_moves(start, moves):
    path = [start]
    for u,v in moves:
        path.append(path[-1]^(1<<(u-1))^(1<<(v-1)))
    return path


def monotone(start, goal, adj, *, partial=False, deadline=None):
    """Try a path that adds one of the remaining goal vertices at every step."""
    state = start
    missing = goal&~state
    path = [state]
    while missing:
        if deadline is not None and perf_counter()>=deadline:
            return None
        options = []
        for v in p.vertices(missing):
            blockers = adj[v]&state
            if blockers.bit_count()<=1:
                options.append((v,blockers))
        if not options:
            return path if partial else None
        v,removed = min(options,key=lambda item:(not item[1],item[0]))
        if not removed:
            candidates = state&~goal
            u = cycle_source(candidates,missing,adj)
            if u is None:
                u = max(p.vertices(candidates),key=lambda u:(adj[u]&missing).bit_count())
            removed = 1<<u
        state ^= removed | (1<<v)
        missing ^= 1<<v
        path.append(state)
    return path


def cycle_source(sources, targets, adj):
    """Spend a free target on an alternating cycle before opening an imbalanced path."""
    left = sources
    while left:
        seed = (left&-left).bit_length()-1
        todo = [seed]
        component = 0
        cycle = True
        while todo:
            u = todo.pop()
            bit = 1<<u
            if component&bit:
                continue
            component |= bit
            left &= ~bit
            neighbors = adj[u]&targets
            cycle &= neighbors.bit_count()==2
            for v in p.vertices(neighbors):
                predecessors = adj[v]&sources
                cycle &= predecessors.bit_count()==2
                todo.extend(p.vertices(predecessors&~component))
        if cycle:
            return seed
    return None


def try_shortcut(path, adj, deadline):
    revised = [path[0]]
    first = 0
    while first<len(path)-1:
        next_index = first+1
        segment = path[first:next_index+1]
        for end in range(min(len(path)-1,first+13),first+1,-1):
            if perf_counter()>=deadline:
                return revised+path[first+1:]
            if (path[end]&~path[first]).bit_count()>=end-first:
                continue
            short = monotone(path[first],path[end],adj,deadline=deadline)
            if short and len(short)-1<end-first:
                next_index,segment = end,short
                break
        revised.extend(segment[1:])
        first = next_index
    return revised


def one_detour(start, goal, adj, deadline):
    """Try one non-target jump between two monotone segments."""
    prefix = monotone(start,goal,adj,partial=True,deadline=deadline)
    if prefix is None:
        return None
    universe = (1<<len(adj))-1
    for i in reversed(range(len(prefix))):
        state = prefix[i]
        missing = goal&~state
        out = state&~goal
        candidates = []
        for v in p.vertices(universe&~(state|goal)):
            if perf_counter()>=deadline:
                return None
            blockers = adj[v]&state
            if blockers.bit_count()>1 or blockers&goal:
                continue
            choices = blockers or out
            for u in p.vertices(choices):
                gain = (adj[u]&missing).bit_count()-(adj[v]&missing).bit_count()
                candidates.append((gain,u,v))
        for _,u,v in sorted(candidates,reverse=True)[:192]:
            if perf_counter()>=deadline:
                return None
            after = state^(1<<u)^(1<<v)
            tail = monotone(after,goal,adj,deadline=deadline)
            if tail:
                return prefix[:i+1]+tail
    return None


def improve(case, incumbent, deadline, family, *, splice=False):
    began = perf_counter()
    if perf_counter()>=deadline:
        return incumbent,[]
    start,goal = map(p.mask_of,(case.start,case.target))
    gap = (goal&~start).bit_count()
    if len(incumbent)-1==gap:
        return incumbent,[]
    adj = case.adjacency()
    runs = []
    for reverse in (False,True):
        source,target = (goal,start) if reverse else (start,goal)
        path = monotone(source,target,adj,deadline=deadline)
        if path:
            runs.append(dict(method="monotone",seconds=perf_counter()-began,length=len(path)-1))
            return (path[::-1] if reverse else path),runs
    shortcut = try_shortcut(incumbent,adj,min(deadline,perf_counter()+0.5))
    if len(shortcut)<len(incumbent):
        incumbent = shortcut
        runs.append(dict(method="path_shortcut",seconds=perf_counter()-began,length=len(incumbent)-1))
    if case.n<=500 and len(incumbent)-1>gap+1:
        for reverse in (False,True):
            source,target = (goal,start) if reverse else (start,goal)
            path = one_detour(source,target,adj,min(deadline,perf_counter()+0.45))
            if path and len(path)<len(incumbent):
                runs.append(dict(method="single_detour",seconds=perf_counter()-began,length=len(path)-1))
                incumbent = path[::-1] if reverse else path
                break
    n = isqrt(case.n)
    if family=="queen" and n*n==case.n and len(case.start)==n-1:
        board = latest.queen.Board(n,goal)
        strategies = [(32,32,2,False),(48,36,2,True),(64,48,8,False),(64,48,8,True),
                      (96,72,1,False),(96,72,1,True),(96,72,4,False),(96,72,4,True),
                      (136,96,12,False),(136,96,12,True),(160,100,3,False),(160,100,3,True)]
        if splice:
            strategies = [(48,36,2,False),(48,36,2,True),(64,48,6,False),(64,48,6,True),
                          (96,72,1,False),(96,72,1,True),(120,90,10,False),(120,90,10,True),
                          (192,120,3,False),(192,120,3,True)]
        for index,(width,branch,penalty,reverse) in enumerate(strategies):
            now = perf_counter()
            if now>=deadline or len(incumbent)-1==gap:
                break
            allocation = (deadline-now)/min(4,len(strategies)-index)
            path,work = latest.queen.search(board,start,width,branch,now+allocation,penalty,reverse,
                                            depth_limit=len(incumbent)-2,
                                            incumbent=incumbent if splice else None)
            runs.append(dict(method="queen_beam",width=width,penalty=penalty,reverse=reverse,
                             seconds=perf_counter()-began,work=work,length=len(path)-1 if path else None))
            if path:
                incumbent = path
    elif case.n<=500:
        result = latest.alg.solve(case,"fixed",budget=max(0,deadline-perf_counter()))
        path = result["path"]
        if path and len(path)<len(incumbent):
            incumbent = path
            runs.append(dict(method="face_first",seconds=perf_counter()-began,length=len(path)-1))
        if perf_counter()<deadline and len(incumbent)-1>gap:
            for proposed_limit in range(gap,len(incumbent)-1):
                now = perf_counter()
                if now>=deadline:
                    break
                for seed in (774,531,29):
                    try:
                        path,*_ = p.solve(case,proposed_limit,"llm_rule",16,seed,deadline=deadline)
                    except p.SearchTimeout:
                        return incumbent,runs
                    if path:
                        incumbent = path
                        runs.append(dict(method="bounded_blocker_beam",seconds=perf_counter()-began,
                                         length=len(path)-1))
                        break
                if path:
                    break
    return incumbent,runs


def compact_path(case, family, deadline):
    compact,classes,index = latest.twins.quotient(case)
    adj = compact.adjacency()
    start,goal = map(p.mask_of,(compact.start,compact.target))
    if family=="sp":
        blocks = latest.twins.capacity_two_partition(compact,adj)
        if blocks is None:
            return dict(status="unsupported",path=None)
        blocks,probe = packed.choose_direction(compact,blocks)
        choices = [(probe["order"],blocks)]
    elif family=="exp_instance":
        patterns,_ = latest.alg.assess(compact,adj,start,goal,min(deadline,perf_counter()+1))
        blocks = patterns.get(0) or latest.alg.clique_partition(adj)
        if not old["saturated"](compact,blocks,adj):
            return dict(status="unsupported",path=None)
        orders = list(old["ordering"].candidates(blocks,adj,start,goal))
        orders.sort(key=lambda entry: not entry[0].startswith("reverse-greedy"))
        choices = ((label,[blocks[i] for i in order]) for label,order in orders)
    else:
        try:
            choices = [("recognized",latest.alg.core.structure.recognize(compact))]
        except ValueError:
            return dict(status="unsupported",path=None)
    failures, seen = [], set()
    for label,order in choices:
        if perf_counter()>=deadline:
            break
        identity = tuple(map(tuple,order))
        if identity in seen:
            continue
        seen.add(identity)
        if not old["saturated"](compact,order,adj):
            continue
        if family=="exp_instance":
            first_order = not failures
            quota = 12 if first_order or label.startswith("reverse-greedy") else 3
            end = min(deadline,perf_counter()+quota)
        else:
            end = deadline
        pair_cap = 360_000 if family=="exp_instance" else 250_000
        result = structures["compressed_solve"](compact,order,packed,end,pair_cap=pair_cap)
        if result["status"]=="unreachable":
            return dict(result,method="compact_certificate",order=label)
        if result["status"]=="found":
            witness = structures["lift_witness"](result["witness"],case,classes,index)
            length = structures["verify_witness"](witness,case.adjacency(),*map(p.mask_of,(case.start,case.target)))
            return dict(result,method="compressed_contraction",order=label,witness=witness,length=length)
        failures.append(dict(order=label,**result))
    return dict(status="budget",path=None,compressed_attempts=failures)


def solve(case, family, budget=15, *, name=None, quality=False, incumbent=None, splice=False):
    """Return either an explicit path or a verified compressed move sequence."""
    start = perf_counter()
    deadline = start+budget
    instance_name = name or getattr(case,"name","")
    if family=="grid":
        proof = structures["grid_certificate"](case)
        if proof:
            return dict(status="unreachable",path=None,method="grid_phase",certificate=proof,
                        seconds=perf_counter()-start)
    if family=="ph-isr":
        match = re.fullmatch(r"ph-(\d+)-(\d+)(?:_01\.dat)?",instance_name)
        if match:
            result = ph["solve"](case,*map(int,match.groups()))
            if result["status"] in {"found","unreachable"}:
                moves = result.pop("moves")
                path = path_from_moves(p.mask_of(case.start),moves) if moves is not None else None
                return dict(result,path=path,method="gated_matching",seconds=perf_counter()-start)
    if family=="exp_instance":
        match = re.fullmatch(r"SAT_exp_instance(\d+)(?:_01\.dat)?",instance_name)
        if match:
            branch_deadline = min(deadline,start+min(2,budget/2))
            result = sat["solve"](case,int(match[1]),branch_deadline)
            if result["status"] in {"found","unreachable"}:
                return dict(result,method="sat_blocker_projection",seconds=perf_counter()-start)
    if incumbent is None and (quality or (family=="color04" and case.n>=2500)):
        near,goal = map(p.mask_of,(case.start,case.target))
        candidate = monotone(near,goal,case.adjacency(),deadline=deadline)
        if candidate and perf_counter()<=deadline:
            return dict(status="found",path=candidate,method="monotone_lower_bound",seconds=perf_counter()-start)
    if incumbent is not None:
        result = dict(status="found",path=incumbent,method="incumbent")
    elif family in {"sp","power","power_wide","power_wider","exp_instance"}:
        first = old["solve"](case,family,min(1,budget/4))
        if first["status"] in {"found","unreachable"}:
            return dict(first,seconds=perf_counter()-start)
        result = compact_path(case,family,deadline)
        if result["status"] in {"found","unreachable"}:
            return dict(result,seconds=perf_counter()-start)
    else:
        result = old["solve"](case,family,min(budget,2) if quality else budget)
    if result["status"] not in {"found","unreachable"} and perf_counter()<deadline:
        failed = result.get("compressed_attempts")
        result = old["solve"](case,family,deadline-perf_counter())
        if failed is not None:
            result["compressed_attempts"] = failed
    if quality and result.get("path") is not None:
        result["path"],result["quality_runs"] = improve(case,result["path"],deadline,family,splice=splice)
    result["seconds"] = perf_counter()-start
    return result
