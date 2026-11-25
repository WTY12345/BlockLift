"""Try shorter queen subpaths and test a length bound by complete bounded search."""
from heapq import heappop, heappush
from pathlib import Path
from time import perf_counter

HERE=Path(__file__).resolve().parent
def shorten(path,side,deadline,queen):
    for width in (6,10,16,24):
        i=0
        while i<len(path)-2:
            j=min(i+width,len(path)-1)
            now=perf_counter()
            if now>=deadline:
                return path
            if (path[j]&~path[i]).bit_count()<j-i:
                board=queen.Board(side,path[j])
                improved,_=queen.search(board,path[i],24,24,min(deadline,now+0.075),5,
                                        bool(i%2),depth_limit=j-i-1)
                if improved:
                    path=path[:i]+improved+path[j+1:]
            i+=2
    return path


def bounded(board,start,limit,deadline,cap=180_000):
    """Complete when exhausted. The mismatch count is an admissible lower bound."""
    g={start:0}
    parent={start:None}
    h=lambda s:(board.goal&~s).bit_count()
    queue=[(h(start),0,start)]
    expanded=0
    while queue:
        if perf_counter()>=deadline or len(g)>=cap:
            return None,False,expanded
        _,cost,state=heappop(queue)
        if cost!=g[state]:
            continue
        if state==board.goal:
            path=[]
            while state is not None:
                path.append(state)
                state=parent[state]
            return path[::-1],True,expanded
        expanded+=1
        for u,v in board.moves(state):
            nxt=state^(1<<u)^(1<<v)
            if cost+1>=g.get(nxt,limit+1) or cost+1+h(nxt)>limit:
                continue
            g[nxt]=cost+1
            parent[nxt]=state
            heappush(queue,(cost+1+h(nxt),cost+1,nxt))
    return None,True,expanded
