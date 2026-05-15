"""Storage overflow detection — Rules 2, 3, 4, 13, 25, 26."""

from __future__ import annotations
from ..ast_nodes import Program, Procedure, ScopeKind, VarDecl
from ..scope import ScopeStack, SCOPE_LIMITS
from ..report import Warning, WarningKind

COMBINED_LIMIT = 32768


def _check_unresolved_templates(program: Program, warnings: list[Warning]) -> None:
    seen: set[tuple[str, str]] = set()
    for proc in program.procedures:
        for decl in proc.locals_:
            if (decl.tal_type.name == "STRUCT"
                    and decl.template_name
                    and decl.struct_fields is None):
                key = (proc.name.upper(), decl.template_name.upper())
                if key in seen:
                    continue
                seen.add(key)
                indirect_label = "indirect" if decl.is_indirect else "direct"
                msg = (f"Unresolved template in {proc.name}: {decl.name} references "
                       f"{decl.template_name} ({indirect_label}) — "
                       f"size unknown, storage totals may be underestimated")
                warnings.append(Warning(
                    kind=WarningKind.UNRESOLVED_TEMPLATE,
                    message=msg,
                    loc=f"{program.source_file}{decl.loc}",
                ))
    for decl in program.globals_:
        if (decl.tal_type.name == "STRUCT"
                and decl.template_name
                and decl.struct_fields is None
                and not decl.is_template):
            msg = (f"Unresolved global template reference: {decl.name} references "
                   f"{decl.template_name} — size unknown")
            warnings.append(Warning(
                kind=WarningKind.UNRESOLVED_TEMPLATE,
                message=msg,
                loc=f"{program.source_file}{decl.loc}",
            ))


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

    _check_unresolved_templates(program, warnings)

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
    W = 81
    lines.append("=" * W)
    lines.append("STORAGE SUMMARY")
    lines.append("=" * W)
    lines.append(
        f"{'Scope':<32s}| {'Primary':>7s} | {'Secondary':>9s} | {'Extend.':>7s} | {'Combined':>13s} "
    )
    lines.append("-" * 32 + "+" + "-" * 9 + "+" + "-" * 11 + "+" + "-" * 9 + "+" + "-" * 15)

    def _fmt_name(name: str) -> str:
        if len(name) > 32:
            return name[:30] + ".."
        return name

    def _row(name: str, pw: int, plim: int, sw: int, ew: int, cw: int) -> str:
        return (
            f"{_fmt_name(name):<32s}"
            f"| {f'{pw}/{plim}w':>7s} "
            f"| {f'{sw}w':>9s} "
            f"| {f'{ew}w':>7s} "
            f"| {f'{cw}/{COMBINED_LIMIT}w':>13s} "
        )

    scope = ScopeStack()
    scope.push(ScopeKind.GLOBAL)
    for decl in program.globals_:
        scope.declare(decl, ScopeKind.GLOBAL)

    gl = scope.levels[0]
    lines.append(_row("GLOBAL", gl.primary_words,
                       SCOPE_LIMITS[ScopeKind.GLOBAL],
                       gl.secondary_words, gl.extended_words,
                       gl.combined_words))
    scope.pop()

    for proc in program.procedures:
        scope.push(ScopeKind.LOCAL)
        for decl in proc.locals_:
            scope.declare(decl, ScopeKind.LOCAL)

        lv = scope.current
        lines.append(_row(proc.name, lv.primary_words,
                           SCOPE_LIMITS[ScopeKind.LOCAL],
                           lv.secondary_words, lv.extended_words,
                           lv.combined_words))
        scope.pop()

        for sp in proc.subprocs:
            scope.push(ScopeKind.SUBLOCAL)
            for decl in sp.locals_:
                scope.declare(decl, ScopeKind.SUBLOCAL)

            sv = scope.current
            lines.append(_row(sp.name, sv.primary_words,
                               SCOPE_LIMITS[ScopeKind.SUBLOCAL],
                               sv.secondary_words, sv.extended_words,
                               sv.combined_words))
            scope.pop()

    lines.append("=" * W)
    return "\n".join(lines)
