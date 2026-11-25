"""Vacancy-based search for n-1 queens under Token Jumping."""
from collections import Counter
import heapq
import json
from pathlib import Path
from time import perf_counter

HERE=Path(__file__).resolve().parent


class Board:
    def __init__(self,n,goal):
        self.n=n
        self.axes=[(r,c,r-c+n-1,r+c) for r in range(n) for c in range(n)]
        self.goal=goal
        lines=[set() for _ in range(4)]
        for v in self.vertices(goal):
            for group,value in zip(lines,self.axes[v]):
                group.add(value)
        self.target_degree=[sum(i in g for i,g in zip(coords,lines)) if not goal&(1<<v) else 0
                            for v,coords in enumerate(self.axes)]
        self.line_mask=(1<<n)-1

    @staticmethod
    def vertices(state):
        while state:
            bit=state&-state
            yield bit.bit_length()-1
            state^=bit

    def moves(self,state):
        queens=list(self.vertices(state))
        assert len(queens)==self.n-1
        rows=cols=diag=anti=0
        for v in queens:
            r,c,d,a=self.axes[v]
            rows|=1<<r
            cols|=1<<c
            diag|=1<<d
            anti|=1<<a
        free_row=(self.line_mask^rows).bit_length()-1
        free_col=(self.line_mask^cols).bit_length()-1
        common=free_row*self.n+free_col
        for u in queens:
            r,c,d,a=self.axes[u]
            d0=diag^(1<<d)
            a0=anti^(1<<a)
            for v in (r*self.n+free_col,free_row*self.n+c,common):
                _,_,nv,na=self.axes[v]
                if not (d0&(1<<nv) or a0&(1<<na)):
                    yield u,v

    def validate(self,path,start):
        assert path[0]==start and path[-1]==self.goal
        for state in path:
            coords=[self.axes[v] for v in self.vertices(state)]
            assert len(coords)==self.n-1
            assert all(len(set(axis))==len(coords) for axis in zip(*coords))
        assert all((a^b).bit_count()==2 for a,b in zip(path,path[1:]))


def search(board,start,width,branch,deadline,penalty,reverse=False,*,depth_limit=None,incumbent=None):
    if reverse:
        # The reverse problem uses the same geometry and swapped target features.
        back = incumbent[::-1] if incumbent is not None else None
        result,work=search(Board(board.n,start),board.goal,width,branch,deadline,penalty,
                           depth_limit=depth_limit,incumbent=back)
        return (result[::-1] if result else None),work
    goal=board.goal
    if start==goal:
        return [start],0
    parents={start:None}
    suffixes = {state:i for i,state in enumerate(incumbent)} if incumbent and depth_limit is not None else {}
    beam=[(start,(goal&~start).bit_count(),sum(board.target_degree[v] for v in board.vertices(start)))]
    work=0
    for depth in range(1,(256 if depth_limit is None else depth_limit)+1):
        candidates={}
        for state,gap,degree in beam:
            if perf_counter()>=deadline:
                return None,work
            local=[]
            for u,v in board.moves(state):
                work+=1
                nxt=state^(1<<u)^(1<<v)
                if nxt in parents or nxt in candidates:
                    continue
                if nxt==goal:
                    full=[nxt,state]
                    while parents[full[-1]] is not None:
                        full.append(parents[full[-1]])
                    return full[::-1],work
                if nxt in suffixes and depth + len(incumbent)-1-suffixes[nxt] <= depth_limit:
                    full = [nxt,state]
                    while parents[full[-1]] is not None:
                        full.append(parents[full[-1]])
                    return full[::-1]+incumbent[suffixes[nxt]+1:],work
                remaining=gap+int(bool(goal&(1<<u)))-int(bool(goal&(1<<v)))
                if depth_limit is not None and depth+remaining>depth_limit:
                    continue
                blockers=degree-board.target_degree[u]+board.target_degree[v]
                local.append((remaining*penalty+blockers,remaining,blockers,nxt))
            for _,g,d,nxt in heapq.nsmallest(branch,local):
                candidates[nxt]=g,d,state
        retained=heapq.nsmallest(width,candidates,key=lambda s:(
            candidates[s][0]*penalty+candidates[s][1],candidates[s][0],s))
        if not retained:
            break
        beam=[(s,*candidates[s][:2]) for s in retained]
        parents.update((s,candidates[s][2]) for s in retained)
    return None,work


def audit():
    from itertools import combinations
    for n in (4,5):
        board=Board(n,0)
        for occupied in combinations(range(n*n),n-1):
            moves_coordinates=[board.axes[v] for v in occupied]
            if any(len(set(axis))!=n-1 for axis in zip(*moves_coordinates)):
                continue
            mask=sum(1<<v for v in occupied)
            expected={(u,v) for u in occupied for v in range(n*n) if v not in occupied
                      and all(all(a!=b for a,b in zip(board.axes[w],board.axes[v])) for w in occupied if w!=u)}
            assert set(board.moves(mask))==expected


def main():
    audit()
    records=[]
    for line in (HERE/"CoRe已知漏解放宽时间.jsonl").read_bytes().splitlines():
        ref=json.loads(line)
        if ref["family"]!="queen" or ref["result"]["status"]=="found":
            continue
        ends=HERE/"srip对照/instances"/ref["endpoints"]
        vertices={}
        for line in ends.read_text(encoding="utf-8-sig").splitlines():
            row=line.split()
            if row and row[0] in ("s","t"):
                vertices[row[0]]=sum(1<<(int(v)-1) for v in row[1:])
        n=20 if "020x020" in ends.name else 200
        started=perf_counter()
        board=Board(n,vertices["t"])
        path=None
        runs=[]
        for width,branch,penalty,reverse,seconds in [(16,16,4,False,1),(48,24,4,True,2),
                                                      (96,32,2,False,4),(144,48,8,True,7)]:
            t=perf_counter()
            path,work=search(board,vertices["s"],width,branch,t+seconds,penalty,reverse)
            runs.append(dict(width=width,branch=branch,penalty=penalty,reverse=reverse,
                             work=work,seconds=perf_counter()-t,found=path is not None))
            if path:
                break
        elapsed=perf_counter()-started
        if path:
            board.validate(path,vertices["s"])
        result=dict(name=ends.name,known=ref["reference_length"],length=len(path)-1 if path else None,
                    moves=[[(a&~b).bit_length(),(b&~a).bit_length()] for a,b in zip(path,path[1:])] if path else None,
                    seconds=elapsed,runs=runs)
        records.append(result)
        (HERE/"皇后图空行空列搜索结果.json").write_text(json.dumps(records,indent=2)+"\n",encoding="utf-8")
        print(ends.name,result["known"],result["length"],round(elapsed,3),runs,flush=True)


if __name__=="__main__":
    main()
