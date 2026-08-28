"""Suffix-influence sensitivity over a straightline statement trace.

This mirrors state-bench's ``sensitivity_summary`` reverse pass: walk the
executed trace backward propagating output-liveness through copies/operations
and killing it at statements that fully overwrite a variable from sources that
are not local state (the analogue of a constant assignment). A variable is
*live* at a boundary if perturbing its value there could change the returned
output.

With a single returned output there is no output fanout, so density and
coverage coincide; we report the shared value as ``sensitivity_density``.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from .statements import StatementInfo
from .tracing import TraceResult


@dataclass(frozen=True)
class SensitivitySummary:
    num_events: int
    num_variables: int
    sensitivity_density: float
    """Mean over trace boundaries of (live variables / trace variables)."""
    mean_live_variables: float
    max_live_variables: int
    return_dependency_length: int
    """Length of the longest def-use chain feeding the returned value."""

    def to_dict(self) -> dict[str, float | int]:
        return {
            "num_events": self.num_events,
            "num_variables": self.num_variables,
            "sensitivity_density": self.sensitivity_density,
            "mean_live_variables": self.mean_live_variables,
            "max_live_variables": self.max_live_variables,
            "return_dependency_length": self.return_dependency_length,
        }


def trace_variables(
    events: list[StatementInfo], parameters: frozenset[str]
) -> frozenset[str]:
    """Local state of the trace: parameters plus every written name."""
    written: set[str] = set(parameters)
    for event in events:
        written |= event.targets
    return frozenset(written)


def sensitivity_summary(trace: TraceResult) -> SensitivitySummary:
    events = trace.events
    variables = trace_variables(events, trace.parameters)
    if not events or not variables:
        return SensitivitySummary(
            num_events=len(events),
            num_variables=len(variables),
            sensitivity_density=0.0,
            mean_live_variables=0.0,
            max_live_variables=0,
            return_dependency_length=0,
        )

    live: set[str] = set()
    live_counts: list[int] = []
    for event in reversed(events):
        sources = event.sources & variables
        if event.is_return:
            live |= sources
        elif event.targets & live:
            live -= event.targets
            live |= sources
        live_counts.append(len(live))

    depth: dict[str, int] = {name: 1 for name in trace.parameters}
    return_depth = 0
    for event in events:
        source_depth = max(
            (depth.get(name, 0) for name in event.sources & variables), default=0
        )
        if event.is_return:
            return_depth = max(return_depth, source_depth)
        for target in event.targets:
            depth[target] = source_depth + 1

    return SensitivitySummary(
        num_events=len(events),
        num_variables=len(variables),
        sensitivity_density=statistics.fmean(live_counts) / len(variables),
        mean_live_variables=statistics.fmean(live_counts),
        max_live_variables=max(live_counts),
        return_dependency_length=return_depth,
    )
