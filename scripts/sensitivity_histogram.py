#!/usr/bin/env python3
"""Plot a histogram of per-function sensitivity from a scored JSONL file."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import matplotlib.pyplot as plt


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        default=Path("results/cruxeval-test.jsonl"),
        help="Scored JSONL produced by `sensitivity-estimate cruxeval`.",
    )
    parser.add_argument("--metric", default="sensitivity_density")
    parser.add_argument("--bins", type=int, default=40)
    parser.add_argument("--output", type=Path, default=None, help="Defaults to figures/<metric>.pdf")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    with args.input.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    values = [row[args.metric] for row in rows if row.get("completed") and args.metric in row]
    if not values:
        raise SystemExit(f"no completed records with {args.metric!r} in {args.input}")

    fig, ax = plt.subplots(figsize=(5, 3.2), constrained_layout=True)
    ax.hist(values, bins=args.bins, edgecolor="white", linewidth=0.4)
    median = statistics.median(values)
    ax.axvline(median, linestyle="--", linewidth=1, color="black", label=f"median = {median:.2f}")
    ax.set_xlabel(args.metric.replace("_", " "))
    ax.set_ylabel("functions")
    ax.set_title(f"{args.input.stem} (n = {len(values)})")
    ax.legend(frameon=False)

    output = args.output or Path("figures") / f"{args.metric}.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output)
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
