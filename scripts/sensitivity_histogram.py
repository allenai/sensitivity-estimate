#!/usr/bin/env python3
"""Plot a histogram of per-function sensitivity from a scored JSONL file."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import aesthetics as aes
import matplotlib.pyplot as plt
import seaborn as sns


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
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output stem or filename; defaults to figures/<metric>.",
    )
    parser.add_argument("--title", default=None, help="Defaults to a metric-based title.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    with args.input.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    values = [row[args.metric] for row in rows if row.get("completed") and args.metric in row]
    if not values:
        raise SystemExit(f"no completed records with {args.metric!r} in {args.input}")

    figure, axis = plt.subplots(figsize=(aes.PAPER_WIDTH_IN, aes.FIG_HEIGHT_DOUBLE_ROW_IN))
    sns.histplot(values, bins=args.bins, color=aes.NONSEMANTIC_COLOR, ax=axis)
    median = statistics.median(values)
    axis.axvline(
        median,
        linestyle="--",
        linewidth=1,
        color=aes.darken(aes.NONSEMANTIC_COLOR, by=0.4),
        label=f"median = {median:.2f}",
    )
    metric_label = args.metric.replace("_", " ").capitalize()
    axis.set_xlabel(metric_label)
    axis.set_ylabel("Functions")
    axis.yaxis.set_major_formatter(aes.NICE_FORMATTER)
    if args.metric in {"sensitivity_density", "sensitivity_coverage"}:
        axis.xaxis.set_major_formatter(aes.PCT_FORMATTER)
    axis.legend(frameon=False)
    sns.despine(fig=figure)

    title = args.title or f"{metric_label} of executed CruxEval functions"
    aes.set_figure_title(figure, title, f"{args.input.stem}, n = {len(values)}")
    output = args.output or Path("figures") / args.metric
    pdf_path, _ = aes.save_figure(output, fig=figure, save_png=True)
    print(f"wrote {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
