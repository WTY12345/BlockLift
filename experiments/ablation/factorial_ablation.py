"""Pair four fixed-budget solver configurations on the frozen CoRe suite."""
import argparse
from collections import Counter
from dataclasses import replace
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import random
import runpy
import shutil
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

HERE = Path(__file__).resolve().parent
FROZEN = HERE.parents[1]
DATA = HERE / "data"
REFERENCE = DATA / "audit-reference.jsonl"
EXPECTED_SOURCE = "ad3ee3f3155c96af43a5ddf3489ac9ec79adc5452ad6f682e737e88d45ece96c"
ARMS = ((0, 0), (1, 0), (0, 1), (1, 1))

# Preserve generic search, twin reduction, certified one-vacancy search,
# and the block recognizers used by the saturated summary.
PATCHES = {
    "orchestrator.py": [
        ('if family in CHAINS:', 'if flags.summary and family in CHAINS:'),
        ('if family=="exp_instance" and perf_counter()<deadline:',
         'if flags.summary and family=="exp_instance" and perf_counter()<deadline:'),
        ('board=family=="queen"', 'board=flags.special and family=="queen"'),
    ],
    "solver.py": [
        ('if family=="queen" and n*n==case.n', 'if flags.special and family=="queen" and n*n==case.n'),
        ('if family=="grid":', 'if flags.special and family=="grid":'),
        ('if family=="ph-isr":', 'if flags.special and family=="ph-isr":'),
        ('if family=="exp_instance":\n        match', 'if flags.special and family=="exp_instance":\n        match'),
        ('elif family in {"sp","power","power_wide","power_wider","exp_instance"}:',
         'elif flags.summary and family in {"sp","power","power_wide","power_wider","exp_instance"}:'),
    ],
    "long_path_search.py": [
        ('if family not in {"sp","power","power_wide","power_wider","exp_instance"}:',
         'if not flags.summary or family not in {"sp","power","power_wide","power_wider","exp_instance"}:'),
    ],
    "structure_dispatch.py": [
        ('if family == "queen" and', 'if flags.special and family == "queen" and'),
        ('elif family == "ph-isr" and', 'elif flags.special and family == "ph-isr" and'),
    ],
    "twin_quotient.py": [
        ('if groups is not None:', 'if flags.summary and groups is not None:'),
    ],
    "adaptive_partition.py": [
        ('if 0 in partitions:', 'if flags.summary and 0 in partitions:'),
    ],
}


def check_source():
    sources = hashlib.sha256()
    for path in sorted((FROZEN / "blocklift").glob("*.py")):
        sources.update(path.name.encode("utf-8") + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    digest = sources.hexdigest()
    if digest != EXPECTED_SOURCE:
        raise ValueError("Expected the frozen solver bytes. See the reproduction section in README.md.")
    return digest


def prepare(destination):
    package = destination / "blocklift"
    shutil.copytree(FROZEN / "blocklift", package, ignore=shutil.ignore_patterns("__pycache__"))
    (package / "ablation_flags.py").write_text("summary = True\nspecial = True\n", encoding="utf-8")
    for name, changes in PATCHES.items():
        path = package / name
        source = path.read_text(encoding="utf-8")
        for old, new in changes:
            assert source.count(old) == 1, (name, old)
            source = source.replace(old, new)
        assert "from pathlib import Path" in source
        source = source.replace("from pathlib import Path",
                                "from pathlib import Path\nfrom blocklift import ablation_flags as flags", 1)
        path.write_text(source, encoding="utf-8")
    return package


def verified_run(solver, flags, audit, cli, case, reference, budget, arm):
    flags.summary, flags.special = arm
    before = perf_counter()
    result = solver(case, case.family, budget, name=case.name)
    seconds = perf_counter() - before
    status = result["status"]
    length = None
    if status in {"found", "unreachable"}:
        assert status == reference["status"], (case.name, arm, status, reference["status"])
    if status == "found":
        start, goal = (sum(1 << v for v in ends) for ends in (case.start, case.target))
        path = result.get("path")
        length = result["length"] if path is None else len(path) - 1
        if path is None:
            audit["compressed"](case.adjacency(), start, goal, result["witness"], length, 0)
        else:
            audit["explicit"](case.adjacency(), start, goal, cli.moves_from_path(path), length)
    return dict(status=status, seconds=seconds, in_budget=seconds <= budget,
                length=length, method=result.get("method"), branch=result.get("branch"),
                attempts=[{key: item[key] for key in ("method", "status") if key in item}
                          for item in result.get("attempts", [])])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", default=1.0, type=float)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--inputs", type=Path, default=FROZEN / "benchmark/instances")
    args = parser.parse_args()
    if not __debug__:
        parser.error("Run without Python optimization so witness assertions are checked.")
    digest = check_source()
    with (FROZEN / "benchmark/core-693.csv").open(encoding="utf-8-sig", newline="") as lines:
        suite = [tuple(str(PurePosixPath(p)) for p in row) for row in csv.reader(lines)]
    truth = {(row["graph"], row["endpoints"]): row["run"]
             for row in map(json.loads, REFERENCE.read_text(encoding="utf-8").splitlines())}
    assert len(suite) == len(set(suite)) == len(truth) == 693
    assert set(suite) == set(truth)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="blocklift-ablation-") as location:
        copied = prepare(Path(location))
        sys.path.insert(0, location)
        from blocklift import cli, ablation_flags
        solve = runpy.run_path(str(copied / "orchestrator.py"))["solve"]
        audit = runpy.run_path(str(FROZEN / "verify_benchmark.py"))
        data = args.inputs.resolve()
        seen = set()
        if args.output.exists():
            for row in map(json.loads, args.output.read_text(encoding="utf-8").splitlines()):
                assert row["budget"] == args.seconds and row["source"] == digest
                seen.add((row["graph"], row["endpoints"]))
        rng = random.Random(428219)
        counts = Counter()
        with args.output.open("a", encoding="utf-8", buffering=1) as file:
            for i, (graph, endpoints) in enumerate(suite, 1):
                arms = list(ARMS)
                rng.shuffle(arms)
                if (graph, endpoints) in seen:
                    continue
                case = cli.read_case(data / graph, data / endpoints)
                family = cli.choose_family(data / graph, data / endpoints)
                if family == "queen" and not cli.queen_board(case):
                    family = "generic"
                case = replace(case, family=family)
                results = {}
                for arm in arms:
                    key = "".join(map(str, arm))
                    meas = verified_run(solve, ablation_flags, audit, cli, case,
                                        truth[graph, endpoints], args.seconds, arm)
                    results[key] = meas
                    counts[key] += meas["status"] in {"found", "unreachable"} and meas["in_budget"]
                row = dict(graph=graph, endpoints=endpoints, family=family, vertices=case.n,
                           budget=args.seconds, source=digest, reference_status=truth[graph, endpoints]["status"],
                           reference_method=truth[graph, endpoints].get("method"), arms=results)
                file.write(json.dumps(row) + "\n")
                if i % 25 == 0 or i == len(suite):
                    print(i, dict(counts), flush=True)


if __name__ == "__main__":
    main()
