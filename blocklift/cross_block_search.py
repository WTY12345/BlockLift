"""Exact bidirectional search with cross-block extensions."""
from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from time import perf_counter

HERE = Path(__file__).resolve().parent
TIME = 5
STATE_LIMIT = 100_000


def load(filename):
    spec = spec_from_file_location(filename, HERE / filename)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


incidence = load("residual_sets.py")
ev, p = incidence.ev, incidence.p


def block_extensions(adj, blocks):
    @lru_cache(maxsize=8192)
    def blocked(tokens):
        union = 0
        for v in p.vertices(tokens):
            union |= adj[v]
        return union

    def extensions(state):
        parts = [state & block for block in blocks]
        signatures = [blocked(part) for part in parts]
        suffix = [0] * (len(parts) + 1)
        for i in range(len(parts) - 1, -1, -1):
            suffix[i] = suffix[i + 1] | signatures[i]
        prefix = 0
        for i, part in enumerate(parts):
            outside = prefix | suffix[i + 1]
            if part:
                for face, allowed in incidence.faces(part, adj, -1):
                    residual = (state ^ part) | face
                    yield residual, allowed & ~outside & ~residual
            prefix |= signatures[i]
    return extensions


def exact(case, mode, blocks, adj, *, deadline=None, state_limit=STATE_LIMIT, residual_limit=None):
    began = perf_counter()
    if deadline is None:
        deadline = began + TIME
    start, goal = map(p.mask_of, (case.start, case.target))
    trees = [{start: None}, {goal: None}]
    frontiers = [[start], [goal]]
    # 两侧分别记录已经展开的 k−1 令牌剩余集，双向搜索各自保留可恢复的父指针。
    seen_residual = [set(), set()]
    universe = (1 << case.n) - 1
    block_moves = block_extensions(adj, blocks) if mode == "block" else None
    scans = 0

    def result(status, path=None):
        return dict(status=status,path=path,length=len(path)-1 if path is not None else None,
                    candidates=scans,visited=sum(map(len,trees)),seconds=perf_counter()-began)

    if start == goal:
        return result("found", [start])
    while all(frontiers):
        side = int(len(frontiers[1]) < len(frontiers[0]))
        following = []
        for state in frontiers[side]:
            if perf_counter() > deadline or sum(map(len,trees)) >= state_limit:
                return result("budget")
            if mode == "full":
                successors = (state ^ (1<<u) ^ (1<<v) for u,v in
                              p.candidate_moves(p.summarize(state,adj),"full",None,None,None))
            else:
                faces = block_moves(state) if block_moves else incidence.faces(state,adj,universe)
                def generate():
                    # 所有包含同一剩余集的大小 k 独立集，两两之间都只差一次跳跃。每一侧展开一次即可。
                    for residual, allowed in faces:
                        if residual in seen_residual[side]:
                            continue
                        if residual_limit is not None and len(seen_residual[side]) >= residual_limit:
                            raise p.SearchTimeout(scans, 0)
                        seen_residual[side].add(residual)
                        for v in p.vertices(allowed & universe & ~state):
                            yield residual | (1<<v)
                successors = generate()
            for successor in successors:
                scans += 1
                if scans % 256 == 0 and perf_counter() >= deadline:
                    return result("budget")
                if successor in trees[side]:
                    continue
                trees[side][successor] = state
                if successor in trees[1-side]:
                    halves = []
                    for tree in trees:
                        half, current = [], successor
                        while current is not None:
                            half.append(current)
                            current = tree[current]
                        halves.append(half)
                    return result("found", halves[0][::-1] + halves[1][1:])
                if sum(map(len,trees)) >= state_limit:
                    return result("budget")
                following.append(successor)
        frontiers[side] = following
    return result("unreachable")
