"""Improve paths using only the input, within a shared solver budget."""
from math import isqrt
from pathlib import Path
import runpy
from time import perf_counter

HERE=Path(__file__).resolve().parent
base=runpy.run_path(str(HERE/"71_综合结构求解.py"))
weighted=runpy.run_path(str(HERE/"84_CoRe带权展开实验.py"))["solve"]
queen_tools=runpy.run_path(str(HERE/"85_皇后局部替换与最短性检查.py"))
structures=base["structures"]
CHAINS={"sp","power","power_wide","power_wider","square","square_wide","square_wider"}


def solve(case,family,budget,*,name=None,quality=False,splice=False):
    began=perf_counter()
    deadline=began+budget
    if family in CHAINS:
        candidate=weighted(case,family,min(0.5,budget/4),base)
        if candidate["status"]=="found":
            return dict(candidate,path=None,method="weighted_compressed_contraction",
                        seconds=perf_counter()-began)
    result=base["solve"](case,family,max(0,deadline-perf_counter()),name=name)
    if result["status"]!="found" or result.get("optimal"):
        return dict(result,seconds=perf_counter()-began)

    if family=="exp_instance" and perf_counter()<deadline:
        # Keep the viable original witness throughout the improvement attempt.
        extra=deadline-perf_counter()
        if extra>=0.25:
            better=weighted(case,family,extra,base)
            incumbent=result.get("path")
            length=len(incumbent)-1 if incumbent is not None else result["length"]
            if better["status"]=="found" and better["length"]<length:
                result=dict(better,path=None,method="weighted_compressed_contraction")
    path=result.get("path")
    if path is None or result.get("method")=="gated_matching":
        return dict(result,seconds=perf_counter()-began)
    p=base["p"]
    start,goal=map(p.mask_of,(case.start,case.target))
    gap=(goal&~start).bit_count()
    if len(path)-1==gap:
        return dict(result,optimal=True,length=gap,seconds=perf_counter()-began)

    now=perf_counter()
    side=isqrt(case.n)
    board=family=="queen" and side**2==case.n and len(case.start)==side-1
    if now<deadline and (board or quality or family in {"color04","random_instance","handcrafted"}):
        stop=deadline if quality else min(deadline,now+(6 if board else 0.65))
        first=now+(stop-now)*(0.5 if board else 1)
        path,runs=base["improve"](case,path,first,family,splice=splice)
        result["quality_runs"]=runs
        if board and len(path)-1>gap and perf_counter()<stop:
            queen=base["latest"].queen
            path=queen_tools["shorten"](path,side,min(stop,first+0.75),queen)
            if len(path)-1>gap and perf_counter()<stop:
                better,complete,expanded=queen_tools["bounded"](
                    queen.Board(side,goal),start,len(path)-2,stop)
                if better is not None:
                    path=better
                if complete:
                    result["optimal"]=True
                result["exact_check"]=dict(complete=complete,expanded=expanded)
    return dict(result,path=path,length=len(path)-1,seconds=perf_counter()-began,
                optimal=result.get("optimal",False) or len(path)-1==gap)
