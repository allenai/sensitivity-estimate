# sensitivity-estimate

Estimate the suffix-influence sensitivity of real code by executing it.

Running a function on a concrete input resolves all control flow, so the
sequence of executed statements is a straightline assignment trace — the same
object [state-bench](https://github.com/jopetty/state-bench) computes exact
suffix influence over. This package:

1. statically summarizes each statement of a Python function by the variables
   it writes and reads ([statements.py](src/sensitivity_estimate/statements.py)),
2. traces a call with `sys.settrace` to get the unrolled statement sequence
   ([tracing.py](src/sensitivity_estimate/tracing.py)), and
3. runs a state-bench-style reverse liveness pass over the trace: a variable is
   live at a boundary if perturbing it there could change the returned value
   ([semantics.py](src/sensitivity_estimate/semantics.py)).

Per-trace metrics: `sensitivity_density` (mean fraction of trace variables live
per boundary; with a single returned output density and coverage coincide),
`mean_live_variables`, `max_live_variables`, and `return_dependency_length`
(longest def-use chain feeding the return).

## Usage

```bash
uv sync
uv run sensitivity-estimate cruxeval --output results/cruxeval-test.jsonl
```

This scores all 800 [CruxEval](https://huggingface.co/datasets/cruxeval-org/cruxeval)
functions on their provided inputs and writes one JSON record per sample.
CruxEval is the first corpus because per-problem output-prediction results are
published for many models, so sensitivity can be correlated against solve
rates without running any inference.

Library use:

```python
from sensitivity_estimate import trace_call, sensitivity_summary

trace = trace_call("def f(x):\n    y = x\n    return y", "f(3)")
print(sensitivity_summary(trace))
```

## Known approximations

- Subscript/attribute stores and method calls on a name (`a[i] = x`,
  `a.append(x)`) are treated as mutations: the base name stays live (it is both
  target and source). Argument mutation through plain calls (`g(a)`) is not
  modeled.
- Only the outermost activation of the target function is traced; recursive
  calls are opaque and counted in `extra_activations`.
- Comprehensions and nested function bodies execute in their own frames and are
  treated as opaque expressions.
- Untraced execution is bounded by a wall-clock timeout and a statement budget;
  failures are recorded per sample rather than aborting the run.
