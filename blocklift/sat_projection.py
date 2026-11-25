"""Search variable configurations of certified SAT-derived Token Jumping graphs."""
from collections import deque
from time import perf_counter


def vertices(mask):
    while mask:
        bit = mask & -mask
        yield bit.bit_length()-1
        mask ^= bit


def recognize(case, count):
    left_size = 2*count
    if not 0 < left_size < case.n:
        return None
    adj = case.adjacency()
    left_mask = (1<<left_size)-1
    if any(adj[v]&left_mask != 1<<(v^1) for v in range(left_size)):
        return None
    blocks = []
    remaining = ((1<<case.n)-1)^left_mask
    while remaining:
        v = (remaining&-remaining).bit_length()-1
        group = (1<<v)|(adj[v]&~left_mask)
        if group&remaining != group or not 2 <= group.bit_count() <= 3:
            return None
        ports = []
        for u in vertices(group):
            if (adj[u]&~left_mask)|(1<<u) != group:
                return None
            blocker = adj[u]&left_mask
            if blocker.bit_count()!=1:
                return None
            ports.append((u,blocker))
        blocks.append(ports)
        remaining ^= group
    for endpoint in (case.start,case.target):
        active = set(endpoint)
        if len(active)!=count+len(blocks) or len(active)!=len(endpoint):
            return None
        if any((i in active)==(i+1 in active) for i in range(0,left_size,2)):
            return None
        if any(sum(u in active for u,_ in block)!=1 for block in blocks):
            return None
    return adj, blocks, left_mask


def project(start, target, count, blocks, deadline, state_limit):
    by_variable = [[] for _ in range(count)]
    for block in blocks:
        blocked_by = 0
        for _,bit in block:
            blocked_by |= bit
        for variable in {v//2 for v in vertices(blocked_by)}:
            by_variable[variable].append(blocked_by)
    parent = {start:None}
    queue = deque([start])
    edge_visits = max_degree = 0
    complete = True
    while queue:
        if perf_counter()>=deadline or len(parent)>state_limit:
            complete = False
            break
        state = queue.popleft()
        degree = 0
        for i,clauses in enumerate(by_variable):
            change = 3<<(2*i)
            next_state = state^change
            # A right-hand token must have one available position on both sides of the flip.
            if any(not (ports&~(state|next_state)) for ports in clauses):
                continue
            degree += 1
            if next_state not in parent:
                queue.append(next_state)
                parent[next_state] = state
        edge_visits += degree
        max_degree = max(max_degree,degree)
    data = dict(projected_states=len(parent),projection_complete=complete)
    if complete:
        data.update(projected_edges=edge_visits//2,projected_max_degree=max_degree)
    if target not in parent:
        return None,data
    path = [target]
    while parent[path[-1]] is not None:
        path.append(parent[path[-1]])
    return path[::-1],data


def minimum_block_schedule(block, path, initial, final):
    """Minimize moves in one clause block for a fixed variable trajectory."""
    back = []
    costs = {initial:0}
    for before,after in zip(path,path[1:]):
        boundary = before|after
        choices = [u for u,blocker in block if not blocker&boundary]
        previous = {u:min(costs,key=lambda v:(costs[v]+(u!=v),v)) for u in choices}
        costs = {u:costs[v]+(u!=v) for u,v in previous.items()}
        back.append(previous)
    current = min(costs,key=lambda v:(costs[v]+(v!=final),v))
    minimum = costs[current]+(current!=final)
    schedule = [current]
    for previous in reversed(back):
        current = previous[current]
        schedule.append(current)
    assert schedule[-1]==initial
    return schedule[-2::-1] if back else [],minimum


def lift(case, blocks, projected, deadline):
    start,target = set(case.start),set(case.target)
    initial = [next(u for u,_ in block if u in start) for block in blocks]
    final = [next(u for u,_ in block if u in target) for block in blocks]
    choices, auxiliary_moves = [],0
    for block,a,b in zip(blocks,initial,final):
        if perf_counter()>=deadline:
            raise TimeoutError
        schedule,cost = minimum_block_schedule(block,projected,a,b)
        choices.append(schedule)
        auxiliary_moves += cost
    moves = []
    at = initial[:]
    for step,(before,after) in enumerate(zip(projected,projected[1:])):
        for i,states in enumerate(choices):
            wanted = states[step]
            if wanted!=at[i]:
                moves.append((at[i],wanted))
                at[i] = wanted
        moves.append(((before&~after).bit_length()-1,(after&~before).bit_length()-1))
    moves.extend((a,b) for a,b in zip(at,final) if a!=b)
    assert len(moves)==len(projected)-1+auxiliary_moves
    return moves,auxiliary_moves


def verify(case, adj, moves):
    state = sum(1<<v for v in case.start)
    path = [state]
    for u,v in moves:
        remove,add = 1<<u,1<<v
        assert remove&state and not add&state
        state ^= remove
        assert not adj[v]&state
        state |= add
        path.append(state)
    assert state==sum(1<<v for v in case.target)
    return path


def solve(case, variables, deadline, *, state_limit=100_000):
    parts = recognize(case,variables)
    if parts is None:
        return dict(status="unsupported",path=None)
    adj,blocks,left_mask = parts
    start,target = (sum(1<<v for v in end)&left_mask for end in (case.start,case.target))
    projected,data = project(start,target,variables,blocks,deadline,state_limit)
    if projected is None:
        state = "unreachable" if data["projection_complete"] else "budget"
        return dict(status=state,path=None,**data)
    if perf_counter()>=deadline:
        return dict(status="budget",path=None,**data)
    try:
        moves,auxiliary = lift(case,blocks,projected,deadline)
    except TimeoutError:
        return dict(status="budget",path=None,**data)
    path = verify(case,adj,moves)
    if perf_counter()>=deadline:
        return dict(status="budget",path=None,**data)
    # On a tree the only simple variable path is forced. Returning to an earlier
    # assignment can be shortened by adjusting the independent clause blocks there.
    exact = data["projection_complete"] and data["projected_edges"]==data["projected_states"]-1
    return dict(status="found",path=path,length=len(moves),optimal=exact,
                variables=variables,clause_blocks=len(blocks),variable_moves=len(projected)-1,
                clause_moves=auxiliary,**data)
