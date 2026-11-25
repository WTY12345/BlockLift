"""Recognize the benchmark's five-vertex blocks from edges; test random relabeling."""
from itertools import combinations
from pathlib import Path
from importlib.util import spec_from_file_location,module_from_spec

HERE=Path(__file__).resolve().parent
spec=spec_from_file_location("contract",HERE/"boundary_contraction.py")
m=module_from_spec(spec)
spec.loader.exec_module(m)
p=m.p


def recognize(case):
    adj=case.adjacency()
    blocks=set()
    for a in range(case.n):
        for b,c in combinations(p.vertices(adj[a]),2):
            if not adj[b]&(1<<c):
                continue
            triangle=(1<<a)|(1<<b)|(1<<c)
            for x in p.vertices(adj[b]&~triangle):
                for y in p.vertices(adj[x]&adj[c]&~triangle):
                    mask=triangle|(1<<x)|(1<<y)
                    if sum((adj[v]&mask).bit_count() for v in p.vertices(mask))==12:
                        blocks.add(mask)
    covered=0
    for mask in blocks:
        if mask&covered:
            raise ValueError("overlapping candidate blocks")
        covered|=mask
    universe=(1<<case.n)-1
    prefix=universe^covered
    if prefix.bit_count()!=4:
        raise ValueError("unrecognized remainder")
    order=[list(p.vertices(prefix))]
    def neighbors(mask):
        joined=0
        for v in p.vertices(mask):
            joined|=adj[v]
        return joined
    frontier=neighbors(prefix)&~prefix
    while blocks:
        def score(mask):
            new_boundary=(frontier|neighbors(mask))&~(prefix|mask)
            return new_boundary.bit_count(),-(frontier&mask).bit_count(),mask
        mask=min(blocks,key=score)
        prefix|=mask
        frontier=(frontier|neighbors(mask))&~prefix
        blocks.remove(mask)
        order.append(list(p.vertices(mask)))
    return order
