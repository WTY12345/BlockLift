"""Compare identical prefix products with and without same-label contraction."""
import argparse
from collections import Counter
import csv
from itertools import chain, combinations, product
import json
from pathlib import Path, PurePosixPath
import random
import sys
from time import perf_counter

from factorial_ablation import FROZEN, REFERENCE, check_source

sys.path.insert(0, str(FROZEN))
from blocklift import boundary_contraction, cli, structure_dispatch, twin_quotient


def prefix_solver(contract):
    path = Path(boundary_contraction.__file__)
    source = path.read_text(encoding="utf-8")
    changes = {
        "        index={pair:i for i,pair in enumerate(pairs)}":
            "        work.append((len(labels)*len(local), len(pairs)))\n"
            "        index={pair:i for i,pair in enumerate(pairs)}",
    }
    if not contract:
        begin = source.index("        comp=[-1]*len(pairs)")
        end = source.index("    # 所有顶点处理完之后", begin)
        source = source[:begin] + """        labels=signatures
        edges=graph
        stages.append(pairs)
        initial,target=a,b
        if observe is not None:
            observe(len(pairs), len(set(signatures)), len(labels))
""" + source[end:]
        begin = source.index("    if initial!=target:")
        source = source[:begin] + """    path=[]
    for node in route(edges,initial,target,lambda _:True):
        state=0
        for layer in reversed(stages):
            node,local_state=layer[node]
            state |= local_state
        path.append(state)
    return path,[]
"""
    for old, new in changes.items():
        assert source.count(old) == 1, old
        source = source.replace(old, new)
    scope = {"__file__": str(path)}
    exec(compile(source, str(path), "exec"), scope)
    return scope


