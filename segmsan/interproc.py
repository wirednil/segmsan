"""Call graph + interprocedural taint analysis for TAL.

Builds a call graph from PROC declarations, computes procedure summaries
(what each proc does with references), and propagates taints across
procedure boundaries to detect cross-frame use-after-scope.

Architecture:
  1. Call Graph: main → proc_a → proc_b → ...
  2. Proc Summary: per-proc, does it store refs globally? pass to whom?
  3. Interprocedural Taint: @local passed as param → callee stores globally
  4. Frame Lifetime: when proc returns, its frame is reclaimed/overwritten
"""

from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional
from copy import deepcopy

from .ast_nodes import (
    Expr, VarExpr, DerefExpr, IndexExpr, AddressOfExpr, LiteralExpr,
    BinOpExpr, CallExpr, DollarFuncExpr, FieldExpr,
    Statement, AssignStmt, CallStmt, IfStmt, WhileStmt, ForStmt,
    ScanStmt, ReturnStmt, Procedure, VarDecl, ParamDecl, ScopeKind,
    Program,
)
from .scope import ScopeStack
from .report import Warning, WarningKind


@dataclass
class CallEdge:
    caller: str
    callee: str
    line: int
    arg_taints: list[bool]


@dataclass
class ProcSummary:
    name: str
    calls: list[str] = field(default_factory=list)
    stores_refs_globally: bool = False
    ref_params_stored: set[int] = field(default_factory=set)
    ref_params_passed_on: dict[int, list[tuple[str, int]]] = field(default_factory=dict)
    tainted_locals: dict[str, set[int]] = field(default_factory=dict)
    param_names: list[str] = field(default_factory=list)
    locals_direct_words: int = 0
    locals_indirect_words: int = 0
    frame_size_words: int = 0
    is_recursive: bool = False


@dataclass
class FrameInfo:
    proc_name: str
    depth: int
    locals_: dict[str, VarDecl] = field(default_factory=dict)
    params: list[ParamDecl] = field(default_factory=list)
    alloc_words: int = 0


