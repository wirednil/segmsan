#!/usr/bin/env python3
"""Test runner for TAL analyzer."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from segmsan.lexer import Lexer
from segmsan.parser import Parser
from segmsan.checks import run_all_checks
from segmsan.report import format_report, WarningKind


def test_lexer():
    print("=== Lexer Test ===")
    source = 'INT .ptr := @local_buf;'
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    for t in tokens:
        print(f"  {t.type.name:20s} {t.value!r:20s} line={t.line} col={t.col}")
    assert len(tokens) > 0
    print(f"  OK: {len(tokens)} tokens\n")


def test_parser():
    print("=== Parser Test ===")
    source = """
PROC main;
    INT .ptr;
    INT buf[0:99];
    .ptr := @buf;
END;
"""
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    program = parser.parse("test.tal")
    print(f"  Procedures: {len(program.procedures)}")
    for proc in program.procedures:
        print(f"  PROC {proc.name}: {len(proc.locals_)} locals, {len(proc.body)} stmts")
        for loc in proc.locals_:
            print(f"    {loc.name}: indirect={loc.is_indirect} bounds={loc.array_bounds} size={loc.word_size()}")
        for stmt in proc.body:
            print(f"    stmt: {type(stmt).__name__}")
    assert len(program.procedures) == 1
    print("  OK\n")


def test_full_analysis():
    print("=== Full Analysis Test (sample1.tal) ===")
    test_dir = os.path.dirname(os.path.abspath(__file__))
    sample = os.path.join(test_dir, "sample1.tal")
    source = open(sample).read()

    lexer = Lexer(source)
    tokens = lexer.tokenize()
    print(f"  Tokens: {len(tokens)}")
    if lexer.errors:
        for e in lexer.errors:
            print(f"  Lexer error: {e.message} line={e.line}")

    parser = Parser(tokens)
    program = parser.parse(source_file=sample)
    print(f"  Globals: {len(program.globals_)}")
    print(f"  Procedures: {len(program.procedures)}")
    for proc in program.procedures:
        print(f"    {proc.name}: params={len(proc.params)} locals={len(proc.locals_)} "
              f"body={len(proc.body)} subprocs={len(proc.subprocs)} "
              f"recursive={proc.calls_self} largestack={proc.has_largestack}")

    warnings = run_all_checks(program)
    print(f"\n  Warnings: {len(warnings)}")
    for w in warnings:
        print(f"    [{w.severity}] Rule {w.rule}: {w.kind.name}")
        print(f"      {w.message}")

    report = format_report(warnings, sample)
    print()
    print(report)

    expected_rules = {
        WarningKind.DANGLING_POINTER_STORE,
        WarningKind.RECURSION_WITHOUT_LARGESTACK,
        WarningKind.SCAN_WITHOUT_CARRY_CHECK,
    }
    found_rules = {w.kind for w in warnings}
    print(f"\n  Expected rules found: {expected_rules & found_rules}")
    print(f"  Missing expected rules: {expected_rules - found_rules}")

    return len(warnings) > 0


if __name__ == "__main__":
    test_lexer()
    test_parser()
    success = test_full_analysis()
    if success:
        print("\nAll tests passed!")
    else:
        print("\nNo warnings found — check analyzer logic")
        sys.exit(1)
