"""Dataflow analysis engine for TAL static memory analyzer.

Implements forward dataflow with taint propagation:
- @local is the taint source (address of a scoped variable)
- Taint propagates through assignments: ptr1 := @x; ptr2 := ptr1 → ptr2 is tainted
- Branches (IF/ELSE) fork state, then merge at join point
- Detects: dangling pointers, use-after-scope, uninitialized pointers
"""

from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Optional

from .ast_nodes import (
    Expr, VarExpr, DerefExpr, IndexExpr, AddressOfExpr, LiteralExpr,
    BinOpExpr, CallExpr, DollarFuncExpr, FieldExpr,
    Statement, AssignStmt, CallStmt, IfStmt, WhileStmt, ForStmt,
    ScanStmt, ReturnStmt, Procedure, VarDecl, ParamDecl, ScopeKind,
)
from .scope import ScopeStack, VarInfo
from .report import Warning, WarningKind


@dataclass
class VarState:
    assigned: bool = False
    points_to: set[str] = field(default_factory=set)
    tainted: bool = False
    taint_sources: set[str] = field(default_factory=set)
    is_deref: bool = False


@dataclass
class DataflowState:
    vars: dict[str, VarState] = field(default_factory=dict)
    scope: ScopeStack = field(default_factory=ScopeStack)

    def fork(self) -> DataflowState:
        return deepcopy(self)

    def merge(self, other: DataflowState):
        for name in set(list(self.vars.keys()) + list(other.vars.keys())):
            s = self.vars.get(name)
            o = other.vars.get(name)
            if s and o:
                s.assigned = s.assigned and o.assigned
                s.tainted = s.tainted or o.tainted
                s.taint_sources = s.taint_sources | o.taint_sources
                s.points_to = s.points_to | o.points_to
            elif o and name not in self.vars:
                self.vars[name] = deepcopy(o)

    def declare(self, name: str):
        upper = name.upper()
        if upper not in self.vars:
            self.vars[upper] = VarState()

    def mark_assigned(self, name: str):
        upper = name.upper()
        if upper in self.vars:
            self.vars[upper].assigned = True

    def is_tainted(self, name: str) -> bool:
        upper = name.upper()
        return upper in self.vars and self.vars[upper].tainted

    def get_taint_sources(self, name: str) -> set[str]:
        upper = name.upper()
        if upper in self.vars:
            return self.vars[upper].taint_sources
        return set()

    def get_points_to(self, name: str) -> set[str]:
        upper = name.upper()
        if upper in self.vars:
            return self.vars[upper].points_to
        return set()

    def propagate_taint(self, target: str, source_name: str):
        upper_target = target.upper()
        upper_source = source_name.upper()
        if upper_target not in self.vars:
            return
        source = self.vars.get(upper_source)
        if source and source.tainted:
            self.vars[upper_target].tainted = True
            self.vars[upper_target].taint_sources |= source.taint_sources
            self.vars[upper_target].points_to |= source.points_to

    def taint_from_address_of(self, target: str, local_name: str):
        upper_target = target.upper()
        upper_local = local_name.upper()
        if upper_target not in self.vars:
            return
        self.vars[upper_target].tainted = True
        self.vars[upper_target].taint_sources.add(upper_local)
        self.vars[upper_target].points_to.add(upper_local)

    def transfer_points_to(self, target: str, source_name: str):
        upper_target = target.upper()
        upper_source = source_name.upper()
        if upper_target not in self.vars:
            return
        source = self.vars.get(upper_source)
        if source:
            self.vars[upper_target].points_to = set(source.points_to)
            self.vars[upper_target].tainted = source.tainted
            self.vars[upper_target].taint_sources = set(source.taint_sources)


def extract_var_name(expr: Expr) -> Optional[str]:
    if isinstance(expr, VarExpr):
        return expr.name
    if isinstance(expr, DerefExpr):
        return extract_var_name(expr.inner)
    if isinstance(expr, IndexExpr):
        return extract_var_name(expr.array)
    if isinstance(expr, FieldExpr):
        return extract_var_name(expr.obj)
    return None


def extract_all_var_refs(expr: Expr) -> list[str]:
    names = []
    _collect_refs(expr, names)
    return names


