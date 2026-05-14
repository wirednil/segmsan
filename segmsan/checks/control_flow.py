"""Control flow checks — Rules 10 (recursion without LARGESTACK), 11 (SCAN without $CARRY)."""

from __future__ import annotations
from ..ast_nodes import (
    Program, Procedure, ScanStmt, CallStmt, AssignStmt,
    CallExpr, DollarFuncExpr, VarExpr, BinOpExpr,
    IfStmt, WhileStmt, ForStmt, ReturnStmt, Statement,
)
from ..report import Warning, WarningKind


def check_control_flow(program: Program) -> list[Warning]:
    warnings: list[Warning] = []
    warnings.extend(_check_recursion(program))
    warnings.extend(_check_scan_carry(program))
    return warnings


def _check_recursion(program: Program) -> list[Warning]:
    warnings: list[Warning] = []
    _check_proc_recursion(program.procedures, program.source_file, warnings)
    return warnings


def _check_proc_recursion(procs: list[Procedure], source_file: str, warnings: list[Warning]):
    for proc in procs:
        if proc.calls_self and not proc.has_largestack:
            warnings.append(Warning(
                kind=WarningKind.RECURSION_WITHOUT_LARGESTACK,
                message=f"Procedure '{proc.name}' calls itself recursively "
                        f"without ?LARGESTACK directive",
                loc=f"{source_file}{proc.loc}",
                suggestion=f"Add '?LARGESTACK' directive before the PROC declaration for '{proc.name}'",
            ))
        _check_proc_recursion(proc.subprocs, source_file, warnings)


def _check_scan_carry(program: Program) -> list[Warning]:
    warnings: list[Warning] = []
    for proc in program.procedures:
        _check_proc_scan(proc, program.source_file, warnings)
    return warnings


def _check_proc_scan(proc: Procedure, source_file: str, warnings: list[Warning]):
    stmts = proc.body
    for i, stmt in enumerate(stmts):
        if isinstance(stmt, ScanStmt):
            has_carry_check = False
            for j in range(i + 1, min(i + 5, len(stmts))):
                if _references_carry(stmts[j]):
                    has_carry_check = True
                    break
            if not has_carry_check:
                warnings.append(Warning(
                    kind=WarningKind.SCAN_WITHOUT_CARRY_CHECK,
                    message=f"{stmt.direction} without subsequent $CARRY test "
                            f"in procedure '{proc.name}'",
                    loc=f"{source_file}{stmt.loc}",
                    suggestion="Test $CARRY after SCAN to handle the case where the search fails",
                ))

    for subproc in proc.subprocs:
        _check_proc_scan(subproc, source_file, warnings)


def _references_carry(stmt: Statement) -> bool:
    if isinstance(stmt, IfStmt):
        return _expr_references_carry(stmt.condition)
    if isinstance(stmt, AssignStmt):
        return _expr_references_carry(stmt.source) or _expr_references_carry(stmt.target)
    return False


def _expr_references_carry(expr) -> bool:
    if expr is None:
        return False
    if isinstance(expr, DollarFuncExpr):
        return expr.name.upper() == "CARRY"
    if isinstance(expr, BinOpExpr):
        return _expr_references_carry(expr.left) or _expr_references_carry(expr.right)
    if isinstance(expr, CallExpr):
        return any(_expr_references_carry(a) for a in expr.args)
    return False
