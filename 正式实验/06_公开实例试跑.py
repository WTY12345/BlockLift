"""Run the existing beam policies and bounded BFS on a fixed CoRe pilot."""

import csv
import argparse
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path, PurePosixPath
import statistics
import sys
from time import perf_counter
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "srip对照"
COMMIT = "df807b6b6ea66b7ec37a5371c58967eecc5ce762"
SOURCE = f"https://raw.githubusercontent.com/TakehideSoh/KR2026/{COMMIT}/"
FAMILIES = ("grid", "color04", "handcrafted", "sp", "square", "random_instance")
STATE_CAP = 12000
spec = spec_from_file_location("isr_pilot", ROOT.parent / "02_机制核验.py")
pilot = module_from_spec(spec)
sys.modules[spec.name] = pilot
spec.loader.exec_module(pilot)


def selection():
    """First four distinct graph files per family, independent of solver outcomes."""
    with (DATA / "official_693.csv").open(newline="", encoding="utf-8-sig") as file:
        rows = [(PurePosixPath(g), PurePosixPath(d)) for g, d in csv.reader(file) if g and d]
    assert len(rows) == 693
    counts, graphs, chosen = Counter(), set(), []
    for graph, endpoints in rows:
        family = graph.parent.name
        if family in FAMILIES and counts[family] < 4 and graph not in graphs:
            counts[family] += 1
            graphs.add(graph)
            chosen.append((family, graph, endpoints))
    assert counts == Counter(dict.fromkeys(FAMILIES, 4)), counts
    return chosen


def download(remote):
    target = DATA / "instances" / remote
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        upstream = PurePosixPath("benchmark/instances", *remote.parts[1:])
        with urlopen(SOURCE + upstream.as_posix(), timeout=15) as response:
            body = response.read()
        body.decode("utf-8-sig")
        target.write_bytes(body)
    return target


class EdgeLimitExceeded(ValueError):
    pass


def load_case(row, edge_cap=None):
    family, graph, endpoints = row
    graph_path, endpoints_path = map(download, (graph, endpoints))
    with graph_path.open(encoding="utf-8-sig") as file:
        lines = (line.split() for line in file)
        header = next(line for line in lines if line and line[0] == "p")
        count, expected_edges = map(int, header[-2:])
        if edge_cap is not None and expected_edges > edge_cap:
            raise EdgeLimitExceeded(f"{expected_edges} edges")
        edges = tuple(tuple(int(v) - 1 for v in line[1:]) for line in lines if line and line[0] == "e")
    assert len(edges) == expected_edges
    assert all(0 <= u < count and 0 <= v < count and u != v for u, v in edges)
    endpoints_by_type = {}
    for line in endpoints_path.read_text(encoding="utf-8-sig").splitlines():
        values = line.split()
        if values and values[0] in {"s", "t"}:
            endpoints_by_type[values[0]] = tuple(int(v) - 1 for v in values[1:])
    start, end = endpoints_by_type["s"], endpoints_by_type["t"]
    assert len(start) == len(end)
    for group in (start, end):
        members = set(group)
        assert len(group) == len(members) and all(0 <= v < count for v in group)
        assert all(u not in members or v not in members for u, v in edges)
    return pilot.Instance(endpoints.name, family, count, edges, start, end)


def bounded_bfs(case, limit):
    """Local exact reference only when the bounded search finishes."""
    adj = case.adjacency()
    start, goal = pilot.mask_of(case.start), pilot.mask_of(case.target)
    queue = deque([(start, 0)])
    parents = {start: None}
    checked = 0
    deadline = perf_counter() + 1
    while queue:
        state, depth = queue.popleft()
        if state == goal:
            path = []
            while state is not None:
                path.append(state)
                state = parents[state]
            return "found", path[::-1], checked
        if depth >= limit:
            continue
        moves = pilot.candidate_moves(pilot.summarize(state, adj), "full", None, None, None)
        for removed, added in moves:
            checked += 1
            if checked % 256 == 0 and perf_counter() >= deadline:
                return "time_cap", None, checked
            successor = state ^ (1 << removed) ^ (1 << added)
            if successor in parents or (goal & ~successor).bit_count() > limit - depth - 1:
                continue
            if len(parents) >= STATE_CAP and successor != goal:
                return "state_cap", None, checked
            parents[successor] = state
            queue.append((successor, depth + 1))
    return "no_path_within_limit", None, checked


