"""Call backtrace analysis for TAL programs.

Builds a call graph from procedure bodies, resolves call paths
(either manual or auto-discovered via BFS), and computes the
accumulated stack usage along the call chain.
"""

from __future__ import annotations
import os
from collections import deque
from .ast_nodes import (
    Program, Procedure, Statement,
    CallStmt, CallExpr, AssignStmt, IfStmt, WhileStmt, ForStmt,
    BinOpExpr, ScopeKind,
)
from .scope import ScopeStack, SCOPE_LIMITS

COMBINED_LIMIT = 32768


def build_call_graph(program: Program) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for proc in program.procedures:
        callees: set[str] = set()
        for stmt in proc.body:
            _collect_calls(stmt, callees)
        for sp in proc.subprocs:
            for stmt in sp.body:
                _collect_calls(stmt, callees)
        graph[proc.name.upper()] = callees
    return graph


def _collect_calls(stmt: Statement, out: set[str]) -> None:
    if isinstance(stmt, CallStmt):
        out.add(stmt.expr.name.upper())
    if isinstance(stmt, AssignStmt):
        _collect_expr_calls(stmt.source, out)
    if isinstance(stmt, IfStmt):
        if hasattr(stmt, 'condition'):
            _collect_expr_calls(stmt.condition, out)
        for s in stmt.then_body + stmt.else_body:
            _collect_calls(s, out)
    if isinstance(stmt, WhileStmt):
        for s in stmt.body:
            _collect_calls(s, out)
    if isinstance(stmt, ForStmt):
        for s in stmt.body:
            _collect_calls(s, out)


def _collect_expr_calls(expr, out: set[str]) -> None:
    if isinstance(expr, CallExpr):
        out.add(expr.name.upper())
        for a in expr.args:
            _collect_expr_calls(a, out)
    if isinstance(expr, BinOpExpr):
        _collect_expr_calls(expr.left, out)
        _collect_expr_calls(expr.right, out)


def find_path(graph: dict[str, set[str]], start: str, end: str) -> list[str] | None:
    if start == end:
        return [start]
    start_u = start.upper()
    end_u = end.upper()
    visited: set[str] = {start_u}
    queue: deque[tuple[str, list[str]]] = deque([(start_u, [start_u])])
    while queue:
        node, path = queue.popleft()
        for callee in graph.get(node, set()):
            if callee == end_u:
                return path + [callee]
            if callee not in visited:
                visited.add(callee)
                queue.append((callee, path + [callee]))
    return None


def _proc_primary_words(proc: Procedure) -> int:
    scope = ScopeStack()
    scope.push(ScopeKind.LOCAL)
    for decl in proc.locals_:
        scope.declare(decl, ScopeKind.LOCAL)
    words = scope.current.primary_words if scope.current else 0
    scope.pop()
    return words


def _global_words(program: Program) -> int:
    scope = ScopeStack()
    scope.push(ScopeKind.GLOBAL)
    for decl in program.globals_:
        scope.declare(decl, ScopeKind.GLOBAL)
    words = scope.current.primary_words if scope.current else 0
    scope.pop()
    return words


def _find_proc(program: Program, name: str) -> Procedure | None:
    name_u = name.upper()
    for proc in program.procedures:
        if proc.name.upper() == name_u:
            return proc
    return None


def _entry_point(program: Program) -> Procedure:
    return program.procedures[0] if program.procedures else None


def _is_api(program: Program, graph: dict[str, set[str]], proc: Procedure) -> bool:
    name_u = proc.name.upper()
    if program.procedures and program.procedures[0].name.upper() == name_u:
        return False
    for caller, callees in graph.items():
        if name_u in callees:
            return False
    return True


def resolve_backtrace_path(
    program: Program,
    bt_str: str,
) -> list[str] | None:
    parts = [p.strip() for p in bt_str.split(":") if p.strip()]
    if not parts:
        return None

    graph = build_call_graph(program)
    entry = _entry_point(program)
    if not entry:
        return None

    if len(parts) == 1:
        target = parts[0]
        target_proc = _find_proc(program, target)
        if target_proc is None:
            return None
        if target.upper() == entry.name.upper():
            return [entry.name]
        path = find_path(graph, entry.name, target)
        return path

    first_known = parts[0]
    first_proc = _find_proc(program, first_known)
    if first_proc is None:
        first_proc = entry
        parts = [entry.name] + parts

    resolved: list[str] = []
    current = parts[0]

    for i, target in enumerate(parts):
        target_proc = _find_proc(program, target)
        if target_proc is None:
            return None

        if i == 0:
            resolved.append(target)
            current = target
            continue

        current_u = current.upper()
        target_u = target.upper()

        if target_u in graph.get(current_u, set()):
            resolved.append(target)
            current = target
        else:
            path = find_path(graph, current, target)
            if path and len(path) > 1:
                resolved.extend(path[1:])
                current = target
            else:
                return None

    return resolved


def format_backtrace(program: Program, bt_str: str) -> str:
    path = resolve_backtrace_path(program, bt_str)
    if not path:
        return f"Error: could not resolve backtrace path: {bt_str}"

    proc_map: dict[str, Procedure] = {}
    for proc in program.procedures:
        proc_map[proc.name.upper()] = proc

    frames: list[dict] = []
    for name in path:
        proc = proc_map.get(name.upper())
        if proc is None:
            frames.append({
                "name": name,
                "source": "*",
                "words": 0,
            })
            continue
        if proc.is_extern:
            src = "*"
        else:
            src = os.path.basename(program.source_file) if program.source_file else "*"
        frames.append({
            "name": proc.name,
            "source": src,
            "words": _proc_primary_words(proc),
            "proc": proc,
        })

    entry_proc = frames[0].get("proc")
    graph = build_call_graph(program)
    is_api = _is_api(program, graph, entry_proc) if entry_proc else True

    global_w = _global_words(program)
    n_frames = len(frames)
    marker_w = 3 * n_frames
    total_primary = sum(f["words"] for f in frames)
    total_accum = total_primary + marker_w + global_w

    path_display = " -> ".join(f["name"] for f in frames)

    lines: list[str] = []
    lines.append(f"Call backtrace: {path_display}")
    lines.append("=" * 73)

    max_name = max(len(f["name"]) for f in frames)
    col_name = max(max_name + 10, 25)

    for i in range(n_frames - 1, -1, -1):
        f = frames[i]
        frame_num = n_frames - 1 - i
        accumulated = sum(frames[j]["words"] for j in range(i + 1)) + 3 * (i + 1) + global_w
        label = ""
        if i == 0 and is_api:
            label = " (api)"
        name_field = f["name"] + label
        lines.append(
            f"  #{frame_num:<3d} "
            f"{f['source']:<14s} "
            f"{name_field:<{col_name}s} "
            f"{f['words']:>5d}w  [{accumulated:>5d}w]"
        )

    lines.append("-" * 73)
    lines.append(
        f"      markers (3w x {n_frames}){marker_w:>4d}w"
        f"    global{global_w:>4d}w"
        f"    total{total_accum:>5d}w/{COMBINED_LIMIT}w"
    )
    lines.append("=" * 73)

    return "\n".join(lines)
