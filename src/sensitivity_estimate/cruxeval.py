"""Score CruxEval functions with trace-based suffix-influence sensitivity.

CruxEval (``cruxeval-org/cruxeval``) provides ~800 small executable Python
functions named ``f`` together with concrete inputs and outputs, which makes it
the cheapest corpus for correlating sensitivity against published per-problem
output-prediction accuracy.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .semantics import sensitivity_summary
from .tracing import trace_call


@dataclass(frozen=True)
class SampleResult:
    sample_id: str
    completed: bool
    error: str | None
    extra_activations: int
    metrics: dict[str, float | int] | None

    def to_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "id": self.sample_id,
            "completed": self.completed,
            "error": self.error,
            "extra_activations": self.extra_activations,
        }
        if self.metrics is not None:
            record.update(self.metrics)
        return record


def score_sample(
    sample_id: str,
    code: str,
    call_arguments: str,
    *,
    timeout_seconds: float = 5.0,
) -> SampleResult:
    try:
        trace = trace_call(
            code, f"f({call_arguments})", timeout_seconds=timeout_seconds
        )
    except (SyntaxError, ValueError) as exc:
        return SampleResult(
            sample_id=sample_id,
            completed=False,
            error=f"{type(exc).__name__}: {exc}",
            extra_activations=0,
            metrics=None,
        )
    metrics = sensitivity_summary(trace).to_dict() if trace.events else None
    return SampleResult(
        sample_id=sample_id,
        completed=trace.completed,
        error=trace.error,
        extra_activations=trace.extra_activations,
        metrics=metrics,
    )


def load_cruxeval(split: str = "test") -> Iterable[dict[str, Any]]:
    from datasets import load_dataset

    return load_dataset("cruxeval-org/cruxeval", split=split)


def score_cruxeval(
    samples: Iterable[dict[str, Any]],
    *,
    limit: int | None = None,
    timeout_seconds: float = 5.0,
) -> Iterator[SampleResult]:
    for index, sample in enumerate(samples):
        if limit is not None and index >= limit:
            return
        yield score_sample(
            sample["id"],
            sample["code"],
            sample["input"],
            timeout_seconds=timeout_seconds,
        )


def write_results(results: Iterable[SampleResult], output_path: Path) -> int:
    count = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result.to_dict()) + "\n")
            count += 1
    return count