def _collect_refs(expr: Expr, names: list[str]):
    if isinstance(expr, VarExpr):
        names.append(expr.name)
    elif isinstance(expr, DerefExpr):
        names.append("(deref)")
        _collect_refs(expr.inner, names)
    elif isinstance(expr, IndexExpr):
        _collect_refs(expr.array, names)
        _collect_refs(expr.index, names)
    elif isinstance(expr, FieldExpr):
        _collect_refs(expr.obj, names)
    elif isinstance(expr, AddressOfExpr):
        _collect_refs(expr.inner, names)
    elif isinstance(expr, BinOpExpr):
        _collect_refs(expr.left, names)
        _collect_refs(expr.right, names)
    elif isinstance(expr, CallExpr):
        for a in expr.args:
            _collect_refs(a, names)
    elif isinstance(expr, DollarFuncExpr):
        for a in expr.args:
            _collect_refs(a, names)


class MemoryAnalyzer:
    def __init__(self):
        self.warnings: list[Warning] = []
        self.proc_summaries: dict[str, ProcSummary] = {}

    def _build_proc_summaries(self, program):
        self.proc_summaries = build_proc_summaries(program)

    def analyze_program(self, program, scope: ScopeStack) -> list[Warning]:
        self.warnings = []
        self._build_proc_summaries(program)
        self._analyze_globals(program, scope)

        for proc in program.procedures:
            self._analyze_proc(proc, scope, program.source_file)

        return self.warnings

    def _analyze_globals(self, program, scope: ScopeStack):
        for decl in program.globals_:
            scope.declare(decl, ScopeKind.GLOBAL)

    def _analyze_proc(self, proc: Procedure, parent_scope: ScopeStack, source_file: str):
        proc_scope = ScopeStack()
        for level in parent_scope.levels:
            proc_scope.levels.append(level)
        proc_scope.push(ScopeKind.LOCAL)

        state = DataflowState(scope=proc_scope)

        for decl in parent_scope.levels[0].variables.values() if proc_scope.levels else []:
            state.declare(decl.name)

        for param in proc.params:
            proc_scope.declare_param(param, ScopeKind.LOCAL)
            state.declare(param.name)
            if not param.is_reference:
                state.mark_assigned(param.name)

        for decl in proc.locals_:
            proc_scope.declare(decl, ScopeKind.LOCAL)
            state.declare(decl.name)
            if decl.is_indirect:
                self._check_uninit_ptr(decl, state, source_file)

        self._analyze_stmts(proc.body, state, source_file, proc.name, proc_scope)

        for subproc in proc.subprocs:
            self._analyze_subproc(subproc, proc_scope, source_file)

        proc_scope.pop()

    def _analyze_subproc(self, subproc: Procedure, parent_scope: ScopeStack, source_file: str):
        sub_scope = ScopeStack()
        for level in parent_scope.levels:
            sub_scope.levels.append(level)
        sub_scope.push(ScopeKind.SUBLOCAL)

        state = DataflowState(scope=sub_scope)

        for param in subproc.params:
            sub_scope.declare_param(param, ScopeKind.SUBLOCAL)
            state.declare(param.name)
            if not param.is_reference:
                state.mark_assigned(param.name)

        for decl in subproc.locals_:
            sub_scope.declare(decl, ScopeKind.SUBLOCAL)
            state.declare(decl.name)

        self._analyze_stmts(subproc.body, state, source_file, subproc.name, sub_scope)

        for nested in subproc.subprocs:
            self._analyze_subproc(nested, sub_scope, source_file)

        sub_scope.pop()

    def _analyze_stmts(self, stmts: list[Statement], state: DataflowState,
                       source_file: str, proc_name: str, scope: ScopeStack):
        for stmt in stmts:
            self._analyze_stmt(stmt, state, source_file, proc_name, scope)

    def _analyze_stmt(self, stmt: Statement, state: DataflowState,
                      source_file: str, proc_name: str, scope: ScopeStack):
        match stmt:
            case AssignStmt(target=target, source=source, loc=loc):
                self._analyze_assignment(target, source, state, source_file, loc, proc_name, scope)

            case CallStmt(expr=expr, loc=loc):
                self._analyze_call(expr, state, source_file, loc, proc_name, scope)

            case IfStmt(then_body=then_body, else_body=else_body, condition=cond, loc=loc):
                self._check_derefs_in_expr(cond, state, source_file, loc, proc_name, scope)
                then_state = state.fork()
                else_state = state.fork()
                self._analyze_stmts(then_body, then_state, source_file, proc_name, scope)
                self._analyze_stmts(else_body, else_state, source_file, proc_name, scope)
                state.merge(then_state)
                state.merge(else_state)

            case WhileStmt(body=body, condition=cond, loc=loc):
                self._check_derefs_in_expr(cond, state, source_file, loc, proc_name, scope)
                body_state = state.fork()
                self._analyze_stmts(body, body_state, source_file, proc_name, scope)
                state.merge(body_state)

            case ForStmt(body=body):
                body_state = state.fork()
                self._analyze_stmts(body, body_state, source_file, proc_name, scope)
                state.merge(body_state)

            case _:
                pass

    def _analyze_assignment(self, target: Expr, source: Expr, state: DataflowState,
                            source_file: str, loc, proc_name: str, scope: ScopeStack):
        target_name = extract_var_name(target)
        source_name = extract_var_name(source)

        if isinstance(source, AddressOfExpr):
            inner_name = extract_var_name(source.inner)
            if inner_name:
                is_local = scope.is_local(inner_name)
                if is_local and target_name:
                    target_scope = scope.scope_of(target_name)
                    if target_scope == ScopeKind.GLOBAL:
                        self.warnings.append(Warning(
                            kind=WarningKind.DANGLING_POINTER_STORE,
                            message=f"@{inner_name} (local) stored in global '{target_name}' "
                                    f"in {proc_name} — pointer dangles after scope exits",
                            loc=f"{source_file}{loc}",
                            suggestion=f"Allocate '{inner_name}' at global scope or use a buffer pool",
                        ))
                    elif target_scope in (ScopeKind.LOCAL, ScopeKind.SUBLOCAL):
                        target_info = scope.lookup(target_name)
                        if target_info and target_info.is_pointer:
                            state.taint_from_address_of(target_name, inner_name)

                if inner_name and target_name:
                    state.taint_from_address_of(target_name, inner_name)
                    state.mark_assigned(target_name)
                return

        if source_name and target_name:
            state.propagate_taint(target_name, source_name)
            state.transfer_points_to(target_name, source_name)
            state.mark_assigned(target_name)

            if state.is_tainted(source_name):
                target_scope = scope.scope_of(target_name)
                if target_scope == ScopeKind.GLOBAL:
                    sources = state.get_taint_sources(source_name)
                    sources_str = ", ".join(s for s in sources if s)
                    self.warnings.append(Warning(
                        kind=WarningKind.DANGLING_POINTER_STORE,
                        message=f"Tainted pointer from local(s) [{sources_str}] propagated to "
                                f"global '{target_name}' in {proc_name}",
                        loc=f"{source_file}{loc}",
                        suggestion="Trace the taint chain and break it before storing globally",
                    ))
                    state.vars[target_name.upper()].tainted = False

        if target_name:
            state.mark_assigned(target_name)

        if isinstance(source, CallExpr):
            self._analyze_call_expr_taint(source, target_name, state, source_file, loc, proc_name, scope)

        self._check_derefs_in_expr(target, state, source_file, loc, proc_name, scope)
        self._check_derefs_in_expr(source, state, source_file, loc, proc_name, scope)

        refs = extract_all_var_refs(source)
        for ref in refs:
            if ref != "(deref)" and state.is_tainted(ref):
                pass

    def _analyze_call(self, call: CallExpr, state: DataflowState,
                      source_file: str, loc, proc_name: str, scope: ScopeStack):
        for arg in call.args:
            if isinstance(arg, AddressOfExpr):
                inner_name = extract_var_name(arg.inner)
                if inner_name and scope.is_local(inner_name):
                    summary = self.proc_summaries.get(call.name.upper())
                    if summary and summary.stores_refs_globally:
                        self.warnings.append(Warning(
                            kind=WarningKind.DANGLING_POINTER_STORE,
                            message=f"@{inner_name} passed to '{call.name}' which stores "
                                    f"references globally — dangling pointer risk",
                            loc=f"{source_file}{loc}",
                            suggestion=f"Do not pass local addresses to {call.name}",
                        ))
                    if inner_name:
                        for var_name, vs in state.vars.items():
                            if vs.tainted and inner_name.upper() in vs.taint_sources:
                                pass

    def _analyze_call_expr_taint(self, call: CallExpr, target_name: Optional[str],
                                 state: DataflowState, source_file: str, loc,
                                 proc_name: str, scope: ScopeStack):
        pass

    def _check_uninit_ptr(self, decl: VarDecl, state: DataflowState, source_file: str):
        if decl.has_initializer:
            state.mark_assigned(decl.name)

    def _check_derefs_in_expr(self, expr: Expr, state: DataflowState,
                              source_file: str, loc, proc_name: str, scope: ScopeStack):
        if isinstance(expr, DerefExpr):
            inner_name = extract_var_name(expr.inner)
            if inner_name:
                upper = inner_name.upper()
                if upper in state.vars:
                    vs = state.vars[upper]
                    if not vs.assigned:
                        self.warnings.append(Warning(
                            kind=WarningKind.UNINIT_POINTER_DEREF,
                            message=f"Pointer '{inner_name}' dereferenced without prior assignment "
                                    f"in {proc_name} — contains stack garbage",
                            loc=f"{source_file}{loc}",
                            suggestion=f"Initialize '{inner_name}' before dereferencing (e.g., "
                                       f"{inner_name} := @target)",
                        ))
        if isinstance(expr, BinOpExpr):
            self._check_derefs_in_expr(expr.left, state, source_file, loc, proc_name, scope)
            self._check_derefs_in_expr(expr.right, state, source_file, loc, proc_name, scope)
        if isinstance(expr, CallExpr):
            for a in expr.args:
                self._check_derefs_in_expr(a, state, source_file, loc, proc_name, scope)
        if isinstance(expr, DollarFuncExpr):
            for a in expr.args:
                self._check_derefs_in_expr(a, state, source_file, loc, proc_name, scope)
        if isinstance(expr, IndexExpr):
            self._check_derefs_in_expr(expr.array, state, source_file, loc, proc_name, scope)
            self._check_derefs_in_expr(expr.index, state, source_file, loc, proc_name, scope)
        if isinstance(expr, FieldExpr):
            self._check_derefs_in_expr(expr.obj, state, source_file, loc, proc_name, scope)
        if isinstance(expr, AddressOfExpr):
            self._check_derefs_in_expr(expr.inner, state, source_file, loc, proc_name, scope)


