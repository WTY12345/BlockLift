"""Choose a contraction order using the certified block interaction graph."""
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=spec_from_file_location("packed",HERE/"explicit_lifting.py")
packed=module_from_spec(spec)
spec.loader.exec_module(packed)
latest,p,ev=packed.latest,packed.p,packed.ev


def candidates(blocks,adj,start,goal):
    masks=[p.mask_of(b) for b in blocks]
    outside=[]
    for block,mask in zip(blocks,masks):
        joined=0
        for v in block:
            joined|=adj[v]
        outside.append(joined&~mask)
    connections=[{i for i,m in enumerate(masks) if m&link} for link in outside]
    original=list(range(len(blocks)))
    changed=[i for i,g in enumerate(masks) if g&(start^goal)]
    yield "original",original
    yield "reverse",original[::-1]
    for anchor in (None,*(changed[:2]),max(original,key=lambda i:len(connections[i]))):
        available=set(original)
        chosen=[]
        inside=frontier=0
        if anchor is not None:
            chosen.append(anchor)
            available.remove(anchor)
            inside=masks[anchor]
            frontier=outside[anchor]
        while available:
            nxt=min(available,key=lambda i:(((outside[i]|frontier)&~(inside|masks[i])).bit_count(),
                                           -(frontier&masks[i]).bit_count(),len(connections[i]),i))
            chosen.append(nxt)
            available.remove(nxt)
            inside|=masks[nxt]
            frontier=(frontier|outside[nxt])&~inside
        yield f"greedy-{anchor}",chosen
        yield f"reverse-greedy-{anchor}",chosen[::-1]
    # Repeatedly eliminate low-degree vertices, adding fill edges.
    live=set(original)
    link=[a.copy() for a in connections]
    order=[]
    while live:
        def cost(i):
            neighbors=sorted(link[i]&live)
            missing=sum(b not in link[a] for j,a in enumerate(neighbors) for b in neighbors[j+1:])
            return missing,len(neighbors),i
        i=min(live,key=cost)
        order.append(i)
        live.remove(i)
        neighbors=link[i]&live
        for a in neighbors:
            link[a].update(neighbors-{a})
    yield "minfill",order
    yield "minfill-reverse",order[::-1]