def measured(run, case, limit, repeat=3):
    timings = []
    for _ in range(repeat):
        started = perf_counter()
        status, path, checked = run()
        timings.append(perf_counter() - started)
        if path is not None:
            assert pilot.valid_path(case, path, limit), case.name
    return {"status": status, "wall_ms": statistics.median(timings) * 1000,
            "length": len(path) - 1 if path is not None else None, "checks": checked,
            "path": [list(pilot.vertices(s)) for s in path] if path is not None else None}


def beam(case, limit, policy, budget):
    if set(case.start) == set(case.target):
        return "found", [pilot.mask_of(case.start)], 0
    path, checked, _, _ = pilot.solve(case, limit, policy, budget, seed=20261117)
    return ("found" if path is not None else "not_found"), path, checked


def author_results():
    with (DATA / "作者完整结果.csv").open(newline="", encoding="utf-8-sig") as file:
        rows = [row for row in csv.DictReader(file) if row["solver"] == "v47-d1-d2"]
    assert len(rows) == 733
    return {(row["col_file"], row["dat_file"]): row for row in rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slack", type=int, default=4)
    args = parser.parse_args()
    if args.slack < 0:
        parser.error("--slack must be nonnegative")
    chosen = selection()
    official = author_results()
    with ThreadPoolExecutor(max_workers=8) as pool:
        cases = list(pool.map(load_case, chosen))
    rows = []
    for case, (_, graph, endpoints) in zip(cases, chosen):
        gap = len(set(case.start) - set(case.target))
        limit = gap + args.slack
        row = {"name": case.name, "family": case.family, "n": case.n, "limit": limit,
               "gap": gap, "graph_file": graph.as_posix(), "endpoint_file": endpoints.as_posix()}
        for key, strategy, b in (
            ("blocker_2", "llm_rule", 2), ("blocker_4", "llm_rule", 4),
            ("blocker_8", "llm_rule", 8), ("full_beam", "full", None),
        ):
            row[key] = measured(lambda: beam(case, limit, strategy, b), case, limit)
        row["bounded_bfs"] = measured(lambda: bounded_bfs(case, limit), case, limit, repeat=1)
        reference = row["bounded_bfs"]
        author = official[graph.name, endpoints.name]
        distance = int(author["transition_length"]) if author["status"] == "OK" and author["result"] == "YES" else None
        if distance is not None and reference["status"] == "found":
            assert reference["length"] == distance
        if distance is not None and reference["status"] == "no_path_within_limit":
            assert distance > limit
        if reference["status"] == "no_path_within_limit":
            assert all(row[key]["status"] != "found" for key in ("blocker_2", "blocker_4", "blocker_8", "full_beam"))
        row["srip_author_history"] = {
            "status": author["status"], "result": author["result"], "reported_length": distance,
            "cpu_time_s": author["cpu_time_s"], "within_limit": distance <= limit if distance is not None else None,
        }
        print(case.name, case.n, limit, *(row[k]["status"] for k in ("blocker_2", "full_beam", "bounded_bfs")), flush=True)
        rows.append(row)
    output = {"source_commit": COMMIT, "vertex_numbering": "zero_based", "width": pilot.WIDTH,
              "slack": args.slack, "bfs_state_cap": STATE_CAP, "bfs_wall_cap_s": 1, "rows": rows}
    (DATA / f"本地逐例结果_额外{args.slack}步.json").write_text(
        json.dumps(output, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
