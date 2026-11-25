"""Run and verify minimum-cost compressed expansion across structured graph families."""
from pathlib import Path
import runpy
from time import perf_counter

HERE=Path(__file__).resolve().parent
build=runpy.run_path(str(HERE/"weighted_lifting.py"))["shortest_witness"]


def solve(case,family,seconds,solver):
    began=perf_counter()
    deadline=began+seconds
    packed,latest,structures=solver["packed"],solver["latest"],solver["structures"]
    compact,classes,index=latest.twins.quotient(case)
    adj=compact.adjacency()
    start,goal=map(solver["p"].mask_of,(compact.start,compact.target))
    if family=="sp":
        blocks=latest.twins.capacity_two_partition(compact,adj)
        if blocks is None:
            return dict(status="unsupported")
        ordered,probe=packed.choose_direction(compact,blocks)
        choices=[(probe["order"],ordered)]
    elif family=="exp_instance":
        original=latest.alg.clique_partition(adj)
        if not solver["old"]["saturated"](compact,original,adj):
            return dict(status="unsupported")
        orders=list(solver["old"]["ordering"].candidates(original,adj,start,goal))
        orders.sort(key=lambda item:not item[0].startswith("reverse-greedy"))
        choices=[(label,[original[i] for i in order]) for label,order in orders]
    else:
        try:
            choices=[("recognized",latest.alg.core.structure.recognize(compact))]
        except ValueError:
            return dict(status="unsupported")
    best=None
    seen=set()
    trials=[]
    for label,blocks in choices:
        key=tuple(map(tuple,blocks))
        if key in seen:
            continue
        seen.add(key)
        now=perf_counter()
        if now>=deadline:
            break
        if not solver["old"]["saturated"](compact,blocks,adj):
            continue
        end=min(deadline,now+max(1,seconds/4)) if family=="exp_instance" else deadline
        result=structures["compressed_solve"](compact,blocks,packed,end,pair_cap=360_000,build=build)
        if result["status"]!="found":
            trials.append(dict(order=label,status=result["status"],limit=result.get("limit_data")))
            continue
        witness=structures["lift_witness"](result["witness"],case,classes,index)
        length=structures["verify_witness"](witness,case.adjacency(),
                                            *map(solver["p"].mask_of,(case.start,case.target)))
        trials.append(dict(order=label,status="found",length=length))
        if best is None or length<best["length"]:
            best=dict(status="found",length=length,order=label,witness=witness,
                      representation="compressed",time_to_path=perf_counter()-began)
    return dict(best or {"status":"budget"},seconds=perf_counter()-began,trials=trials)