class CallGraph:
    def __init__(self):
        self.edges: list[CallEdge] = []
        self.summaries: dict[str, ProcSummary] = {}
        self.adjacency: dict[str, list[str]] = defaultdict(list)
        self.reverse_adj: dict[str, list[str]] = defaultdict(list)
        self.proc_defs: dict[str, Procedure] = {}
        self._global_names: set[str] = set()

    def build(self, program: Program):
        self._global_names = {d.name.upper() for d in program.globals_}
        for proc in program.procedures:
            self.proc_defs[proc.name.upper()] = proc
            summary = self._compute_summary(proc, program)
            self.summaries[proc.name.upper()] = summary

        from .system_stubs import SYSTEM_PROC_STUBS
        for name, stub in SYSTEM_PROC_STUBS.items():
            if name not in self.summaries:
                self.summaries[name] = stub

        self._detect_recursion()
        self._build_adjacency()

    def _compute_summary(self, proc: Procedure, program: Program) -> ProcSummary:
        summary = ProcSummary(
            name=proc.name,
            param_names=[p.name for p in proc.params],
        )

        for decl in proc.locals_:
            if decl.is_indirect:
                summary.locals_indirect_words += decl.data_word_size()
            else:
                summary.locals_direct_words += decl.word_size()

        summary.frame_size_words = (
            summary.locals_direct_words
            + sum(1 if d.is_indirect and not d.is_extended else (2 if d.is_indirect else 0) for d in proc.locals_)
            + len(proc.params) + 3
        )

        local_names = {d.name.upper() for d in proc.locals_}
        param_name_set = {p.name.upper() for p in proc.params}

        self._analyze_body(proc.body, summary, proc.params, local_names, param_name_set)

        return summary

    def _analyze_body(self, stmts: list[Statement], summary: ProcSummary,
                      params: list[ParamDecl], local_names: set[str],
                      param_name_set: set[str]):
        for stmt in stmts:
            self._analyze_stmt(stmt, summary, params, local_names, param_name_set)

    def _analyze_stmt(self, stmt: Statement, summary: ProcSummary,
                      params: list[ParamDecl], local_names: set[str],
                      param_name_set: set[str]):
        match stmt:
            case AssignStmt(target=target, source=source):
                self._analyze_assign(target, source, summary, params, local_names, param_name_set)

            case CallStmt(expr=expr):
                callee = expr.name.upper()
                summary.calls.append(callee)

            case IfStmt(then_body=then_body, else_body=else_body):
                self._analyze_body(then_body, summary, params, local_names, param_name_set)
                self._analyze_body(else_body, summary, params, local_names, param_name_set)

            case WhileStmt(body=body):
                self._analyze_body(body, summary, params, local_names, param_name_set)

            case ForStmt(body=body):
                self._analyze_body(body, summary, params, local_names, param_name_set)

    def _analyze_assign(self, target: Expr, source: Expr,
                        summary: ProcSummary, params: list[ParamDecl],
                        local_names: set[str], param_name_set: set[str]):
        target_name = self._extract_name(target)
        target_is_deref = isinstance(target, DerefExpr)

        if isinstance(source, AddressOfExpr):
            inner_name = self._extract_name(source.inner)
            if inner_name:
                inner_upper = inner_name.upper()
                for i, param in enumerate(params):
                    if param.name.upper() == inner_upper and param.is_reference:
                        if target_name:
                            t_upper = target_name.upper()
                            if t_upper in self._global_names:
                                summary.stores_refs_globally = True
                                summary.ref_params_stored.add(i)
                            elif t_upper in local_names or t_upper in param_name_set:
                                summary.tainted_locals.setdefault(t_upper, set()).add(i)

        if isinstance(source, VarExpr):
            source_upper = source.name.upper()
            if source_upper in summary.tainted_locals:
                if target_name:
                    t_upper = target_name.upper()
                    if t_upper in self._global_names:
                        param_indices = summary.tainted_locals[source_upper]
                        summary.stores_refs_globally = True
                        summary.ref_params_stored |= param_indices
                    elif t_upper in local_names:
                        summary.tainted_locals.setdefault(t_upper, set()).update(
                            summary.tainted_locals[source_upper]
                        )
            for i, param in enumerate(params):
                if param.name.upper() == source_upper:
                    if target_name:
                        t_upper = target_name.upper()
                        if t_upper in self._global_names:
                            summary.stores_refs_globally = True
                            summary.ref_params_stored.add(i)
                        elif t_upper in local_names:
                            summary.tainted_locals.setdefault(t_upper, set()).add(i)

    def _is_global_like(self, name: str) -> bool:
        return name.upper() in self._global_names

    def _extract_name(self, expr: Optional[Expr]) -> Optional[str]:
        if expr is None:
            return None
        if isinstance(expr, VarExpr):
            return expr.name
        if isinstance(expr, DerefExpr):
            return self._extract_name(expr.inner)
        if isinstance(expr, IndexExpr):
            return self._extract_name(expr.array)
        if isinstance(expr, FieldExpr):
            return self._extract_name(expr.obj)
        return None

    def _detect_recursion(self):
        for name, summary in self.summaries.items():
            visited = set()
            if self._reaches(name, name, visited):
                summary.is_recursive = True

    def _reaches(self, start: str, target: str, visited: set) -> bool:
        if start in visited:
            return False
        visited.add(start)
        summary = self.summaries.get(start)
        if summary is None:
            return False
        for callee in summary.calls:
            if callee == target:
                return True
            if self._reaches(callee, target, visited):
                return True
        return False

    def _build_adjacency(self):
        for name, summary in self.summaries.items():
            for callee in summary.calls:
                self.adjacency[name].append(callee)
                self.reverse_adj[callee].append(name)

    def find_main(self) -> Optional[str]:
        for name in self.summaries:
            upper = name.upper()
            if upper.endswith("^PROC") or upper == "MAIN" or upper.startswith("MAIN"):
                return name
        if self.summaries:
            return list(self.summaries.keys())[-1]
        return None

    def topological_order(self) -> list[str]:
        visited = set()
        order = []

        def visit(name):
            if name in visited:
                return
            visited.add(name)
            for callee in self.adjacency.get(name, []):
                visit(callee)
            order.append(name)

        for name in self.summaries:
            visit(name)

        return order

    def propagates_taint_to_global(self, callee_name: str, param_index: int,
                                   visited: Optional[set] = None) -> bool:
        if visited is None:
            visited = set()
        if callee_name in visited:
            return False
        visited.add(callee_name)

        summary = self.summaries.get(callee_name.upper())
        if summary is None:
            return False

        if param_index in summary.ref_params_stored:
            return True

        return False

    def print_graph(self) -> str:
        lines = []
        main = self.find_main()
        lines.append(f"Main entry: {main}")
        lines.append("")

        for name, summary in self.summaries.items():
            s = summary
            lines.append(f"PROC {s.name}:")
            lines.append(f"  Frame: {s.frame_size_words}w "
                         f"(direct={s.locals_direct_words}w, indirect_data={s.locals_indirect_words}w, "
                         f"{len(s.param_names)} params + 3 marker)")
            lines.append(f"  Calls: {s.calls}")
            lines.append(f"  Stores refs globally: {s.stores_refs_globally}")
            if s.ref_params_stored:
                stored_params = [s.param_names[i] for i in s.ref_params_stored if i < len(s.param_names)]
                lines.append(f"  Params stored globally: {stored_params}")
            lines.append(f"  Recursive: {s.is_recursive}")
            lines.append("")

        return "\n".join(lines)


