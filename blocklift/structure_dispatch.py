"""Dispatch graph-specific solvers and generic fallback."""
from importlib.util import module_from_spec, spec_from_file_location
from math import isqrt
from pathlib import Path
from time import perf_counter

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "CoRe最新结构算法全量.jsonl"
MODES = ("beam", "previous", "latest")
BUDGET = 1.0
PUBLIC = ("v47-d1-d2", "nuasp", "paris", "reconfaigeration")


def load(filename):
    path = HERE / filename
    spec = spec_from_file_location(path.stem, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


twins = load("twin_quotient.py")
queen = load("queen_search.py")
gate = load("pigeonhole_structure.py")
alg, ev, p = twins.alg, twins.ev, twins.p


def solve(case, family, budget=BUDGET, *, beam_limit=alg.DEFAULT_BEAM_LIMIT):
    started = perf_counter()
    deadline = started + budget
    start, goal = map(p.mask_of, (case.start,case.target))
    attempts = []
    if (goal & ~start).bit_count() <= 1:
        path = [start] if start == goal else [start, goal]
        return dict(status="found",path=path,seconds=perf_counter()-started,branch="direct",attempts=attempts)
    n = isqrt(case.n)
    if family == "queen" and n*n == case.n and len(case.start) == n-1:
        board = queen.Board(n,goal)
        strategies = [(32,True),(16,False)] if n<=20 else [(16,False),(48,True)]
        for width, reverse in strategies:
            now = perf_counter()
            if now >= deadline:
                break
            share = 0.75 if width == strategies[0][0] else 0.5
            path, work = queen.search(board,start,width,width,now+share*(deadline-now),4,reverse)
            attempts.append(dict(method="queen",work=work,width=width,reverse=reverse))
            if path is not None:
                board.validate(path,start)
                if perf_counter()<=deadline:
                    return dict(status="found",path=path,seconds=perf_counter()-started,branch="queen",attempts=attempts)
                break
    elif family == "ph-isr" and case.n<=500:
        result = gate.solve(case,max_assignments=512)
        attempts.append(dict(method="gateway",status=result["status"]))
        if result["status"] in ("found","unreachable") and perf_counter()<=deadline:
            return dict(status=result["status"],path=result["path"],seconds=perf_counter()-started,
                        branch="gateway",attempts=attempts)
    elif case.n<=500 or (case.n<=2000 and len(case.edges)<=20*case.n):
        # Avoid constructing a replacement instance on the common no-equivalent-vertices path.
        adj = case.adjacency()
        closed = {values | (1<<v) for v,values in enumerate(adj)}
        wider_block = twins.capacity_two_partition(case,adj)
        if len(closed)<case.n or wider_block is not None:
            remaining = deadline-perf_counter()
            if remaining>0:
                result=twins.solve(case,budget=remaining,beam_limit=beam_limit)
                attempts.append(dict(method=result["method"],classes=result["classes"]))
                if result["status"] in ("found","unreachable") and perf_counter()<=deadline:
                    return dict(status=result["status"],path=result["path"],seconds=perf_counter()-started,
                                branch=result["method"],attempts=attempts)
    remaining = deadline-perf_counter()
    if remaining<=0:
        return dict(status="budget",path=None,seconds=perf_counter()-started,branch="adaptive",attempts=attempts)
    result=alg.solve(case,"rule",budget=remaining,beam_limit=beam_limit)
    elapsed=perf_counter()-started
    return dict(status=result["status"] if elapsed<=budget else "budget",
                path=result["path"] if elapsed<=budget else None,seconds=elapsed,
                branch="adaptive",attempts=attempts+result["attempts"])
