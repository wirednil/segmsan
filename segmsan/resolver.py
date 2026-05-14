"""Dependency import resolver for TAL source files.

Resolves ?SOURCE directives to local files, merges globals/literals/procedures
from parsed includes into the main program. System stubs ($SYSTEM.SYSTEM.EXTDECS
etc.) are handled by system_stubs.py.
"""

from __future__ import annotations
import os
import sys
from .lexer import Lexer
from .parser import Parser
from .ast_nodes import Program, Procedure, SourceImport


def resolve_imports(program: Program, base_dir: str,
                    skip_missing: bool = False) -> None:
    for si in program.source_imports:
        if si.is_system:
            continue
        local_file = _find_local_file(si.path, base_dir)
        if local_file:
            _merge_file(program, local_file, si, skip_missing)
        elif not skip_missing:
            names_str = ", ".join(si.names[:5]) if si.names else "*"
            print(f"[IMPORT] Not found: {si.path} ({names_str})",
                  file=sys.stderr)


def _find_local_file(path: str, base_dir: str) -> str | None:
    name = path.split(".")[-1]
    candidates = [
        os.path.join(base_dir, name.lower() + ".tal"),
        os.path.join(base_dir, name + ".tal"),
        os.path.join(base_dir, name.lower()),
        os.path.join(base_dir, name),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def _merge_file(program: Program, filepath: str, si: SourceImport,
                skip_missing: bool) -> None:
    try:
        source = open(filepath).read()
    except OSError:
        if not skip_missing:
            print(f"[IMPORT] Cannot read: {filepath}", file=sys.stderr)
        return

    tokens = Lexer(source).tokenize()
    included = Parser(tokens).parse(source_file=filepath)

    n_globals = 0
    n_procs = 0
    n_literals = 0

    for decl in included.globals_:
        program.globals_.append(decl)
        n_globals += 1

    for proc in included.procedures:
        proc.is_extern = True
        program.procedures.append(proc)
        n_procs += 1

    for name, value in included.literals.items():
        if name not in program.literals:
            program.literals[name] = value
            n_literals += 1

    for sub_si in included.source_imports:
        if sub_si.is_system:
            continue
        local_file = _find_local_file(sub_si.path, os.path.dirname(filepath))
        if local_file:
            _merge_file(program, local_file, sub_si, skip_missing)

    si.resolved = True
    if not skip_missing:
        print(f"[IMPORT] Resolved: {si.path} -> {os.path.basename(filepath)} "
              f"({n_procs} procs, {n_globals} globals, {n_literals} literals)",
              file=sys.stderr)
