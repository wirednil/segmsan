"""Array bounds checking — Rule 17.

Detects array indexing without explicit bounds validation.
When `arr[i]` is used without a preceding `IF i >= lo AND i <= hi`,
the index could be out of range, causing silent memory corruption.

Suppressions:
- Literal / DEFINE constant indices (known safe)
- Indices guarded by IF comparison (IF i < max THEN arr[i])
- FOR loop variables within their loop body (bounded by FROM/TO)
"""

from __future__ import annotations
from ..ast_nodes import (
    Program, Procedure, IndexExpr, AssignStmt, IfStmt, WhileStmt,
    ForStmt, CallStmt, ScanStmt, ReturnStmt, Statement, Expr,
    VarExpr, BinOpExpr, DollarFuncExpr, CallExpr, DerefExpr, FieldExpr,
    LiteralExpr,
)
from ..report import Warning, WarningKind


def check_bounds(program: Program) -> list[Warning]:
    warnings: list[Warning] = []
    for proc in program.procedures:
        _check_proc_bounds(proc, program.source_file, warnings, program.literals)
    return warnings


def _check_proc_bounds(proc: Procedure, source_file: str, warnings: list[Warning],
                       literals: dict[str, int]):
    _check_stmts_bounds(proc.body, frozenset(), source_file, proc.name, warnings, literals)
    for subproc in proc.subprocs:
        _check_proc_bounds(subproc, source_file, warnings, literals)


def _extract_comparison_vars(expr: Expr) -> set[str]:
    """Extract variable names that appear in comparison sub-expressions.

    Patterns like `IF i >= lo AND i <= hi` extract {I} as guarded.
    """
    guarded: set[str] = set()
    if isinstance(expr, BinOpExpr):
        if expr.op in ('>=', '>', '<=', '<', '=<>'):
            guarded |= _collect_var_names(expr)
        guarded |= _extract_comparison_vars(expr.left)
        guarded |= _extract_comparison_vars(expr.right)
    return guarded


def _collect_var_names(expr: Expr) -> set[str]:
    names: set[str] = set()
    if isinstance(expr, VarExpr):
        names.add(expr.name.upper())
    elif isinstance(expr, BinOpExpr):
        names |= _collect_var_names(expr.left)
        names |= _collect_var_names(expr.right)
    elif isinstance(expr, DerefExpr):
        names |= _collect_var_names(expr.inner)
    elif isinstance(expr, FieldExpr):
        names |= _collect_var_names(expr.obj)
    elif isinstance(expr, CallExpr):
        for a in expr.args:
            names |= _collect_var_names(a)
    elif isinstance(expr, DollarFuncExpr):
        for a in expr.args:
            names |= _collect_var_names(a)
    return names


def _check_stmts_bounds(stmts: list[Statement], guarded: frozenset,
                        source_file: str, proc_name: str, warnings: list[Warning],
                        literals: dict[str, int]):
    for stmt in stmts:
        _check_stmt_bounds(stmt, guarded, source_file, proc_name, warnings, literals)


def _check_stmt_bounds(stmt: Statement, guarded: frozenset, source_file: str,
                       proc_name: str, warnings: list[Warning], literals: dict[str, int]):
    if isinstance(stmt, AssignStmt):
        for t in stmt.targets:
            _check_expr_bounds(t, guarded, source_file, stmt.loc, proc_name, warnings, literals)
        _check_expr_bounds(stmt.source, guarded, source_file, stmt.loc, proc_name, warnings, literals)
    elif isinstance(stmt, IfStmt):
        _check_expr_bounds(stmt.condition, guarded, source_file, stmt.loc, proc_name, warnings, literals)
        new_guards = guarded | _extract_comparison_vars(stmt.condition)
        _check_stmts_bounds(stmt.then_body, frozenset(new_guards), source_file, proc_name, warnings, literals)
        _check_stmts_bounds(stmt.else_body, guarded, source_file, proc_name, warnings, literals)
    elif isinstance(stmt, WhileStmt):
        _check_expr_bounds(stmt.condition, guarded, source_file, stmt.loc, proc_name, warnings, literals)
        new_guards = guarded | _extract_comparison_vars(stmt.condition)
        _check_stmts_bounds(stmt.body, frozenset(new_guards), source_file, proc_name, warnings, literals)
    elif isinstance(stmt, ForStmt):
        _check_stmts_bounds(stmt.body, guarded, source_file, proc_name, warnings, literals)
    elif isinstance(stmt, CallStmt):
        for arg in stmt.args:
            _check_expr_bounds(arg, guarded, source_file, stmt.loc, proc_name, warnings, literals)


def _check_expr_bounds(expr: Expr, guarded: frozenset, source_file: str, loc,
                       proc_name: str, warnings: list[Warning], literals: dict[str, int]):
    if isinstance(expr, IndexExpr):
        idx = expr.index
        if isinstance(idx, LiteralExpr):
            pass
        elif isinstance(idx, VarExpr):
            name_upper = idx.name.upper()
            if name_upper in literals:
                pass
            elif name_upper in guarded:
                pass
            else:
                warnings.append(Warning(
                    kind=WarningKind.INDEX_WITHOUT_BOUNDS_CHECK,
                    message=f"Array indexed by '{idx.name}' without explicit bounds check "
                            f"in {proc_name}",
                    loc=f"{source_file}{loc}",
                    suggestion=f"Validate '{idx.name}' before indexing (e.g., "
                               f"IF {idx.name} >= lo AND {idx.name} <= hi)",
                ))
        else:
            for sub_name in _collect_var_names(idx):
                if sub_name not in literals and sub_name not in guarded:
                    warnings.append(Warning(
                        kind=WarningKind.INDEX_WITHOUT_BOUNDS_CHECK,
                        message=f"Array indexed by expression involving '{sub_name}' "
                                f"without explicit bounds check in {proc_name}",
                        loc=f"{source_file}{loc}",
                        suggestion=f"Validate '{sub_name}' before indexing",
                    ))

    elif isinstance(expr, BinOpExpr):
        _check_expr_bounds(expr.left, guarded, source_file, loc, proc_name, warnings, literals)
        _check_expr_bounds(expr.right, guarded, source_file, loc, proc_name, warnings, literals)
    elif isinstance(expr, CallExpr):
        for a in expr.args:
            _check_expr_bounds(a, guarded, source_file, loc, proc_name, warnings, literals)
    elif isinstance(expr, DollarFuncExpr):
        for a in expr.args:
            _check_expr_bounds(a, guarded, source_file, loc, proc_name, warnings, literals)
    elif isinstance(expr, DerefExpr):
        _check_expr_bounds(expr.inner, guarded, source_file, loc, proc_name, warnings, literals)
    elif isinstance(expr, FieldExpr):
        _check_expr_bounds(expr.obj, guarded, source_file, loc, proc_name, warnings, literals)
