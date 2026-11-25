"""Minimum-cost realization of each fixed contracted trajectory using a move DAG."""
from functools import cache
from pathlib import Path
import runpy

HERE=Path(__file__).resolve().parent
Grammar=runpy.run_path(str(HERE/"compressed_witness.py"))["Grammar"]


def shortest_witness(stages, route, check):
    grammar=Grammar(check)
    word=0
    for pairs,graph,component,_,start,goal,_ in reversed(stages):
        check(len(grammar.nodes))
        crossings={}
        for u,neighbors in enumerate(graph):
            for v in sorted(neighbors):
                if component[u]!=component[v]:
                    crossings.setdefault((component[u],component[v]),[]).append((u,v))

        def encode(i,j):
            a,x=pairs[i]
            b,y=pairs[j]
            if a!=b:
                assert x==y
                return grammar.add(("bridge",a,b))
            return grammar.add(("move",(x&~y).bit_length()-1,(y&~x).bit_length()-1))

        @cache
        def within(a,b):
            chain=route(graph,a,b,lambda j:component[j]==component[a])
            return len(chain)-1,grammar.join(*(encode(i,j) for i,j in zip(chain,chain[1:])))

        @cache
        def transduce(node,current):
            check(len(grammar.nodes))
            if node==0:
                return {current:(0,0)}
            kind,*args=grammar.nodes[node]
            if kind=="move":
                return {current:(1,node)}
            if kind=="bridge":
                a,b=args
                assert component[current]==a
                best={}
                for u,v in crossings[a,b]:
                    cost,prefix=within(current,u)
                    if v not in best or cost+1<best[v][0]:
                        best[v]=(cost+1,grammar.join(prefix,encode(u,v)))
                return best
            costs={current:(0,0)}
            for child in args:
                following={}
                for a,(prefix_cost,prefix) in costs.items():
                    for b,(suffix_cost,suffix) in transduce(child,a).items():
                        cost=prefix_cost+suffix_cost
                        if b not in following or cost<following[b][0]:
                            following[b]=(cost,grammar.join(prefix,suffix))
                costs=following
            return costs

        realizations=transduce(word,start)
        a=min(realizations,key=lambda v:within(v,goal)[0]+realizations[v][0])
        word=grammar.join(realizations[a][1],within(a,goal)[1])
        transduce.cache_clear()
        within.cache_clear()
        if len(grammar.nodes)>50_000:
            current=grammar.export(word,final=False)
            grammar.nodes=current["nodes"]
            grammar.ids={node:i for i,node in enumerate(grammar.nodes)}
            word=current["root"]
    return grammar.export(word)
