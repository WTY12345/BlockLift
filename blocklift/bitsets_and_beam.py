"""Bitset state representation, candidate generation and beam search."""

from dataclasses import dataclass
from heapq import heapify, heappop, heappush, nsmallest
from itertools import count, product
from random import Random
from time import perf_counter

WIDTH = 8


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
