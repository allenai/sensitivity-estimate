"""Dynamically trace a function call into a straightline statement sequence.

Executing a function on a concrete input resolves all control flow: the
sequence of executed statements is a straightline assignment trace, the same
object state-bench computes exact suffix influence over. We record line events
for the traced function's outermost activation only and map them through the
static per-line dataflow table.
"""

from __future__ import annotations

import ast
import signal
import sys
from dataclasses import dataclass, field
from typing import Any

from .statements import StatementInfo, parameter_names, statement_table


class TraceBudgetExceeded(RuntimeError):
    """The traced call executed more statements than allowed."""


class TraceTimeout(RuntimeError):
    """The traced call ran longer than the wall-clock limit."""


@dataclass
class TraceResult:
    events: list[StatementInfo]
    parameters: frozenset[str]
    return_value: Any = None
    completed: bool = False
    error: str | None = None
    extra_activations: int = field(default=0)
    """Recursive or repeated activations of the traced function that were not
    traced; nonzero means the trace under-approximates the computation."""


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise ValueError(f"no function named {name!r} in source")


def trace_call(
    source: str,
    call: str,
    *,
    function_name: str = "f",
    max_events: int = 200_000,
    timeout_seconds: float = 5.0,
) -> TraceResult:
    """Execute ``call`` (e.g. ``"f(1, [2])"``) against ``source`` and record
    the straightline statement trace of ``function_name``'s first activation.
    """
    tree = ast.parse(source)
    func = _find_function(tree, function_name)
    table = statement_table(func)
    params = parameter_names(func)

    namespace: dict[str, Any] = {}
    exec(compile(source, "<traced>", "exec"), namespace)  # noqa: S102
    target = namespace[function_name]
    code = target.__code__

    result = TraceResult(events=[], parameters=params)
    active_frame: list[Any] = []  # the single frame being traced

    def local_trace(frame: Any, event: str, arg: Any) -> Any:
        if event == "line":
            if len(result.events) >= max_events:
                raise TraceBudgetExceeded(f"exceeded {max_events} statements")
            info = table.get(frame.f_lineno)
            if info is not None:
                result.events.append(info)
        elif event == "return":
            result.return_value = arg
        return local_trace

    def global_trace(frame: Any, event: str, arg: Any) -> Any:
        if event == "call" and frame.f_code is code:
            if active_frame:
                result.extra_activations += 1
                return None
            active_frame.append(frame)
            return local_trace
        return None

    def on_timeout(signum: int, frame: Any) -> None:
        raise TraceTimeout(f"exceeded {timeout_seconds}s")

    use_alarm = hasattr(signal, "setitimer")
    old_handler = None
    if use_alarm:
        old_handler = signal.signal(signal.SIGALRM, on_timeout)
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    sys.settrace(global_trace)
    try:
        result.return_value = eval(call, namespace)  # noqa: S307
        result.completed = True
    except (TraceBudgetExceeded, TraceTimeout, Exception) as exc:  # noqa: BLE001
        result.error = f"{type(exc).__name__}: {exc}"
    finally:
        sys.settrace(None)
        if use_alarm:
            signal.setitimer(signal.ITIMER_REAL, 0.0)
            signal.signal(signal.SIGALRM, old_handler)
    return result
