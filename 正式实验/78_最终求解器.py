"""Run the final Token Jumping solver on local CoRe/DIMACS inputs."""
import argparse
from dataclasses import dataclass, replace
import json
from math import isfinite, isqrt
from pathlib import Path
import runpy
from tempfile import NamedTemporaryFile
from time import perf_counter

HERE = Path(__file__).resolve().parent
FAMILIES = ("generic","grid","queen","ph-isr","exp_instance","sp","power","power_wide",
            "power_wider","square","square_wide","square_wider","color04","random_instance",
            "handcrafted")
SCHEMA = "tj-witness-v1"


# 一个整数表示一个顶点集合，第 v 位对应内部顶点 v。只枚举置位的顶点。
def vertices(mask):
    while mask:
        bit = mask & -mask
        yield bit.bit_length()-1
        mask ^= bit


@dataclass(frozen=True)
class Edges:
    adjacency: tuple
    count: int

    def __len__(self):
        return self.count

    # 邻接表对无向边存了两份。只枚举 v > u，每条边正好返回一次。
    def __iter__(self):
        for u,neighbors in enumerate(self.adjacency):
            for v in vertices(neighbors & ~((1<<(u+1))-1)):
                yield u,v


@dataclass(frozen=True)
class Case:
    name: str
    n: int
    edges: Edges
    start: tuple
    target: tuple
    family: str = "generic"

    def adjacency(self):
        return self.edges.adjacency


