"""Recognize the CoRe pigeonhole construction and solve its gated assignment."""
from collections import Counter
from importlib.util import module_from_spec, spec_from_file_location
from itertools import combinations
from math import comb
from pathlib import Path
from time import perf_counter

from scipy.optimize import linear_sum_assignment

HERE = Path(__file__).resolve().parent
spec = spec_from_file_location("gateway", HERE / "pigeonhole_structure.py")
gateway = module_from_spec(spec)
spec.loader.exec_module(gateway)
p, ev = gateway.p, gateway.ev
CORE_EDGES = {(0, 1), (0, 3), (1, 2), (2, 3), (2, 4), (3, 4)}
CORE_MOVES = [(2, 4), (0, 1), (4, 3)]


def recognize(case, rows, columns):
    """Verify every edge and both endpoints before treating the graph as a matching problem."""
    variable_end = 5 + 3 * rows * columns
    row_end = variable_end + rows * columns
    if case.n != row_end + 2 * comb(rows, 2) * columns:
        return None
    adj = case.adjacency()
    start, target = set(case.start), set(case.target)
    if start & set(range(5)) != {0, 2} or target & set(range(5)) != {1, 3}:
        return None
    if start - set(range(5)) != target - set(range(5)):
        return None
    expected = set(CORE_EDGES)
    variables = []
    row_groups = []
    for i in range(rows):
        group = []
        for j in range(columns):
            false = 5 + 3 * (i * columns + j)
            true, idle = false + 1, false + 2
            clause = variable_end + i * columns + j
            variables.append((false, true, idle))
            group.append(clause)
            if idle not in start or false in start or true in start:
                return None
            expected.update(combinations((false, true, idle), 2))
            expected.update(((4, idle), (false, clause)))
        if len(start.intersection(group)) != 1:
            return None
        row_groups.append(group)
        expected.update(combinations(group, 2))

    conflicts = []
    match_pairs = set()
    true_index = {v: divmod(i, columns) for i, (_, v, _) in enumerate(variables)}
    for a in range(row_end, case.n, 2):
        b = a + 1
        left = [v for v in p.vertices(adj[a]) if v in true_index]
        right = [v for v in p.vertices(adj[b]) if v in true_index]
        if len(left) != 1 or len(right) != 1 or len(start & {a, b}) != 1:
            return None
        li, lj = true_index[left[0]]
        ri, rj = true_index[right[0]]
        key = min(li, ri), max(li, ri), lj
        if li == ri or lj != rj or key in match_pairs:
            return None
        match_pairs.add(key)
        expected.update(((a, b), (left[0], a), (right[0], b)))
        conflicts.append(((a, left[0]), (b, right[0])))
    if expected != {tuple(sorted(edge)) for edge in case.edges}:
        return None
    return variables, row_groups, conflicts


def solve(case, rows, columns):
    started = perf_counter()
    parts = recognize(case, rows, columns)
    if parts is None:
        return dict(status="unsupported", seconds=perf_counter()-started, moves=None)
    if rows > columns:
        return dict(status="unreachable", seconds=perf_counter()-started, moves=None,
                    certificate="No injection from rows to columns")

    variables, row_groups, conflicts = parts
    start = set(case.start)
    penalty = Counter(v for clause in conflicts for u, v in clause if u in start)
    costs = [[(clause not in start) + penalty[variables[i * columns + j][1]]
              for j, clause in enumerate(group)] for i, group in enumerate(row_groups)]
    _, assignment = linear_sum_assignment(costs)
    active = {variables[i * columns + int(j)][1] for i, j in enumerate(assignment)}
    setup = []
    for i, group in enumerate(row_groups):
        chosen = group[assignment[i]]
        current = next(v for v in group if v in start)
        if current != chosen:
            setup.append((current, chosen))
    for clause in conflicts:
        (current, blocker), (other, _) = sorted(clause, key=lambda entry: entry[0] not in start)
        if blocker in active:
            setup.append((current, other))
    setup.extend((idle, true if true in active else false) for false, true, idle in variables)
    path = setup + CORE_MOVES + [(v, u) for u, v in reversed(setup)]
    cost = sum(costs[i][j] for i, j in enumerate(assignment))
    assert len(path) == 2 * (rows * columns + cost) + 3
    elapsed = perf_counter() - started

    state = p.mask_of(case.start)
    states = [state]
    for u, v in path:
        assert state & (1 << u) and not state & (1 << v)
        state ^= (1 << u) | (1 << v)
        states.append(state)
    ev.validate(case, dict(path=states, length=len(path)), 10**9, None, case.adjacency(), materialize=False)
    return dict(status="found", seconds=elapsed, length=len(path), matching=[int(j)+1 for j in assignment],
                minimum_setup=len(setup), moves=[[u+1, v+1] for u, v in path])
