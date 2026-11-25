"""Find and certify shortest token-jumping paths for a gated four-cycle."""
from collections import Counter
from importlib.util import module_from_spec, spec_from_file_location
from itertools import combinations, product
from math import prod
from pathlib import Path
from time import perf_counter

HERE = Path(__file__).resolve().parent
spec = spec_from_file_location("eval", HERE / "search_support.py")
ev = module_from_spec(spec)
spec.loader.exec_module(ev)
p = ev.reference.pilot


def recognize(case, adj, start, goal):
    changed = start ^ goal
    if changed.bit_count() != 4 or (start & changed).bit_count() != 2:
        return None
    if any((adj[v] & changed).bit_count() != 2 for v in p.vertices(changed)):
        return None
    neighbors = 0
    for v in p.vertices(changed):
        neighbors |= adj[v]
    gateway_mask = neighbors & ~changed
    if gateway_mask.bit_count() != 1 or gateway_mask & (start | goal):
        return None
    gateway = gateway_mask.bit_length() - 1
    core_mask = changed | gateway_mask
    outside_mask = ((1 << case.n) - 1) & ~core_mask
    core_states = []
    for a,b in combinations(p.vertices(core_mask),2):
        if not adj[a] & (1 << b):
            core_states.append((1 << a) | (1 << b))
    if any(not any(adj[u] & (1 << v) for u,v in combinations(group,2))
           for group in combinations(p.vertices(core_mask),3)):
        return None

    # Certify that the only route through the five-vertex block is a three-jump chain.
    current = start & core_mask
    finish = goal & core_mask
    core_path = [current]
    while current != finish:
        forward = [s for s in core_states if (s ^ current).bit_count() == 2 and s not in core_path]
        if len(forward) != 1:
            return None
        current = forward[0]
        core_path.append(current)
    if len(core_path) != 4 or set(core_states) != set(core_path):
        return None
    if not all(s & gateway_mask for s in core_path[1:-1]):
        return None

    triangles = set()
    for a in p.vertices(outside_mask):
        for b,c in combinations(p.vertices(adj[a] & outside_mask),2):
            if adj[b] & (1 << c):
                triangles.add(p.mask_of((a,b,c)))
    seen = 0
    groups = []
    for group in sorted(triangles):
        if seen & group:
            return None
        seen |= group
        groups.append(group)
    # In this construction the vertices outside the triangles form disjoint edges.
    rest = outside_mask & ~seen
    for v in p.vertices(rest):
        neighbors = adj[v] & rest
        if neighbors.bit_count() != 1:
            return None
        group = neighbors | (1 << v)
        if not group & seen:
            seen |= group
            groups.append(group)
    if seen != outside_mask or any((start & group).bit_count() != 1 for group in groups):
        return None

    # Every exterior block is a clique with one token; the core is also saturated.
    variables = [g for g in groups if g & adj[gateway]]
    constraints = [g for g in groups if not g & adj[gateway]]
    for side in (variables,constraints):
        union = 0
        for group in side:
            if any(adj[v] & union for v in p.vertices(group)):
                return None
            union |= group
    variable_mask = sum(variables)
    constraint_mask = sum(constraints)
    if any(adj[v] & constraint_mask for v in p.vertices(start & variable_mask)):
        return None
    return gateway, core_mask, core_path, variables, constraints


def solve(case, *, max_assignments=1_000_000):
    """Return a certified shortest path, proven unreachable, unsupported, or budget."""
    began = perf_counter()
    adj = case.adjacency()
    start, goal = map(p.mask_of,(case.start,case.target))
    parts = recognize(case,adj,start,goal)
    if parts is None:
        return dict(status="unsupported",path=None)
    gateway, core_mask, core_path, variables, constraints = parts
    allowed = [list(p.vertices(group & ~adj[gateway])) for group in variables]
    if prod(map(len, allowed)) > max_assignments:
        return dict(status="budget",path=None,seconds=perf_counter()-began)
    best = None
    counts = Counter()
    for choice in product(*allowed):
        counts["assignments"] += 1
        blocked = 0
        for v in choice:
            blocked |= adj[v]
        auxiliary = []
        for group in constraints:
            legal = group & ~blocked
            if not legal:
                break
            preferred = legal & start
            chosen = preferred or (legal & -legal)
            auxiliary.append(chosen)
        else:
            counts["feasible"] += 1
            variable_mask = p.mask_of(choice)
            auxiliary_mask = sum(auxiliary)
            cost = ((variable_mask | auxiliary_mask) & ~start).bit_count()
            if best is None or cost < best[0]:
                best = cost,variable_mask,auxiliary_mask
    if best is None:
        return dict(status="unreachable",path=None,seconds=perf_counter()-began,counts=dict(counts))

    cost,variable_mask,auxiliary_mask = best
    prefix = [start]
    for group in constraints + variables:
        old = prefix[-1] & group
        new = (variable_mask | auxiliary_mask) & group
        if new != old:
            prefix.append(prefix[-1] ^ old ^ new)
    exterior = prefix[-1] & ~core_mask
    path = prefix + [exterior | s for s in core_path[1:]]
    path.extend((state & ~core_mask) | core_path[-1] for state in prefix[-2::-1])
    assert len(path)-1 == 2*cost+3
    ev.validate(case,{"path":path,"length":len(path)-1},10**9,None,adj)
    return dict(status="found",path=path,length=len(path)-1,seconds=perf_counter()-began,
                gateway=gateway+1,setup_cost=cost,
                variables=[[v+1 for v in p.vertices(g)] for g in variables],
                constraints=[[v+1 for v in p.vertices(g)] for g in constraints],
                counts=dict(counts),certificate="2 * minimum exterior changes + 3")
