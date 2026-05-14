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
from .preprocessor import preprocess, collect_defines, collect_defines_from_file, expand_macros
from .resolver import resolve_imports


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
        source, expansions = _preprocess_with_imports(source, base_dir)

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

    resolve_imports(program, base_dir, skip_missing=args.skip_missing_sources)

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

    if any(w.severity == Severity.CRITICAL for w in warnings):
        sys.exit(1)


def _preprocess_with_imports(source: str, base_dir: str):
    macros, cleaned = collect_defines(source)

    for m in re.finditer(r'SOURCE\s+([^\s,(]+)', source, re.IGNORECASE):
        path = m.group(1).strip()
        if path.upper().startswith("$SYSTEM."):
            continue
        name = path.split(".")[-1]
        for ext in [".tal", ""]:
            for c in [
                os.path.join(base_dir, name.lower() + ext),
                os.path.join(base_dir, name + ext),
            ]:
                if os.path.isfile(c):
                    macros.extend(collect_defines_from_file(c))
                    break

    _, cleaned = collect_defines(cleaned)
    return expand_macros(cleaned, macros)


if __name__ == "__main__":
    main()
