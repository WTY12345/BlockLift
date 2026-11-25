"""Evaluate the frozen four-candidate rule on the CoRe holdout."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path, PurePosixPath
from time import perf_counter, sleep
from urllib.error import HTTPError


spec = spec_from_file_location("core_pilot", Path(__file__).with_name("06_公开实例试跑.py"))
reference = module_from_spec(spec)
spec.loader.exec_module(reference)
DATA = reference.DATA
EDGE_CAP = 1_000_000
WALL_CAP_S = 1.0
SLACKS = (4, 16)


def holdout():
    development = {(graph, ends) for _, graph, ends in reference.selection()}
    with (DATA / "official_693.csv").open(newline="", encoding="utf-8-sig") as file:
        all_cases = [(PurePosixPath(g), PurePosixPath(d)) for g, d in csv.reader(file)]
    assert len(set(all_cases)) == len(all_cases) == 693
    assert len({(g.name, d.name) for g, d in all_cases}) == 693
    return [(g.parent.name, g, d) for g, d in all_cases if (g, d) not in development]


def prepare(case_rows, author):
    paths = sorted({
        path for _, graph, ends in case_rows
        if int(author[graph.name, ends.name]["edges"] or 0) <= EDGE_CAP
        for path in (graph, ends)
    })

    def fetch(path):
        for attempt in range(3):
            try:
                reference.download(path)
                return path, None
            except (OSError, UnicodeError) as error:
                message = str(error)
                if isinstance(error, HTTPError) and error.code in (404, 410):
                    break
                if attempt < 2:
                    sleep(attempt + 1)
        return path, message

    failures = {}
    with ThreadPoolExecutor(max_workers=16) as pool:
        for index, (path, error) in enumerate(pool.map(fetch, paths), 1):
            if error:
                failures[path] = error
            if index % 100 == 0 or index == len(paths):
                print(f"input files {index}/{len(paths)}, failures {len(failures)}", flush=True)
    return failures


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def run(case, limit, strategy, budget, scorer=None, started=None):
    pilot = reference.pilot
    if started is None:
        started = perf_counter()
    try:
        if set(case.start) == set(case.target):
            path, checked, expanded = [pilot.mask_of(case.start)], 0, 0
        else:
            path, checked, expanded, _ = pilot.solve(
                case, limit, strategy, budget, seed=20261117, deadline=started + WALL_CAP_S, scorer=scorer
            )
        status = "found" if path else "not_found"
        if perf_counter() - started > WALL_CAP_S:
            status, path = "time_cap", None
    except pilot.SearchTimeout as error:
        status, path = "time_cap", None
        checked, expanded = error.checked, error.expanded
    elapsed_ms = (perf_counter() - started) * 1000
    return {
        "status": status, "wall_ms": elapsed_ms, "checks": checked, "expanded": expanded,
        "length": len(path) - 1 if path else None, "path": path,
    }


def validate(case, result, limit, known_length, adj, *, materialize=True):
    path = result["path"]
    if path is None:
        return
    pilot = reference.pilot
    assert path[0] == pilot.mask_of(case.start) and path[-1] == pilot.mask_of(case.target)
    assert result["length"] <= limit
    assert known_length is None or result["length"] >= known_length
    for before, after in zip(path, path[1:]):
        removed, added = before & ~after, after & ~before
        assert removed.bit_count() == added.bit_count() == 1
        assert not (adj[added.bit_length() - 1] & (before ^ removed))
    if materialize:
        result["path"] = [list(pilot.vertices(state)) for state in path]


def evaluate(chosen, author, failures):
    assert len(chosen) == 669
    rows = []
    metadata = {
        "source_commit": reference.COMMIT, "width": reference.pilot.WIDTH,
        "proposal_budget": 4, "slacks": SLACKS, "wall_cap_s": WALL_CAP_S,
        "edge_cap": EDGE_CAP, "repetitions": 1, "rows": rows,
    }
    output = DATA / "留出评估_逐例结果.json"
    engines = (("blocker_4", "llm_rule", 4), ("full_beam", "full", None))
    for index, item in enumerate(chosen, 1):
        family, graph, ends = item
        history = author[graph.name, ends.name]
        known = history["transition_length"]
        known_length = int(known) if known and history["status"] == "OK" and history["result"] == "YES" else None
        row = {
            "family": family, "graph_file": graph.as_posix(), "endpoint_file": ends.as_posix(),
            "author_status": history["status"], "author_result": history["result"],
            "author_length": known_length, "author_edges": history["edges"], "runs": [],
        }
        try:
            if int(history["edges"] or 0) > EDGE_CAP:
                raise reference.EdgeLimitExceeded(f'{history["edges"]} edges (author CSV)')
            errors = [failures[path] for path in (graph, ends) if path in failures]
            if errors:
                raise OSError("; ".join(errors))
            case = reference.load_case(item, edge_cap=EDGE_CAP)
        except reference.EdgeLimitExceeded as error:
            row.update(input_status="edge_cap", input_error=str(error))
        except OSError as error:
            row.update(input_status="input_unavailable", input_error=str(error))
        except (ValueError, AssertionError, KeyError, StopIteration) as error:
            row.update(input_status="input_invalid", input_error=f"{type(error).__name__}: {error}")
        else:
            gap = len(set(case.start) - set(case.target))
            row.update(input_status="ok", vertices=case.n, edges=len(case.edges), gap=gap)
            adj = case.adjacency()
            for offset, slack in enumerate(SLACKS):
                limit = gap + slack
                pair = {"slack": slack, "limit": limit}
                for label, strategy, budget in engines[::(-1 if (index + offset) % 2 else 1)]:
                    pair[label] = run(case, limit, strategy, budget)
                for label, _, _ in engines:
                    validate(case, pair[label], limit, known_length, adj)
                row["runs"].append(pair)
        rows.append(row)
        if index % 25 == 0 or index == len(chosen):
            write_json(output, metadata)
            print(f"holdout {index}/{len(chosen)} ({sum(r['input_status'] == 'ok' for r in rows)} run)", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--download-only", action="store_true")
    args = parser.parse_args()
    chosen = holdout()
    author = reference.author_results()
    failures = prepare(chosen, author)
    if args.download_only:
        return
    evaluate(chosen, author, failures)


if __name__ == "__main__":
    main()
