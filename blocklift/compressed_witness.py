"""Grid phase certificates and compressed witnesses for saturated decompositions."""
from functools import cache
from math import isqrt
from time import perf_counter


def grid_certificate(case):
    side = isqrt(case.n)
    slack = case.n//2-len(case.start)
    if (len(case.start)!=len(case.target) or side**2 != case.n or side%2 or slack < 0
            or (side//2)**2 <= 2*slack**2):
        return None

    def parity(vertices):
        return {(v//side+v%side)%2 for v in vertices}

    start, goal = parity(case.start), parity(case.target)
    if len(start) != 1 or len(goal) != 1 or start == goal:
        return None
    expected = {(u,u+1) for u in range(case.n) if u%side != side-1}
    expected.update((u,u+side) for u in range(case.n-side))
    if expected != {tuple(sorted(e)) for e in case.edges}:
        return None
    return dict(tile_side=side//2, slack=slack, giant_lower_bound=(side//2)**2-slack**2,
                start_parity=next(iter(start)), target_parity=next(iter(goal)))


class Grammar:
    """Nodes are moves, component transitions, or ordered concatenations."""
    def __init__(self, check):
        self.nodes = [()]
        self.ids = {():0}
        self.check = check

    def add(self, node):
        if node not in self.ids:
            self.check(len(self.nodes))
            self.ids[node] = len(self.nodes)
            self.nodes.append(node)
        return self.ids[node]

    def join(self, *parts):
        active = tuple(part for part in parts if part)
        if not active:
            return 0
        if len(active)==1:
            return active[0]
        return self.add(("seq",*active))

    def export(self, root, *, final=True):
        reached = {0}
        pending = [root]
        while pending:
            node = pending.pop()
            if node in reached:
                continue
            reached.add(node)
            kind,*args = self.nodes[node]
            if kind=="seq":
                pending.extend(args)
        ids = {old:i for i,old in enumerate(sorted(reached))}
        nodes = [()]
        for old in sorted(reached-{0}):
            kind,*args = self.nodes[old]
            if kind=="seq":
                nodes.append((kind,*(ids[a] for a in args)))
            else:
                assert kind=="move" or not final
                nodes.append(self.nodes[old])
        return dict(root=ids[root],nodes=nodes)


def build_witness(stages, route, check):
    grammar = Grammar(check)
    word = 0
    for pairs,graph,component,bridges,start,goal,_ in reversed(stages):
        check(len(grammar.nodes))

        def product_move(i,j):
            old,i_state = pairs[i]
            new,j_state = pairs[j]
            if old != new:
                assert i_state == j_state
                return grammar.add(("bridge",old,new))
            removed,added = i_state & ~j_state, j_state & ~i_state
            assert removed.bit_count() == added.bit_count() == 1
            return grammar.add(("move",removed.bit_length()-1,added.bit_length()-1))

        @cache
        def within(a,b):
            chain = route(graph,a,b,lambda j:component[j]==component[a])
            return grammar.join(*(product_move(i,j) for i,j in zip(chain,chain[1:])))

        @cache
        def transduce(node,current):
            check(len(grammar.nodes))
            if node==0:
                return 0,current
            kind,*args = grammar.nodes[node]
            if kind=="move":
                return node,current
            if kind=="bridge":
                old,new = args
                assert component[current]==old
                tail,head = bridges[old,new]
                return grammar.join(within(current,tail),product_move(tail,head)),head
            parts = []
            for child in args:
                output,current = transduce(child,current)
                parts.append(output)
            return grammar.join(*parts),current

        output,current = transduce(word,start)
        assert component[current]==component[goal]
        word = grammar.join(output,within(current,goal))
        transduce.cache_clear()
        within.cache_clear()
        if len(grammar.nodes)>50_000:
            live = grammar.export(word,final=False)
            grammar.nodes = live["nodes"]
            grammar.ids = {node:i for i,node in enumerate(grammar.nodes)}
            word = live["root"]
    return grammar.export(word)


def verify_witness(witness, adjacency, start, goal):
    """Check the effect of every word on a bitset via on/off preconditions and XOR."""
    summaries = [(0,0,0,0)]
    for i,(kind,*args) in enumerate(witness["nodes"][1:],1):
        if kind=="move":
            u,v = args
            assert 0<=u<len(adjacency) and 0<=v<len(adjacency) and u!=v
            removed,added = 1<<u,1<<v
            summaries.append((removed,added|(adjacency[v]&~removed),removed|added,1))
            continue
        assert kind=="seq"
        on = off = delta = length = 0
        for j in args:
            assert 0<=j<i
            child_on,child_off,child_delta,child_length = summaries[j]
            on |= (child_on&~delta)|(child_off&delta)
            off |= (child_off&~delta)|(child_on&delta)
            assert not on & off
            delta ^= child_delta
            length += child_length
        summaries.append((on,off,delta,length))
    on,off,delta,length = summaries[witness["root"]]
    assert start&on == on and not start&off and start^delta == goal
    return length


def iter_moves(witness):
    """Read the witness as zero-based physical moves without materializing the path."""
    nodes = witness["nodes"]
    todo = [witness["root"]]
    while todo:
        position = todo.pop()
        if position==0:
            continue
        kind,*args = nodes[position]
        if kind=="move":
            yield args[0],args[1]
        else:
            assert kind=="seq"
            todo.extend(reversed(args))


def compressed_solve(case, blocks, packed, deadline, *, pair_cap=250_000, node_cap=600_000,
                     build=build_witness):
    sizes = []

    def guard(limit, label):
        def check(count):
            if perf_counter()>=deadline:
                raise TimeoutError(label)
            if count>limit:
                raise OverflowError(label,count)
        return check

    try:
        witness, stages = packed.contract.solve(
            case,blocks,restrict_local=True,restrict_prefix=True,check=guard(pair_cap,"contraction"),
            observe=lambda pairs,labels,components:sizes.append((pairs,labels,components)),
            witness_builder=lambda stages:build(stages,packed.contract.route,guard(node_cap,"witness")),
        )
    except (OverflowError,TimeoutError,RecursionError) as error:
        return dict(status="budget",path=None,limit=type(error).__name__,limit_data=list(error.args),
                    completed_merges=len(sizes),peak_pairs=max((s[0] for s in sizes),default=0))
    if witness is None:
        return dict(status="unreachable",path=None)
    start, goal = map(packed.p.mask_of,(case.start,case.target))
    length = verify_witness(witness,case.adjacency(),start,goal)
    return dict(status="found",path=None,witness=witness,length=length,stages=stages)


def lift_witness(witness, case, classes, index):
    """Fix one representative per class and attach endpoint-only swaps."""
    start = {index[v]:v for v in case.start}
    target = {index[v]:v for v in case.target}
    representative = [start.get(i,target.get(i,group[0])) for i,group in enumerate(classes)]
    nodes = [()]
    for kind,*args in witness["nodes"][1:]:
        if kind=="move":
            nodes.append((kind,*(representative[i] for i in args)))
        else:
            nodes.append((kind,*args))
    suffix = []
    for i,v in target.items():
        if representative[i]!=v:
            suffix.append(len(nodes))
            nodes.append(("move",representative[i],v))
    root = witness["root"]
    if suffix:
        nodes.append(("seq",root,*suffix))
        root = len(nodes)-1
    return dict(root=root,nodes=nodes)
