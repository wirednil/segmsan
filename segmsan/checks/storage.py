"""Storage overflow detection — Rules 2, 3, 4, 13, 25, 26."""

from __future__ import annotations
from ..ast_nodes import Program, Procedure, ScopeKind, VarDecl
from ..scope import ScopeStack, SCOPE_LIMITS
from ..report import Warning, WarningKind

COMBINED_LIMIT = 32768


def check_storage_overflows(program: Program) -> list[Warning]:
    warnings: list[Warning] = []
    scope = ScopeStack()
    scope.push(ScopeKind.GLOBAL)

    limit = SCOPE_LIMITS[ScopeKind.GLOBAL]

    for decl in program.globals_:
        scope.declare(decl, ScopeKind.GLOBAL)
        primary = scope.global_allocated()
        if primary > limit:
            if decl.is_indirect:
                msg = (f"Global primary overflow: {decl.name} pointer pushes total to "
                       f"{primary} words (max {limit})")
                suggestion = "Reduce number of indirect variables or use .EXT (2w pointer but data in extended segment)"
            else:
                msg = (f"Global primary overflow: {decl.name} pushes total to "
                       f"{primary} words (max {limit})")
                suggestion = "Use indirect (.) declarations to move data to secondary storage"
            warnings.append(Warning(
                kind=WarningKind.GLOBAL_OVERFLOW,
                message=msg,
                loc=f"{program.source_file}{decl.loc}",
                suggestion=suggestion,
            ))

        combined = scope.global_secondary() + primary
        if combined > COMBINED_LIMIT:
            warnings.append(Warning(
                kind=WarningKind.SECONDARY_OVERFLOW,
                message=f"Global secondary overflow: combined primary + secondary is "
                        f"{combined} words (max {COMBINED_LIMIT}). "
                        f"Primary: {primary}w, secondary: {scope.global_secondary()}w",
                loc=f"{program.source_file}{decl.loc}",
                suggestion="Use .EXT for large indirect data to move it from secondary to extended segment",
            ))

    upper_32k_warnings = _check_upper_32k_globals(program)
    warnings.extend(upper_32k_warnings)

    scope.pop()

    for proc in program.procedures:
        _check_proc_storage(proc, program.source_file, warnings)

    return warnings


def _check_proc_storage(proc: Procedure, source_file: str, warnings: list[Warning]):
    scope = ScopeStack()
    scope.push(ScopeKind.LOCAL)

    limit = SCOPE_LIMITS[ScopeKind.LOCAL]

    for decl in proc.locals_:
        scope.declare(decl, ScopeKind.LOCAL)
        primary = scope.local_allocated()
        if primary > limit:
            if decl.is_indirect:
                msg = (f"Local overflow in {proc.name}: {decl.name} pointer pushes total to "
                       f"{primary} words (max {limit})")
                suggestion = "Reduce number of indirect locals or use .EXT (2w pointer but data in extended segment)"
            else:
                size = decl.word_size()
                msg = (f"Local overflow in {proc.name}: {decl.name} ({size} words) "
                       f"pushes total to {primary} words (max {limit})")
                suggestion = f"Use . (standard indirect) for <64KB combined, .EXT for larger"
            warnings.append(Warning(
                kind=WarningKind.LOCAL_OVERFLOW,
                message=msg,
                loc=f"{source_file}{decl.loc}",
                suggestion=suggestion,
            ))

        combined = scope.local_secondary() + primary
        if combined > COMBINED_LIMIT:
            warnings.append(Warning(
                kind=WarningKind.SECONDARY_OVERFLOW,
                message=f"Local secondary overflow in {proc.name}: combined primary + secondary is "
                        f"{combined} words (max {COMBINED_LIMIT}). "
                        f"Primary: {primary}w, secondary: {scope.local_secondary()}w",
                loc=f"{source_file}{decl.loc}",
                suggestion="Use .EXT for large indirect data to move it from secondary to extended segment",
            ))

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
        if decl.is_indirect:
            warnings.append(Warning(
                kind=WarningKind.SUBLOCAL_INDIRECT,
                message=f"Sublocal indirect in {subproc.name}: {decl.name} "
                        f"— compiler converts to direct (no secondary area in subproc)",
                loc=f"{source_file}{decl.loc}",
                suggestion="Move to parent PROC scope for proper indirect allocation",
            ))

        scope.declare(decl, ScopeKind.SUBLOCAL)
        allocated = scope.local_allocated()
        if allocated > limit:
            size = decl.word_size()
            warnings.append(Warning(
                kind=WarningKind.SUBLOCAL_OVERFLOW,
                message=f"Sublocal overflow in {subproc.name}: {decl.name} ({size} words) "
                        f"pushes total to {allocated} words (max {limit})",
                loc=f"{source_file}{decl.loc}",
                suggestion="Move variable to parent PROC scope or use indirect allocation",
            ))

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


def format_storage_summary(program: Program) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("STORAGE SUMMARY")
    lines.append("=" * 60)
    lines.append(f"{'Scope':<20s} {'Primary':>12s} {'Secondary':>12s} {'Extended':>12s} {'Combined':>14s}")
    lines.append("-" * 60)

    scope = ScopeStack()
    scope.push(ScopeKind.GLOBAL)
    for decl in program.globals_:
        scope.declare(decl, ScopeKind.GLOBAL)

    gl = scope.levels[0]
    lines.append(
        f"{'GLOBAL':<20s} "
        f"{gl.primary_words:>4d}/{SCOPE_LIMITS[ScopeKind.GLOBAL]:<6d} "
        f"{gl.secondary_words:>10d}w "
        f"{gl.extended_words:>10d}w "
        f"{gl.combined_words:>6d}/{COMBINED_LIMIT}w"
    )
    scope.pop()

    for proc in program.procedures:
        scope.push(ScopeKind.LOCAL)
        for decl in proc.locals_:
            scope.declare(decl, ScopeKind.LOCAL)

        lv = scope.current
        lines.append(
            f"{proc.name:<20s} "
            f"{lv.primary_words:>4d}/{SCOPE_LIMITS[ScopeKind.LOCAL]:<6d} "
            f"{lv.secondary_words:>10d}w "
            f"{lv.extended_words:>10d}w "
            f"{lv.combined_words:>6d}/{COMBINED_LIMIT}w"
        )
        scope.pop()

        for sp in proc.subprocs:
            scope.push(ScopeKind.SUBLOCAL)
            for decl in sp.locals_:
                scope.declare(decl, ScopeKind.SUBLOCAL)

            sv = scope.current
            lines.append(
                f"{sp.name:<20s} "
                f"{sv.primary_words:>4d}/{SCOPE_LIMITS[ScopeKind.SUBLOCAL]:<6d} "
                f"{sv.secondary_words:>10d}w "
                f"{sv.extended_words:>10d}w "
                f"{sv.combined_words:>6d}/{COMBINED_LIMIT}w"
            )
            scope.pop()

    lines.append("=" * 60)
    return "\n".join(lines)