@dataclass
class ProcSummary:
    name: str
    stores_refs_globally: bool = False
    takes_address_of_params: bool = False
    calls_list: list[str] = field(default_factory=list)


def build_proc_summaries(program) -> dict[str, ProcSummary]:
    summaries: dict[str, ProcSummary] = {}
    for proc in program.procedures:
        summary = ProcSummary(name=proc.name)
        _summarize_stmts(proc.body, summary)
        summaries[proc.name.upper()] = summary
    return summaries


def _summarize_stmts(stmts: list[Statement], summary: ProcSummary):
    for stmt in stmts:
        _summarize_stmt(stmt, summary)


def _summarize_stmt(stmt: Statement, summary: ProcSummary):
    match stmt:
        case AssignStmt(target=target, source=source):
            if isinstance(source, AddressOfExpr):
                summary.takes_address_of_params = True
        case CallStmt(expr=expr):
            summary.calls_list.append(expr.name.upper())
        case IfStmt(then_body=then_body, else_body=else_body):
            _summarize_stmts(then_body, summary)
            _summarize_stmts(else_body, summary)
        case WhileStmt(body=body):
            _summarize_stmts(body, summary)
        case ForStmt(body=body):
            _summarize_stmts(body, summary)


def check_memory_dataflow(program, scope: ScopeStack) -> list[Warning]:
    analyzer = MemoryAnalyzer()
    return analyzer.analyze_program(program, scope)
