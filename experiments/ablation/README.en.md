# Blocking-summary ablations

[简体中文](README.md) · [English](README.en.md) · [Project home](../../README.en.md)

The archived experiments use the solver snapshot 428f21983f234cc6cd16c948471fb68dcb2235ef, Python 3.14.2, and the pinned CoRe inputs. The published branch retains the same solver files.

## Results

The 693-case factorial experiment turns saturated contraction and specialized branches on and off independently. All configurations keep generic search, closed-neighborhood reduction, and the one-vacancy branch. We count results returned and verified within the one-second solver budget.

| Saturated summary | Specialized branches | Reachable | Unreachable | Total |
|---|---|---:|---:|---:|
| Off | Off | 453 | 10 | 463 |
| On | Off | 575 | 11 | 586 |
| Off | On | 475 | 66 | 541 |
| On | On | 598 | 66 | 664 |

The net gains are 123 from saturated summaries and 78 from specialized branches in this configuration. The median off-to-on timing ratio for the 229 equal-outcome, equal-length pairs above 10 ms with specialized branches enabled is 0.998.

The paired prefix experiment keeps partitions, block order, and pruning fixed. Enabling contraction raises three-repetition completion from 32 to 114 out of 121, with gains in 13 of 14 groups. In the 32 fully paired cases, contraction reduces states in 27 and time in 26, while producing longer witnesses in 12. Where the labels are distinct, the measured number of states remains the same and contraction adds overhead. See the [full results](README.md) for per-group ratios.

[Factorial logs](data/factorial-693.jsonl) · [Prefix logs](data/prefix-121.jsonl) · [Summary](data/summary.json)

## Reproduce

From the repository root, recompute the archived tables without downloading the benchmark.

~~~text
python -X utf8 experiments/ablation/ablation_metrics.py --output ablation-summary.json
~~~

To rerun after installing project requirements, download the pinned instances and use fresh output paths.

~~~text
python -X utf8 download_benchmark.py
python -X utf8 experiments/ablation/factorial_ablation.py --seconds 1 --output factorial-reproduction.jsonl
python -X utf8 experiments/ablation/cross_family_ablation.py --seconds 1 --cap 40000 --repeats 3 --public-per-family 8 --output prefix-reproduction.jsonl
python -X utf8 experiments/ablation/ablation_metrics.py --factorial factorial-reproduction.jsonl --prefix prefix-reproduction.jsonl --output ablation-rerun-summary.json
~~~
