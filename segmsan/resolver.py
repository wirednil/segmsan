"""Dependency import resolver for TAL source files.

Resolves ?SOURCE directives to local files, merges globals/literals/procedures
from parsed includes into the main program. System stubs ($SYSTEM.SYSTEM.EXTDECS
etc.) are handled by system_stubs.py.

Builds an ImportNode tree for dependency reporting.
"""

from __future__ import annotations
import os
import sys
from .lexer import Lexer
from .parser import Parser
from .ast_nodes import Program, Procedure, SourceImport, ImportNode, VarDecl, TalType


def resolve_imports(program: Program, base_dir: str,
                    skip_missing: bool = False,
                    search_dirs: list[str] | None = None) -> list[ImportNode]:
    all_dirs = [base_dir] + (search_dirs or [])
    visited: set[str] = set()
    tree: list[ImportNode] = []

    for si in program.source_imports:
        if si.is_system:
            node = ImportNode(
                source_path=si.path,
                names=si.names,
                is_system=True,
            )
            tree.append(node)
            continue
        local_file = _find_local_file(si.path, all_dirs)
        if local_file:
            abs_path = os.path.abspath(local_file)
            node = ImportNode(
                source_path=si.path,
                resolved_path=local_file,
                names=si.names,
            )
            _merge_file(program, local_file, node, all_dirs, visited, skip_missing)
            si.resolved = True
            tree.append(node)
        else:
            node = ImportNode(
                source_path=si.path,
                names=si.names,
            )
            tree.append(node)
            if not skip_missing:
                names_str = ", ".join(si.names[:5]) if si.names else "*"
                print(f"[IMPORT] Not found: {si.path} ({names_str})",
                      file=sys.stderr)

    return tree


def _find_local_file(path: str, search_dirs: list[str]) -> str | None:
    name = path.split(".")[-1]
    for base in search_dirs:
        for candidate in [
            os.path.join(base, name.lower() + ".tal"),
            os.path.join(base, name + ".tal"),
            os.path.join(base, name.lower()),
            os.path.join(base, name),
        ]:
            if os.path.isfile(candidate):
                return candidate
    return None


def _merge_file(program: Program, filepath: str, node: ImportNode,
                search_dirs: list[str], visited: set[str],
                skip_missing: bool) -> None:
    abs_path = os.path.abspath(filepath)
    if abs_path in visited:
        return
    visited.add(abs_path)

    try:
        source = open(filepath).read()
    except OSError:
        if not skip_missing:
            print(f"[IMPORT] Cannot read: {filepath}", file=sys.stderr)
        return

    tokens = Lexer(source).tokenize()
    included = Parser(tokens).parse(source_file=filepath)

    for decl in included.globals_:
        program.globals_.append(decl)
        node.n_globals += 1

    for proc in included.procedures:
        proc.is_extern = True
        program.procedures.append(proc)
        node.n_procs += 1

    for name, value in included.literals.items():
        if name not in program.literals:
            program.literals[name] = value
            node.n_literals += 1

    file_dir = os.path.dirname(abs_path)
    sub_dirs = [file_dir] + search_dirs

    for sub_si in included.source_imports:
        if sub_si.is_system:
            child = ImportNode(
                source_path=sub_si.path,
                names=sub_si.names,
                is_system=True,
            )
            node.children.append(child)
            continue
        local_file = _find_local_file(sub_si.path, sub_dirs)
        if local_file:
            child = ImportNode(
                source_path=sub_si.path,
                resolved_path=local_file,
                names=sub_si.names,
            )
            child_abs = os.path.abspath(local_file)
            if child_abs not in visited:
                _merge_file(program, local_file, child, sub_dirs, visited, skip_missing)
                sub_si.resolved = True
            node.children.append(child)
        else:
            child = ImportNode(
                source_path=sub_si.path,
                names=sub_si.names,
            )
            node.children.append(child)
            if not skip_missing:
                names_str = ", ".join(sub_si.names[:5]) if sub_si.names else "*"
                print(f"[IMPORT] Not found: {sub_si.path} ({names_str})",
                      file=sys.stderr)


def format_import_tree(tree: list[ImportNode], source_file: str) -> str:
    lines: list[str] = []
    basename = os.path.basename(source_file)
    lines.append(f"Import tree for {basename}:")

    resolved = 0
    unresolved = 0
    system = 0
    total_procs = 0
    total_globals = 0
    total_defines = 0

    def _count(node: ImportNode):
        nonlocal resolved, unresolved, system, total_procs, total_globals
        if node.is_system:
            system += 1
        elif node.resolved_path:
            resolved += 1
            total_procs += node.n_procs
            total_globals += node.n_globals
        else:
            unresolved += 1
        for c in node.children:
            _count(c)

    for node in tree:
        _count(node)

    def _show(nodes: list[ImportNode], prefix: str):
        for i, node in enumerate(nodes):
            last = (i == len(nodes) - 1)
            has_children = bool(node.children)
            if has_children:
                connector = "\u251c\u2500"
            elif last:
                connector = "\u2514\u2500"
            else:
                connector = "\u251c\u2500"
            if node.is_system:
                lines.append(f"{prefix}{connector} {node.source_path} [system]")
            elif node.resolved_path:
                label = os.path.basename(node.resolved_path)
                parts = []
                if node.n_procs:
                    parts.append(f"{node.n_procs}p")
                if node.n_globals:
                    parts.append(f"{node.n_globals}g")
                if node.n_literals:
                    parts.append(f"{node.n_literals}l")
                if node.n_defines:
                    parts.append(f"{node.n_defines}d")
                detail = f" ({', '.join(parts)})" if parts else ""
                lines.append(f"{prefix}{connector} {node.source_path} -> {label}{detail}")
                if node.children:
                    child_prefix = prefix + ("\u2502   " if not last else "    ")
                    _show(node.children, child_prefix)
            else:
                lines.append(f"{prefix}{connector} {node.source_path} [NOT FOUND]")

    _show(tree, "  ")

    lines.append("")
    parts = [f"{resolved} resolved"]
    if unresolved:
        parts.append(f"{unresolved} not found")
    if system:
        parts.append(f"{system} system")
    lines.append(f"Imports: {', '.join(parts)}")
    if total_procs or total_globals:
        lines.append(f"Imported: {total_procs} procedures, {total_globals} globals")

    return "\n".join(lines)


def resolve_templates(program: Program) -> int:
    template_map: dict[str, VarDecl] = {}
    for g in program.globals_:
        if g.is_template and g.tal_type == TalType.STRUCT and g.struct_fields is not None:
            template_map[g.name.upper()] = g

    resolved = 0

    def _resolve_in_list(decls: list[VarDecl]) -> None:
        nonlocal resolved
        for decl in decls:
            if (decl.tal_type == TalType.STRUCT
                    and decl.struct_fields is None
                    and decl.template_name):
                tmpl = template_map.get(decl.template_name.upper())
                if tmpl is not None:
                    decl.struct_fields = tmpl.struct_fields
                    resolved += 1

    _resolve_in_list(program.globals_)

    for proc in program.procedures:
        _resolve_in_list(proc.locals_)
        for sp in proc.subprocs:
            _resolve_in_list(sp.locals_)

    return resolved
