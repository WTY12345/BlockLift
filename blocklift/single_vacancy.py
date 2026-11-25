"""Exact reachability by connected components of fixed-vacancy layers."""
from collections import deque
from itertools import combinations
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location
from time import perf_counter

spec = spec_from_file_location("core", Path(__file__).with_name("search_support.py"))
ev = module_from_spec(spec)
spec.loader.exec_module(ev)
p = ev.reference.pilot


def capacity(block, adj):
    for size in range(len(block), 0, -1):
        for vertices in combinations(block, size):
            mask = p.mask_of(vertices)
            if all(not adj[v] & mask for v in vertices):
                return size
    return 0


# 总空额经验证等于 1，所以任何合法状态都恰好有一个未满块。
def vacancy(state, block_masks, capacities):
    return next(i for i, (mask, cap) in enumerate(zip(block_masks, capacities))
                if (state & mask).bit_count() < cap)


def moves(state, adj, block_of, block_masks, vacancy_block, *, crossing):
    # 沿用原版阻挡摘要。零阻挡允许任意符合层条件的来源，单阻挡只允许移走唯一的阻挡令牌。
    _, free, single = p.summarize(state, adj)

    def allowed(u, v):
        source, destination = block_of[u], block_of[v]
        if crossing:
            return source != destination and destination == vacancy_block
        return source == destination

    for v in free:
        destination = block_of[v]
        if crossing and destination != vacancy_block:
            continue
        sources = state & (~block_masks[destination] if crossing else block_masks[destination])
        for u in p.vertices(sources):
            yield state ^ (1 << u) ^ (1 << v)
    for u, v in single:
        if allowed(u, v):
            yield state ^ (1 << u) ^ (1 << v)


def solve(case, blocks, *, seconds=5, state_limit=100_000, complete_graph=False):
    """Return an exact reachability status or budget, and a lifted witness if found."""
    started = perf_counter()
    blocks = [tuple(block) for block in blocks]
    assert all(blocks) and sorted(v for block in blocks for v in block) == list(range(case.n))
    adj = case.adjacency()
    masks = [p.mask_of(block) for block in blocks]
    block_of = {v:i for i, block in enumerate(blocks) for v in block}
    capacities = [capacity(block, adj) for block in blocks]
    start, target = map(p.mask_of, (case.start, case.target))
    assert len(case.start) == len(case.target) and sum(capacities)-len(case.start) == 1
    assert all(not adj[v] & state for state in (start, target) for v in p.vertices(state))
    # owner 将具体状态映射到层内分量，internal_parent 保存分量内部的路径树。当前实现仍要访问这些具体状态。
    owner, internal_parent = {}, {}
    components, roots, bridges, entry = [], [], {}, {}
    checked = 0

    def check():
        if len(owner) > state_limit or perf_counter()-started >= seconds:
            raise p.SearchTimeout(checked, len(owner))

    def discover(root):
        """Close precisely the within-layer component containing root."""
        nonlocal checked
        index = len(components)
        layer = vacancy(root, masks, capacities)
        # 从入口状态做块内搜索。所有块内移动都保持占用向量，因此这次闭包只访问同一层。
        states = [root]
        components.append((layer, states))
        roots.append(root)
        owner[root], internal_parent[root] = index, None
        for state in states:
            check()
            for nxt in moves(state, adj, block_of, masks, layer, crossing=False):
                checked += 1
                if nxt not in owner:
                    owner[nxt], internal_parent[nxt] = index, state
                    states.append(nxt)
                else:
                    assert owner[nxt] == index
        return index

    def towards_root(state):
        path = []
        while state is not None:
            path.append(state)
            state = internal_parent[state]
        return path

    def lift(index):
        # 用每个分量的内部路径树走到存好的出口，再执行见证中的跨块跳跃。
        # For every quotient edge, follow the component tree to the stored exit.
        edges = []
        while index != 0:
            src, before, after = entry[index]
            edges.append((before, after))
            index = src
        path = [start]
        for before, after in reversed(edges):
            path.extend(towards_root(before)[-2::-1] if internal_parent[before] is not None else [])
            path.append(after)
        path.extend(towards_root(target)[-2::-1] if internal_parent[target] is not None else [])
        return path

    path = None
    status = "unreachable"
    quotient_complete = False
    try:
        origin = discover(start)
        # 外层对分量做 BFS，每条边恰好消耗一次跨块跳跃。首次抵达终点分量时，跨块次数最少。
        queue = deque([origin])
        while queue:
            index = queue.popleft()
            if owner.get(target) == index:
                path, status = lift(index), "found"
                if not complete_graph:
                    break
            layer, states = components[index]
            for state in states:
                check()
                for nxt in moves(state, adj, block_of, masks, layer, crossing=True):
                    checked += 1
                    if nxt not in owner:
                        other = discover(nxt)
                        queue.append(other)
                        entry[other] = (index, state, nxt)
                    else:
                        other = owner[nxt]
                    assert components[other][0] != layer
                    # 同一对分量之间存一条具体跳跃见证即可恢复可达路径。缩短块内步数需要另外处理。
                    if (index, other) not in bridges:
                        bridges[index, other] = (state, nxt)
                        bridges[other, index] = (nxt, state)
        # 外层队列耗尽才完成全部可达分量的构造。默认找到终点会提前返回一张部分摘要图。
        else:
            quotient_complete = True
    except p.SearchTimeout:
        if path is None:
            status = "budget"
    return dict(status=status,path=path,capacities=capacities,quotient_complete=quotient_complete,
                components=[dict(vacancy_block=layer,root=root,size=len(states))
                            for (layer,states),root in zip(components,roots)],
                edges=[dict(source=a,target=b,exit=x,arrival=y)
                       for (a,b),(x,y) in sorted(bridges.items()) if a<b],
                states=len(owner),checked=checked,seconds=perf_counter()-started)