# 读取 CoRe/DIMACS 图，文件顶点从 1 编号，读入后从 0 编号。
def read_graph(path):
    with path.open("r",encoding="utf-8-sig") as source:
        n = expected = None
        seen = 0
        for line in source:
            fields = line.split()
            if not fields or fields[0]=="c":
                continue
            if fields[0]=="p" and n is None and len(fields) in (3,4):
                n,expected = map(int,fields[-2:])
                if n<1 or not 0<=expected<=n*(n-1)//2:
                    raise ValueError("Invalid problem header")
                # 边很多时先原地更新字节数组，读完再统一转换为整数位集。
                dense = expected>1_000_000 and n<=50_000
                rows = [bytearray((n+7)//8) for _ in range(n)] if dense else [0]*n
                continue
            if fields[0]!="e" or n is None or len(fields)!=3:
                raise ValueError(f"Invalid graph line: {line.rstrip()}")
            u,v = (int(x)-1 for x in fields[1:])
            if not (0<=u<n and 0<=v<n) or u==v:
                raise ValueError("Edges must join distinct vertices within the graph")
            if dense:
                col,bit = v//8,1<<(v%8)
                if rows[u][col]&bit:
                    raise ValueError("Duplicate undirected edge")
                rows[u][col] |= bit
                rows[v][u//8] |= 1<<(u%8)
            else:
                if rows[u]&(1<<v):
                    raise ValueError("Duplicate undirected edge")
                rows[u] |= 1<<v
                rows[v] |= 1<<u
            seen += 1
    if n is None or seen!=expected:
        raise ValueError("The edge count does not match the problem header")
    adjacency = tuple(int.from_bytes(row,"little") for row in rows) if dense else tuple(rows)
    return Edges(adjacency,seen)


# 读取起点 s 和终点 t，检查它们都是等大小的独立集。
def read_case(graph, ends):
    edges = read_graph(graph)
    n = len(edges.adjacency)
    endpoints = {}
    for line in ends.read_text(encoding="utf-8-sig").splitlines():
        fields = line.split()
        if not fields or fields[0]=="c":
            continue
        tag,*tokens = fields
        if tag not in {"s","t"} or tag in endpoints:
            raise ValueError("Endpoint file must contain one s line and one t line")
        group = tuple(int(v)-1 for v in tokens)
        if len(set(group))!=len(group) or any(v<0 or v>=n for v in group):
            raise ValueError("Endpoint vertices must be distinct and within the graph")
        mask = sum(1<<v for v in group)
        if any(edges.adjacency[v]&mask for v in group):
            raise ValueError("Each endpoint must be an independent set")
        endpoints[tag] = group
    if endpoints.keys()!={"s","t"} or len(endpoints["s"])!=len(endpoints["t"]):
        raise ValueError("Provide both endpoints with the same number of tokens")
    return Case(ends.name,n,edges,endpoints["s"],endpoints["t"])


# 用实例名和目录名选择候选图族，图族用于分派搜索策略。
def choose_family(graph, ends):
    name = ends.name.lower()
    if name.startswith("sat_exp_instance") or name.startswith("lgc_exp_instance"):
        return "exp_instance"
    if name.startswith("ph-"):
        return "ph-isr"
    if graph.parent.name in FAMILIES:
        return graph.parent.name
    for prefix,family in (("queen","queen"),("grid","grid"),("sp","sp"),
                          ("hc-power-","power"),("hc-square-","square")):
        if name.startswith(prefix):
            return family
    return "generic"


def queen_board(case):
    """Verify the row, column, and both diagonal constraints before using board moves."""
    # 按行、列和两条对角线重建攻击邻接表，再逐点与输入图核对。
    side = isqrt(case.n)
    if side*side!=case.n:
        return False
    axes = [(r,c,r-c+side-1,r+c) for r in range(side) for c in range(side)]
    line_masks = [[0]*side,[0]*side,[0]*(2*side-1),[0]*(2*side-1)]
    for v,indices in enumerate(axes):
        for table,i in zip(line_masks,indices):
            table[i] |= 1<<v
    for v,(r,c,d,a) in enumerate(axes):
        mask = line_masks[0][r]|line_masks[1][c]|line_masks[2][d]|line_masks[3][a]
        if case.edges.adjacency[v]!=mask^(1<<v):
            return False
    return True


# 显式路径存的是状态序列。相邻状态的两个差集给出移出点与移入点。
def moves_from_path(path):
    for i in range(1,len(path)):
        before,after = path[i-1],path[i]
        removed,added = before&~after,after&~before
        if removed.bit_count()!=1 or added.bit_count()!=1:
            raise ValueError("Witness contains a non-jump transition")
        yield removed.bit_length(),added.bit_length()


# 从起点独立重放每一步。Token Jumping 允许跳到任意空顶点。
def replay(case, moves, destination=None):
    mask = sum(1<<v for v in case.start)
    target = sum(1<<v for v in case.target)
    count = 0
    for u,v in moves:
        if not (1<=u<=case.n and 1<=v<=case.n):
            raise ValueError("Witness vertex is outside the graph")
        removed,added = 1<<(u-1),1<<(v-1)
        # 移出点必须已有令牌，移入点必须为空，且它与移出后留下的令牌均不相邻。
        if not mask&removed or mask&added or case.edges.adjacency[v-1]&(mask^removed):
            raise ValueError(f"Illegal jump at step {count+1}")
        mask ^= removed|added
        count += 1
        if destination is not None:
            destination.write(f"{u} {v}\n")
    if mask!=target:
        raise ValueError("Witness does not reach the supplied target")
    return count


def verify_document(case, result, structure):
    if result.get("schema")!=SCHEMA or result.get("status")!="found":
        raise ValueError("Verification requires a found witness in tj-witness-v1 format")
    if result["representation"]=="moves":
        count = replay(case,result["moves"])
    # 压缩见证用 DAG 共享子序列。转回内部编号后，交由结构模块验证。
    elif result["representation"]=="compressed":
        witness = result["witness"]
        nodes = witness["nodes"]
        if not nodes or nodes[0] or not 0<=witness["root"]<len(nodes):
            raise ValueError("Invalid compressed witness root or empty node")
        normalized = dict(root=witness["root"],nodes=[
            ("move",node[1]-1,node[2]-1) if node and node[0]=="move" else node
            for node in nodes
        ])
        start,target = (sum(1<<v for v in group) for group in (case.start,case.target))
        count = structure["verify_witness"](normalized,case.adjacency(),start,target)
    else:
        raise ValueError("Unknown witness representation")
    # 合法性检查同时核对实际移动步数。最短性依据由求解器单独给出。
    if count!=result["length"]:
        raise ValueError("Witness length does not match its metadata")
    return count


# 边重放边写临时文件，验证完成后再替换目标文件。
def write_moves(path, case, moves, expected):
    temporary = None
    try:
        with NamedTemporaryFile(mode="w",encoding="utf-8",newline="\n",delete=False,dir=path.parent) as f:
            temporary = Path(f.name)
            if replay(case,moves,f)!=expected:
                raise ValueError("Expanded witness length does not match its metadata")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph",type=Path)
    parser.add_argument("endpoints",type=Path)
    parser.add_argument("--family",choices=("auto",*FAMILIES),default="auto")
    parser.add_argument("--seconds",type=float,default=15)
    parser.add_argument("--quality",action="store_true",help="Try to improve an explicit path within the budget")
    parser.add_argument("--output",type=Path,help="Save the JSON result to this file")
    parser.add_argument("--moves-out",type=Path,help="Also stream a validated explicit move list, u v per line")
    parser.add_argument("--verify",type=Path,help="Verify a saved found result against the input")
    args = parser.parse_args()
    if not isfinite(args.seconds) or args.seconds<=0:
        parser.error("the solve budget must be a positive finite number")
    inputs = {args.graph.resolve(),args.endpoints.resolve()}
    if args.verify:
        inputs.add(args.verify.resolve())
    outputs = [p.resolve() for p in (args.output,args.moves_out) if p is not None]
    if inputs.intersection(outputs) or len(set(outputs))!=len(outputs):
        parser.error("inputs and outputs must be distinct files")
    if args.verify and outputs:
        parser.error("verification cannot be combined with output options")

    try:
        started = perf_counter()
        case = read_case(args.graph,args.endpoints)
        family = choose_family(args.graph,args.endpoints) if args.family=="auto" else args.family
        # 皇后图特化依赖真实的攻击邻接关系，因此在分派前检查图结构。
        if family=="queen" and not queen_board(case):
            if args.family!="auto":
                raise ValueError("The graph does not satisfy queen-board adjacency")
            family = "generic"
        case = replace(case,family=family)
        input_seconds = perf_counter()-started
        # 真正的搜索在集成求解器中：链式图族优先试带权压缩，
        # 一般情况交给综合结构求解器，有余量时按图族尝试缩短已有路径。
        solver = runpy.run_path(str(HERE/"88_改短集成求解器.py"))
        structure = solver["structures"]
        if args.verify:
            length = verify_document(case,json.loads(args.verify.read_text(encoding="utf-8-sig")),structure)
            print(json.dumps(dict(status="verified",length=length),ensure_ascii=False))
            return
        # seconds 是搜索阶段的预算。读取、见证验证和导出各有独立计时范围。
        # quality 请求在预算内进一步改短，并允许拼接已有路径片段。
        result = solver["solve"](case,family,args.seconds,name=case.name,quality=args.quality,splice=args.quality)
        path = result.pop("path",None)
        result.update(schema=SCHEMA,family=family,input_seconds=input_seconds,budget_seconds=args.seconds)
        if result["status"]=="found":
            began = perf_counter()
            if path is not None:
                moves = list(moves_from_path(path))
                if replay(case,moves)!=len(path)-1:
                    raise ValueError("Witness length does not match the explicit path")
                result.update(moves=moves,length=len(moves),representation="moves")
                stream = iter(moves)
            else:
                witness = result["witness"]
                # 导出时把 DAG 中 move 节点的顶点转成从 1 开始的编号，引用下标保持原值。
                # The internal DAG uses zero-based vertices. Outgoing witness vertices are one-based.
                nodes = [node if not node or node[0]!="move" else ("move",node[1]+1,node[2]+1)
                         for node in witness["nodes"]]
                result.update(witness=dict(root=witness["root"],nodes=nodes),representation="compressed")
                verify_document(case,result,structure)
                stream = ((u+1,v+1) for u,v in structure["iter_moves"](witness))
            if args.moves_out:
                write_moves(args.moves_out,case,stream,result["length"])
            result["validation_and_export_seconds"] = perf_counter()-began
        output = json.dumps(result,ensure_ascii=False)+"\n"
        if args.output:
            args.output.write_text(output,encoding="utf-8")
        else:
            print(output,end="")
    except (OSError,ValueError,AssertionError,KeyError,TypeError,IndexError) as error:
        parser.exit(2,f"error: {error or 'witness check failed'}\n")


if __name__=="__main__":
    main()
