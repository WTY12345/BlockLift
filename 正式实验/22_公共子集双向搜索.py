"""Search the incidence graph of independent sets and their one-token deletions."""
import json
from pathlib import Path, PurePosixPath
from time import perf_counter
from importlib.util import spec_from_file_location, module_from_spec

HERE = Path(__file__).resolve().parent
spec = spec_from_file_location("reference", HERE / "09_CoRe留出评估.py")
ev = module_from_spec(spec)
spec.loader.exec_module(ev)
p = ev.reference.pilot


def faces(state, adj, universe):
    tokens = list(p.vertices(state))
    suffix = [0] * (len(tokens) + 1)
    for i in reversed(range(len(tokens))):
        suffix[i] = suffix[i+1] | adj[tokens[i]]
    prefix = 0
    for i, token in enumerate(tokens):
        face = state ^ (1 << token)
        yield face, universe & ~(face | prefix | suffix[i+1])
        prefix |= adj[token]


def search(case, mode):
    start, goal = p.mask_of(case.start), p.mask_of(case.target)
    adj, universe = case.adjacency(), (1 << case.n)-1
    parents = [{start: None}, {goal: None}]
    layers = [[start], [goal]]
    visited_faces = [set(), set()]
    count = scans = skipped = 0
    began = perf_counter()
    weights = [(a & goal).bit_count()-4*bool(goal & (1 << v)) for v,a in enumerate(adj)]
    def result(status, path=None):
        return dict(status=status, path=path, expanded=count, candidates=scans, reused_faces=skipped,
                    elapsed=perf_counter()-began)
    while all(layers):
        side = int(mode != "top4_forward" and len(layers[1]) < len(layers[0]))
        following = []
        for state in layers[side]:
            count += 1
            if perf_counter()-began > 30 or sum(map(len,parents)) > 300000:
                return result("budget")
            if mode == "faces":
                def successors():
                    nonlocal skipped
                    for face, mask in faces(state, adj, universe):
                        if face in visited_faces[side]:
                            skipped += 1
                            continue
                        visited_faces[side].add(face)
                        for v in p.vertices(mask & ~state):
                            yield face | (1 << v)
                moves = successors()
            else:
                strategy = "llm_rule" if mode == "top4_forward" else "full"
                moves = (state ^ (1 << u) ^ (1 << v) for u,v in
                         p.candidate_moves(p.summarize(state,adj), strategy,4,None,weights))
            for new in moves:
                scans += 1
                if new in parents[side]:
                    continue
                parents[side][new] = state
                if new in parents[1-side]:
                    halves = []
                    for tree in parents:
                        seq, node = [], new
                        while node is not None:
                            seq.append(node)
                            node = tree[node]
                        halves.append(seq)
                    return result("found", halves[0][::-1]+halves[1][1:])
                following.append(new)
        layers[side] = following
    return result("exhausted")


def main():
    rows=json.loads((HERE/"LLM实验/精确宏动作1.5B/CoRe_beam_全量.json").read_bytes())["rows"]
    output=[]
    for row in rows:
        name=PurePosixPath(row["endpoint_file"]).name
        if name not in {"DSJC500.9_02.dat","hc-square-008-002_01.dat","hc-power-004-002_01.dat"}:
            continue
        case=ev.reference.load_case((row["family"],PurePosixPath(row["graph_file"]),PurePosixPath(row["endpoint_file"])))
        result={"instance":name,"n":case.n,"k":len(case.start),"runs":{}}
        for mode in ("top4_forward","full_bidir","faces"):
            r=search(case,mode)
            r["length"]=len(r["path"])-1 if r["path"] else None
            ev.validate(case,r,10**9,row["author_length"],case.adjacency())
            result["runs"][mode]=r
            print(name,mode,{k:v for k,v in r.items() if k!="path"},flush=True)
        output.append(result)
        ev.write_json(HERE/"公共子集搜索结果.json",output)


if __name__=="__main__":
    main()
