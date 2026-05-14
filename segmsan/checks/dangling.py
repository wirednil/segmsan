"""Dangling pointer detection — Rules 1, 14."""

from __future__ import annotations
from ..ast_nodes import (
    Program, Procedure, Statement, Expr, ScopeKind,
    VarDecl, ParamDecl, AssignStmt, CallStmt, AddressOfExpr, VarExpr,
    DerefExpr, IndexExpr, FieldExpr, BinOpExpr, CallExpr, DollarFuncExpr,
    IfStmt, WhileStmt, ForStmt, ScanStmt, ReturnStmt, OtherStmt,
)
from ..scope import ScopeStack
from ..report import Warning, WarningKind


def check_dangling_pointers(program: Program) -> list[Warning]:
    warnings: list[Warning] = []
    scope = ScopeStack()
    scope.push(ScopeKind.GLOBAL)

    for decl in program.globals_:
        scope.declare(decl, ScopeKind.GLOBAL)

    for proc in program.procedures:
        _check_proc(proc, scope, program.source_file, warnings)

    scope.pop()
    return warnings


def _check_proc(proc: Procedure, parent_scope: ScopeStack, source_file: str, warnings: list[Warning]):
    scope = ScopeStack()
    for level in parent_scope.levels:
        scope.levels.append(level)

    scope.push(ScopeKind.LOCAL)

    for param in proc.params:
        scope.declare_param(param, ScopeKind.LOCAL)

    for decl in proc.locals_:
        scope.declare(decl, ScopeKind.LOCAL)

    _check_body(proc.body, scope, source_file, warnings)

    for subproc in proc.subprocs:
        _check_proc(subproc, scope, source_file, warnings)

    scope.pop()


def _check_body(stmts: list[Statement], scope: ScopeStack, source_file: str, warnings: list[Warning]):
    for stmt in stmts:
        _check_stmt(stmt, scope, source_file, warnings)


def _check_stmt(stmt: Statement, scope: ScopeStack, source_file: str, warnings: list[Warning]):
    match stmt:
        case AssignStmt(target=target, source=source, loc=loc):
            _check_assignment(target, source, scope, source_file, loc, warnings)
        case CallStmt(expr=expr, loc=loc):
            _check_call_args(expr, scope, source_file, loc, warnings)
        case IfStmt(then_body=then_body, else_body=else_body):
            _check_body(then_body, scope, source_file, warnings)
            _check_body(else_body, scope, source_file, warnings)
        case WhileStmt(body=body):
            _check_body(body, scope, source_file, warnings)
        case ForStmt(body=body):
            _check_body(body, scope, source_file, warnings)
        case ScanStmt():
            pass
        case ReturnStmt():
            pass
        case _:
            pass


def _check_assignment(
    target: Expr, source: Expr, scope: ScopeStack,
    source_file: str, loc, warnings: list[Warning]
):
    if isinstance(source, AddressOfExpr):
        inner = source.inner
        addr_name = _extract_var_name(inner)
        if addr_name and scope.is_local(addr_name):
            target_name = _extract_var_name(target)
            if target_name:
                target_info = scope.lookup(target_name)
                if target_info and target_info.scope_kind == ScopeKind.GLOBAL:
                    warnings.append(Warning(
                        kind=WarningKind.DANGLING_POINTER_STORE,
                        message=f"Address of local '{addr_name}' stored in global '{target_name}'"
                                f" — pointer will dangle after scope exits",
                        loc=f"{source_file}{loc}",
                        suggestion=f"Allocate '{addr_name}' globally or use a heap-like buffer pool",
                    ))

            target_deref = _is_deref_of(target)
            if target_deref:
                deref_name = _extract_var_name(target_deref)
                if deref_name:
                    deref_info = scope.lookup(deref_name)
                    if deref_info and deref_info.scope_kind == ScopeKind.GLOBAL:
                        warnings.append(Warning(
                            kind=WarningKind.DANGLING_POINTER_STORE,
                            message=f"Address of local '{addr_name}' stored via global pointer "
                                    f"'{deref_name}' — pointer will dangle",
                            loc=f"{source_file}{loc}",
                            suggestion="Do not store local addresses through global pointers",
                        ))

            if target_name:
                target_info = scope.lookup(target_name)
                if target_info and target_info.scope_kind == ScopeKind.GLOBAL and target_info.is_pointer:
                    warnings.append(Warning(
                        kind=WarningKind.GLOBAL_PTR_FROM_LOCAL,
                        message=f"Global pointer '{target_name}' initialized with address of "
                                f"local '{addr_name}'",
                        loc=f"{source_file}{loc}",
                        suggestion=f"Ensure '{target_name}' is not used after '{addr_name}' goes out of scope",
                    ))

    if isinstance(source, BinOpExpr):
        _check_expr_for_dangling(source, scope, source_file, loc, warnings)

    if isinstance(target, VarExpr) or isinstance(target, DerefExpr):
        name = _extract_var_name(target)
        if name:
            scope.mark_assigned(name)


def _check_call_args(
    call: CallExpr, scope: ScopeStack,
    source_file: str, loc, warnings: list[Warning]
):
    for arg in call.args:
        if isinstance(arg, AddressOfExpr):
            inner_name = _extract_var_name(arg.inner)
            if inner_name and scope.is_local(inner_name):
                pass


def _check_expr_for_dangling(expr: Expr, scope: ScopeStack, source_file: str, loc, warnings: list[Warning]):
    if isinstance(expr, AddressOfExpr):
        name = _extract_var_name(expr.inner)
        if name and scope.is_local(name):
            scope.mark_address_taken(name)
    elif isinstance(expr, BinOpExpr):
        _check_expr_for_dangling(expr.left, scope, source_file, loc, warnings)
        _check_expr_for_dangling(expr.right, scope, source_file, loc, warnings)
    elif isinstance(expr, CallExpr):
        for a in expr.args:
            _check_expr_for_dangling(a, scope, source_file, loc, warnings)


def _extract_var_name(expr: Expr) -> str | None:
    if isinstance(expr, VarExpr):
        return expr.name
    if isinstance(expr, DerefExpr):
        return _extract_var_name(expr.inner)
    if isinstance(expr, IndexExpr):
        return _extract_var_name(expr.array)
    if isinstance(expr, FieldExpr):
        return _extract_var_name(expr.obj)
    return None


def _is_deref_of(expr: Expr) -> Expr | None:
    if isinstance(expr, DerefExpr):
        return expr.inner
    if isinstance(expr, AssignStmt):
        return _is_deref_of(expr.target)
    return None
