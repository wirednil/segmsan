"""Phase 5 tests: procedure and subprocedure headers."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from segmsan.lexer import Lexer
from segmsan.lexer import to_proc_header_stream
from segmsan.transformers.proc_header import parse_proc_header
from segmsan.ast_nodes import ParamDecl, ProcHeader, TalType


def _parse_header(source: str) -> ProcHeader:
    raw = Lexer(source).tokenize()
    lark_tokens = list(to_proc_header_stream(raw))
    return parse_proc_header(iter(lark_tokens))


# ---------------------------------------------------------------------------
# Grupo 1 — PROC básico
# ---------------------------------------------------------------------------

def test_proc_simple():
    h = _parse_header("PROC foo;")
    assert h.name == "foo"
    assert not h.is_subproc
    assert h.return_type is None
    assert h.params == []
    assert h.param_pairs == []
    assert not h.is_external
    assert not h.is_forward

def test_proc_name_case_preserved():
    h = _parse_header("PROC MyProc;")
    assert h.name == "MyProc"

def test_proc_no_attrs():
    h = _parse_header("PROC p;")
    assert not h.is_main
    assert not h.is_variable
    assert not h.is_callable
    assert not h.is_interrupt
    assert not h.is_priv
    assert not h.is_resident
    assert not h.is_extensible
    assert h.extensible_count is None
    assert h.language == ""
    assert h.public_name == ""

def test_proc_external():
    h = _parse_header("PROC ext_proc;\nEXTERNAL;")
    assert h.name == "ext_proc"
    assert h.is_external
    assert not h.is_forward

def test_proc_forward():
    h = _parse_header("PROC fwd_proc;\nFORWARD;")
    assert h.is_forward
    assert not h.is_external


# ---------------------------------------------------------------------------
# Grupo 2 — Return types
# ---------------------------------------------------------------------------

def test_return_type_int():
    h = _parse_header("INT PROC get_int;")
    assert h.return_type == TalType.INT

def test_return_type_int32():
    h = _parse_header("INT(32) PROC get_int32;")
    assert h.return_type == TalType.INT32

def test_return_type_real():
    h = _parse_header("REAL PROC get_real;")
    assert h.return_type == TalType.REAL

def test_return_type_real64():
    h = _parse_header("REAL(64) PROC get_real64;")
    assert h.return_type == TalType.REAL64

def test_return_type_fixed():
    h = _parse_header("FIXED PROC get_fixed;")
    assert h.return_type == TalType.FIXED

def test_return_type_unsigned():
    h = _parse_header("UNSIGNED PROC get_unsigned;")
    assert h.return_type == TalType.UNSIGNED

def test_return_type_string():
    h = _parse_header("STRING PROC get_string;")
    assert h.return_type == TalType.STRING

def test_return_type_none_void():
    h = _parse_header("PROC do_work;")
    assert h.return_type is None


# ---------------------------------------------------------------------------
# Grupo 3 — Public name (Binder)
# ---------------------------------------------------------------------------

def test_pub_name_simple():
    h = _parse_header('PROC my_proc = "my-proc";')
    assert h.public_name == "my-proc"

def test_pub_name_with_return_type():
    h = _parse_header('INT PROC my_func = "myfunc";')
    assert h.name == "my_func"
    assert h.public_name == "myfunc"
    assert h.return_type == TalType.INT

def test_pub_name_empty_when_absent():
    h = _parse_header("PROC p;")
    assert h.public_name == ""


# ---------------------------------------------------------------------------
# Grupo 4 — Parámetros: nombres y pares
# ---------------------------------------------------------------------------

def test_params_single_name():
    h = _parse_header("PROC foo(a);")
    assert len(h.params) == 1
    assert h.params[0].name == "a"

def test_params_multiple_names():
    h = _parse_header("PROC foo(a, b, c);")
    assert len(h.params) == 3
    names = [p.name for p in h.params]
    assert names == ["a", "b", "c"]

def test_params_default_type_int():
    h = _parse_header("PROC foo(x);")
    assert h.params[0].tal_type == TalType.INT

def test_params_param_pair():
    h = _parse_header("PROC foo(buf : len);")
    assert h.params == []
    assert len(h.param_pairs) == 1
    assert h.param_pairs[0] == ("buf", "len")

def test_params_mixed_name_and_pair():
    h = _parse_header("PROC foo(a, buf : len, b);")
    assert len(h.params) == 2
    assert h.params[0].name == "a"
    assert h.params[1].name == "b"
    assert len(h.param_pairs) == 1
    assert h.param_pairs[0] == ("buf", "len")

def test_params_no_params():
    h = _parse_header("PROC foo;")
    assert h.params == []
    assert h.param_pairs == []

def test_params_typed_int():
    h = _parse_header("PROC foo(INT x);")
    assert len(h.params) == 1
    p = h.params[0]
    assert p.name == "x"
    assert p.tal_type == TalType.INT
    assert not p.is_reference

def test_params_typed_ref():
    h = _parse_header("PROC foo(INT .x);")
    assert h.params[0].is_reference is True
    assert h.params[0].is_extended is False

def test_params_typed_ext_ref():
    h = _parse_header("PROC foo(INT .EXT x);")
    p = h.params[0]
    assert p.is_reference is True
    assert p.is_extended is True


# ---------------------------------------------------------------------------
# Grupo 5 — Atributos de procedimiento
# ---------------------------------------------------------------------------

def test_attr_main():
    h = _parse_header("PROC main_proc MAIN;")
    assert h.is_main

def test_attr_variable():
    h = _parse_header("PROC var_proc VARIABLE;")
    assert h.is_variable

def test_attr_callable():
    h = _parse_header("PROC cb CALLABLE;")
    assert h.is_callable

def test_attr_interrupt():
    h = _parse_header("PROC isr INTERRUPT;")
    assert h.is_interrupt

def test_attr_priv():
    h = _parse_header("PROC prv PRIV;")
    assert h.is_priv

def test_attr_resident():
    h = _parse_header("PROC res_proc RESIDENT;")
    assert h.is_resident

def test_attr_extensible():
    h = _parse_header("PROC ext_proc EXTENSIBLE;")
    assert h.is_extensible
    assert h.extensible_count is None

def test_attr_extensible_n():
    h = _parse_header("PROC ext_proc EXTENSIBLE(4);")
    assert h.is_extensible
    assert h.extensible_count == 4

def test_attr_language_c():
    h = _parse_header("PROC c_proc LANGUAGE C;")
    assert h.language == "C"

def test_attr_language_cobol():
    h = _parse_header("PROC cob LANGUAGE COBOL;")
    assert h.language == "COBOL"

def test_attr_language_fortran():
    h = _parse_header("PROC fort LANGUAGE FORTRAN;")
    assert h.language == "FORTRAN"

def test_attr_language_pascal():
    h = _parse_header("PROC pas LANGUAGE PASCAL;")
    assert h.language == "PASCAL"

def test_attr_language_unspecified():
    h = _parse_header("PROC u LANGUAGE UNSPECIFIED;")
    assert h.language == "UNSPECIFIED"

def test_attr_multiple():
    h = _parse_header("PROC p MAIN, RESIDENT, CALLABLE;")
    assert h.is_main
    assert h.is_resident
    assert h.is_callable


# ---------------------------------------------------------------------------
# Grupo 6 — EXTERNAL / FORWARD
# ---------------------------------------------------------------------------

def test_external_with_return_type():
    h = _parse_header("INT PROC ext_fn;\nEXTERNAL;")
    assert h.return_type == TalType.INT
    assert h.is_external

def test_forward_with_params():
    h = _parse_header("PROC fwd(a, b);\nFORWARD;")
    assert h.is_forward
    assert len(h.params) == 2

def test_no_ext_fwd():
    h = _parse_header("PROC local_proc;")
    assert not h.is_external
    assert not h.is_forward


# ---------------------------------------------------------------------------
# Grupo 7 — SUBPROC
# ---------------------------------------------------------------------------

def test_subproc_simple():
    h = _parse_header("SUBPROC bar;")
    assert h.name == "bar"
    assert h.is_subproc

def test_subproc_return_type():
    h = _parse_header("INT SUBPROC get_val;")
    assert h.return_type == TalType.INT
    assert h.is_subproc

def test_subproc_variable():
    h = _parse_header("SUBPROC varbar VARIABLE;")
    assert h.is_subproc
    assert h.is_variable

def test_subproc_no_variable_by_default():
    h = _parse_header("SUBPROC bar;")
    assert not h.is_variable

def test_subproc_with_params():
    h = _parse_header("SUBPROC bar(x, y);")
    assert h.is_subproc
    assert len(h.params) == 2

def test_subproc_flags_always_false():
    h = _parse_header("SUBPROC bar;")
    assert not h.is_main
    assert not h.is_callable
    assert not h.is_extensible
    assert not h.is_interrupt
    assert not h.is_priv
    assert not h.is_resident
    assert not h.is_external
    assert not h.is_forward
    assert h.public_name == ""
    assert h.language == ""


# ---------------------------------------------------------------------------
# Grupo 8 — Combinaciones completas
# ---------------------------------------------------------------------------

def test_full_proc_with_all():
    h = _parse_header('INT PROC full_proc = "full-proc" (a, b) MAIN, RESIDENT;')
    assert h.name == "full_proc"
    assert h.return_type == TalType.INT
    assert h.public_name == "full-proc"
    assert len(h.params) == 2
    assert h.is_main
    assert h.is_resident

def test_full_proc_external_with_attrs():
    h = _parse_header("PROC extern_fn CALLABLE, LANGUAGE C;\nEXTERNAL;")
    assert h.is_callable
    assert h.language == "C"
    assert h.is_external

def test_subproc_full():
    h = _parse_header("STRING SUBPROC fmt(buf : len) VARIABLE;")
    assert h.return_type == TalType.STRING
    assert h.is_subproc
    assert h.is_variable
    assert len(h.param_pairs) == 1
    assert h.param_pairs[0] == ("buf", "len")

def test_proc_extensible_with_language():
    h = _parse_header("PROC p EXTENSIBLE(2), LANGUAGE COBOL;")
    assert h.is_extensible
    assert h.extensible_count == 2
    assert h.language == "COBOL"

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback
    fns = {k: v for k, v in globals().items() if k.startswith("test_")}
    passed = failed = 0
    for name, fn in sorted(fns.items()):
        try:
            fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    total = passed + failed
    print(f"\n{'OK' if failed == 0 else 'FAILED'} — {passed}/{total} passed")
