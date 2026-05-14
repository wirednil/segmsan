"""Storage overflow detection — Rules 2, 3, 4, 13."""

from __future__ import annotations
from ..ast_nodes import Program, Procedure, ScopeKind, VarDecl
from ..scope import ScopeStack, SCOPE_LIMITS
from ..report import Warning, WarningKind


def check_storage_overflows(program: Program) -> list[Warning]:
    warnings: list[Warning] = []
    scope = ScopeStack()
    scope.push(ScopeKind.GLOBAL)

    for decl in program.globals_:
        if not decl.is_indirect:
            size = decl.word_size()
            allocated = scope.global_allocated() + size
            limit = SCOPE_LIMITS[ScopeKind.GLOBAL]
            scope.declare(decl, ScopeKind.GLOBAL)
            if allocated > limit:
                warnings.append(Warning(
                    kind=WarningKind.GLOBAL_OVERFLOW,
                    message=f"Global primary overflow: {decl.name} pushes total to "
                            f"{scope.global_allocated()} words (max {limit})",
                    loc=f"{program.source_file}{decl.loc}",
                    suggestion="Use indirect (dot) declarations to move to secondary storage",
                ))
        else:
            scope.declare(decl, ScopeKind.GLOBAL)

    upper_32k_warnings = _check_upper_32k_globals(program)
    warnings.extend(upper_32k_warnings)

    scope.pop()

    for proc in program.procedures:
        _check_proc_storage(proc, program.source_file, warnings)

    return warnings


def _check_proc_storage(proc: Procedure, source_file: str, warnings: list[Warning]):
    scope = ScopeStack()
    scope.push(ScopeKind.LOCAL)

    for decl in proc.locals_:
        if not decl.is_indirect:
            size = decl.word_size()
            old = scope.local_allocated()
            scope.declare(decl, ScopeKind.LOCAL)
            new = scope.local_allocated()
            limit = SCOPE_LIMITS[ScopeKind.LOCAL]
            if new > limit:
                warnings.append(Warning(
                    kind=WarningKind.LOCAL_OVERFLOW,
                    message=f"Local overflow in {proc.name}: {decl.name} ({size} words) "
                            f"pushes total to {new} words (max {limit})",
                    loc=f"{source_file}{decl.loc}",
                    suggestion=f"Use INT .{decl.name} (indirect) to allocate from secondary area",
                ))
        else:
            scope.declare(decl, ScopeKind.LOCAL)

    upper_32k = _check_upper_32k_locals(proc, source_file)
    warnings.extend(upper_32k)

    scope.pop()

    for subproc in proc.subprocs:
        _check_subproc_storage(subproc, source_file, warnings)


def _check_subproc_storage(subproc: Procedure, source_file: str, warnings: list[Warning]):
    scope = ScopeStack()
    scope.push(ScopeKind.SUBLOCAL)

    limit = SCOPE_LIMITS[ScopeKind.SUBLOCAL]

    for decl in subproc.locals_:
        if not decl.is_indirect:
            size = decl.word_size()
            scope.declare(decl, ScopeKind.SUBLOCAL)
            allocated = scope.local_allocated()
            if allocated > limit:
                warnings.append(Warning(
                    kind=WarningKind.SUBLOCAL_OVERFLOW,
                    message=f"Sublocal overflow in {subproc.name}: {decl.name} ({size} words) "
                            f"pushes total to {allocated} words (max {limit})",
                    loc=f"{source_file}{decl.loc}",
                    suggestion="Move variable to parent PROC scope or use indirect allocation",
                ))
        else:
            scope.declare(decl, ScopeKind.SUBLOCAL)

    scope.pop()

    for nested in subproc.subprocs:
        _check_subproc_storage(nested, source_file, warnings)


def _check_upper_32k_globals(program: Program) -> list[Warning]:
    warnings: list[Warning] = []
    for decl in program.globals_:
        if not decl.is_indirect and decl.array_bounds:
            total = decl.word_size()
            if total > 32767:
                warnings.append(Warning(
                    kind=WarningKind.UPPER_32K_WITHOUT_PTR,
                    message=f"Global array {decl.name} is {total} words — crosses 32K boundary",
                    loc=f"{program.source_file}{decl.loc}",
                    suggestion="Use indirect allocation (dot) for arrays crossing 32K words",
                ))
    return warnings


def _check_upper_32k_locals(proc: Procedure, source_file: str) -> list[Warning]:
    warnings: list[Warning] = []
    for decl in proc.locals_:
        if not decl.is_indirect and decl.array_bounds:
            total = decl.word_size()
            if total > 32767:
                warnings.append(Warning(
                    kind=WarningKind.UPPER_32K_WITHOUT_PTR,
                    message=f"Local array {decl.name} in {proc.name} is {total} words — crosses 32K",
                    loc=f"{source_file}{decl.loc}",
                    suggestion="Use indirect allocation (dot) for large arrays",
                ))
    return warnings
