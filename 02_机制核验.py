"""Compare four token-jumping candidate generators on a fixed small suite."""

from collections import deque
from dataclasses import dataclass
from heapq import heapify, heappop, heappush, nsmallest
from itertools import combinations, count, product
import json
from pathlib import Path
from random import Random
from statistics import median
from time import perf_counter

SEED = 20261110
WIDTH = 8
BUDGETS = (2, 4, 8)
FAMILIES = ("random", "grid", "detour")
ROOT = Path(__file__).resolve().parent


def vertices(mask):
    while mask:
        bit = mask & -mask
        yield bit.bit_length() - 1
        mask ^= bit


def mask_of(items):
    return sum(1 << v for v in items)


@dataclass(frozen=True)
class Instance:
    name: str
    family: str
    n: int
    edges: tuple
    start: tuple
    target: tuple

    def adjacency(self):
        masks = [0] * self.n
        for u, v in self.edges:
            masks[u] |= 1 << v
            masks[v] |= 1 << u
        return masks


def pick_set(rng, masks, k):
    for _ in range(100):
        order = list(range(len(masks)))
        rng.shuffle(order)
        chosen = 0
        for v in order:
            if not (masks[v] & chosen):
                chosen |= 1 << v
                if chosen.bit_count() == k:
                    return tuple(vertices(chosen))
    raise ValueError("could not generate independent set")


def make_suite():
    rng = Random(SEED)
    cases = []
    for family in FAMILIES:
        for i in range(24):
            name = f"{family}-{i:02d}"
            if family == "random":
                n, k = 16 + i % 5, 4 + i % 3
                p = (0.12, 0.20, 0.28)[i % 3]
                edges = [(u, v) for u, v in combinations(range(n), 2) if rng.random() < p]
            elif family == "grid":
                rows, cols, k = 4, 4 + i % 2, 4 + i % 3
                n = rows * cols
                edges = [
                    (r * cols + c, (r + dr) * cols + c + dc)
                    for r, c in product(range(rows), range(cols))
                    for dr, dc in ((1, 0), (0, 1))
                    if r + dr < rows and c + dc < cols
                ]
            else:
                k = 3 + i % 4
                start = range(k)
                target = range(k, 2 * k)
                buffers = range(2 * k, 3 * k - 1)
                n = 3 * k - 1 + 4 + i % 3
                decoys = range(3 * k - 1, n)
                edges = list(product(start, target))
                for v in decoys:
                    p = rng.choice((0.2, 0.45, 0.7))
                    edges.extend(
                        (u, v) for u in range(v)
                        if rng.random() < (p / 2 if u in buffers else p)
                    )

            labels = list(range(n))
            rng.shuffle(labels)
            edges = tuple(sorted(tuple(sorted((labels[u], labels[v]))) for u, v in edges))
            if family == "detour":
                start = tuple(sorted(labels[u] for u in start))
                target = tuple(sorted(labels[v] for v in target))
            else:
                masks = Instance(name, family, n, edges, (), ()).adjacency()
                start, target = pick_set(rng, masks, k), pick_set(rng, masks, k)
                while start == target:
                    target = pick_set(rng, masks, k)
            cases.append(Instance(name, family, n, edges, start, target))
    return cases


def exact_distance(case):
    """Independent reference: enumerate swaps and check original edge incidences."""
    adjacent = [set() for _ in range(case.n)]
    for u, v in case.edges:
        adjacent[u].add(v)
        adjacent[v].add(u)
    start, target = frozenset(case.start), frozenset(case.target)
    seen = {start}
    queue = deque([(start, 0)])
    while queue:
        state, depth = queue.popleft()
        if state == target:
            return depth
        outside = set(range(case.n)) - state
        for u in state:
            remainder = state - {u}
            for v in outside:
                if adjacent[v].isdisjoint(remainder):
                    new = remainder | {v}
                    if new not in seen:
                        seen.add(new)
                        queue.append((new, depth + 1))
    return None


