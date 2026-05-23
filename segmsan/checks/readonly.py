"""Read-only array modification detection — Rule 12."""

from __future__ import annotations
from ..ast_nodes import (
    Program, Procedure, AssignStmt, VarExpr, DerefExpr, IndexExpr,
    FieldExpr, Expr, Statement, IfStmt, WhileStmt, ForStmt,
    CallStmt, ScanStmt, ReturnStmt,
)
from ..report import Warning, WarningKind


def check_readonly(program: Program) -> list[Warning]:
    warnings: list[Warning] = []
    readonly_arrays = set()
    for decl in program.globals_:
        if decl.is_readonly:
            readonly_arrays.add(decl.name.upper())
    for proc in program.procedures:
        for decl in proc.locals_:
            if decl.is_readonly:
                readonly_arrays.add(decl.name.upper())

    for proc in program.procedures:
        _check_proc_readonly(proc, readonly_arrays, program.source_file, warnings)
    return warnings


def _check_proc_readonly(
    proc: Procedure, readonly: set[str], source_file: str, warnings: list[Warning]
):
    for stmt in proc.body:
        _check_stmt_readonly(stmt, readonly, source_file, proc.name, warnings)
    for subproc in proc.subprocs:
        _check_proc_readonly(subproc, readonly, source_file, warnings)


def _check_stmt_readonly(
    stmt: Statement, readonly: set[str], source_file: str, proc_name: str,
    warnings: list[Warning]
):
    if isinstance(stmt, AssignStmt):
        target_name = _extract_base_name(stmt.targets[0]) if stmt.targets else None
        if target_name and target_name.upper() in readonly:
            warnings.append(Warning(
                kind=WarningKind.READONLY_ARRAY_MODIFICATION,
                message=f"Read-only array '{target_name}' modified in procedure '{proc_name}'",
                loc=f"{source_file}{stmt.loc}",
                suggestion=f"Remove assignment to '{target_name}' — it is declared = 'P' (program file constant)",
            ))

    if isinstance(stmt, IfStmt):
        for s in stmt.then_body + stmt.else_body:
            _check_stmt_readonly(s, readonly, source_file, proc_name, warnings)
    if isinstance(stmt, WhileStmt):
        for s in stmt.body:
            _check_stmt_readonly(s, readonly, source_file, proc_name, warnings)
    if isinstance(stmt, ForStmt):
        for s in stmt.body:
            _check_stmt_readonly(s, readonly, source_file, proc_name, warnings)


def _extract_base_name(expr: Expr) -> str | None:
    if isinstance(expr, VarExpr):
        return expr.name
    if isinstance(expr, DerefExpr):
        return _extract_base_name(expr.inner)
    if isinstance(expr, IndexExpr):
        return _extract_base_name(expr.array)
    if isinstance(expr, FieldExpr):
        return _extract_base_name(expr.obj)
    return None
