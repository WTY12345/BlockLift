"""Plot the fixed-core timing comparison directly from the review logs."""
import argparse
import json
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import NullLocator

HERE = Path(__file__).resolve().parent
IMPLICIT = "#175b84"
ASTAR = "#a64b20"


def load(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def plot(data, output):
    rows = load(data / "matched-core-only.jsonl")
    followup = next(row for row in load(data / "matched-large-cap.jsonl")
                    if (row["family"], row["pairs"]) == ("detour", 1024))
    extended = followup["core_only"]["1000000"]
    assert all(s == "complete" for s in extended["statuses"])
    detours = sorted((row for row in rows if row["family"] == "detour"), key=lambda row: row["pairs"])

    with plt.rc_context({"font.size": 8, "pdf.fonttype": 42, "ps.fonttype": 42,
                         "axes.spines.top": False, "axes.spines.right": False}):
        fig, (left, right) = plt.subplots(1, 2, sharey=True, figsize=(4.8, 2.75),
                                         gridspec_kw={"width_ratios": [1.25, 1]})
        fig.subplots_adjust(left=.136, right=.985, bottom=.23, top=.76, wspace=.28)
        for ax, title in [(left, "(a) Forced detour"), (right, "(b) At 1,024 pairs")]:
            ax.set_title(title, loc="left", fontweight="bold", pad=7)
            ax.set_yscale("log")
            ax.set_ylim(.029, 8500)
            ax.set_yticks([.1, 1, 10, 100, 1000], labels=["0.1", "1", "10", "100", "1,000"])
            ax.yaxis.set_minor_locator(NullLocator())
            ax.grid(axis="y", color=".88", linewidth=.55)
            ax.set_axisbelow(True)
            ax.axhline(1000, color=".52", linewidth=.75, linestyle=":")
            ax.tick_params(length=2.8, width=.6, labelsize=7.4)
        left.set_ylabel("Median time (ms)")
        left.set_xscale("log", base=2)
        left.set_xticks([8, 16, 64, 256, 1024], labels=["8", "16", "64", "256", "1,024"])
        left.xaxis.set_minor_locator(NullLocator())
        left.set_xlim(6.5, 1380)
        left.set_xlabel("Exterior matched pairs")
        left.text(.04, 1000, "1 s time budget", va="bottom", ha="left", fontsize=6.8,
                  color=".32", transform=left.get_yaxis_transform())

        def ms(result):
            return 1000 * result["seconds"]

        def result(row, key):
            return row["implicit"] if key == "implicit" else row["core_only"]["200000"]

        for key, color, symbol, style, label in (
            ("implicit", IMPLICIT, "o", "-", "2-SAT"),
            ("astar", ASTAR, "s", "--", "Core-only A*"),
        ):
            completed = [(row["pairs"], ms(result(row,key))) for row in detours
                         if result(row,key)["status"] == "complete"]
            left.plot(*zip(*completed), color=color, marker=symbol, linestyle=style,
                      markersize=3.5, linewidth=1.1, label=label)
            for x, family in enumerate(("path", "sparse", "detour")):
                group = [result(row,key) for row in rows
                         if (row["family"],row["pairs"]) == (family,1024)]
                statuses = {entry["status"] for entry in group}
                assert len(statuses) == 1
                if statuses == {"complete"}:
                    right.plot(x+(-.12 if key=="implicit" else .12), median(map(ms,group)),
                               marker=symbol, color=color, linestyle="none", markersize=4)
                else:
                    assert key == "astar" and statuses == {"state_cap"}
                    right.plot(x+.12, median(map(ms,group)), marker="x", color=color,
                               linestyle="none", markersize=5)
        right.set_xticks(range(3), ["Path", "Sparse", "Detour"])
        right.set_xlim(-.38, 2.44)
        right.set_xlabel("Conflict family")

        stopped = result(detours[-1], "astar")
        assert detours[-1]["pairs"] == 1024 and stopped["status"] == "state_cap"
        left.plot(1024, ms(stopped), marker="x", color=ASTAR, linestyle="none",
                  markersize=5, label="State cap (stop time)")
        left.plot(1024, ms(extended), marker="s", markerfacecolor="white", markeredgecolor=ASTAR,
                  linestyle="none", markersize=5, label="A* at larger budget")
        left.annotate(f'{extended["seconds"]:.2f} s', (1024, ms(extended)),
                      xytext=(-7,0), textcoords="offset points", ha="right", va="center",
                      color=ASTAR, fontsize=7.1)
        left.annotate("200k states", (1024, ms(stopped)), xytext=(-7,-6),
                      textcoords="offset points", ha="right", va="top", color=ASTAR, fontsize=7.1)
        left.annotate(f'{ms(result(detours[-1],"implicit")):.2f} ms',
                      (1024, ms(result(detours[-1],"implicit"))), xytext=(-7,6),
                      textcoords="offset points", ha="right", color=IMPLICIT, fontsize=7.1)
        handles, labels = left.get_legend_handles_labels()
        fig.legend(handles, labels, loc="upper center", ncol=2, frameon=False,
                   handlelength=1.6, columnspacing=1.5, fontsize=7.4)
        for ext in ("pdf", "eps"):
            fig.savefig(output.with_suffix(f".{ext}"), facecolor="white")
        plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=HERE/"data")
    parser.add_argument("--output", type=Path, default=HERE/"Fig4", help="Output path stem")
    args = parser.parse_args()
    plot(args.data, args.output)
