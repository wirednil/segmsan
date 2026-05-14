"""FIXED precision loss detection — Rule 9.

FIXED(n) / FIXED(n) yields FIXED(0) — all decimal places vanish.
Must use $SCALE(dividend, n) before dividing to preserve precision.
"""

from __future__ import annotations
from ..ast_nodes import (
    Program, Procedure, AssignStmt, BinOpExpr, DollarFuncExpr,
    VarExpr, IfStmt, WhileStmt, ForStmt, CallStmt, ScanStmt,
    ReturnStmt, Statement, Expr, DerefExpr, IndexExpr, FieldExpr,
    CallExpr, TalType,
)
from ..report import Warning, WarningKind


def check_fixed_precision(program: Program) -> list[Warning]:
    warnings: list[Warning] = []
    type_map = _build_type_map(program)

    for proc in program.procedures:
        _check_proc_fixed(proc, type_map, program.source_file, warnings)
    return warnings


def _build_type_map(program: Program) -> dict[str, int]:
    type_map: dict[str, int] = {}
    for decl in program.globals_:
        if decl.tal_type == TalType.FIXED:
            type_map[decl.name.upper()] = decl.fpoint
    for proc in program.procedures:
        _collect_proc_types(proc, type_map)
    return type_map


def _collect_proc_types(proc: Procedure, type_map: dict[str, int]):
    for param in proc.params:
        if param.tal_type == TalType.FIXED:
            type_map[param.name.upper()] = param.fpoint
    for decl in proc.locals_:
        if decl.tal_type == TalType.FIXED:
            type_map[decl.name.upper()] = decl.fpoint
    for subproc in proc.subprocs:
        _collect_proc_types(subproc, type_map)


def _check_proc_fixed(proc: Procedure, type_map: dict[str, int],
                      source_file: str, warnings: list[Warning]):
    for stmt in proc.body:
        _check_stmt_fixed(stmt, type_map, source_file, warnings)
    for subproc in proc.subprocs:
        _check_proc_fixed(subproc, type_map, source_file, warnings)


def _check_stmt_fixed(stmt: Statement, type_map: dict[str, int],
                      source_file: str, warnings: list[Warning]):
    if isinstance(stmt, AssignStmt):
        _check_expr_fixed(stmt.source, type_map, source_file, stmt.loc, warnings)
    elif isinstance(stmt, IfStmt):
        _check_expr_fixed(stmt.condition, type_map, source_file, stmt.loc, warnings)
        for s in stmt.then_body + stmt.else_body:
            _check_stmt_fixed(s, type_map, source_file, warnings)
    elif isinstance(stmt, WhileStmt):
        _check_expr_fixed(stmt.condition, type_map, source_file, stmt.loc, warnings)
        for s in stmt.body:
            _check_stmt_fixed(s, type_map, source_file, warnings)
    elif isinstance(stmt, ForStmt):
        for s in stmt.body:
            _check_stmt_fixed(s, type_map, source_file, warnings)


def _check_expr_fixed(expr: Expr, type_map: dict[str, int],
                      source_file: str, loc, warnings: list[Warning]):
    if isinstance(expr, BinOpExpr):
        if expr.op == "/":
            left_fp = _get_fpoint(expr.left, type_map)
            right_fp = _get_fpoint(expr.right, type_map)
            if left_fp > 0 and right_fp > 0 and left_fp == right_fp:
                if not _is_scaled(expr.left):
                    warnings.append(Warning(
                        kind=WarningKind.FIXED_DIV_PRECISION_LOSS,
                        message=f"FIXED({left_fp}) / FIXED({right_fp}) yields FIXED(0) "
                                f"— all decimal places lost",
                        loc=f"{source_file}{loc}",
                        suggestion=f"Use $SCALE(dividend, {right_fp}) before dividing to "
                                   f"preserve decimal precision",
                    ))

        _check_expr_fixed(expr.left, type_map, source_file, loc, warnings)
        _check_expr_fixed(expr.right, type_map, source_file, loc, warnings)

    elif isinstance(expr, CallExpr):
        for a in expr.args:
            _check_expr_fixed(a, type_map, source_file, loc, warnings)
    elif isinstance(expr, DollarFuncExpr):
        for a in expr.args:
            _check_expr_fixed(a, type_map, source_file, loc, warnings)


def _get_fpoint(expr: Expr, type_map: dict[str, int]) -> int:
    if isinstance(expr, VarExpr):
        return type_map.get(expr.name.upper(), 0)
    if isinstance(expr, BinOpExpr):
        if expr.op in ("+", "-"):
            l = _get_fpoint(expr.left, type_map)
            r = _get_fpoint(expr.right, type_map)
            return max(l, r)
        if expr.op == "*":
            l = _get_fpoint(expr.left, type_map)
            r = _get_fpoint(expr.right, type_map)
            return l + r
    if isinstance(expr, DollarFuncExpr):
        if expr.name.upper() == "SCALE":
            if expr.args and len(expr.args) >= 2:
                base_fp = _get_fpoint(expr.args[0], type_map)
                return base_fp
    return 0


def _is_scaled(expr: Expr) -> bool:
    if isinstance(expr, DollarFuncExpr) and expr.name.upper() == "SCALE":
        return True
    return False