def valid_path(case, path, limit):
    if len(path) - 1 > limit:
        return False
    if path[0] != mask_of(case.start) or path[-1] != mask_of(case.target):
        return False
    states = [set(vertices(state)) for state in path]
    if any(len(state) != len(case.start) for state in states):
        return False
    if any(u in state and v in state for state in states for u, v in case.edges):
        return False
    return all(len(a - b) == len(b - a) == 1 for a, b in zip(states, states[1:]))


def summarize(state, adj):
    removed, free, single = list(vertices(state)), [], []
    for v, neighbors in enumerate(adj):
        if state & (1 << v):
            continue
        blockers = state & neighbors
        if blockers == 0:
            free.append(v)
        elif blockers & (blockers - 1) == 0:
            single.append((blockers.bit_length() - 1, v))
    return removed, free, single


def ranked_moves(removed, free, single, weights, budget):
    """Top b by (descending score, ascending removed/added vertex IDs)."""
    removed = sorted(removed, key=lambda u: (-weights[u], u))
    free = sorted(free, key=lambda v: (weights[v], v))
    # All rows have the same column order. Rows beyond the first b cannot
    # enter the top b because their first element is already out-ranked.
    heap = [
        (weights[free[0]] - weights[u], u, free[0], 0)
        for u in removed[:budget] if free
    ]
    heap.extend(
        (weights[v] - weights[u], u, v, -1)
        for u, v in nsmallest(budget, single, key=lambda pair: (
            weights[pair[1]] - weights[pair[0]], *pair
        ))
    )
    heapify(heap)
    for _ in range(budget):
        if not heap:
            break
        _, u, v, column = heappop(heap)
        yield u, v
        if 0 <= column < len(free) - 1:
            nxt = free[column + 1]
            heappush(heap, (weights[nxt] - weights[u], u, nxt, column + 1))


def candidate_moves(summary, strategy, budget, rng, weights):
    removed, free, single = summary
    if strategy == "full":
        yield from product(removed, free)
        yield from single
    elif strategy == "random":
        free_count = len(removed) * len(free)
        total = free_count + len(single)
        for i in rng.sample(range(total), min(budget, total)):
            if i >= free_count:
                yield single[i - free_count]
            else:
                row, col = divmod(i, len(free))
                yield removed[row], free[col]
    else:
        yield from ranked_moves(removed, free, single, weights, budget)


def audit(cases):
    rng = Random(SEED + 1)
    checks = 0
    for case in cases:
        adj = case.adjacency()
        edges = set(case.edges)
        for state in (case.start, case.target, pick_set(rng, adj, len(case.start))):
            summary = summarize(mask_of(state), adj)
            actual = set(candidate_moves(summary, "full", None, None, None))
            expected = {
                (u, v) for u in state for v in set(range(case.n)) - set(state)
                if all(tuple(sorted((w, v))) not in edges for w in state if w != u)
            }
            assert actual == expected
            weights = [rng.randrange(-4, 5) for _ in adj]
            expected_order = sorted(expected, key=lambda pair: (
                weights[pair[1]] - weights[pair[0]], *pair
            ))
            for budget in BUDGETS:
                assert list(ranked_moves(*summary, weights, budget)) == expected_order[:budget]
            checks += 1
    return checks


class SearchTimeout(TimeoutError):
    def __init__(self, checked, expanded):
        super().__init__("beam search exceeded its wall-clock budget")
        self.checked = checked
        self.expanded = expanded


