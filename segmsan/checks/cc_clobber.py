"""Condition code clobber detection — Rule 18.

In TAL, many operations set the hardware condition code (CC), but any
intervening operation between the CC-setting operation and the CC test
will clobber it. Pattern: <operation>; <other_op>; IF < THEN — the CC
test reads the result of <other_op>, not <operation>.
"""

from __future__ import annotations
from ..ast_nodes import (
    Program, Procedure, AssignStmt, CallStmt, IfStmt, WhileStmt,
    ForStmt, ScanStmt, ReturnStmt, Statement, Expr,
    BinOpExpr, DollarFuncExpr, CallExpr, VarExpr, LiteralExpr,
)
from ..report import Warning, WarningKind


def check_cc_clobber(program: Program) -> list[Warning]:
    warnings: list[Warning] = []
    for proc in program.procedures:
        _check_proc_cc(proc, program.source_file, warnings)
    return warnings


def _check_proc_cc(proc: Procedure, source_file: str, warnings: list[Warning]):
    _check_stmts_cc(proc.body, source_file, proc.name, warnings)
    for subproc in proc.subprocs:
        _check_proc_cc(subproc, source_file, warnings)


def _check_stmts_cc(stmts: list[Statement], source_file: str,
                    proc_name: str, warnings: list[Warning]):
    for i, stmt in enumerate(stmts):
        if isinstance(stmt, IfStmt):
            if _is_cc_test(stmt.condition):
                if i > 0:
                    prev = stmts[i - 1]
                    if isinstance(prev, AssignStmt):
                        if _is_cc_setter(prev.source):
                            pass
                        elif isinstance(prev, CallStmt):
                            pass
                        else:
                            if not _is_cc_setter_stmt(prev):
                                continue
                    elif isinstance(prev, CallStmt):
                        pass
                    else:
                        continue

                    if i > 1:
                        prev_prev = stmts[i - 2]
                        if _is_cc_setter_stmt(prev_prev) and not _is_cc_setter_stmt(prev):
                            intervening = _describe_stmt(prev)
                            warnings.append(Warning(
                                kind=WarningKind.CONDITION_CODE_CLOBBER,
                                message=f"Condition code test after intervening '{intervening}' "
                                        f"in {proc_name} — CC may have been clobbered",
                                loc=f"{source_file}{stmt.loc}",
                                suggestion="Move the CC test immediately after the operation "
                                           "that sets it, or re-test",
                            ))

        _check_stmt_cc(stmt, source_file, proc_name, warnings)


def _check_stmt_cc(stmt: Statement, source_file: str,
                   proc_name: str, warnings: list[Warning]):
    if isinstance(stmt, IfStmt):
        for s in stmt.then_body + stmt.else_body:
            _check_stmts_cc_nested(s, source_file, proc_name, warnings)
    elif isinstance(stmt, WhileStmt):
        _check_stmts_cc_nested(stmt.body, source_file, proc_name, warnings)
    elif isinstance(stmt, ForStmt):
        for s in stmt.body:
            _check_stmts_cc_nested(s, source_file, proc_name, warnings)


def _check_stmts_cc_nested(stmt: Statement, source_file: str,
                           proc_name: str, warnings: list[Warning]):
    if isinstance(stmt, IfStmt):
        for s in stmt.then_body + stmt.else_body:
            _check_stmts_cc_nested(s, source_file, proc_name, warnings)
    elif isinstance(stmt, WhileStmt):
        for s in stmt.body:
            _check_stmts_cc_nested(s, source_file, proc_name, warnings)


def _is_cc_test(expr: Expr) -> bool:
    if isinstance(expr, BinOpExpr):
        if expr.op in ("<", ">", "<=", ">=", "=", "<>"):
            left = expr.left
            if isinstance(left, VarExpr):
                pass
            return True
    return False


def _is_cc_setter(expr: Expr) -> bool:
    if isinstance(expr, CallExpr):
        return True
    if isinstance(expr, DollarFuncExpr):
        return True
    if isinstance(expr, BinOpExpr):
        if expr.op in ("+", "-", "*", "/", "LAND", "LOR", "XOR"):
            return True
        return False
    return False


def _is_cc_setter_stmt(stmt: Statement) -> bool:
    if isinstance(stmt, AssignStmt):
        return _is_cc_setter(stmt.source)
    if isinstance(stmt, CallStmt):
        return True
    if isinstance(stmt, ScanStmt):
        return True
    return False


def _describe_stmt(stmt: Statement) -> str:
    if isinstance(stmt, AssignStmt):
        t = _describe_expr(stmt.targets[0]) if stmt.targets else "?"
        s = _describe_expr(stmt.source)
        return f"{t} := {s}"
    if isinstance(stmt, CallStmt):
        return f"{stmt.name}()"
    return "statement"


def _describe_expr(expr: Expr) -> str:
    if isinstance(expr, VarExpr):
        return expr.name
    if isinstance(expr, CallExpr):
        return f"{expr.name}()"
    if isinstance(expr, DollarFuncExpr):
        return f"${expr.name}()"
    if isinstance(expr, LiteralExpr):
        return str(expr.value)
    return "expr"
