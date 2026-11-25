"""Enumerate one-token deletions and extensions through shared residual sets."""
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec

HERE = Path(__file__).resolve().parent
spec = spec_from_file_location("reference", HERE / "search_support.py")
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
