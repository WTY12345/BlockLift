"""Export the paper's CoRe table from the independent run and public references."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import statistics

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
REPRODUCED = DATA / "reproduced-core-693.jsonl"
PUBLIC = DATA / "public-reference.csv"


def optional_number(value):
    return int(value) if value else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=REPRODUCED)
    parser.add_argument("--references", type=Path, default=PUBLIC)
    parser.add_argument("--audit", type=Path, default=DATA/"audit-summary.json")
    parser.add_argument("--output-dir", type=Path, default=HERE)
    args = parser.parse_args()
    with args.references.open(encoding="utf-8-sig",newline="") as file:
        refs = {row["实例"]:row for row in csv.DictReader(file)}
    source = args.run.read_bytes()
    rows = []
    for line in source.splitlines():
        rec = json.loads(line)
        run = rec["run"]
        name = PurePosixPath(rec["endpoints"]).name
        ref = refs[name]
        best = optional_number(ref["公开最佳记录"])
        exact = optional_number(ref["作者精确参照"])
        lower = optional_number(ref["端点差集下界"])
        length = run.get("length") if run["status"]=="found" else None
        relation = evidence = ""
        if length is not None:
            assert lower is not None and length>=lower
            if best is not None:
                relation = "shorter" if length<best else "longer" if length>best else "equal"
            if length==lower:
                evidence = "endpoint_lower_bound"
            elif run.get("optimal") or run.get("method")=="gated_matching":
                evidence = "solver_certificate"
            elif length==exact:
                evidence = "external_exact_length"
            else:
                evidence = "path_only"
        certificate = ""
        if run["status"]=="unreachable":
            certificate = {"grid_phase":"grid_phase","gated_matching":"pigeonhole"}.get(
                run.get("method"),"complete_independent_bfs")
        rows.append(dict(graph=rec["graph"],endpoints=rec["endpoints"],family=run["family"],
                         status=run["status"],representation=run.get("representation",""),
                         nonreachability_certificate=certificate,
                         solver_method=run.get("method",""),length=length,seconds=run["seconds"],
                         within_15s=run["seconds"]<=15,endpoint_bound=lower,public_best=best,
                         external_exact=exact,public_relation=relation,optimality_evidence=evidence))
    assert len(rows)==len({(r["graph"],r["endpoints"]) for r in rows})==693
    found = [r for r in rows if r["status"]=="found"]
    summary = dict(
        source_sha256=hashlib.sha256(source).hexdigest(),
        comparison_input_sha256=hashlib.sha256(args.references.read_bytes()).hexdigest(),
        statuses=Counter(r["status"] for r in rows),
        representations=Counter(r["representation"] for r in found),
        nonreachability_certificates=Counter(r["nonreachability_certificate"] for r in rows
                                              if r["status"]=="unreachable"),
        public_comparison=Counter(r["public_relation"] or "no_path_record" for r in found),
        optimum_evidence=Counter(r["optimality_evidence"] for r in found),
        within_15s=sum(r["within_15s"] for r in rows),
        median_seconds=statistics.median(r["seconds"] for r in rows),
    )
    expected = json.loads(args.audit.read_text(encoding="utf-8"))
    assert summary["statuses"]==expected["counts"]
    assert summary["representations"]==expected["representations"]
    assert {k:v for k,v in summary["public_comparison"].items() if k!="no_path_record"}==expected["versus_public"]
    assert summary["nonreachability_certificates"]==expected["unreachable_certificates"]
    assert summary["optimum_evidence"]==dict(
        endpoint_lower_bound=expected["optimum"]["independently_met_endpoint_lower_bound"],
        solver_certificate=expected["optimum"]["solver_structural_or_bounded_proof"],
        external_exact_length=expected["optimum"]["matched_external_exact_reference"],
        path_only=expected["optimum"]["path_only"],
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir/"core-paper-per-instance.csv").open("w",encoding="utf-8-sig",newline="") as file:
        writer=csv.DictWriter(file,fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    (args.output_dir/"core-paper-summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))


if __name__=="__main__":
    main()
