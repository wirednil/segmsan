"""EQUIVALENCE pitfall detection — Rules 5, 16."""

from __future__ import annotations
from ..ast_nodes import Program, Procedure, VarDecl, TalType
from ..report import Warning, WarningKind


def check_equivalence(program: Program) -> list[Warning]:
    warnings: list[Warning] = []
    global_vars: dict[str, VarDecl] = {}
    for decl in program.globals_:
        global_vars[decl.name.upper()] = decl

    for decl in program.globals_:
        if decl.is_equivalence and decl.equivalence_target:
            _check_equivalence_decl(decl, program.source_file, "global", warnings, global_vars)
    for proc in program.procedures:
        _check_proc_equivalence(proc, program.source_file, warnings, global_vars)
    return warnings


def _build_scope_vars(proc: Procedure, global_vars: dict[str, VarDecl]) -> dict[str, VarDecl]:
    scope = dict(global_vars)
    for decl in proc.locals_:
        scope[decl.name.upper()] = decl
    return scope


def _check_proc_equivalence(proc: Procedure, source_file: str, warnings: list[Warning],
                            global_vars: dict[str, VarDecl]):
    scope = _build_scope_vars(proc, global_vars)
    for decl in proc.locals_:
        if decl.is_equivalence and decl.equivalence_target:
            _check_equivalence_decl(decl, source_file, proc.name, warnings, scope)
    for subproc in proc.subprocs:
        sub_scope = dict(scope)
        for decl in subproc.locals_:
            sub_scope[decl.name.upper()] = decl
        for decl in subproc.locals_:
            if decl.is_equivalence and decl.equivalence_target:
                _check_equivalence_decl(decl, source_file, subproc.name, warnings, sub_scope)


def _check_equivalence_decl(decl: VarDecl, source_file: str, context: str,
                            warnings: list[Warning], scope_vars: dict[str, VarDecl]):
    target = scope_vars.get(decl.equivalence_target.upper()) if decl.equivalence_target else None
    if not target:
        return

    if target.is_indirect and not decl.is_indirect:
        warnings.append(Warning(
            kind=WarningKind.EQUIVALENCE_TO_IMPLICIT_PTR,
            message=f"Variable '{decl.name}' equivalenced to indirect '{decl.equivalence_target}' "
                    f"overlays the pointer, not the data",
            loc=f"{source_file}{decl.loc}",
            suggestion=f"Declare '{decl.name}' as indirect (dot) to overlay the array data",
        ))
        return

    decl_is_string = decl.tal_type == TalType.STRING
    target_is_string = target.tal_type == TalType.STRING
    if decl_is_string != target_is_string and not decl.is_indirect and not target.is_indirect:
        warnings.append(Warning(
            kind=WarningKind.EQUIVALENCE_CROSS_ADDRESSING,
            message=f"EQUIVALENCE '{decl.name}' ({decl.tal_type.value}) to "
                    f"'{decl.equivalence_target}' ({target.tal_type.value}) — "
                    f"cross-addressing (byte vs word) produces incorrect offsets",
            loc=f"{source_file}{decl.loc}",
            suggestion="Ensure both sides use the same addressing mode, or use indirect declarations",
        ))


def check_equivalence_to_implicit(program: Program) -> list[Warning]:
    return check_equivalence(program)
