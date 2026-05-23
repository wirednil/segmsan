"""Analysis passes for TAL static memory analyzer."""

from ..ast_nodes import Program, Procedure, ScopeKind
from ..report import Warning
from ..scope import ScopeStack
from .storage import check_storage_overflows
from .control_flow import check_control_flow
from .equivalence import check_equivalence, check_equivalence_to_implicit
from .readonly import check_readonly
from .misc import check_misc
from .fixed import check_fixed_precision
from .ext_ptr import check_ext_needed
from .bounds import check_bounds
from .cc_clobber import check_cc_clobber
from .padding import check_padding
from ..interproc import check_interproc
from ..dataflow import check_memory_dataflow


def _local_only(program: Program) -> Program:
    local = Program(
        globals_=program.globals_,
        directives=program.directives,
        procedures=[p for p in program.procedures if not p.is_external and not p.is_forward],
        source_file=program.source_file,
        literals=program.literals,
        source_imports=program.source_imports,
    )
    return local


def run_all_checks(program: Program) -> list[Warning]:
    local = _local_only(program)
    warnings: list[Warning] = []
    warnings.extend(check_storage_overflows(local))
    warnings.extend(check_control_flow(local))
    warnings.extend(check_equivalence(local))
    warnings.extend(check_equivalence_to_implicit(local))
    warnings.extend(check_readonly(local))
    warnings.extend(check_misc(local))
    warnings.extend(check_fixed_precision(local))
    warnings.extend(check_ext_needed(local))
    warnings.extend(check_bounds(local))
    warnings.extend(check_cc_clobber(local))
    warnings.extend(check_padding(local))
    warnings.extend(check_interproc(program, program.source_file))
    scope = ScopeStack()
    scope.push(ScopeKind.GLOBAL)
    for decl in program.globals_:
        scope.declare(decl, ScopeKind.GLOBAL)
    warnings.extend(check_memory_dataflow(local, scope))
    scope.pop()

    seen: set[tuple] = set()
    deduped: list[Warning] = []
    for w in warnings:
        key = (w.kind, w.loc or "")
        if key not in seen:
            seen.add(key)
            deduped.append(w)
    return deduped