def synthetic():
    for topology, size, rep in product(("path", "ring", "tree", "grid"), (6, 10, 15, 20), range(3)):
        rng = random.Random(735900 + 29 * size + rep)
        blocks = [tuple(range(4*i, 4*i+4)) for i in range(size)]
        if topology in {"path", "ring"}:
            between = [(i-1, i) for i in range(1, size)]
            if topology == "ring":
                between.append((0, size-1))
        elif topology == "tree":
            between = [((i-1)//2, i) for i in range(1, size)]
        else:
            width = 3 if size == 6 else 5
            between = [(i, i+1) for i in range(size-1) if (i+1) % width]
            between.extend((i, i+width) for i in range(size-width))
        edges = {edge for block in blocks for edge in combinations(block, 2)}
        for a, b in between:
            choices = [(u,v) for u,v in product(range(4), repeat=2)
                       if not (u in (0, 2) and v in (0, 2))]
            for u,v in rng.sample(choices, 2+rep):
                edges.add((blocks[a][u], blocks[b][v]))
        name = f"{topology}-{size}-{rep}"
        raw = make_case(name, 4*size, edges, [b[0] for b in blocks], [b[2] for b in blocks])
        yield f"synthetic/{topology}", name, raw, raw, blocks, None

    # Preserve many distinct prefixes up to the final block.
    for size in (5, 7, 9, 11, 13):
        blocks = [(2*i, 2*i+1) for i in range(size)]
        last = tuple(range(2*size, 3*size+1))
        edges = set(blocks) | set(combinations(last, 2))
        edges.update((block[0], last[i]) for i, block in enumerate(blocks))
        name = f"wide-{size}"
        raw = make_case(name, 3*size+1, edges,
                        [b[0] for b in blocks]+[last[-1]], [b[1] for b in blocks]+[last[-1]])
        yield "synthetic/wide", name, raw, raw, blocks+[last], None

    for size in (4, 6, 8, 10, 12):
        paths = [tuple(range(4*i, 4*i+4)) for i in range(size)]
        x, y = 4*size, 4*size+1
        edges = {(u,v) for block in paths for u,v in zip(block,block[1:])}
        edges.update((v,x) for v in range(x))
        edges.add((x,y))
        name = f"projection-{size}"
        raw = make_case(name, y+1, edges, [v for b in paths for v in (b[0],b[2])]+[y],
                        [v for b in paths for v in (b[1],b[3])]+[y])
        yield "synthetic/projection", name, raw, raw, paths+[(x,y)], None


def make_case(name, n, edges, start, target):
    adj = [0]*n
    for u,v in edges:
        adj[u] |= 1 << v
        adj[v] |= 1 << u
    return cli.Case(name, n, cli.Edges(tuple(adj),len(edges)), tuple(start), tuple(target))


def partition(case, family):
    adj = case.adjacency()
    if family == "sp":
        blocks = twin_quotient.capacity_two_partition(case, adj)
    elif family == "exp_instance":
        blocks = structure_dispatch.alg.clique_partition(adj)
    else:
        try:
            blocks = structure_dispatch.alg.core.structure.recognize(case)
        except ValueError:
            return None
    if not blocks or sorted(v for b in blocks for v in b) != list(range(case.n)):
        return None
    start, goal = map(structure_dispatch.p.mask_of, (case.start, case.target))
    for block in blocks:
        mask = structure_dispatch.p.mask_of(block)
        a = (start & mask).bit_count()
        if (goal & mask).bit_count() != a or len(block) > 14:
            return None
        if any(not any(adj[u] & (1<<v) for u,v in combinations(candidate,2))
               for candidate in combinations(block,a+1)):
            return None
    return blocks


def public_suite(limit, data):
    public = {"sp", "exp_instance", "power", "power_wide", "power_wider",
              "square", "square_wide", "square_wider"}
    accepted, inspected = Counter(), Counter()
    seen = set()
    with (FROZEN / "benchmark/core-693.csv").open(encoding="utf-8-sig", newline="") as file:
        listed = [tuple(str(PurePosixPath(p)) for p in row) for row in csv.reader(file)]
    listed.sort(key=lambda row: (Path(row[0]).name.lower(), row[1]))
    for graph,endpoints in listed:
        family = cli.choose_family(data/graph,data/endpoints)
        if family not in public or accepted[family] >= limit or graph in seen:
            continue
        raw = cli.read_case(data/graph,data/endpoints)
        if raw.n>500 or len(set(raw.target)-set(raw.start))<2:
            continue
        inspected[family] += 1
        compact,classes,index = twin_quotient.quotient(raw)
        blocks = partition(compact, family)
        if blocks is None:
            continue
        seen.add(graph)
        accepted[family] += 1
        yield f"CoRe/{family}", endpoints, raw, compact, blocks, (classes,index)
    print("public accepted", dict(accepted), "checked", dict(inspected), flush=True)


def run(scope, raw, compact, blocks, lift, seconds, cap):
    before = perf_counter()
    layers, work = [], []
    scope["work"] = work
    def guard(count):
        if count > cap:
            raise OverflowError
        if perf_counter() - before > seconds:
            raise TimeoutError
    try:
        path, _ = scope["solve"](compact, blocks, restrict_local=True, restrict_prefix=True,
                                  observe=lambda *item: layers.append(item), check=guard)
        status = "found" if path is not None else "unreachable"
    except (OverflowError, TimeoutError) as error:
        status, path = ("state_cap" if isinstance(error, OverflowError) else "time_cap"), None
    if path is not None and lift is not None:
        classes, index = lift
        path = twin_quotient.lift(raw, path, index, [group[0] for group in classes])
    elapsed = perf_counter() - before
    length = cli.replay(raw, cli.moves_from_path(path)) if path is not None else None
    return dict(status=status, elapsed=elapsed, in_budget=elapsed<=seconds, length=length,
                len_product=sum(v for _,v in work), candidate_pairs=sum(c for c,_ in work),
                per_layer=work, retained_layers=layers)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=1)
    parser.add_argument("--cap", type=int, default=40000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--public-per-family", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, default=FROZEN / "benchmark/instances")
    args = parser.parse_args()
    if not __debug__:
        parser.error("Run without Python optimization so witness assertions are checked.")
    check_source()
    scopes = {mode: prefix_solver(mode=="on") for mode in ("on","off")}
    rng = random.Random(310720)
    with REFERENCE.open(encoding="utf-8") as records:
        truth = {r["endpoints"]:r["run"]["status"] for r in map(json.loads,records)}
    with args.output.open("x", encoding="utf-8", buffering=1) as file:
        for group,key,raw,compact,blocks, lift in chain(synthetic(), public_suite(args.public_per_family, args.inputs.resolve())):
            measurements = []
            for _ in range(args.repeats):
                order = ["on", "off"]
                rng.shuffle(order)
                runs = {mode: run(scopes[mode],raw,compact,blocks,lift,args.seconds,args.cap)
                        for mode in order}
                complete = {run["status"] for run in runs.values()} & {"found", "unreachable"}
                assert len(complete) < 2, (group,key,runs)
                assert complete <= {truth.get(key, "found")}, (group,key,runs)
                measurements.append(runs)
            row = dict(group=group, instance=key, n=raw.n, compact_n=compact.n, blocks=len(blocks),
                       seconds=args.seconds, cap=args.cap, repeats=measurements)
            file.write(json.dumps(row)+"\n")
            print(group,key,[{k:v["status"] for k,v in run.items()} for run in measurements],flush=True)


if __name__ == "__main__":
    main()
