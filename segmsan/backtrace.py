"""Call backtrace analysis for TAL programs.

Builds a call graph from procedure bodies, resolves call paths
(either manual or auto-discovered via BFS), extends the path
upward to the root caller, and computes accumulated stack usage.

bt semantics:
  bt func1:func2:print
  → breakpoint at print inside func2 inside func1
  → backtrace continues upward from func1 to root (main or api)
"""

from __future__ import annotations
import os
from collections import deque
from .ast_nodes import (
    Program, Procedure, Statement,
    CallStmt, CallExpr, AssignStmt, IfStmt, WhileStmt, ForStmt, CaseStmt,
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


def build_reverse_graph(graph: dict[str, set[str]]) -> dict[str, set[str]]:
    reverse: dict[str, set[str]] = {}
    for caller, callees in graph.items():
        for callee in callees:
            reverse.setdefault(callee, set()).add(caller)
    return reverse


def _collect_calls(stmt: Statement, out: set[str]) -> None:
    if isinstance(stmt, CallStmt):
        out.add(stmt.name.upper())
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
    if isinstance(stmt, CaseStmt):
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


def find_path_down(graph: dict[str, set[str]], start: str, end: str) -> list[str] | None:
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


def find_path_up(reverse_graph: dict[str, set[str]], start: str) -> list[str]:
    path: list[str] = [start.upper()]
    current = start.upper()
    visited: set[str] = {current}
    while True:
        callers = reverse_graph.get(current, set())
        local_callers = callers - visited
        if not local_callers:
            break
        next_caller = sorted(local_callers)[0]
        visited.add(next_caller)
        path.append(next_caller)
        current = next_caller
    path.reverse()
    return path


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


def _has_callers(reverse_graph: dict[str, set[str]], name: str) -> bool:
    callers = reverse_graph.get(name.upper(), set())
    return bool(callers)


def resolve_backtrace_path(
    program: Program,
    bt_str: str,
) -> list[str] | None:
    parts = [p.strip() for p in bt_str.split(":") if p.strip()]
    if not parts:
        return None

    graph = build_call_graph(program)
    reverse_graph = build_reverse_graph(graph)

    all_names = set(graph.keys())
    for callee_set in graph.values():
        all_names |= callee_set
    for p in parts:
        if _find_proc(program, p) is None and p.upper() not in all_names:
            return None

    if len(parts) == 1:
        target = parts[0]
        upward = find_path_up(reverse_graph, target)
        return upward

    first = parts[0]
    last = parts[-1]

    first_proc = _find_proc(program, first)
    if first_proc is None:
        return None

    down_path = [first.upper()]
    current = first.upper()

    for i in range(1, len(parts)):
        target = parts[i].upper()
        if target in graph.get(current, set()):
            down_path.append(target)
            current = target
        else:
            auto = find_path_down(graph, current, target)
            if auto and len(auto) > 1:
                down_path.extend(auto[1:])
                current = target
            else:
                return None

    upward = find_path_up(reverse_graph, down_path[0])

    if upward and upward[-1] == down_path[0]:
        full_path = upward + down_path[1:]
    else:
        full_path = upward + down_path
    return full_path


def format_backtrace(program: Program, bt_str: str) -> str:
    path = resolve_backtrace_path(program, bt_str)
    if not path:
        return f"Error: could not resolve backtrace path: {bt_str}"

    graph = build_call_graph(program)
    reverse_graph = build_reverse_graph(graph)

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
                "line": 0,
                "words": 0,
            })
            continue
        if proc.is_external:
            src = "*"
        else:
            src = os.path.basename(program.source_file) if program.source_file else "*"
        line = proc.loc.line if proc.loc else 0
        frames.append({
            "name": proc.name,
            "source": src,
            "line": line,
            "words": _proc_primary_words(proc),
        })

    n_frames = len(frames)
    root_name = path[0].upper()
    root_proc = proc_map.get(root_name)
    is_root_main = root_proc is not None and root_proc.is_main
    is_api = not is_root_main and not _has_callers(reverse_graph, root_name)

    global_w = _global_words(program)
    marker_w = 3 * n_frames
    total_primary = sum(f["words"] for f in frames)
    total_accum = total_primary + marker_w + global_w

    bp_idx = n_frames - 1
    entry_label = "MAIN" if is_root_main else "API"

    lines: list[str] = []
    lines.append(f"Backtrace - Breakpoint en cadena: {bt_str}")
    lines.append("=" * 73)

    col_num = 5
    col_src = 22
    col_name = max(len(f["name"]) + 2 for f in frames)
    col_name = max(col_name, 12)

    lines.append(
        f"{'frame':<{col_num}s} "
        f"{'procedures':<{col_name}s} "
        f"{'source':<{col_src}s} "
        f"{'per frame':>10s}"
    )
    lines.append("=" * 73)

    for i in range(n_frames - 1, -1, -1):
        f = frames[i]
        accumulated = sum(frames[j]["words"] for j in range(i + 1)) + 3 * (i + 1) + global_w

        if f["source"] == "*" or f["line"] == 0:
            src_str = f"{f['source']}"
        else:
            src_str = f"{f['source']}:{f['line']}"

        bp_marker = "   ← breakpoint" if i == bp_idx else ""
        star = "*" if f["source"] == "*" else " "
        label = ""
        if i == 0 and is_api:
            label = " (api)"

        name_field = f["name"] + label
        lines.append(
            f"  #{i:<3d}{star}"
            f"{name_field:<{col_name}s} "
            f"{src_str:<{col_src}s} "
            f"{f['words']:>4d}w  [{accumulated:>4d}w]{bp_marker}"
        )

    lines.append(
        f"  #global"
        f"{'':<{col_name - 5}s} "
        f"{'':<{col_src}s} "
        f"{global_w:>4d}w"
    )

    pct = (total_accum / COMBINED_LIMIT) * 100
    lines.append("-" * 73)
    lines.append(f"  Total: {total_accum}w / {COMBINED_LIMIT}w   ({pct:.1f}% usado)")
    lines.append("")
    lines.append(f"  Entry point: {frames[0]['name']} → Etiquetado como: {entry_label}")
    lines.append("=" * 73)

    return "\n".join(lines)
