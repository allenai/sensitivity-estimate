"""Static per-statement dataflow facts for a Python function.

Each statement is summarized by the variable names it writes (``targets``) and
the names it reads (``sources``). Compound statements (``for``, ``while``,
``if``, ``with``, ...) contribute only their header expressions; their bodies
are separate statements with their own line numbers, so the dynamic trace
resolves control flow.

Approximations (documented, deliberately conservative for a v0):

- A store through a subscript or attribute (``a[i] = x``, ``a.b = x``) and a
  method call on a name (``a.append(x)``) are treated as *mutations* of the
  base name: the base appears in both ``targets`` and ``sources``, so the
  reverse liveness pass keeps its history alive instead of killing it.
- Mutation of arguments through plain calls (``g(a)`` where ``g`` mutates
  ``a``) is not modeled.
- Nested function/class definitions are opaque: the definition binds its name
  and reads its free variables' names.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class StatementInfo:
    line: int
    targets: frozenset[str]
    sources: frozenset[str]
    is_return: bool = False


def _load_names(node: ast.AST | None) -> set[str]:
    if node is None:
        return set()
    return {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
    }


def _store_names(node: ast.AST | None) -> tuple[set[str], set[str]]:
    """Return (targets, mutated) names bound by an assignment target.

    ``mutated`` names are bases of subscript/attribute stores; they must also
    be treated as sources because the store only partially overwrites them.
    """
    targets: set[str] = set()
    mutated: set[str] = set()
    if node is None:
        return targets, mutated
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
            targets.add(child.id)
        elif isinstance(child, (ast.Subscript, ast.Attribute)) and isinstance(
            child.ctx, (ast.Store, ast.Del)
        ):
            base = child.value
            while isinstance(base, (ast.Subscript, ast.Attribute)):
                base = base.value
            if isinstance(base, ast.Name):
                targets.add(base.id)
                mutated.add(base.id)
    return targets, mutated


def _mutated_call_bases(node: ast.AST) -> set[str]:
    """Names whose methods are called: ``a.append(x)`` mutates ``a`` (maybe)."""
    bases: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            base = child.func.value
            while isinstance(base, (ast.Subscript, ast.Attribute)):
                base = base.value
            if isinstance(base, ast.Name):
                bases.add(base.id)
    return bases


def _header_info(stmt: ast.stmt) -> StatementInfo | None:
    targets: set[str] = set()
    sources: set[str] = set()
    is_return = False

    if isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            stored, mutated = _store_names(target)
            targets |= stored
            sources |= mutated
        sources |= _load_names(stmt.value)
        sources |= _mutated_call_bases(stmt.value)
    elif isinstance(stmt, ast.AugAssign):
        stored, _ = _store_names(stmt.target)
        targets |= stored
        sources |= stored  # augmented assignment reads its target
        sources |= _load_names(stmt.value)
    elif isinstance(stmt, ast.AnnAssign):
        stored, mutated = _store_names(stmt.target)
        targets |= stored
        sources |= mutated | _load_names(stmt.value)
    elif isinstance(stmt, (ast.For, ast.AsyncFor)):
        stored, mutated = _store_names(stmt.target)
        targets |= stored
        sources |= mutated | _load_names(stmt.iter)
    elif isinstance(stmt, (ast.While, ast.If)):
        sources |= _load_names(stmt.test)
    elif isinstance(stmt, ast.Return):
        sources |= _load_names(stmt.value)
        is_return = True
    elif isinstance(stmt, ast.Expr):
        sources |= _load_names(stmt.value)
        mutated = _mutated_call_bases(stmt.value)
        targets |= mutated
        sources |= mutated
    elif isinstance(stmt, (ast.With, ast.AsyncWith)):
        for item in stmt.items:
            sources |= _load_names(item.context_expr)
            stored, mutated = _store_names(item.optional_vars)
            targets |= stored
            sources |= mutated
    elif isinstance(stmt, ast.Delete):
        for target in stmt.targets:
            stored, mutated = _store_names(target)
            targets |= stored
            sources |= mutated
    elif isinstance(stmt, (ast.Assert, ast.Raise)):
        for field in ast.iter_child_nodes(stmt):
            sources |= _load_names(field)
    elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        targets.add(stmt.name)
        sources |= _load_names(stmt)
    elif isinstance(stmt, ast.Match):
        sources |= _load_names(stmt.subject)
    elif isinstance(stmt, (ast.Pass, ast.Break, ast.Continue, ast.Global, ast.Nonlocal)):
        pass
    elif isinstance(stmt, (ast.Try, ast.TryStar)):
        pass
    else:
        sources |= _load_names(stmt)

    if not targets and not sources and not is_return:
        return None
    return StatementInfo(
        line=stmt.lineno,
        targets=frozenset(targets),
        sources=frozenset(sources),
        is_return=is_return,
    )


def statement_table(func: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[int, StatementInfo]:
    """Map line number -> dataflow facts for every statement in ``func``.

    Statements sharing a line are merged. Nested function bodies are skipped;
    the definition itself is summarized by :func:`_header_info`.
    """
    table: dict[int, StatementInfo] = {}

    def visit(stmts: list[ast.stmt]) -> None:
        for stmt in stmts:
            info = _header_info(stmt)
            if info is not None:
                existing = table.get(info.line)
                if existing is not None:
                    info = StatementInfo(
                        line=info.line,
                        targets=existing.targets | info.targets,
                        sources=existing.sources | info.sources,
                        is_return=existing.is_return or info.is_return,
                    )
                table[info.line] = info
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for field in ("body", "orelse", "finalbody"):
                visit(getattr(stmt, field, []) or [])
            for handler in getattr(stmt, "handlers", []) or []:
                if handler.name:
                    table[handler.lineno] = StatementInfo(
                        line=handler.lineno,
                        targets=frozenset({handler.name}),
                        sources=frozenset(),
                    )
                visit(handler.body)
            for case in getattr(stmt, "cases", []) or []:
                visit(case.body)

    visit(func.body)
    return table


def parameter_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> frozenset[str]:
    args = func.args
    names = [
        arg.arg
        for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs)
    ]
    if args.vararg:
        names.append(args.vararg.arg)
    if args.kwarg:
        names.append(args.kwarg.arg)
    return frozenset(names)
