"""EXT pointer detection — Rule 8.

On TNS/R and TNS/X, addresses above 32K words (%100000) require an
extended (EXT) pointer. Direct pointers are 16-bit and cannot reach
upper memory. Detect when a variable/array may hold addresses >= 32K
without being declared .EXT.
"""

from __future__ import annotations
from ..ast_nodes import (
    Program, Procedure, AssignStmt, AddressOfExpr, VarExpr, VarDecl,
    DerefExpr, IndexExpr, FieldExpr, Expr, Statement,
    IfStmt, WhileStmt, ForStmt, CallStmt, ScopeKind, TalType,
)
from ..report import Warning, WarningKind
from ..scope import ScopeStack


def check_ext_needed(program: Program) -> list[Warning]:
    warnings: list[Warning] = []
    scope = ScopeStack()
    scope.push(ScopeKind.GLOBAL)

    for decl in program.globals_:
        scope.declare(decl, ScopeKind.GLOBAL)

    for proc in program.procedures:
        _check_proc_ext(proc, scope, program.source_file, warnings)

    scope.pop()
    return warnings


def _check_proc_ext(proc: Procedure, parent_scope: ScopeStack,
                    source_file: str, warnings: list[Warning]):
    proc_scope = ScopeStack()
    for level in parent_scope.levels:
        proc_scope.levels.append(level)
    proc_scope.push(ScopeKind.LOCAL)

    for param in proc.params:
        proc_scope.declare_param(param, ScopeKind.LOCAL)
    for decl in proc.locals_:
        proc_scope.declare(decl, ScopeKind.LOCAL)

    _check_stmts_ext(proc.body, proc_scope, source_file, warnings)

    for subproc in proc.subprocs:
        _check_subproc_ext(subproc, proc_scope, source_file, warnings)

    proc_scope.pop()


def _check_subproc_ext(subproc: Procedure, parent_scope: ScopeStack,
                       source_file: str, warnings: list[Warning]):
    sub_scope = ScopeStack()
    for level in parent_scope.levels:
        sub_scope.levels.append(level)
    sub_scope.push(ScopeKind.SUBLOCAL)

    for param in subproc.params:
        sub_scope.declare_param(param, ScopeKind.SUBLOCAL)
    for decl in subproc.locals_:
        sub_scope.declare(decl, ScopeKind.SUBLOCAL)

    _check_stmts_ext(subproc.body, sub_scope, source_file, warnings)

    for nested in subproc.subprocs:
        _check_subproc_ext(nested, sub_scope, source_file, warnings)

    sub_scope.pop()


def _check_stmts_ext(stmts: list[Statement], scope: ScopeStack,
                     source_file: str, warnings: list[Warning]):
    for stmt in stmts:
        _check_stmt_ext(stmt, scope, source_file, warnings)


def _check_stmt_ext(stmt: Statement, scope: ScopeStack,
                    source_file: str, warnings: list[Warning]):
    if isinstance(stmt, AssignStmt):
        if isinstance(stmt.source, AddressOfExpr):
            inner_name = _extract_name(stmt.source.inner)
            target_name = _extract_name(stmt.target)
            if inner_name and target_name:
                inner_info = scope.lookup(inner_name)
                target_info = scope.lookup(target_name)
                if inner_info and target_info:
                    inner_decl = inner_info.decl
                    if hasattr(inner_decl, 'word_size') and hasattr(inner_decl, 'is_indirect'):
                        if not inner_decl.is_indirect and inner_decl.array_bounds:
                            total = inner_decl.word_size()
                            if total > 32767:
                                if hasattr(target_info.decl, 'is_extended'):
                                    if not target_info.decl.is_extended:
                                        warnings.append(Warning(
                                            kind=WarningKind.EXTENDED_POINTER_NEEDED,
                                            message=f"Address of large array '{inner_name}' "
                                                    f"(>{total}w, crosses 32K) stored in "
                                                    f"non-EXT pointer '{target_name}'",
                                            loc=f"{source_file}{stmt.loc}",
                                            suggestion=f"Declare '{target_name}' as .EXT to "
                                                       f"hold addresses above 32K words",
                                        ))

    elif isinstance(stmt, IfStmt):
        for s in stmt.then_body + stmt.else_body:
            _check_stmt_ext(s, scope, source_file, warnings)
    elif isinstance(stmt, WhileStmt):
        for s in stmt.body:
            _check_stmt_ext(s, scope, source_file, warnings)
    elif isinstance(stmt, ForStmt):
        for s in stmt.body:
            _check_stmt_ext(s, scope, source_file, warnings)


def _extract_name(expr: Expr) -> str | None:
    if isinstance(expr, VarExpr):
        return expr.name
    if isinstance(expr, DerefExpr):
        return _extract_name(expr.inner)
    if isinstance(expr, IndexExpr):
        return _extract_name(expr.array)
    if isinstance(expr, FieldExpr):
        return _extract_name(expr.obj)
    return None
