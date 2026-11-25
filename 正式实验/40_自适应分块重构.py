"""Adaptive partitioning and budgeted routing for Token Jumping."""
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location
from time import perf_counter

HERE = Path(__file__).resolve().parent
spec = spec_from_file_location("core", HERE / "35_CoRe全量分块组合对照.py")
core = module_from_spec(spec)
spec.loader.exec_module(core)
p = core.p
vacancy = core.pilot.load("38_单空额分层重构.py")
ACTIONS = ("beam", "face", "single", "contract")
DEFAULT_BEAM_LIMIT = 2048


def clique_partition(adj):
    # 位集的第 v 位表示顶点 v。这里从尚未分块的顶点里贪心构造小团。
    remaining = (1 << len(adj)) - 1
    groups = []
    while remaining:
        seed = (remaining & -remaining).bit_length() - 1
        group = [seed]
        remaining ^= 1 << seed
        eligible = adj[seed] & remaining
        while eligible and len(group) < 6:
            v = (eligible & -eligible).bit_length() - 1
            group.append(v)
            remaining ^= 1 << v
            eligible &= adj[v] & remaining
        groups.append(group)
    return groups


def assess(case, adj, start, target, deadline):
    # 实验中的分块探测门槛。6k<n 可排除当前块大小范围的饱和分法，但边界上仍可能存在单空额分法。
    if case.n > 500 or 6*len(case.start) < case.n:
        return {}, []
    candidates = []
    recognized = None
    if len(case.edges) <= 2*case.n and case.n % 5 == 4:
        try:
            recognized = core.structure.recognize(case)
        except ValueError:
            pass
    trials = [("recognized",recognized)] if recognized else []
    trials.append(("clique",clique_partition(adj)))
    for size in (3,4,5,6):
        trials.append((f"consecutive{size}",[list(range(i,min(i+size,case.n))) for i in range(0,case.n,size)]))
    best = {}
    seen = set()
    for name, groups in trials:
        # Saturation does not depend on block order. Keep the recognized order when available.
        identity = tuple(sorted(tuple(sorted(g)) for g in groups))
        if identity in seen:
            continue
        seen.add(identity)
        # 精确枚举小块独立数。所有块的容量之和减去令牌总数，就是这套分法的总空额。
        capacities = [vacancy.capacity(g,adj) for g in groups]
        slack = sum(capacities)-len(case.start)
        # 沿候选顺序统计最大外部边界。它是选分块的启发式分数，实际摘要还取决于连通分量。
        prefix = neighbors = boundary_width = 0
        for group in groups:
            prefix |= p.mask_of(group)
            for v in group:
                neighbors |= adj[v]
            boundary_width = max(boundary_width,(neighbors & ~prefix).bit_count())
        info = dict(name=name,slack=slack,width=boundary_width,blocks=len(groups))
        candidates.append(info)
        if slack in (0,1):
            # Favor the smallest observed separator, then smaller local products.
            score = (boundary_width,max(map(len,groups)),len(groups),name!="recognized")
            if slack not in best or score < best[slack][0]:
                best[slack] = (score,groups)
        if perf_counter() >= deadline:
            break
    return {key:value[1] for key,value in best.items()},candidates


# 模型只读取实例规模、目标阻挡概况和分块统计，输出可用求解器的优先顺序。
def context(case, start, goal, adj, candidates):
    missing = goal & ~start
    blockers = [0,0,0]
    for v in p.vertices(missing):
        blockers[min(2,(adj[v]&start).bit_count())] += 1
    return [case.n,len(case.start),missing.bit_count(),sum(x.bit_count() for x in adj)//2,
            *blockers,min((x["slack"] for x in candidates),default=-1),
            min((x["width"] for x in candidates if x["slack"]==1),default=-1)]


