from sensitivity_estimate import sensitivity_summary, trace_call


def test_dead_assignment_and_constant_kill():
    source = """
def f(x):
    y = x + 1
    z = 2
    y = z
    return y
"""
    trace = trace_call(source, "f(0)")
    assert trace.completed
    assert trace.return_value == 2
    summary = sensitivity_summary(trace)
    # Events (forward): y<-x, z<-2, y<-z, return y.
    # Backward liveness at boundaries: {y}, {z}, {}, {} -> counts 1,1,0,0.
    assert summary.num_events == 4
    assert summary.num_variables == 3  # x, y, z
    assert summary.sensitivity_density == (1 + 1 + 0 + 0) / (4 * 3)
    assert summary.max_live_variables == 1
    # x + 1 is dead code, so the return only depends on the constant 2.
    assert summary.return_dependency_length == 2  # z<-2 then y<-z... via z depth


def test_copy_chain_dependency_length():
    source = """
def f(x):
    a = x
    b = a
    c = b
    return c
"""
    trace = trace_call(source, "f(5)")
    summary = sensitivity_summary(trace)
    # x (depth 1) -> a (2) -> b (3) -> c (4)
    assert summary.return_dependency_length == 4
    # Every boundary keeps exactly one variable live.
    assert summary.mean_live_variables == 1.0


def test_loop_unrolls_and_accumulator_stays_live():
    source = """
def f(n):
    total = 0
    for i in range(n):
        total += i
    return total
"""
    trace = trace_call(source, "f(3)")
    assert trace.completed
    assert trace.return_value == 3
    summary = sensitivity_summary(trace)
    # total <- 0; then (for-header, total += i) per iteration; loop header
    # runs n+1 times; return.
    assert summary.num_events == 1 + 3 + 4 + 1
    # The accumulator is live from its initialization through the return.
    assert summary.max_live_variables >= 1
    assert summary.sensitivity_density > 0


def test_mutation_keeps_base_live():
    source = """
def f(xs):
    xs.append(1)
    ys = xs
    return ys
"""
    trace = trace_call(source, "f([0])")
    summary = sensitivity_summary(trace)
    # xs is mutated, not overwritten: it must stay live back to entry.
    counts_forward_order = summary.num_events
    assert counts_forward_order == 3
    assert summary.mean_live_variables == 1.0


def test_untraceable_error_is_reported():
    source = """
def f(x):
    return 1 // x
"""
    trace = trace_call(source, "f(0)")
    assert not trace.completed
    assert "ZeroDivisionError" in trace.error
