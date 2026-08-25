"""Preprocessor tests — collect_defines, expand_macros, _skip_define."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from segmsan.preprocessor import collect_defines, expand_macros
from segmsan.transformers.program import parse_program_src


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _preprocess(src: str) -> str:
    """collect_defines + expand_macros → return final source text."""
    macros, cleaned = collect_defines(src)
    expanded, _ = expand_macros(cleaned, macros)
    return expanded


# ---------------------------------------------------------------------------
# collect_defines
# ---------------------------------------------------------------------------

def test_collect_no_define():
    macros, cleaned = collect_defines("int x;\n")
    assert macros == []
    assert "int x;" in cleaned


def test_collect_simple_define():
    src = "define max = 100#;\nint x;\n"
    macros, cleaned = collect_defines(src)
    assert len(macros) == 1
    assert macros[0].name == "max"
    assert macros[0].params == []
    assert "100" in macros[0].body
    # define line replaced by blanks in cleaned source
    assert "define" not in cleaned.lower()
    assert "int x;" in cleaned


def test_collect_parametric_define():
    src = "define add(a, b) = a + b#;\n"
    macros, cleaned = collect_defines(src)
    assert macros[0].params == ["a", "b"]


def test_collect_multiline_define():
    src = (
        "define log(msg)=\n"
        "    BEGIN\n"
        "    write(msg);\n"
        "    END#;\n"
        "int x;\n"
    )
    macros, cleaned = collect_defines(src)
    assert macros[0].name == "log"
    assert macros[0].params == ["msg"]
    # cleaned preserves line count (blank lines in place of define body)
    assert cleaned.count('\n') == src.count('\n')
    assert "int x;" in cleaned


def test_collect_multi_name_define():
    # Real TAL syntax: one DEFINE statement can declare several macros,
    # each terminated by '#' and separated by ',', ending at the ';'
    # after the last '#'. Seen in production BASE24 sources, e.g.:
    #   define a = body_a #,
    #          b = body_b #;
    src = (
        "define moni_realtime_mde_d =\n"
        "                   ( flag^g = 1 )          #,\n"
        "         moni_oldptlf_mde_d   =\n"
        "                   ( flag^g = 2 )           #;\n"
        "int x;\n"
    )
    macros, cleaned = collect_defines(src)
    assert len(macros) == 2
    assert macros[0].name == "moni_realtime_mde_d"
    assert "flag^g = 1" in macros[0].body
    assert macros[1].name == "moni_oldptlf_mde_d"
    assert "flag^g = 2" in macros[1].body
    assert "define" not in cleaned.lower()
    assert cleaned.count('\n') == src.count('\n')
    assert "int x;" in cleaned


def test_collect_multi_name_define_with_params():
    # Multi-name form where entries also take parameters, e.g.:
    #   define halt^d( x ) = ... #, check^d( x ) = if <> then halt^d( x ) #;
    src = (
        "define halt^d( x )  = call abort( x ) #,\n"
        "       check^d( x ) = if <> then halt^d( x ) #;\n"
        "int x;\n"
    )
    macros, cleaned = collect_defines(src)
    assert len(macros) == 2
    assert macros[0].name == "halt^d"
    assert macros[0].params == ["x"]
    assert macros[1].name == "check^d"
    assert macros[1].params == ["x"]
    assert "int x;" in cleaned


def test_multi_name_define_parses_end_to_end():
    # Regression for a real parse failure: without multi-name DEFINE support,
    # the ',' after the first macro's '#' was left in the cleaned source and
    # broke the top-level declaration grammar.
    src = (
        "?SECTION test\n"
        "define   a_d =\n"
        "                   ( flag^g = 1 )          #,\n"
        "         b_d   =\n"
        "                   ( flag^g = 2 )           #;\n"
        "\n"
        "INT proc test^multi;\n"
        "BEGIN\n"
        "  INT flag^g;\n"
        "  IF a_d THEN\n"
        "    RETURN 1;\n"
        "  RETURN 0;\n"
        "END;\n"
    )
    program = parse_program_src(src)
    assert program is not None


# ---------------------------------------------------------------------------
# expand_macros — no-param macros
# ---------------------------------------------------------------------------

def test_expand_no_param_macro():
    src = "define maxval = 100#;\nint x := maxval;\n"
    result = _preprocess(src)
    assert "100" in result
    assert "maxval" not in result


def test_no_param_macro_not_expanded_mid_name():
    # 'max' in 'maxval' must NOT be expanded if macro is named 'max'
    src = "define max = 99#;\nint x := maxval;\n"
    result = _preprocess(src)
    # 'maxval' should remain unchanged — word-boundary \b prevents partial match
    assert "maxval" in result


# ---------------------------------------------------------------------------
# expand_macros — parametric macros
# ---------------------------------------------------------------------------

def test_expand_parametric_macro_called():
    src = "define double(x) = x + x#;\nint n := double(5);\n"
    result = _preprocess(src)
    assert "5 + 5" in result
    assert "double" not in result


def test_expand_parametric_macro_not_expanded_without_args():
    # Regression: macro with params must NOT expand when referenced without '('.
    # Before the fix, expand_macros would search for the next '(' anywhere in
    # the file and use it as the argument list, corrupting unrelated code.
    src = (
        "define log(msg)=\n"
        "    BEGIN\n"
        "    write(msg);\n"
        "    END#;\n"
        "?section log\n"           # 'log' here is a section name, not a call
        "int proc foo(params);\n"  # this '(' must NOT be stolen as log's args
        "begin\n"
        "    return 0;\n"
        "end;\n"
    )
    macros, cleaned = collect_defines(src)
    expanded, records = expand_macros(cleaned, macros)

    # '?section log' must stay as '?section log' — NOT become '?section BEGIN...'
    lines = expanded.split('\n')
    section_lines = [l for l in lines if '?section' in l.lower()]
    assert len(section_lines) == 1
    assert section_lines[0].strip() == '?section log'

    # The proc declaration must be intact — '(' was not stolen
    assert 'proc foo(params)' in expanded

    # No expansion records for the wrong match
    assert all(r.macro_name.lower() != 'log' for r in records)


def test_expand_parametric_macro_in_section_then_real_call():
    # Both the section reference and a real call exist.
    # Only the real call should be expanded.
    src = (
        "define log(msg)=\n"
        "    BEGIN\n"
        "    write(msg);\n"
        "    END#;\n"
        "?section log\n"
        "int proc foo;\n"
        "begin\n"
        "    log(\"hello\");\n"   # real call — must be expanded
        "    return 0;\n"
        "end;\n"
    )
    macros, cleaned = collect_defines(src)
    expanded, records = expand_macros(cleaned, macros)

    # Section line untouched
    section_lines = [l for l in expanded.split('\n') if '?section' in l.lower()]
    assert section_lines[0].strip() == '?section log'

    # Real call was expanded — body appears inside proc
    assert 'write' in expanded
    assert '"hello"' in expanded

    # Exactly one expansion record (the real call)
    log_records = [r for r in records if r.macro_name.lower() == 'log']
    assert len(log_records) == 1


def test_expand_multiple_calls_same_macro():
    src = "define sq(x) = x * x#;\nint a := sq(3);\nint b := sq(7);\n"
    result = _preprocess(src)
    assert "3 * 3" in result
    assert "7 * 7" in result


# ---------------------------------------------------------------------------
# Integration: parse_program_src must not choke on parametric defines
# ---------------------------------------------------------------------------

def test_parse_program_with_section_and_parametric_define():
    # Full integration regression for the ?section log / expand_macros bug.
    # Before the fix this raised:
    #   Unexpected token Token('LPAREN', '(') at line N, column M.
    src = (
        "define log(msg)=\n"
        "    BEGIN\n"
        "    write(msg);\n"
        "    END#;\n"
        "?section log\n"
        "int proc foo(params);\n"
        "string .params;\n"
        "begin\n"
        "    return 0;\n"
        "end;\n"
    )
    # Must not raise
    p = parse_program_src(src)
    assert any(pr.name == "foo" for pr in p.procedures)


def test_parse_program_parametric_define_call_expands():
    # define is used via a real call — expansion happens, program parses OK.
    src = (
        "define double(x) = x + x#;\n"
        "int proc foo;\n"
        "begin\n"
        "    int n := double(5);\n"
        "    return n;\n"
        "end;\n"
    )
    p = parse_program_src(src)
    assert any(pr.name == "foo" for pr in p.procedures)


# ---------------------------------------------------------------------------
# _skip_define via to_proc_body_stream
# ---------------------------------------------------------------------------

def test_skip_define_inside_proc_body():
    # A parametric define inside a proc body must be skipped entirely —
    # its body tokens must not reach the Lark parser.
    from segmsan.transformers.proc_body import parse_procedure_src
    src = (
        "int proc test;\n"
        "define log(msg)=\n"
        "    BEGIN\n"
        "    write(msg);\n"
        "    END#;\n"
        "begin\n"
        "    int x := 5;\n"
        "    return x;\n"
        "end;\n"
    )
    p = parse_procedure_src(src)
    assert p.name == "test"
    assert p.locals_[0].name == "x"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  OK  {fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"FAIL  {fn.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
