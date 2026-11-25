"""Run BlockLift through its CLI for all 693 CoRe cases."""
import argparse
from collections import Counter
from contextlib import redirect_stderr
import csv
from hashlib import sha256
import io
import json
from math import isfinite
from pathlib import Path, PurePosixPath
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

HERE = Path(__file__).resolve().parent
DATA = HERE / "benchmark"
SOLVER = HERE / "blocklift"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds",type=float,default=15)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    if not isfinite(args.seconds) or args.seconds<=0:
        parser.error("a positive finite budget is required")
    source_hash = sha256()
    for module in sorted(SOLVER.glob("*.py")):
        source_hash.update(module.name.encode("utf-8") + b"\0")
        source_hash.update(sha256(module.read_bytes()).digest())
    digest = source_hash.hexdigest()
    with (DATA/"core-693.csv").open(encoding="utf-8-sig",newline="") as source:
        suite = [tuple(str(PurePosixPath(p)) for p in row) for row in csv.reader(source)]
    assert len(suite)==len(set(suite))==693
    seen = set()
    counts = Counter()
    if args.output.exists():
        with args.output.open(encoding="utf-8") as source:
            for line in source:
                row = json.loads(line)
                assert row["source_sha256"]==digest and row["budget_seconds"]==args.seconds
                key = row["graph"],row["endpoints"]
                assert key not in seen
                seen.add(key)
                counts[row["run"]["status"]] += 1
        assert seen<=set(suite)
    print("source",digest,"seconds",args.seconds,"already completed",len(seen),flush=True)

    from blocklift.cli import main as cli

    with TemporaryDirectory(prefix="blocklift-") as temporary:
        workspace = Path(temporary)
        trial = workspace/"trial.json"
        with args.output.open("a",encoding="utf-8",buffering=1) as destination:
            for graph,endpoints in suite:
                if (graph,endpoints) in seen:
                    continue
                argv = sys.argv
                diagnostics = io.StringIO()
                trial.unlink(missing_ok=True)
                began = perf_counter()
                try:
                    sys.argv = ["blocklift",str(DATA/"instances"/graph),str(DATA/"instances"/endpoints),
                                "--seconds",str(args.seconds),"--output",str(trial)]
                    with redirect_stderr(diagnostics):
                        cli()
                    elapsed = perf_counter()-began
                    run = json.loads(trial.read_bytes())
                    assert run["schema"]=="tj-witness-v1" and run["budget_seconds"]==args.seconds
                    if run["status"]=="found":
                        assert run["representation"] in {"moves","compressed"}
                        if run["representation"]=="moves":
                            assert run["length"]==len(run["moves"])
                except SystemExit as error:
                    elapsed = perf_counter()-began
                    run = dict(status="cli_error",exit_code=error.code,diagnostics=diagnostics.getvalue().strip())
                finally:
                    sys.argv = argv
                counts[run["status"]]+=1
                record = dict(graph=graph,endpoints=endpoints,budget_seconds=args.seconds,
                              source_sha256=digest,command_seconds=elapsed,run=run)
                destination.write(json.dumps(record,ensure_ascii=False)+"\n")
                completed = sum(counts.values())
                if completed%25==0 or completed==len(suite) or run["status"]=="cli_error":
                    print(completed,"/",len(suite),PurePosixPath(endpoints).name,dict(counts),flush=True)
    assert sum(counts.values())==693


if __name__=="__main__":
    main()
