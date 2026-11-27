"""Summarize saturated-summary attribution and paired prefix experiments."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from statistics import median

from factorial_ablation import ARMS, DATA, REFERENCE

KEYS = tuple("".join(map(str, arm)) for arm in ARMS)


def load(path):
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file]


def completed(run):
    return run["status"] in {"found", "unreachable"} and run["in_budget"]


def prefix_report(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["group"]].append(row)
    output = {}
    for group, entries in groups.items():
        stats = Counter(n=len(entries))
        ratios = defaultdict(list)
        for entry in entries:
            trials = entry["repeats"]
            off, on = ([rep[mode] for rep in trials] for mode in ("off", "on"))
            off_done, on_done = (all(completed(run) for run in arm) for arm in (off, on))
            stats["off"] += off_done
            stats["on"] += on_done
            stats["on_only"] += on_done and not off_done
            stats["off_only"] += off_done and not on_done
            stats["off_state_limit"] += all(r["status"] == "state_cap" for r in off)
            stats["on_state_limit"] += all(r["status"] == "state_cap" for r in on)
            if not (off_done and on_done):
                continue
            stats["paired"] += 1
            before, after = (median(r["len_product"] for r in arm) for arm in (off, on))
            seconds_off, seconds_on = (median(r["elapsed"] for r in arm) for arm in (off, on))
            if before and after:
                ratios["state"].append(before / after)
                stats["fewer_states"] += after < before
            ratios["time"].append(seconds_off / seconds_on)
            stats["faster"] += seconds_off > seconds_on
            lengths = [r["length"] for r in off + on]
            if None not in lengths:
                stats["length_equal"] += lengths[0] == lengths[-1]
                stats["length_longer"] += lengths[0] < lengths[-1]
                stats["length_shorter"] += lengths[0] > lengths[-1]
                ratios["length"].append(lengths[-1] / lengths[0] if lengths[0] else 1)
            for mode, arm in (("off", off), ("on", on)):
                assert len({r["len_product"] for r in arm}) == 1, (group, entry["instance"], mode)
                assert len({r["length"] for r in arm}) == 1, (group, entry["instance"], mode)
        output[group] = {**stats, **{f"median_{k}": median(v) for k,v in ratios.items()}}
    return output


def arm_report(rows):
    keys = {(row["graph"], row["endpoints"]) for row in rows}
    assert len(rows) == len(keys) == 693
    groups = defaultdict(list)
    for row in rows:
        groups[row["family"]].append(row)
    stats = {}
    for group, entries in list(groups.items()) + [("all", rows)]:
        results = Counter(n=len(entries))
        comparable = defaultdict(list)
        for row in entries:
            done = {key: completed(row["arms"][key]) for key in KEYS}
            for key, value in done.items():
                results[key] += value
                arm = row["arms"][key]
                results[f"{key}_overrun"] += arm["status"] in {"found", "unreachable"} and not arm["in_budget"]
                results[f"{key}_found"] += value and arm["status"] == "found"
            for old,new in (("00","10"),("01","11"),("00","01"),("10","11"),("00","11")):
                results[f"{old}->{new}_gain"] += not done[old] and done[new]
                results[f"{old}->{new}_loss"] += done[old] and not done[new]
                before, after = (row["arms"][key] for key in (old,new))
                if (done[old] and done[new] and before["length"] == after["length"]
                        and min(before["seconds"],after["seconds"]) >= .01):
                    comparable[f"{old}->{new}"].append(before["seconds"]/after["seconds"])
        a,b,c,d = (results[key] for key in KEYS)
        stats[group] = dict(results, summary_mean=((b-a)+(d-c))/2, special_mean=((c-a)+(d-b))/2,
                            interaction=d-b-c+a, comparable_time={
                                key: {"n": len(items), "median": median(items)}
                                for key, items in comparable.items()
                            })
    return stats


def trace_report(rows):
    counts = Counter()
    explicit_methods = {"weighted_compressed_contraction", "compressed_contraction",
                        "compact_contraction", "compact_certificate"}
    for row in rows:
        run = row["run"]
        method, branch = run.get("method"), run.get("branch")
        attempts = run.get("attempts", [])
        terminal = attempts[-1] if attempts else {}
        if method in explicit_methods or branch == "capacity_two_contract" or (
                branch == "adaptive" and terminal.get("method") == "contract"
                and terminal.get("status") == run["status"]):
            counts["saturated"] += 1
        elif method in {"gated_matching", "grid_phase", "sat_blocker_projection"} or branch in {"queen", "gateway"}:
            counts["special"] += 1
        elif branch == "quotient_adaptive":
            counts["unresolved_route"] += 1
        else:
            counts["other_logged"] += 1
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factorial", type=Path, default=DATA / "factorial-693.jsonl")
    parser.add_argument("--prefix", type=Path, default=DATA / "prefix-121.jsonl")
    parser.add_argument("--output", type=Path, help="Write a regenerated summary to this file")
    args = parser.parse_args()
    arms = load(args.factorial)
    prefix = load(args.prefix)
    old = load(REFERENCE)
    output = dict(factorial=arm_report(arms), prefix=prefix_report(prefix), historical=trace_report(old))
    text = json.dumps(output, indent=2, ensure_ascii=False)
    if args.output is not None:
        args.output.write_text(text+"\n", encoding="utf-8")
    print(text)
