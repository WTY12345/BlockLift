"""Exact Token Jumping reachability reduction by closed-neighborhood twins."""
from itertools import combinations
from collections import defaultdict
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from time import perf_counter

HERE=Path(__file__).resolve().parent
spec=spec_from_file_location("routing",HERE/"adaptive_partition.py")
alg=module_from_spec(spec)
spec.loader.exec_module(alg)
p=alg.p
ev=alg.core.ev


def quotient(case):
    groups=defaultdict(list)
    for v,neighbors in enumerate(case.adjacency()):
        groups[neighbors | (1<<v)].append(v)
    classes=list(groups.values())
    index={v:i for i,group in enumerate(classes) for v in group}
    edges={tuple(sorted((index[u],index[v]))) for u,v in case.edges if index[u]!=index[v]}
    compact=p.Instance(case.name,case.family,len(classes),tuple(sorted(edges)),
                       tuple(index[v] for v in case.start),tuple(index[v] for v in case.target))
    assert len(set(compact.start))==len(case.start) and len(set(compact.target))==len(case.target)
    return compact,classes,index


def lift(case,path,index,representatives):
    """Choose the target representative on entry, then fix any surviving start representatives."""
    occupied={index[v]:v for v in case.start}
    target={index[v]:v for v in case.target}
    concrete=[p.mask_of(occupied.values())]
    for before,after in zip(path,path[1:]):
        source=(before&~after).bit_length()-1
        destination=(after&~before).bit_length()-1
        removed=occupied.pop(source)
        added=target.get(destination)
        if added is None:
            added=representatives[destination]
        occupied[destination]=added
        concrete.append(concrete[-1]^(1<<removed)^(1<<added))
    for group,v in sorted(target.items()):
        if occupied[group]!=v:
            concrete.append(concrete[-1]^(1<<occupied[group])^(1<<v))
    return concrete


def capacity_two_partition(case, adj):
    # The numbered SP inputs suggest a larger partition than the generic small-block menu.
    # Certification depends only on independent sets and applies to any candidate with this shape.
    if case.n % 13 or 2*case.n != 13*len(case.start):
        return None
    start,goal=map(p.mask_of,(case.start,case.target))
    groups=[list(range(i,i+13)) for i in range(0,case.n,13)]
    for block in groups:
        mask=p.mask_of(block)
        if (start&mask).bit_count()!=2 or (goal&mask).bit_count()!=2:
            return None
        for a,b,c in combinations(block,3):
            if not (adj[a]&((1<<b)|(1<<c)) or adj[b]&(1<<c)):
                return None
    return groups


def solve(case,budget=1.0,*,beam_limit=alg.DEFAULT_BEAM_LIMIT):
    began=perf_counter()
    compact,classes,index=quotient(case)
    groups=capacity_two_partition(compact,compact.adjacency())
    deadline=began+budget
    result=None
    if groups is not None:
        def check(states):
            if states>=100000 or perf_counter()>=deadline:
                raise p.SearchTimeout(0,0)
        try:
            path,layers=alg.core.structure.m.solve(compact,groups,True,restrict_local=True,restrict_prefix=True,check=check)
            result=dict(path=path,status="found" if path is not None else "unreachable",
                        method="capacity_two_contract",layers=layers)
        except p.SearchTimeout:
            pass
    if result is None:
        result=alg.solve(compact,"rule",budget=max(0,deadline-perf_counter()),beam_limit=beam_limit)
        result["method"]="quotient_adaptive"
    path=result["path"]
    if path is not None:
        path=lift(case,path,index,[group[0] for group in classes])
    elapsed=perf_counter()-began
    if elapsed>budget:
        path=None
        result["status"]="budget"
    result.update(path=path,seconds=elapsed,classes=len(classes))
    return result
