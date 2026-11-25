"""Compare exact cross-block Token Jumping and existing CoRe baselines."""
from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
from itertools import combinations
import json
from pathlib import Path, PurePosixPath
from time import perf_counter

HERE = Path(__file__).resolve().parent
TIME = 5
STATE_LIMIT = 100_000


def load(filename):
    spec = spec_from_file_location(filename, HERE / filename)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


incidence = load("22_公共子集双向搜索.py")
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


def verify_transition_generator():
    from random import Random
    rng = Random(772)
    for n in range(2,10):
        for _ in range(10):
            edges = tuple((u,v) for u,v in combinations(range(n),2) if rng.random()<0.25)
            case = p.Instance("test","synthetic",n,edges,(),())
            adj = case.adjacency()
            vertices = list(range(n))
            rng.shuffle(vertices)
            blocks = [p.mask_of(vertices[i:i+3]) for i in range(0,n,3)]
            generator = block_extensions(adj,blocks)
            universe = (1<<n)-1
            for state in range(1<<n):
                if any(adj[v]&state for v in p.vertices(state)):
                    continue
                expect = {(state^(1<<u))|(1<<v) for u in p.vertices(state)
                          for v in p.vertices(universe & ~state) if not adj[v]&(state^(1<<u))}
                actual = {face|(1<<v) for face,allowed in generator(state)
                          for v in p.vertices(allowed & universe & ~state)}
                assert actual == expect


def main():
    verify_transition_generator()
    author = ev.reference.author_results()
    source = json.loads((HERE/"LLM实验/精确宏动作1.5B/CoRe_beam_全量.json").read_bytes())["rows"]
    structure = load("26_结构识别重编号.py")
    special = {"DSJC500.9_02.dat","hc-power-004-002_01.dat","hc-square-008-002_01.dat","LGC_exp_instance002_01.dat"}
    options = {}
    chosen = []
    identities = set()
    for row in source:
        g,d = [PurePosixPath(row[key]) for key in ("graph_file","endpoint_file")]
        ref = author[g.name,d.name]
        if d.name in special:
            chosen.append((row,g,d,ref))
            identities.add((g,d))
        if 3 <= int(ref["tokens"]) and int(ref["vertices"]) <= 120 and row["family"] not in ("square","power"):
            options.setdefault(row["family"],[]).append((row,g,d,ref))
    for group in options.values():
        group.sort(key=lambda item:(int(item[3]["vertices"]),item[2].name))
        for known in (True,False):
            candidate = next((item for item in group if (item[0]["author_length"] is not None)==known
                              and (item[1],item[2]) not in identities),None)
            if candidate:
                chosen.append(candidate)
                identities.add((candidate[1],candidate[2]))

    results = []
    for row,g,d,ref in chosen:
        case = ev.reference.load_case((row["family"],g,d))
        started = perf_counter()
        adj = case.adjacency()
        adjacency_seconds = perf_counter()-started
        started = perf_counter()
        try:
            groups = structure.recognize(case) if row["family"] in {"power","square"} else None
        except ValueError:
            groups = None
        groups = groups or [list(range(i,min(i+5,case.n))) for i in range(0,case.n,5)]
        blocks = [p.mask_of(group) for group in groups]
        mask_to_block = {v:i for i,group in enumerate(groups) for v in group}
        counts = [len(set(group)&set(case.start)) for group in groups]
        goal_counts = [len(set(group)&set(case.target)) for group in groups]
        minimum_cross = sum(abs(a-b) for a,b in zip(counts,goal_counts))//2
        capacities = [max(len(s) for k in range(len(group)+1) for s in combinations(group,k)
                          if not any(adj[v]&p.mask_of(s) for v in s)) for group in groups]
        slack = sum(capacities)-len(case.start)
        preprocessing = perf_counter()-started
        record = dict(name=d.name,family=row["family"],n=case.n,k=len(case.start),slack=slack,
                      block_start_counts=counts,block_target_counts=goal_counts,minimum_cross=minimum_cross,capacities=capacities,
                      srip_status=ref["status"],reference_shortest=row["author_length"],runs={})
        if slack == 0:
            started = perf_counter()
            path,_ = structure.m.solve(case,groups,optimize_lift=True,restrict_local=True,restrict_prefix=True)
            record["runs"]["saturated"] = dict(path=path,length=len(path)-1 if path is not None else None,
                                               status="found" if path is not None else "unreachable",
                                               seconds=preprocessing+perf_counter()-started)
        for mode in ("beam8","full","face","block"):
            if mode=="beam8":
                started=perf_counter()
                limit=2048
                try:
                    path,checks,_,_=p.solve(case,limit,"llm_rule",8,772,deadline=started+TIME)
                    if set(case.start)==set(case.target):
                        path=[p.mask_of(case.start)]
                    status="found" if path is not None else "no_path_found"
                except p.SearchTimeout as error:
                    path,checks,status=None,error.checked,"budget"
                run=dict(path=path,length=len(path)-1 if path is not None else None,status=status,
                         candidates=checks,seconds=perf_counter()-started)
            else:
                run=exact(case,mode,blocks,adj)
                run["seconds"]+=adjacency_seconds
                if mode=="block":
                    run["seconds"]+=preprocessing
            record["runs"][mode]=run
        limit=10**9
        for run in record["runs"].values():
            path=run["path"]
            if path is not None:
                run["cross_block"]=sum(mask_to_block[(a&~b).bit_length()-1] != mask_to_block[(b&~a).bit_length()-1]
                                       for a,b in zip(path,path[1:]))
                assert run["cross_block"] >= minimum_cross
            ev.validate(case,run,limit,row["author_length"],adj)
        exact_runs=[record["runs"][m] for m in ("full","face","block")]
        assert len({(r["status"],r["length"]) for r in exact_runs if r["status"]!="budget"})<=1
        results.append(record)
        ev.write_json(HERE/"CoRe非饱和分块对照.json",results)
        print(d.name,slack,[(m,v["status"],v["length"]) for m,v in record["runs"].items()],flush=True)


if __name__ == "__main__":
    main()
