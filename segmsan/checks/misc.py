"""Miscellaneous checks — Rules 6, 15, 20."""

from __future__ import annotations
from ..ast_nodes import (
    Program, Procedure, IfStmt, WhileStmt, ForStmt, Statement,
    DollarFuncExpr, TalType,
)
from ..report import Warning, WarningKind


def check_misc(program: Program) -> list[Warning]:
    warnings: list[Warning] = []
    warnings.extend(_check_debug_directives(program))
    warnings.extend(check_string_params(program))
    warnings.extend(check_comp_as_comparison(program))
    return warnings


def _check_debug_directives(program: Program) -> list[Warning]:
    has_inspect = False
    has_symbols = False
    has_procdebug = False
    has_stmtdebug = False

    for d in program.directives:
        upper = d.upper()
        if "INSPECT" in upper:
            has_inspect = True
        if "SYMBOLS" in upper:
            has_symbols = True
        if "PROCDEBUG" in upper:
            has_procdebug = True
        if "STMTDEBUG" in upper:
            has_stmtdebug = True

    if not has_inspect and not has_symbols and not has_procdebug:
        return [Warning(
            kind=WarningKind.MISSING_DEBUG_DIRECTIVE,
            message="Program has no debug directives (?INSPECT, ?SYMBOLS, ?PROCDEBUG, ?STMTDEBUG)",
            loc=program.source_file,
            suggestion="Add ?INSPECT, SYMBOLS for production or ?PROCDEBUG for development",
        )]
    return []


def check_string_params(program: Program) -> list[Warning]:
    warnings: list[Warning] = []
    for proc in program.procedures:
        _check_proc_string_params(proc, program.source_file, warnings)
    return warnings


def _check_proc_string_params(proc: Procedure, source_file: str, warnings: list[Warning]):
    for param in proc.params:
        if param.tal_type == TalType.STRING and not param.is_reference:
            warnings.append(Warning(
                kind=WarningKind.STRING_VALUE_PARAM_MISMATCH,
                message=f"Parameter '{param.name}' in '{proc.name}' is STRING by value — "
                        "only the low byte is passed (calling convention mismatch)",
                loc=f"{source_file}{param.loc}",
                suggestion=f"Declare as STRING .{param.name} (by reference) "
                           f"or STRING .EXT {param.name}",
            ))
    for subproc in proc.subprocs:
        _check_proc_string_params(subproc, source_file, warnings)


def check_comp_as_comparison(program: Program) -> list[Warning]:
    warnings: list[Warning] = []
    for proc in program.procedures:
        _check_proc_comp(proc, program.source_file, warnings)
    return warnings


def _check_proc_comp(proc: Procedure, source_file: str, warnings: list[Warning]):
    _check_stmts_comp(proc.body, source_file, proc.name, warnings)
    for subproc in proc.subprocs:
        _check_proc_comp(subproc, source_file, warnings)


def _check_stmts_comp(stmts: list[Statement], source_file: str,
                      proc_name: str, warnings: list[Warning]):
    for stmt in stmts:
        if isinstance(stmt, IfStmt):
            if isinstance(stmt.condition, DollarFuncExpr):
                if stmt.condition.name.upper() in ("COMP", "$COMP"):
                    warnings.append(Warning(
                        kind=WarningKind.COMP_USED_AS_COMPARISON,
                        message=f"$COMP used as boolean in IF in '{proc_name}' — "
                                "$COMP inverts bits, does not compare",
                        loc=f"{source_file}{stmt.loc}",
                        suggestion="Use $COMP(x) <relop> 0 or compare the result explicitly",
                    ))
            _check_stmts_comp(stmt.then_body + stmt.else_body, source_file, proc_name, warnings)
        elif isinstance(stmt, (WhileStmt, ForStmt)):
            _check_stmts_comp(stmt.body, source_file, proc_name, warnings)
