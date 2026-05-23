"""Phase 1 tests — Variable Declarations (Lark grammar + transformer)."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from segmsan.lexer import Lexer
from segmsan.lexer import to_lark_stream
from segmsan.transformers.var_decl import parse_var_decl
from segmsan.ast_nodes import TalType, ArrayBounds


def _parse(source: str):
    tokens = Lexer(source).tokenize()
    return parse_var_decl(to_lark_stream(tokens))


def test_int_simple():
    d = _parse("INT x;")
    assert len(d) == 1
    assert d[0].name == "x"
    assert d[0].tal_type == TalType.INT
    assert not d[0].is_indirect
    assert not d[0].has_initializer
    assert d[0].array_bounds is None


def test_int32():
    d = _parse("INT(32) dblwd;")
    assert d[0].tal_type == TalType.INT32


def test_real():
    d = _parse("REAL flt;")
    assert d[0].tal_type == TalType.REAL


def test_real64():
    d = _parse("REAL(64) quad;")
    assert d[0].tal_type == TalType.REAL64


def test_fixed():
    d = _parse("FIXED(3) price;")
    assert d[0].tal_type == TalType.FIXED


def test_unsigned():
    d = _parse("UNSIGNED(5) flavor;")
    assert d[0].tal_type == TalType.UNSIGNED


def test_string():
    d = _parse("STRING b;")
    assert d[0].tal_type == TalType.STRING


# ---------------------------------------------------------------------------
# Multiple identifiers per statement
# ---------------------------------------------------------------------------

def test_multiple_vars():
    d = _parse("INT a, b, c;")
    assert len(d) == 3
    assert [x.name for x in d] == ["a", "b", "c"]
    assert all(x.tal_type == TalType.INT for x in d)


def test_multiple_vars_mixed_init():
    d = _parse("INT a, b := 5, c;")
    assert len(d) == 3
    assert not d[0].has_initializer
    assert d[1].has_initializer
    assert not d[2].has_initializer


# ---------------------------------------------------------------------------
# Initializers
# ---------------------------------------------------------------------------

def test_init_integer():
    d = _parse("INT x := 5;")
    assert d[0].has_initializer


def test_init_negative():
    d = _parse("INT x := -32;")
    assert d[0].has_initializer


def test_init_string_lit():
    d = _parse('STRING y := "A";')
    assert d[0].has_initializer


def test_init_char_lit():
    d = _parse("INT a := \"AB\";")
    assert d[0].has_initializer


def test_init_octal():
    d = _parse("INT c := %B110;")
    assert d[0].has_initializer


def test_init_int32():
    d = _parse("INT(32) dblwd := %B1011101D;")
    assert d[0].has_initializer


def test_init_real():
    d = _parse("REAL flt := 365335.6E-3;")
    assert d[0].has_initializer


def test_init_real64():
    d = _parse("REAL(64) flt2 := 2718.2818284590452L-3;")
    assert d[0].has_initializer


def test_init_fixed():
    d = _parse("FIXED(-3) f := 642987F;")
    assert d[0].tal_type == TalType.FIXED
    assert d[0].has_initializer


# ---------------------------------------------------------------------------
# Arrays
# ---------------------------------------------------------------------------

def test_array_simple():
    d = _parse("STRING buf[0:79];")
    assert d[0].tal_type == TalType.STRING
    assert d[0].array_bounds == ArrayBounds(0, 79)


def test_array_int():
    d = _parse("INT arr[0:9];")
    assert d[0].array_bounds == ArrayBounds(0, 9)


def test_array_with_init_list():
    d = _parse("INT arr[0:2] := [1, 2, 3];")
    assert d[0].array_bounds == ArrayBounds(0, 2)
    assert d[0].has_initializer


def test_array_with_repetition():
    d = _parse("INT b[0:9] := 10 * [0];")
    assert d[0].array_bounds == ArrayBounds(0, 9)
    assert d[0].has_initializer


def test_array_string_init():
    d = _parse('STRING msg[0:9] := "hello";')
    assert d[0].array_bounds == ArrayBounds(0, 9)
    assert d[0].has_initializer


# ---------------------------------------------------------------------------
# Indirection
# ---------------------------------------------------------------------------

def test_indirect_standard():
    d = _parse("INT .ptr;")
    assert d[0].is_indirect
    assert not d[0].is_extended


def test_indirect_extended():
    d = _parse("INT .EXT eptr;")
    assert d[0].is_indirect
    assert d[0].is_extended


# ---------------------------------------------------------------------------
# Source location
# ---------------------------------------------------------------------------

def test_location_line():
    d = _parse("INT x;")
    assert d[0].loc.line == 1


# ---------------------------------------------------------------------------
# Regression — TRUE/FALSE as global initializers
#   Fix: lexer always emits TRUE/FALSE as NAME; var_decl.lark init_val accepts NAME.
#   Previously: KW_FALSE/KW_TRUE were emitted in non-LITERAL contexts → parse error.
# ---------------------------------------------------------------------------

def test_init_false():
    # int x := false;  used to raise Unexpected token Token('KW_FALSE', 'false')
    d = _parse("INT x := false;")
    assert d[0].name == "x"
    assert d[0].has_initializer


def test_init_true():
    d = _parse("INT x := true;")
    assert d[0].has_initializer


def test_init_named_constant():
    # Named LITERAL constant as global initializer — same NAME path as true/false.
    d = _parse("INT x := maxval;")
    assert d[0].has_initializer


# ---------------------------------------------------------------------------
# Group: Comment handling in lexer
# Bug: _skip_comment terminated on second ! inside comment, leaving
# trailing tokens as code.  TAL comments run from ! to end-of-line.
# ---------------------------------------------------------------------------

def test_comment_with_internal_exclamation():
    from segmsan.lexer import Lexer
    src = 'INT x := 1; ! 1025 words! OVERFLOW WARNING\nINT y := 2;\n'
    tokens = Lexer(src).tokenize()
    idents = [t.value for t in tokens if str(t.type) == 'TokenType.IDENT']
    assert 'OVERFLOW' not in idents
    assert sum(1 for t in tokens if str(t.type) == 'TokenType.NUMBER') == 2


def test_comment_banner_still_works():
    from segmsan.lexer import Lexer
    src = '!--#############################################################--!\nINT x := 1;\n'
    tokens = Lexer(src).tokenize()
    names = [t.value for t in tokens if str(t.type) == 'TokenType.IDENT']
    assert 'x' in names


def test_comment_end_of_line_with_bang():
    from segmsan.lexer import Lexer
    src = 'END; ! of proc... !\nINT x := 1;\n'
    tokens = Lexer(src).tokenize()
    idents = [t.value for t in tokens if str(t.type) == 'TokenType.IDENT']
    assert 'of' not in idents


def test_bang_define_not_broken():
    from segmsan.lexer import Lexer
    src = '!my_macro!\nINT x := 1;\n'
    tokens = Lexer(src).tokenize()
    names = [t.value for t in tokens if str(t.type) == 'TokenType.IDENT']
    assert 'my_macro' in names


def test_double_dash_comment_still_works():
    from segmsan.lexer import Lexer
    src = 'INT x := 1; -- this is a comment\nINT y := 2;\n'
    tokens = Lexer(src).tokenize()
    assert sum(1 for t in tokens if str(t.type) == 'TokenType.NUMBER') == 2


# ---------------------------------------------------------------------------
# Group 19: Public name with initializer in var_decl
# Bug: string table = 'p' := ["line1", 0]; failed because
# initializer : EQ init_val consumed EQ STRING_LIT, leaving ASSIGN unparsed.
# Fix: var_initializer with pub_name_init : EQ STRING_LIT ASSIGN init_val.
# LALR(1): after EQ STRING_LIT, lookahead ASSIGN → shift (pub_name_init);
#          other lookahead → reduce STRING_LIT as literal_val (eq_init).
# ---------------------------------------------------------------------------

def test_var_public_name_with_init():
    # string table = 'p' := ["line1", "line2", 0];  — genlibs pattern
    d = _parse("STRING .table[0:99] = 'p' := [\"line1\", 0];")
    assert len(d) == 1
    assert d[0].has_initializer
    assert d[0].public_name == "p"

def test_var_public_name_with_constant_list():
    # string table = 'p' := ["a", "b", "c", 0];
    d = _parse("STRING .table[0:9] = 'p' := [\"a\", \"b\", \"c\", 0];")
    assert len(d) == 1
    assert d[0].has_initializer
    assert d[0].public_name == "p"

def test_var_eq_init_still_works():
    # Regression: INT x = 5; — eq_init form
    d = _parse("INT x = 5;")
    assert d[0].has_initializer
    assert d[0].public_name == ""

def test_var_assign_init_still_works():
    # Regression: INT x := 5; — assign_init form
    d = _parse("INT x := 5;")
    assert d[0].has_initializer
    assert d[0].public_name == ""

def test_var_string_init_eq():
    # STRING name = "hello"; — EQ STRING_LIT without ASSIGN → eq_init, not pub_name
    d = _parse('STRING .name[0:9] = "hello";')
    assert d[0].has_initializer
    assert d[0].public_name == ""

def test_var_no_init_still_works():
    # Regression: INT x; — no initializer
    d = _parse("INT x;")
    assert not d[0].has_initializer
    assert d[0].public_name == ""

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
