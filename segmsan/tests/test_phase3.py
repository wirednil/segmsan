"""Phase 3 tests: LITERAL declarations and DEFINE skip."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from segmsan.lexer import Lexer
from segmsan.lexer import to_lark_stream
from segmsan.transformers.literal_decl import parse_literal_decl
from segmsan.ast_nodes import TalType


def _parse_literal(source: str) -> list[tuple[str, int]]:
    """Lex + adapt + parse a single literal_decl statement from source."""
    raw = Lexer(source).tokenize()
    lark_tokens = list(to_lark_stream(raw))
    return parse_literal_decl(iter(lark_tokens))


def _stream_types(source: str) -> list[str]:
    """Return the list of terminal types from the Lark token stream for source."""
    raw = Lexer(source).tokenize()
    return [t.type for t in to_lark_stream(raw)]


# ---------------------------------------------------------------------------
# Grupo 1 — LITERAL básico (valores explícitos)
# ---------------------------------------------------------------------------

def test_literal_single():
    pairs = _parse_literal("LITERAL x = 5;")
    assert pairs == [("X", 5)]


def test_literal_multiple():
    pairs = _parse_literal("LITERAL a = 1, b = 2, c = 3;")
    assert pairs == [("A", 1), ("B", 2), ("C", 3)]


def test_literal_negative():
    pairs = _parse_literal("LITERAL x = -1;")
    assert pairs == [("X", -1)]


def test_literal_negative_large():
    pairs = _parse_literal("LITERAL x = -32768;")
    assert pairs == [("X", -32768)]


def test_literal_octal():
    pairs = _parse_literal("LITERAL x = %1000;")
    assert pairs == [("X", 0o1000)]   # 512


def test_literal_hex():
    pairs = _parse_literal("LITERAL x = %HFF;")
    assert pairs == [("X", 0xFF)]     # 255


def test_literal_binary():
    pairs = _parse_literal("LITERAL x = %B1010;")
    assert pairs == [("X", 0b1010)]   # 10


def test_literal_zero():
    pairs = _parse_literal("LITERAL x = 0;")
    assert pairs == [("X", 0)]


def test_literal_names_uppercased():
    pairs = _parse_literal("LITERAL max^len = 80;")
    assert pairs[0][0] == "MAX^LEN"


# ---------------------------------------------------------------------------
# Grupo 2 — Auto-increment
# ---------------------------------------------------------------------------

def test_auto_increment_all_omitted():
    pairs = _parse_literal("LITERAL a, b, c;")
    assert pairs == [("A", 0), ("B", 1), ("C", 2)]


def test_auto_increment_spec_example():
    # From spec Section 5: d=0, e=1, f=2, g=0(explicit), h=1, i=17(explicit), j=18, k=19
    pairs = _parse_literal("LITERAL d, e, f, g = 0, h, i = 17, j, k;")
    assert pairs == [
        ("D", 0), ("E", 1), ("F", 2),
        ("G", 0),
        ("H", 1),
        ("I", 17), ("J", 18), ("K", 19),
    ]


def test_auto_increment_first_omitted():
    pairs = _parse_literal("LITERAL x, y = 5;")
    assert pairs == [("X", 0), ("Y", 5)]


def test_auto_increment_after_explicit():
    pairs = _parse_literal("LITERAL a = 10, b, c;")
    assert pairs == [("A", 10), ("B", 11), ("C", 12)]


def test_auto_increment_reset_to_zero():
    pairs = _parse_literal("LITERAL x = 0, y;")
    assert pairs == [("X", 0), ("Y", 1)]


# ---------------------------------------------------------------------------
# Grupo 3 — DEFINE skip
# ---------------------------------------------------------------------------

def test_define_simple_not_in_stream():
    types = _stream_types("DEFINE x = body #;")
    assert "KW_DEFINE" not in types
    assert len(types) == 0   # all tokens consumed


def test_define_with_params_not_in_stream():
    types = _stream_types("DEFINE f(x) = x + 1 #;")
    assert "KW_DEFINE" not in types
    assert len(types) == 0


def test_define_multiple_entries_not_in_stream():
    types = _stream_types("DEFINE a = body1 #, b = body2 #;")
    assert "KW_DEFINE" not in types
    assert len(types) == 0


def test_define_does_not_affect_following_literal():
    # DEFINE skipped, LITERAL parsed normally
    types = _stream_types("DEFINE x = val #; LITERAL y = 5;")
    assert "KW_DEFINE" not in types
    assert "KW_LITERAL" in types
    # Stream contains LITERAL y = 5 ;
    pairs = _parse_literal("LITERAL y = 5;")
    assert pairs == [("Y", 5)]


def test_define_with_eq_in_body_not_in_stream():
    # Body contains = (assignment), must not terminate early
    types = _stream_types("DEFINE swap(a,b) = a := b #;")
    assert "KW_DEFINE" not in types
    assert len(types) == 0


# ---------------------------------------------------------------------------
# Grupo 4 — Edge cases
# ---------------------------------------------------------------------------

def test_dual_run_octal_lark_correct():
    pairs = _parse_literal("LITERAL x = %1000;")
    assert pairs == [("X", 512)]


# ---------------------------------------------------------------------------
# Grupo 5 — Edge cases y tipos de literales
# ---------------------------------------------------------------------------

def test_literal_int32_suffix():
    pairs = _parse_literal("LITERAL x = 14769D;")
    assert pairs == [("X", 14769)]


def test_literal_int32_negative():
    pairs = _parse_literal("LITERAL x = -100D;")
    assert pairs == [("X", -100)]


def test_literal_fixed_suffix():
    pairs = _parse_literal("LITERAL x = 1200F;")
    assert pairs == [("X", 1200)]


def test_literal_char_lit():
    pairs = _parse_literal('LITERAL x = "A";')
    assert pairs == [("X", ord("A"))]   # 65


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