def solve(case, limit, strategy, budget, seed, deadline=None, scorer=None, observer=None, layer_observer=None):
    adj = case.adjacency()
    start, target = mask_of(case.start), mask_of(case.target)
    k = len(case.target)
    target_degree = [(target & neighbors).bit_count() for neighbors in adj]
    is_target = [int(bool(target & (1 << v))) for v in range(case.n)]
    weights = (
        [degree - 4 * flag for degree, flag in zip(target_degree, is_target)]
        if strategy == "llm_rule" else [-flag for flag in is_target]
    )
    initial_block = sum(target_degree[u] for u in case.start)
    rng = Random(seed)
    beam = [(start, initial_block)]
    parents = {start: None}
    checked = expanded = implicit = 0

    depths = count(1) if limit is None else range(1, limit + 1)
    for depth in depths:
        options = {}
        for state, blocker_sum in beam:
            if deadline is not None and perf_counter() >= deadline:
                raise SearchTimeout(checked, expanded)
            expanded += 1
            summary = summarize(state, adj)
            if observer is not None:
                observer(state)
            removed, free, single = summary
            implicit += len(removed) * len(free) + len(single)
            state_weights = weights if scorer is None else scorer(state, adj, target)
            for u, v in candidate_moves(summary, strategy, budget, rng, state_weights):
                checked += 1
                if deadline is not None and checked % 256 == 0 and perf_counter() >= deadline:
                    raise SearchTimeout(checked, expanded)
                new = state ^ (1 << u) ^ (1 << v)
                if new in parents or new in options:
                    continue
                gap = k - (new & target).bit_count()
                # Each jump can occupy at most one new target vertex.
                if limit is not None and gap > limit - depth:
                    continue
                if new == target:
                    path = [new, state]
                    while parents[path[-1]] is not None:
                        path.append(parents[path[-1]])
                    return path[::-1], checked, expanded, implicit
                new_blockers = blocker_sum - target_degree[u] + target_degree[v]
                options[new] = (gap, new_blockers, state)
        retained = nsmallest(WIDTH, options, key=lambda key: (*options[key][:2], key))
        if layer_observer is not None:
            layer_observer(depth, beam, options, retained, parents)
        beam = [(new, options[new][1]) for new in retained]
        parents.update((new, options[new][2]) for new in retained)
        if not beam:
            break
    return None, checked, expanded, implicit


def main():
    cases = make_suite()
    audited = audit(cases)
    print(f"Audited {audited} states. Computing exact distances.", flush=True)
    prepared = []
    for index, case in enumerate(cases):
        distance = exact_distance(case)
        limit = 12 if distance is None else distance + 4
        prepared.append((index, case, distance, limit))
    print(f"Exact positives: {sum(distance is not None for _, _, distance, _ in prepared)}", flush=True)
    configs = [("full", None), *product(("random", "greedy", "llm_rule"), BUDGETS)]
    raw = {}
    for strategy, budget in configs:
        key = strategy if budget is None else f"{strategy}-{budget}"
        times = [[] for _ in cases]
        outcomes = [None for _ in cases]
        for repetition in range(3):
            order = list(prepared)
            Random(SEED + repetition).shuffle(order)
            for index, case, distance, limit in order:
                started = perf_counter()
                path, checked, expanded, implicit = solve(
                    case, limit, strategy, budget, SEED + 1000 + index
                )
                times[index].append(perf_counter() - started)
                if path is not None:
                    assert distance is not None and len(path) - 1 >= distance
                    assert valid_path(case, path, limit), case.name
                result = {
                    "name": case.name,
                    "family": case.family,
                    "distance": distance,
                    "limit": limit,
                    "path_length": None if path is None else len(path) - 1,
                    "path": None if path is None else [list(vertices(state)) for state in path],
                    "checked": checked,
                    "expanded": expanded,
                    "implicit_legal": implicit,
                }
                assert outcomes[index] is None or outcomes[index] == result
                outcomes[index] = result
        for index, result in enumerate(outcomes):
            result["time_ms"] = 1000 * median(times[index])
        raw[key] = outcomes
        print(
            f"{key:12} success={sum(row['path'] is not None for row in outcomes):2} "
            f"checked={sum(row['checked'] for row in outcomes):7} "
            f"ms={sum(row['time_ms'] for row in outcomes):.2f}", flush=True
        )
    output = {
        "seed": SEED, "width": WIDTH, "audit_states": audited,
        "cases": [vars(case) for case in cases], "runs": raw,
    }
    (ROOT / "03_实验结果.json").write_text(
        json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
