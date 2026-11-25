"""Build block partitions and check their capacities."""
from itertools import combinations
from pathlib import Path
from time import perf_counter
from importlib.util import module_from_spec, spec_from_file_location

HERE=Path(__file__).resolve().parent
spec=spec_from_file_location("pilot",HERE/"cross_block_search.py")
pilot=module_from_spec(spec)
spec.loader.exec_module(pilot)
ev,p=pilot.ev,pilot.p
structure=pilot.load("structured_partition.py")


def partition(case):
    if case.n <= 500 and len(case.edges) <= 2*case.n and case.n % 5 == 4:
        try:
            groups=structure.recognize(case)
        except ValueError:
            groups=None
        if groups is not None:
            return groups,"recognized"
    if 5*len(case.start) < case.n:
        # Every nonempty block has capacity at least one.
        return None,"capacity_lower_bound"
    groups=[list(range(i,min(i+5,case.n))) for i in range(0,case.n,5)]
    return groups,"consecutive"


def certified(groups,adj,start,deadline):
    if groups is None:
        return False
    for group in groups:
        k=(start&p.mask_of(group)).bit_count()
        for vertices in combinations(group,k+1):
            mask=p.mask_of(vertices)
            if not any(adj[v]&mask for v in vertices):
                return False
        if perf_counter()>=deadline:
            raise p.SearchTimeout(0,0)
    return True