@dataclass
class VarState:
    assigned: bool = False
    tainted: bool = False
    taint_sources: set[str] = field(default_factory=set)
    points_to: set[str] = field(default_factory=set)
    scope_kind: Optional[ScopeKind] = None


class InterprocAnalyzer:
    def __init__(self, call_graph: CallGraph):
        self.cg = call_graph
        self.warnings: list[Warning] = []

    def analyze(self, program: Program, source_file: str) -> list[Warning]:
        self.warnings = []
        scope = ScopeStack()
        scope.push(ScopeKind.GLOBAL)
        for decl in program.globals_:
            scope.declare(decl, ScopeKind.GLOBAL)

        for proc in program.procedures:
            self._analyze_proc(proc, scope, source_file, depth=0)

        scope.pop()
        return self.warnings

    def _analyze_proc(self, proc: Procedure, global_scope: ScopeStack,
                      source_file: str, depth: int):
        proc_scope = ScopeStack()
        for level in global_scope.levels:
            proc_scope.levels.append(level)
        proc_scope.push(ScopeKind.LOCAL)

        state: dict[str, VarState] = {}

        for param in proc.params:
            proc_scope.declare_param(param, ScopeKind.LOCAL)
            vs = VarState(assigned=True, scope_kind=ScopeKind.LOCAL)
            state[param.name.upper()] = vs

        for decl in proc.locals_:
            proc_scope.declare(decl, ScopeKind.LOCAL)
            vs = VarState(scope_kind=ScopeKind.LOCAL)
            state[decl.name.upper()] = vs

        self._analyze_stmts(proc.body, state, proc_scope, source_file, proc.name, depth)

        for subproc in proc.subprocs:
            self._analyze_subproc(subproc, proc_scope, source_file, depth)

        proc_scope.pop()

    def _analyze_subproc(self, subproc: Procedure, parent_scope: ScopeStack,
                         source_file: str, depth: int):
        sub_scope = ScopeStack()
        for level in parent_scope.levels:
            sub_scope.levels.append(level)
        sub_scope.push(ScopeKind.SUBLOCAL)

        state: dict[str, VarState] = {}
        for param in subproc.params:
            sub_scope.declare_param(param, ScopeKind.SUBLOCAL)
            state[param.name.upper()] = VarState(assigned=True, scope_kind=ScopeKind.SUBLOCAL)
        for decl in subproc.locals_:
            sub_scope.declare(decl, ScopeKind.SUBLOCAL)
            state[decl.name.upper()] = VarState(scope_kind=ScopeKind.SUBLOCAL)

        self._analyze_stmts(subproc.body, state, sub_scope, source_file, subproc.name, depth)
        sub_scope.pop()

    def _analyze_stmts(self, stmts: list[Statement], state: dict[str, VarState],
                       scope: ScopeStack, source_file: str, proc_name: str, depth: int):
        for stmt in stmts:
            self._analyze_stmt(stmt, state, scope, source_file, proc_name, depth)

    def _analyze_stmt(self, stmt: Statement, state: dict[str, VarState],
                      scope: ScopeStack, source_file: str, proc_name: str, depth: int):
        match stmt:
            case AssignStmt(target=target, source=source, loc=loc):
                self._analyze_assign(target, source, state, scope, source_file, loc, proc_name, depth)

            case CallStmt(expr=expr, loc=loc):
                self._analyze_call(expr, state, scope, source_file, loc, proc_name, depth)

            case IfStmt(then_body=then_body, else_body=else_body):
                then_state = deepcopy(state)
                else_state = deepcopy(state)
                self._analyze_stmts(then_body, then_state, scope, source_file, proc_name, depth)
                self._analyze_stmts(else_body, else_state, scope, source_file, proc_name, depth)
                self._merge_states(state, then_state, else_state)

            case WhileStmt(body=body):
                body_state = deepcopy(state)
                self._analyze_stmts(body, body_state, scope, source_file, proc_name, depth)
                self._merge_states(state, body_state)

            case ForStmt(body=body):
                body_state = deepcopy(state)
                self._analyze_stmts(body, body_state, scope, source_file, proc_name, depth)
                self._merge_states(state, body_state)

    def _analyze_assign(self, target: Expr, source: Expr, state: dict[str, VarState],
                        scope: ScopeStack, source_file: str, loc, proc_name: str, depth: int):
        target_name = self._extract_name(target)

        if isinstance(source, AddressOfExpr):
            inner_name = self._extract_name(source.inner)
            if inner_name and target_name:
                is_local = scope.is_local(inner_name)
                if is_local:
                    upper_t = target_name.upper()
                    if upper_t in state:
                        state[upper_t].tainted = True
                        state[upper_t].taint_sources.add(inner_name.upper())
                        state[upper_t].points_to.add(inner_name.upper())
                        state[upper_t].assigned = True

                    target_scope = scope.scope_of(target_name)
                    if target_scope == ScopeKind.GLOBAL:
                        self.warnings.append(Warning(
                            kind=WarningKind.DANGLING_POINTER_STORE,
                            message=f"@{inner_name} (local) → global '{target_name}' in {proc_name} "
                                    f"(depth={depth}) — frame destroyed on return",
                            loc=f"{source_file}{loc}",
                            suggestion=f"Allocate '{inner_name}' globally or use a buffer pool",
                        ))
                else:
                    if target_name:
                        upper_t = target_name.upper()
                        if upper_t in state:
                            state[upper_t].assigned = True
            return

        source_name = self._extract_name(source)
        if source_name and target_name:
            upper_s = source_name.upper()
            upper_t = target_name.upper()

            if upper_s in state and upper_t in state:
                src_vs = state[upper_s]
                if src_vs.tainted:
                    state[upper_t].tainted = True
                    state[upper_t].taint_sources |= src_vs.taint_sources
                    state[upper_t].points_to |= src_vs.points_to
                state[upper_t].assigned = True

                if state[upper_t].tainted:
                    target_scope = scope.scope_of(target_name)
                    if target_scope == ScopeKind.GLOBAL:
                        sources = state[upper_t].taint_sources
                        sources_str = ", ".join(sorted(s for s in sources if s))
                        self.warnings.append(Warning(
                            kind=WarningKind.DANGLING_POINTER_STORE,
                            message=f"Taint chain [{sources_str}] → global '{target_name}' "
                                    f"in {proc_name} (depth={depth})",
                            loc=f"{source_file}{loc}",
                            suggestion="Break the chain before storing globally",
                        ))
                        state[upper_t].tainted = False

        if isinstance(source, CallExpr):
            self._analyze_call_expr(source, target_name, state, scope, source_file, loc, proc_name, depth)

        if target_name:
            upper_t = target_name.upper()
            if upper_t in state:
                state[upper_t].assigned = True

    def _analyze_call(self, call: CallExpr, state: dict[str, VarState],
                      scope: ScopeStack, source_file: str, loc, proc_name: str, depth: int):
        callee_upper = call.name.upper()
        callee_summary = self.cg.summaries.get(callee_upper)

        for i, arg in enumerate(call.args):
            if isinstance(arg, AddressOfExpr):
                inner_name = self._extract_name(arg.inner)
                if inner_name and scope.is_local(inner_name):
                    if callee_summary:
                        if i in callee_summary.ref_params_stored or callee_summary.stores_refs_globally:
                            self.warnings.append(Warning(
                                kind=WarningKind.DANGLING_POINTER_STORE,
                                message=f"@{inner_name} passed to {call.name}() as param {i+1} — "
                                        f"callee stores refs globally (depth={depth})",
                                loc=f"{source_file}{loc}",
                                suggestion=f"Do not pass local addresses to {call.name}",
                            ))

            arg_name = self._extract_name(arg)
            if arg_name:
                upper_a = arg_name.upper()
                if upper_a in state and state[upper_a].tainted:
                    if callee_summary:
                        if callee_summary.stores_refs_globally:
                            sources = state[upper_a].taint_sources
                            sources_str = ", ".join(sorted(s for s in sources if s))
                            self.warnings.append(Warning(
                                kind=WarningKind.DANGLING_POINTER_STORE,
                                message=f"Tainted ptr [{sources_str}] passed to {call.name}() — "
                                        f"callee stores refs globally (depth={depth})",
                                loc=f"{source_file}{loc}",
                                suggestion="Break taint chain before passing to this callee",
                            ))

    def _analyze_call_expr(self, call: CallExpr, target_name: Optional[str],
                           state: dict[str, VarState], scope: ScopeStack,
                           source_file: str, loc, proc_name: str, depth: int):
        pass

    def _merge_states(self, base: dict[str, VarState], *others: dict[str, VarState]):
        for other in others:
            for name in set(list(base.keys()) + list(other.keys())):
                b = base.get(name)
                o = other.get(name)
                if b and o:
                    b.assigned = b.assigned and o.assigned
                    b.tainted = b.tainted or o.tainted
                    b.taint_sources |= o.taint_sources
                    b.points_to |= o.points_to
                elif o:
                    base[name] = deepcopy(o)

    def _extract_name(self, expr: Optional[Expr]) -> Optional[str]:
        if expr is None:
            return None
        if isinstance(expr, VarExpr):
            return expr.name
        if isinstance(expr, DerefExpr):
            return self._extract_name(expr.inner)
        if isinstance(expr, IndexExpr):
            return self._extract_name(expr.array)
        if isinstance(expr, FieldExpr):
            return self._extract_name(expr.obj)
        return None


def check_interproc(program: Program, source_file: str = "") -> list[Warning]:
    cg = CallGraph()
    cg.build(program)

    analyzer = InterprocAnalyzer(cg)
    return analyzer.analyze(program, source_file)
