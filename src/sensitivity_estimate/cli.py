"""Command-line interface for sensitivity estimation."""

from __future__ import annotations

import argparse
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sensitivity-estimate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    crux = subparsers.add_parser(
        "cruxeval", help="score CruxEval functions and write JSONL metrics"
    )
    crux.add_argument("--output", type=Path, default=Path("results/cruxeval.jsonl"))
    crux.add_argument("--split", default="test")
    crux.add_argument("--limit", type=int, default=None)
    crux.add_argument("--timeout", type=float, default=5.0)

    args = parser.parse_args(argv)

    if args.command == "cruxeval":
        from tqdm import tqdm

        from .cruxeval import load_cruxeval, score_cruxeval, write_results

        samples = load_cruxeval(split=args.split)
        results = score_cruxeval(
            tqdm(samples, desc="scoring"),
            limit=args.limit,
            timeout_seconds=args.timeout,
        )
        count = write_results(results, args.output)
        print(f"wrote {count} records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
