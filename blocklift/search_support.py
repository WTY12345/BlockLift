"""Shared path validation and search utilities."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


spec = spec_from_file_location("core_pilot", Path(__file__).with_name("beam_policy.py"))
reference = module_from_spec(spec)
spec.loader.exec_module(reference)


def validate(case, result, limit, known_length, adj, *, materialize=True):
    path = result["path"]
    if path is None:
        return
    pilot = reference.pilot
    assert path[0] == pilot.mask_of(case.start) and path[-1] == pilot.mask_of(case.target)
    assert result["length"] <= limit
    assert known_length is None or result["length"] >= known_length
    for before, after in zip(path, path[1:]):
        removed, added = before & ~after, after & ~before
        assert removed.bit_count() == added.bit_count() == 1
        assert not (adj[added.bit_length() - 1] & (before ^ removed))
    if materialize:
        result["path"] = [list(pilot.vertices(state)) for state in path]
