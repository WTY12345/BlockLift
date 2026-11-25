"""Run the unchanged delivery archive through its CLI for all official CoRe cases."""
import argparse
from collections import Counter
from contextlib import redirect_stderr
import csv
from hashlib import sha256
import io
import json
from math import isfinite
from pathlib import Path, PurePosixPath
import runpy
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
DATA = HERE / "srip对照"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive",type=Path,default=HERE/"artifacts/BlockLift-v2.zip")
    parser.add_argument("--seconds",type=float,default=15)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    if not isfinite(args.seconds) or args.seconds<=0:
        parser.error("a positive finite budget is required")
    digest = sha256(args.archive.read_bytes()).hexdigest()
    with (DATA/"official_693.csv").open(encoding="utf-8-sig",newline="") as source:
        suite = [tuple(str(PurePosixPath(p)) for p in row) for row in csv.reader(source)]
    assert len(suite)==len(set(suite))==693
    seen = set()
    counts = Counter()
    if args.output.exists():
        with args.output.open(encoding="utf-8") as source:
            for line in source:
                row = json.loads(line)
                assert row["archive_sha256"]==digest and row["budget_seconds"]==args.seconds
                key = row["graph"],row["endpoints"]
                assert key not in seen
                seen.add(key)
                counts[row["run"]["status"]] += 1
        assert seen<=set(suite)
    print("archive",digest,"seconds",args.seconds,"already completed",len(seen),flush=True)

    with TemporaryDirectory(prefix="core-frozen-") as temporary:
        workspace = Path(temporary).resolve()
        with ZipFile(args.archive) as archive:
            if any(not (workspace/name).resolve().is_relative_to(workspace) for name in archive.namelist()):
                raise ValueError("Invalid archive member path")
            archive.extractall(workspace)
        entry = workspace/"正式实验/78_最终求解器.py"
        cli = runpy.run_path(str(entry))["main"]
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
                    sys.argv = [str(entry),str(DATA/"instances"/graph),str(DATA/"instances"/endpoints),
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
                              archive_sha256=digest,command_seconds=elapsed,run=run)
                destination.write(json.dumps(record,ensure_ascii=False)+"\n")
                completed = sum(counts.values())
                if completed%25==0 or completed==len(suite) or run["status"]=="cli_error":
                    print(completed,"/",len(suite),PurePosixPath(endpoints).name,dict(counts),flush=True)
    assert sum(counts.values())==693


if __name__=="__main__":
    main()
