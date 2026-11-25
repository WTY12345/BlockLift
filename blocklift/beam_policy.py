"""Beam search adapter and shared state search primitives."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
spec = spec_from_file_location("isr_pilot", ROOT / "bitsets_and_beam.py")
pilot = module_from_spec(spec)
sys.modules[spec.name] = pilot
spec.loader.exec_module(pilot)
