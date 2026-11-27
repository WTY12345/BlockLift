"""Verify CoRe responses independently of the BlockLift solver."""
import argparse
from collections import Counter, deque
import csv
from functools import lru_cache
import json
from math import comb, isqrt
from pathlib import Path, PurePosixPath
import re
from statistics import median

HERE = Path(__file__).resolve().parent
DATA = HERE / "benchmark/instances"


@lru_cache(maxsize=1)
def graph(path):
    with (DATA/path).open("rb") as source:
        header=next(line.split() for line in source if line.startswith(b"p "))
        n,m=map(int,header[-2:])
        dense=m>1_000_000
        a=[bytearray((n+7)//8) for _ in range(n)] if dense else [0]*n
        count=0
        for line in source:
            if not line.startswith(b"e "):
                continue
            _,s,t=line.split()
            u,v=int(s)-1,int(t)-1
            assert 0<=u<n and 0<=v<n and u!=v
            if dense:
                a[u][v//8]|=1<<(v%8)
                a[v][u//8]|=1<<(u%8)
            else:
                a[u]|=1<<v
                a[v]|=1<<u
            count+=1
    masks=tuple(int.from_bytes(x,"little") for x in a) if dense else tuple(a)
    assert count==m and sum(x.bit_count() for x in masks)==2*m
    return masks


def endpoint_masks(path,adj):
    states={}
    for line in (DATA/path).read_bytes().splitlines():
        row=line.split()
        if not row or row[0] not in (b"s",b"t"):
            continue
        vs=[int(v)-1 for v in row[1:]]
        assert len(set(vs))==len(vs) and all(0<=v<len(adj) for v in vs)
        mask=sum(1<<v for v in vs)
        assert all(not adj[v]&mask for v in vs)
        states[row[0]]=mask
    a,b=states[b"s"],states[b"t"]
    assert a.bit_count()==b.bit_count()
    return a,b


def explicit(adj,start,goal,moves,expected):
    steps=0
    state=start
    for u,v in moves:
        assert 1<=u<=len(adj) and 1<=v<=len(adj)
        remove,add=1<<(u-1),1<<(v-1)
        assert state&remove and not state&add
        state-=remove
        assert not state&adj[v-1]
        state+=add
        steps+=1
    assert state==goal and steps==expected


def compressed(adj,start,goal,witness,expected,offset):
    nodes=witness["nodes"]
    assert nodes and not nodes[0] and 0<=witness["root"]<len(nodes)
    table=[(0,0,0,0)]
    for i,(kind,*args) in enumerate(nodes[1:],1):
        if kind=="move":
            u,v=(a-offset for a in args)
            assert 0<=u<len(adj) and 0<=v<len(adj) and u!=v
            take,put=1<<u,1<<v
            table.append((take,(adj[v]&~take)|put,take|put,1))
            continue
        assert kind=="seq"
        ones=zeros=flip=length=0
        for j in args:
            assert 0<=j<i
            a,b,delta,n=table[j]
            ones|=(a&~flip)|(b&flip)
            zeros|=(b&~flip)|(a&flip)
            assert not ones&zeros
            flip^=delta
            length+=n
        table.append((ones,zeros,flip,length))
    ones,zeros,flip,length=table[witness["root"]]
    assert start&ones==ones and not start&zeros and start^flip==goal and length==expected


def bits(mask):
    while mask:
        bit = mask & -mask
        yield bit.bit_length() - 1
        mask -= bit


def grid_invariant(adj, start, goal):
    # Deleting at most d deficient tiles leaves intact rows and columns.
    # Their union is connected and covers at least tile_side**2 - d**2 tiles.
    n = len(adj)
    side = isqrt(n)
    slack = n // 2 - start.bit_count()
    assert side * side == n and side % 2 == 0
    assert 0 <= slack and (side // 2) ** 2 > 2 * slack ** 2
    for vertex, neighbors in enumerate(adj):
        r, c = divmod(vertex, side)
        expected = ((r + dr) * side + c + dc for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))
                    if 0 <= r + dr < side and 0 <= c + dc < side)
        assert neighbors == sum(1 << v for v in expected)
    def colors(mask):
        return {(v // side + v % side) % 2 for v in bits(mask)}
    assert len(colors(start)) == len(colors(goal)) == 1 and colors(start) != colors(goal)


def pigeonhole_obstruction(name, adj, start, goal):
    rows, cols = map(int, re.fullmatch(r"ph-(\d+)-(\d+)(?:_01\.dat)?", name).groups())
    assert rows > cols
    assert start & 31 == 5 and goal & 31 == 10 and start >> 5 == goal >> 5
    slots = rows * cols
    rows_begin = 5 + 3 * slots
    pairs_begin = rows_begin + slots
    assert len(adj) == pairs_begin + 2 * comb(rows, 2) * cols
    allow = [set() for _ in adj]
    def edge(u, v):
        allow[u].add(v)
        allow[v].add(u)
    for u, v in ((0,1),(0,3),(1,2),(2,3),(2,4),(3,4)):
        edge(u,v)
    for slot in range(slots):
        a = 5 + 3 * slot
        assert ((start >> a) & 7) == 4
        edge(a,a+1)
        edge(a,a+2)
        edge(a+1,a+2)
        edge(4,a+2)
        edge(a,rows_begin+slot)
    for r in range(rows):
        ports = range(rows_begin + r * cols, rows_begin + (r+1) * cols)
        assert sum(bool(start & (1 << u)) for u in ports) == 1
        for u in ports:
            for v in range(u+1, ports.stop):
                edge(u,v)
    pair_keys = set()
    for u in range(pairs_begin, len(adj), 2):
        v = u + 1
        assert ((start >> u) & 3) in (1, 2)
        a, = set(bits(adj[u])) - {v}
        b, = set(bits(adj[v])) - {u}
        assert 6 <= a < rows_begin and 6 <= b < rows_begin and a % 3 == b % 3 == 0
        ar, ac = divmod((a - 6) // 3, cols)
        br, bc = divmod((b - 6) // 3, cols)
        assert ac == bc and ar != br
        pair_keys.add((min(ar,br),max(ar,br),ac))
        edge(u,v)
        edge(a,u)
        edge(b,v)
    assert len(pair_keys) == comb(rows, 2) * cols
    assert all(set(bits(actual)) == expected for actual,expected in zip(adj,allow))


def enumerate_component(adj, start, target):
    available = (1 << len(adj)) - 1
    reached = {start}
    todo = deque([start])
    while todo:
        current = todo.popleft()
        candidates = available ^ current
        for u in bits(current):
            residual = current ^ (1 << u)
            for v in bits(candidates):
                if residual & adj[v]:
                    continue
                child = residual | (1 << v)
                if child not in reached:
                    reached.add(child)
                    todo.append(child)
    assert target not in reached
    return len(reached)


def records(path):
    with path.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    index = {(r["graph"], r["endpoints"]): r for r in rows}
    assert len(rows) == len(index)
    return index


def relation(a, b):
    return "shorter" if a < b else "longer" if a > b else "equal"

def main():
    global DATA
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, help="JSONL from run_benchmark.py or the reference run")
    parser.add_argument("--inputs", type=Path, default=DATA, help="Root of the downloaded instance files")
    args = parser.parse_args()
    if not __debug__:
        parser.error("run without Python optimization so witness assertions are checked")
    DATA = args.inputs.resolve()

    with (HERE / "benchmark/core-693.csv").open(encoding="utf-8-sig", newline="") as f:
        suite = {tuple(PurePosixPath(path).as_posix() for path in row) for row in csv.reader(f)}
    current = records(args.results)
    baseline = records(HERE / "results/core-693-run.jsonl")
    if len(suite) != 693 or current.keys() != suite or baseline.keys() != suite:
        parser.error("expected one response per case in the 693-case manifest")

    with (HERE / "results/core-693-per-instance.csv").open(encoding="utf-8-sig", newline="") as f:
        references = {row["实例"]: row for row in csv.DictReader(f)}

    counts, checked, baseline_lengths, public_lengths = (Counter() for _ in range(4))
    seconds, undecided, changes, status_changes = [], [], [], []
    for g, e in sorted(suite):
        name = PurePosixPath(e).name
        answer = current[g, e]["run"]
        prior = baseline[g, e]["run"]
        status = answer["status"]
        counts[status] += 1
        if status != prior["status"]:
            status_changes.append({"instance": name, "reference": prior["status"], "actual": status})
        if "seconds" in answer:
            seconds.append(answer["seconds"])
        if status not in {"found", "unreachable"}:
            undecided.append(name)
            continue
        try:
            adj = graph(g)
            start, goal = endpoint_masks(e, adj)
            if status == "found":
                length = answer["length"]
                if answer["representation"] == "moves":
                    explicit(adj, start, goal, answer["moves"], length)
                    checked["explicit_paths"] += 1
                else:
                    assert answer["representation"] == "compressed"
                    compressed(adj, start, goal, answer["witness"], length, 1)
                    checked["compressed_witnesses"] += 1
                if length == (goal & ~start).bit_count():
                    checked["endpoint_lower_bound_met"] += 1
                if prior["status"] == "found":
                    benchmark_relation = relation(length, prior["length"])
                    baseline_lengths[benchmark_relation] += 1
                    if benchmark_relation != "equal":
                        changes.append({"instance": name, "reference": prior["length"], "actual": length})
                ref = references[name]["公开最佳步数"]
                if ref:
                    public_lengths[relation(length, int(ref))] += 1
            elif answer.get("method") == "grid_phase":
                grid_invariant(adj, start, goal)
                checked["unreachable_grid"] += 1
            elif answer.get("method") == "gated_matching":
                pigeonhole_obstruction(name, adj, start, goal)
                checked["unreachable_pigeonhole"] += 1
            elif len(adj) <= 20:
                enumerate_component(adj, start, goal)
                checked["unreachable_exhaustive_bfs"] += 1
            else:
                checked["unreachable_needs_additional_proof"] += 1
                undecided.append(name)
        except (AssertionError, ValueError, KeyError, OSError) as error:
            parser.exit(1, f"Verification failed for {name}: {error or 'invalid witness or proof'}\\n")
    report = dict(
        cases=len(current), statuses=counts, independently_checked=checked, undecided=undecided,
        relative_to_reference_run=baseline_lengths, relative_to_public_lengths=public_lengths,
        changed_lengths=changes, changed_statuses=status_changes, total_solve_seconds=sum(seconds),
        median_solve_seconds=median(seconds) if seconds else None,
        recorded_solve_times_at_most_15_seconds=sum(t <= 15 for t in seconds),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return bool(undecided)


if __name__ == "__main__":
    raise SystemExit(main())
