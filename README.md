# BlockLift

BlockLift solves independent-set reconfiguration under **Token Jumping**. Each move replaces one vertex of a fixed-size independent set with another vertex. The solver uses blocking summaries and graph-specific decomposition, then lifts a summary-level solution to legal moves in the original graph. It can return an explicit move list or a compressed witness. The frozen V2 artifact runs locally without an LLM, API key, or model download.

## Environment

The reference run used **Python 3.14.2**, **NumPy 2.4.3**, and **SciPy 1.18.1** on Windows. Run the commands from the repository root using Python 3.14.

    python -m pip install -r requirements.txt

## Solve and verify an example

    python -X utf8 "正式实验/78_最终求解器.py" examples/tiny.col examples/tiny.dat --output example-result.json
    python -X utf8 "正式实验/78_最终求解器.py" examples/tiny.col examples/tiny.dat --verify example-result.json

The example has a one-move solution. The graph uses DIMACS-style p and e lines. Endpoint files use s and t lines. Vertex IDs in files and exported witnesses start at 1. Add --moves-out moves.txt to stream the verified move list. Use --family generic for arbitrary graphs when bypassing family inference.

## Reproduce the 693-case CoRe run

    python -X utf8 download_benchmark.py
    python -X utf8 run_benchmark.py --seconds 15 --output reproduction.jsonl

The downloader fetches only inputs from the published CoRe case list in the [pinned SRIP artifact](https://github.com/TakehideSoh/KR2026/tree/df807b6b6ea66b7ec37a5371c58967eecc5ce762/benchmark). Budget roughly 300 MB for inputs. Downloaded inputs are reused on subsequent runs. The runner extracts the original [V2 archive](artifacts/BlockLift-v2.zip) to a temporary directory and invokes its CLI on every case. Restart with the same output path, archive, and budget to resume completed rows. Use a fresh output path to start over.

Archive SHA-256 **9d6371b3045c18f7641c62cd165d2b80fca6860c6ed74459f24b020d79348fa0**. The browsable solver entry adds Chinese comments for readability. The benchmark runner uses the original archive directly.

The configured 15 seconds is a cooperative search budget. Input parsing and witness validation are timed separately from search. Runtime and cutoff-dependent outcomes may vary with hardware and software. The reference run returned five cases after the budget check, with a maximum reported search time of 15.584 seconds.

| Frozen V2 reference result | Cases |
|---|---:|
| Verified reachable | 627 |
| Proved unreachable | 66 |
| Undecided / runtime error | 0 |

## Recorded results

- [Frozen 15-second run with per-case witnesses](results/blocklift-v2-15s.jsonl) and [per-case comparison](results/blocklift-v2-per-instance.csv)
- [Comparison with CoRe and four published studies](reports/comparison.md)
- [Seven uncapped follow-up runs](reports/seven-uncapped.md)
- [Reference experimental protocol and outcomes](reports/frozen-v2.md)

The reproduction command covers the frozen V2 run. The cumulative comparison also uses historical best paths and the seven uncapped follow-up runs. The latter are supplied as recorded results. Benchmark files remain hosted by their original publishers.
