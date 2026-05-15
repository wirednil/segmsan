"""TAL Static Memory Analyzer CLI."""

import sys
import os
import re
import argparse
import json
from .lexer import Lexer
from .parser import Parser
from .checks import run_all_checks
from .report import format_report, format_json, Severity, WarningKind
from .preprocessor import (
    preprocess, collect_defines, collect_defines_recursive, expand_macros,
)
from .resolver import resolve_imports, resolve_templates, format_import_tree


def main():
    ap = argparse.ArgumentParser(
        prog="tal-analyzer",
        description="Static memory analyzer for TAL source code — detects memory bugs without execution",
    )
    ap.add_argument("source", help="TAL source file to analyze")
    ap.add_argument("-s", "--strict", action="store_true",
                    help="Only show CRITICAL and HIGH severity warnings")
    ap.add_argument("-f", "--format", choices=["text", "json"], default="text",
                    help="Output format (default: text)")
    ap.add_argument("--no-banner", action="store_true",
                    help="Suppress header banner")
    ap.add_argument("--skip-missing-sources", action="store_true",
                    help="Suppress warnings about unresolved ?SOURCE imports")
    ap.add_argument("--no-preprocess", action="store_true",
                    help="Skip DEFINE macro expansion")
    ap.add_argument("--padding", action="store_true",
                    help="Enable padding/waste analysis (LOW severity, off by default)")
    ap.add_argument("-I", "--import-dir", action="append", default=[],
                    dest="import_dirs",
                    help="Additional search directory for ?SOURCE imports (repeatable)")
    ap.add_argument("-bt", "--backtrace",
                    help="Call backtrace: func1:func2:...:funcN (use ... for auto-discover)")
    args = ap.parse_args()

    try:
        source = open(args.source).read()
    except FileNotFoundError:
        print(f"Error: file not found: {args.source}", file=sys.stderr)
        sys.exit(2)

    base_dir = os.path.dirname(os.path.abspath(args.source))
    original_lines = source.splitlines()
    expansions = []

    if not args.no_preprocess:
        source, expansions = _preprocess_recursive(source, base_dir, args.import_dirs)

    lexer = Lexer(source)
    tokens = lexer.tokenize()

    if lexer.errors:
        for err in lexer.errors:
            print(f"Lexer error: {err.message} (line {err.line}, col {err.col})",
                  file=sys.stderr)

    parser = Parser(tokens)
    try:
        program = parser.parse(source_file=args.source)
    except Exception as e:
        print(f"Parse error: {e}", file=sys.stderr)
        sys.exit(2)

    import_tree = resolve_imports(
        program, base_dir,
        skip_missing=args.skip_missing_sources,
        search_dirs=args.import_dirs,
    )

    resolve_templates(program)

    warnings = run_all_checks(program)

    if args.strict:
        warnings = [w for w in warnings if w.severity in (Severity.CRITICAL, Severity.HIGH)]

    if not args.padding:
        padding_kinds = {
            WarningKind.PADDING_WASTE_GLOBAL,
            WarningKind.PADDING_WASTE_LOCAL,
            WarningKind.PADDING_WASTE_SUBLOCAL,
            WarningKind.PADDING_WASTE_STRUCT,
        }
        warnings = [w for w in warnings if w.kind not in padding_kinds]

    if args.format == "json":
        print(json.dumps(format_json(warnings), indent=2))
    else:
        preprocessed_lines = source.splitlines()
        report = format_report(warnings, args.source, preprocessed_lines,
                               expansions=expansions, original_lines=original_lines)
        print(report)

        from .checks.storage import format_storage_summary
        print()
        print(format_storage_summary(program))

        if import_tree:
            print()
            print(format_import_tree(import_tree, args.source))

    if args.backtrace:
        from .backtrace import format_backtrace
        print()
        print(format_backtrace(program, args.backtrace))

    if any(w.severity == Severity.CRITICAL for w in warnings):
        sys.exit(1)


def _preprocess_recursive(source: str, base_dir: str,
                          search_dirs: list[str]):
    macros, cleaned = collect_defines(source)
    macros.extend(
        collect_defines_recursive(source, base_dir, search_dirs))
    _, cleaned = collect_defines(cleaned)
    return expand_macros(cleaned, macros)


if __name__ == "__main__":
    main()