def action(case, adj, name, partitions, deadline, *, beam_limit=DEFAULT_BEAM_LIMIT):
    began = perf_counter()
    if began >= deadline:
        return dict(status="budget",path=None,work=0)
    try:
        if name == "beam":
            path,checks,_,_ = p.solve(case,beam_limit,"llm_rule",8,772,deadline=deadline)
            return dict(status="found" if path else "no_path_found",path=path,work=checks)
        # 公共子集搜索允许跨块跳跃，并对共同删除一个令牌后的剩余集去重。
        if name == "face":
            count = min(100000,32*1024**2//(128+(case.n+7)//8))
            result = core.pilot.exact(case,"face",None,adj,deadline=deadline,state_limit=count,residual_limit=count)
            return dict(status=result["status"],path=result["path"],work=result["candidates"])
        # 总空额为 1 时才启用这一分支。容量证书由分块探测提供，求解器内部再次核验。
        if name == "single":
            result = vacancy.solve(case,partitions[1],seconds=deadline-began,state_limit=100000)
            return dict(status=result["status"],path=result["path"],work=result["checked"])
        def check(states):
            if states >= 100000 or perf_counter() >= deadline:
                raise p.SearchTimeout(0,0)
        # 总空额为 0 时，每块一直满载，因此可以精确收缩只包含块内跳跃的解图。
        path,layers = core.structure.m.solve(case,partitions[0],optimize_lift=True,
                                            restrict_local=True,restrict_prefix=True,check=check)
        return dict(status="found" if path else "unreachable",path=path,work=sum(a for a,_ in layers))
    except p.SearchTimeout as error:
        return dict(status="budget",path=None,work=error.checked)


def rule_order(partitions):
    if 0 in partitions:
        return ["contract","beam","face"]
    if 1 in partitions:
        return ["single","beam","face"]
    return ["beam","face"]


def prompt(features, displayed):
    descriptions = {
        "beam":"limited branching toward target",
        "face":"exact bidirectional search with shared deleted token sets",
        "single":"exact layers of the unique vacant block",
    }
    return ("Predict the best first solver for token jumping. "
            "Features [n,k,target_gap,edges,unblocked_targets,singly_blocked_targets,"
            "multiply_blocked_targets,partition_slack,single_vacancy_boundary]: "
            f"{features}. Choose a fast solver likely to find a short path. "
            + " ".join(f"{letter}={descriptions[name]}." for letter,name in zip("ABC",displayed))
            + "\nAnswer:")


# 完整求解入口。rule 为确定性规则，llm 为本地模型首选，fixed 为固定顺序对照，beam 为原算法。
def solve(case, mode, choose=None, budget=1.0, *, beam_limit=DEFAULT_BEAM_LIMIT):
    began = perf_counter()
    deadline = began + budget
    start,goal = map(p.mask_of,(case.start,case.target))
    # 输入已保证起终点均为同样大小的独立集，因此相差一个点时可以直接跳过去。
    if (goal & ~start).bit_count() <= 1:
        path = [start] if start == goal else [start,goal]
        return dict(status="found",path=path,seconds=perf_counter()-began,order=[],attempts=[],inference_ms=0,partitions=[])
    adj = None if mode=="beam" else case.adjacency()
    if mode=="beam":
        partitions,candidates,order = {},[],["beam"]
    else:
        partitions,candidates = assess(case,adj,start,goal,began+0.12*budget)
        order = rule_order(partitions)
    inference_ms = 0
    if mode=="fixed" and order[0]!="contract":
        order = ["face"]+[name for name in order if name!="face"]
    # 饱和收缩优先执行。其他分支在预算允许时询问模型，只把模型选中的求解器提到首位。
    if mode=="llm" and order[0]!="contract" and perf_counter()<began+0.6*budget:
        inference_started = perf_counter()
        first = choose(context(case,start,goal,adj,candidates),order)
        inference_ms = (perf_counter()-inference_started)*1000
        order = [first]+[name for name in order if name!=first]
    attempts = []
    outcome = dict(status="budget",path=None)
    for i,name in enumerate(order):
        remaining = deadline-perf_counter()
        if remaining<=0:
            break
        # 前面的求解器只分到一部分剩余时间，以便后续方法还有机会接手。最后一个可用完余下预算。
        share = 1.0 if i==len(order)-1 else 0.68 if name in ("contract","beam","single") else 0.45
        outcome = action(case,adj,name,partitions,perf_counter()+share*remaining,beam_limit=beam_limit)
        attempts.append(dict(method=name,status=outcome["status"],work=outcome["work"]))
        # 只有找到路径或精确分支完成不可达判定才提前返回。束搜索耗尽可以继续回退。
        if outcome["status"] in ("found","unreachable") and perf_counter()<=deadline:
            break
    elapsed = perf_counter()-began
    if not attempts or elapsed>budget:
        outcome = dict(status="budget",path=None)
    return dict(status=outcome["status"],path=outcome["path"],seconds=elapsed,order=order,
                attempts=attempts,inference_ms=inference_ms,partitions=candidates)
