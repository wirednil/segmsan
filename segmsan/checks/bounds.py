"""Array bounds checking — Rule 17.

Detects array indexing without explicit bounds validation.
When `arr[i]` is used without a preceding `IF i >= lo AND i <= hi`,
the index could be out of range, causing silent memory corruption.
"""

from __future__ import annotations
from ..ast_nodes import (
    Program, Procedure, IndexExpr, AssignStmt, IfStmt, WhileStmt,
    ForStmt, CallStmt, ScanStmt, ReturnStmt, Statement, Expr,
    VarExpr, BinOpExpr, DollarFuncExpr, CallExpr, DerefExpr, FieldExpr,
)
from ..report import Warning, WarningKind


def check_bounds(program: Program) -> list[Warning]:
    warnings: list[Warning] = []
    for proc in program.procedures:
        _check_proc_bounds(proc, program.source_file, warnings, program.literals)
    return warnings


def _check_proc_bounds(proc: Procedure, source_file: str, warnings: list[Warning],
                       literals: dict[str, int]):
    _check_stmts_bounds(proc.body, None, source_file, proc.name, warnings, literals)
    for subproc in proc.subprocs:
        _check_proc_bounds(subproc, source_file, warnings, literals)


def _check_stmts_bounds(stmts: list[Statement], enclosing_if: Statement | None,
                        source_file: str, proc_name: str, warnings: list[Warning],
                        literals: dict[str, int]):
    for i, stmt in enumerate(stmts):
        _check_stmt_bounds(stmt, source_file, proc_name, warnings, literals)


def _check_stmt_bounds(stmt: Statement, source_file: str, proc_name: str,
                       warnings: list[Warning], literals: dict[str, int]):
    if isinstance(stmt, AssignStmt):
        _check_expr_bounds(stmt.target, source_file, stmt.loc, proc_name, warnings, literals)
        _check_expr_bounds(stmt.source, source_file, stmt.loc, proc_name, warnings, literals)
    elif isinstance(stmt, IfStmt):
        _check_expr_bounds(stmt.condition, source_file, stmt.loc, proc_name, warnings, literals)
        for s in stmt.then_body + stmt.else_body:
            _check_stmt_bounds(s, source_file, proc_name, warnings, literals)
    elif isinstance(stmt, WhileStmt):
        _check_expr_bounds(stmt.condition, source_file, stmt.loc, proc_name, warnings, literals)
        for s in stmt.body:
            _check_stmt_bounds(s, source_file, proc_name, warnings, literals)
    elif isinstance(stmt, ForStmt):
        for s in stmt.body:
            _check_stmt_bounds(s, source_file, proc_name, warnings, literals)
    elif isinstance(stmt, CallStmt):
        for arg in stmt.expr.args:
            _check_expr_bounds(arg, source_file, stmt.loc, proc_name, warnings, literals)


def _check_expr_bounds(expr: Expr, source_file: str, loc, proc_name: str,
                       warnings: list[Warning], literals: dict[str, int]):
    if isinstance(expr, IndexExpr):
        idx = expr.index
        if isinstance(idx, VarExpr):
            if idx.name.upper() in literals:
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

    elif isinstance(expr, BinOpExpr):
        _check_expr_bounds(expr.left, source_file, loc, proc_name, warnings, literals)
        _check_expr_bounds(expr.right, source_file, loc, proc_name, warnings, literals)
    elif isinstance(expr, CallExpr):
        for a in expr.args:
            _check_expr_bounds(a, source_file, loc, proc_name, warnings, literals)
    elif isinstance(expr, DollarFuncExpr):
        for a in expr.args:
            _check_expr_bounds(a, source_file, loc, proc_name, warnings, literals)
    elif isinstance(expr, DerefExpr):
        _check_expr_bounds(expr.inner, source_file, loc, proc_name, warnings, literals)
    elif isinstance(expr, FieldExpr):
        _check_expr_bounds(expr.obj, source_file, loc, proc_name, warnings, literals)
