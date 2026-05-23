"""Phase 2 tests: struct declarations (grammar/struct_def.lark + transformers/struct_def.py)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from segmsan.lexer import Lexer
from segmsan.lexer import to_lark_stream
from segmsan.transformers.struct_def import parse_struct_decl
from segmsan.transformers.var_decl import parse_var_decl
from segmsan.ast_nodes import TalType, ArrayBounds

_STRUCT_KW_TERMINALS = frozenset({"KW_STRUCT", "KW_STRUCTURE"})


def _split_struct_chunks(lark_tokens):
    chunks = []
    i = 0
    n = len(lark_tokens)
    while i < n:
        if lark_tokens[i].type not in _STRUCT_KW_TERMINALS:
            i += 1
            continue
        chunk = [lark_tokens[i]]
        i += 1
        while i < n and lark_tokens[i].type != "SEMI":
            chunk.append(lark_tokens[i])
            i += 1
        if i < n:
            chunk.append(lark_tokens[i])
            i += 1
        if i < n and lark_tokens[i].type == "KW_BEGIN":
            depth = 0
            while i < n:
                tok = lark_tokens[i]
                chunk.append(tok)
                i += 1
                if tok.type == "KW_BEGIN":
                    depth += 1
                elif tok.type == "KW_END":
                    depth -= 1
                    if depth == 0:
                        if i < n and lark_tokens[i].type == "SEMI":
                            chunk.append(lark_tokens[i])
                            i += 1
                        break
        chunks.append(chunk)
    return chunks


def _parse_struct(source: str):
    """Parse a single struct_decl; returns first VarDecl (for single-item tests)."""
    raw = Lexer(source).tokenize()
    lark_tokens = list(to_lark_stream(raw))
    return parse_struct_decl(iter(lark_tokens))[0]


def _parse_structs(source: str):
    """Parse a multi-var struct_decl; returns list[VarDecl]."""
    raw = Lexer(source).tokenize()
    lark_tokens = list(to_lark_stream(raw))
    return parse_struct_decl(iter(lark_tokens))


def _parse_var(source: str):
    """Lex + adapt + parse a single var_decl statement from source."""
    raw = Lexer(source).tokenize()
    lark_tokens = list(to_lark_stream(raw))
    return parse_var_decl(iter(lark_tokens))


# ---------------------------------------------------------------------------
# Grupo 1 — Las 4 formas básicas
# ---------------------------------------------------------------------------

def test_template_struct():
    d = _parse_struct("STRUCT args^def (*); BEGIN INT x; END;")
    assert d.name == "args^def"
    assert d.tal_type == TalType.STRUCT
    assert d.is_template is True
    assert d.template_name == ""
    assert d.is_indirect is False
    assert d.struct_fields is not None
    assert len(d.struct_fields) == 1
    assert d.struct_fields[0].name == "x"
    assert d.struct_fields[0].tal_type == TalType.INT


def test_definition_direct():
    d = _parse_struct("STRUCT my^record; BEGIN INT a; STRING b; END;")
    assert d.name == "my^record"
    assert d.is_template is False
    assert d.is_indirect is False
    assert d.template_name == ""
    assert d.struct_fields is not None
    assert len(d.struct_fields) == 2
    assert d.struct_fields[0].name == "a"
    assert d.struct_fields[1].name == "b"


def test_definition_indirect():
    d = _parse_struct("STRUCT .my^record; BEGIN INT x; END;")
    assert d.name == "my^record"
    assert d.is_indirect is True
    assert d.is_extended is False
    assert d.struct_fields is not None


def test_definition_indirect_extended():
    d = _parse_struct("STRUCT .EXT big^rec; BEGIN INT x; END;")
    assert d.name == "big^rec"
    assert d.is_indirect is True
    assert d.is_extended is True
    assert d.struct_fields is not None


def test_referral():
    d = _parse_struct("STRUCT .args^actual (args^def);")
    assert d.name == "args^actual"
    assert d.is_indirect is True
    assert d.is_extended is False
    assert d.template_name == "args^def"
    assert d.is_template is False
    assert d.struct_fields is None


def test_referral_with_bounds():
    d = _parse_struct("STRUCT .EXT customer (record) [0:49];")
    assert d.name == "customer"
    assert d.is_indirect is True
    assert d.is_extended is True
    assert d.template_name == "record"
    assert d.array_bounds == ArrayBounds(0, 49)
    assert d.struct_fields is None


def test_referral_extended():
    d = _parse_struct("STRUCT .EXT s (tmpl);")
    assert d.name == "s"
    assert d.is_indirect is True
    assert d.is_extended is True
    assert d.template_name == "tmpl"
    assert d.struct_fields is None


# ---------------------------------------------------------------------------
# Grupo 2 — Cuerpos con distintos tipos de items
# ---------------------------------------------------------------------------

def test_body_all_types():
    src = """STRUCT all^types (*);
    BEGIN
    INT     a;
    STRING  b;
    REAL    c;
    FIXED   d;
    UNSIGNED e;
    END;"""
    d = _parse_struct(src)
    types = {f.name: f.tal_type for f in d.struct_fields}
    assert types["a"] == TalType.INT
    assert types["b"] == TalType.STRING
    assert types["c"] == TalType.REAL
    assert types["d"] == TalType.FIXED
    assert types["e"] == TalType.UNSIGNED


def test_body_array_field():
    d = _parse_struct("STRUCT s (*); BEGIN STRING lbl[0:9]; END;")
    f = d.struct_fields[0]
    assert f.name == "lbl"
    assert f.tal_type == TalType.STRING
    assert f.array_bounds == ArrayBounds(0, 9)


def test_body_multiple_fields_one_stmt():
    d = _parse_struct("STRUCT s (*); BEGIN INT x, y, z; END;")
    assert len(d.struct_fields) == 3
    names = [f.name for f in d.struct_fields]
    assert names == ["x", "y", "z"]


def test_substructure_direct():
    src = "STRUCT outer (*); BEGIN STRUCT inner; BEGIN INT a; END; INT b; END;"
    d = _parse_struct(src)
    names = {f.name for f in d.struct_fields}
    assert "inner" in names
    assert "b" in names
    inner = next(f for f in d.struct_fields if f.name == "inner")
    assert inner.tal_type == TalType.STRUCT
    assert inner.struct_fields is not None
    assert inner.struct_fields[0].name == "a"


def test_substructure_referral():
    src = "STRUCT outer (*); BEGIN STRUCT sub (tmpl) [0:3]; INT x; END;"
    d = _parse_struct(src)
    sub = next(f for f in d.struct_fields if f.name == "sub")
    assert sub.tal_type == TalType.STRUCT
    assert sub.template_name == "tmpl"
    assert sub.array_bounds == ArrayBounds(0, 3)
    assert sub.struct_fields is None  # referral — no body
    assert sub.is_indirect is False   # substructures are directly addressed


def test_substructure_array():
    src = "STRUCT outer (*); BEGIN STRUCT rgb [0:2]; BEGIN INT r; INT g; INT b; END; END;"
    d = _parse_struct(src)
    rgb = next(f for f in d.struct_fields if f.name == "rgb")
    assert rgb.array_bounds == ArrayBounds(0, 2)
    assert rgb.struct_fields is not None
    assert len(rgb.struct_fields) == 3


def test_filler():
    src = "STRUCT s (*); BEGIN INT x; FILLER 4; INT y; END;"
    d = _parse_struct(src)
    # FILLER items are discarded — only x and y in fields
    names = [f.name for f in d.struct_fields]
    assert names == ["x", "y"]


def test_bit_filler():
    src = "STRUCT s (*); BEGIN INT x; BIT_FILLER 8; INT y; END;"
    d = _parse_struct(src)
    names = [f.name for f in d.struct_fields]
    assert names == ["x", "y"]


# ---------------------------------------------------------------------------
# Grupo 3 — Redefiniciones (6 formas del spec)
# ---------------------------------------------------------------------------

def test_redef_simple():
    d = _parse_struct("STRUCT s (*); BEGIN INT x; INT lo = x; END;")
    lo = next(f for f in d.struct_fields if f.name == "lo")
    assert lo.is_equivalence is True
    assert lo.equivalence_target == "x"
    assert lo.array_bounds is None


def test_redef_array():
    d = _parse_struct("STRUCT s (*); BEGIN INT x; INT y[0:3] = x; END;")
    y = next(f for f in d.struct_fields if f.name == "y")
    assert y.is_equivalence is True
    assert y.equivalence_target == "x"
    assert y.array_bounds == ArrayBounds(0, 3)


def test_redef_indirect():
    d = _parse_struct("STRUCT s (*); BEGIN INT x; INT .p = x; END;")
    p = next(f for f in d.struct_fields if f.name == "p")
    assert p.is_equivalence is True
    assert p.equivalence_target == "x"
    assert p.is_indirect is True


def test_redef_string_array():
    d = _parse_struct("STRUCT s (*); BEGIN STRING lbl[0:9]; STRING y[0:9] = lbl; END;")
    y = next(f for f in d.struct_fields if f.name == "y")
    assert y.is_equivalence is True
    assert y.equivalence_target == "lbl"
    assert y.tal_type == TalType.STRING


def test_redef_struct_ptr():
    d = _parse_struct("STRUCT s (*); BEGIN INT x; INT .y (tmpl) = x; END;")
    y = next(f for f in d.struct_fields if f.name == "y")
    assert y.is_equivalence is True
    assert y.equivalence_target == "x"
    assert y.is_indirect is True
    assert y.template_name == "tmpl"


def test_redef_def_substructure():
    src = "STRUCT outer (*); BEGIN STRUCT sub; BEGIN INT a; END; STRUCT redef = sub; BEGIN INT b; END; END;"
    d = _parse_struct(src)
    redef = next(f for f in d.struct_fields if f.name == "redef")
    assert redef.is_equivalence is True
    assert redef.equivalence_target == "sub"
    assert redef.struct_fields is not None


def test_redef_referral_substructure():
    src = "STRUCT outer (*); BEGIN STRUCT sub (tmpl); STRUCT ref_redef (tmpl) = sub; END;"
    d = _parse_struct(src)
    ref_redef = next(f for f in d.struct_fields if f.name == "ref_redef")
    assert ref_redef.is_equivalence is True
    assert ref_redef.equivalence_target == "sub"
    assert ref_redef.template_name == "tmpl"
    assert ref_redef.struct_fields is None


# ---------------------------------------------------------------------------
# Grupo 4 — Structure pointers como campos
# ---------------------------------------------------------------------------

def test_struct_ptr_field():
    src = "STRUCT node (*); BEGIN STRUCT .left (node); INT value; END;"
    d = _parse_struct(src)
    left = next(f for f in d.struct_fields if f.name == "left")
    assert left.tal_type == TalType.STRUCT
    assert left.is_indirect is True
    assert left.is_extended is False
    assert left.template_name == "node"


def test_struct_ptr_field_extended():
    src = "STRUCT node (*); BEGIN STRUCT .EXT big (node); END;"
    d = _parse_struct(src)
    big = d.struct_fields[0]
    assert big.name == "big"
    assert big.is_indirect is True
    assert big.is_extended is True
    assert big.template_name == "node"


# ---------------------------------------------------------------------------
# Grupo 5 — Structure pointers standalone (via var_decl.lark actualizado)
# ---------------------------------------------------------------------------

def test_standalone_struct_ptr():
    decls = _parse_var("INT .ptr (args^def);")
    assert len(decls) == 1
    d = decls[0]
    assert d.name == "ptr"
    assert d.tal_type == TalType.INT
    assert d.is_indirect is True
    assert d.is_extended is False
    assert d.template_name == "args^def"


def test_standalone_struct_ptr_ext():
    decls = _parse_var("INT .EXT eptr (args^def);")
    assert len(decls) == 1
    d = decls[0]
    assert d.name == "eptr"
    assert d.is_indirect is True
    assert d.is_extended is True
    assert d.template_name == "args^def"


def test_standalone_struct_ptr_no_regression_phase1():
    """Phase 1 test: adding struct_ptr_ref? must not break plain var declarations."""
    decls = _parse_var("INT a, .b, c[0:3];")
    assert len(decls) == 3
    names = [d.name for d in decls]
    assert names == ["a", "b", "c"]
    assert decls[1].is_indirect is True
    assert decls[2].array_bounds == ArrayBounds(0, 3)
    # No template_name for plain vars
    assert decls[0].template_name == ""
    assert decls[1].template_name == ""


# ---------------------------------------------------------------------------
# Grupo 6 — Anidamiento profundo + substructure redefs
# ---------------------------------------------------------------------------

def test_nested_substructure():
    src = """STRUCT outer (*);
    BEGIN
    STRUCT middle (*);
        BEGIN
        STRUCT inner (*);
            BEGIN
            INT x;
            END;
        END;
    END;
    """
    d = _parse_struct(src)
    middle = d.struct_fields[0]
    inner = middle.struct_fields[0]
    assert inner.struct_fields[0].name == "x"


def test_mixed_body_types():
    src = """STRUCT s (*);
    BEGIN
    INT     a;
    FILLER  2;
    STRING  b[0:3];
    STRUCT  sub; BEGIN INT c; END;
    INT     d = a;
    BIT_FILLER 4;
    END;"""
    d = _parse_struct(src)
    names = [f.name for f in d.struct_fields]
    # FILLER and BIT_FILLER discarded
    assert "a" in names
    assert "b" in names
    assert "sub" in names
    assert "d" in names
    assert len(names) == 4
    d_field = next(f for f in d.struct_fields if f.name == "d")
    assert d_field.is_equivalence is True
    assert d_field.equivalence_target == "a"


def test_def_substructure_redef():
    src = """STRUCT outer (*);
    BEGIN
    STRUCT sub; BEGIN INT a; END;
    STRUCT new_sub = sub; BEGIN INT b; END;
    END;"""
    d = _parse_struct(src)
    new_sub = next(f for f in d.struct_fields if f.name == "new_sub")
    assert new_sub.is_equivalence is True
    assert new_sub.equivalence_target == "sub"
    assert new_sub.struct_fields is not None
    assert new_sub.struct_fields[0].name == "b"


def test_referral_substructure_redef():
    src = """STRUCT outer (*);
    BEGIN
    STRUCT abc (tmpl) [0:1];
    STRUCT xyz (tmpl) [0:1] = abc;
    END;"""
    d = _parse_struct(src)
    xyz = next(f for f in d.struct_fields if f.name == "xyz")
    assert xyz.is_equivalence is True
    assert xyz.equivalence_target == "abc"
    assert xyz.template_name == "tmpl"
    assert xyz.array_bounds == ArrayBounds(0, 1)
    assert xyz.struct_fields is None


def test_spec_referral_redef_example():
    """Spec Section 8 example: indirect parent, direct substructs, referral + redef."""
    src = """STRUCT temp (*);
    BEGIN
    STRING a[0:2];
    INT    b;
    END;
    STRUCT .ind_struct;
    BEGIN
    INT    header[0:1];
    STRING abyte;
    STRUCT abc (temp) [0:1];
    STRUCT xyz (temp) [0:1] = abc;
    END;"""
    # Parse two top-level structs
    from segmsan.lexer import to_lark_stream
    from segmsan.transformers.struct_def import parse_struct_decl
    raw = Lexer(src).tokenize()
    lark_tokens = list(to_lark_stream(raw))
    chunks = _split_struct_chunks(lark_tokens)
    assert len(chunks) == 2

    temp = parse_struct_decl(iter(chunks[0]))[0]
    assert temp.name == "temp"
    assert temp.is_template is True

    ind = parse_struct_decl(iter(chunks[1]))[0]
    assert ind.name == "ind_struct"
    assert ind.is_indirect is True
    assert ind.is_extended is False

    field_names = [f.name for f in ind.struct_fields]
    assert "header" in field_names
    assert "abc" in field_names
    assert "xyz" in field_names

    xyz = next(f for f in ind.struct_fields if f.name == "xyz")
    assert xyz.template_name == "tmpl" or xyz.template_name == "temp"
    assert xyz.is_equivalence is True
    assert xyz.equivalence_target == "abc"


# ---------------------------------------------------------------------------
# Group 21: Multi-var struct declarations (COMMA-separated)
# Bug: struct .fact (fact^def), .ptlf (ptlf^def);  → Unexpected token COMMA.
# Fix: struct_var_list rule accepts struct_head_ref (COMMA struct_var_item)* SEMI.
# ---------------------------------------------------------------------------

def test_struct_multi_two_referrals():
    # struct .fact (fact^def), .ptlf (ptlf^def);  — facpweds L896 pattern
    d = _parse_structs("STRUCT .fact (fact^def), .ptlf (ptlf^def);")
    assert len(d) == 2
    assert d[0].name == "fact"
    assert d[0].is_indirect is True
    assert d[0].template_name == "fact^def"
    assert d[1].name == "ptlf"
    assert d[1].is_indirect is True
    assert d[1].template_name == "ptlf^def"


def test_struct_multi_three_mixed():
    # struct .a (X), .b (Y), c;  — last item is bare def (no referral paren)
    d = _parse_structs("STRUCT .a (X), .b (Y), c;")
    assert len(d) == 3
    assert d[0].name == "a"
    assert d[0].template_name == "X"
    assert d[1].name == "b"
    assert d[1].template_name == "Y"
    assert d[2].name == "c"
    assert d[2].template_name == ""


def test_struct_single_referral_still_works():
    # Regression: struct .fact (fact^def);  — single-item via struct_var_list
    d = _parse_struct("STRUCT .fact (fact^def);")
    assert d.name == "fact"
    assert d.is_indirect is True
    assert d.template_name == "fact^def"


def test_struct_multi_with_array_bounds():
    # struct .a (X)[0:9], .b (Y);  — first item has array bounds
    d = _parse_structs("STRUCT .a (X)[0:9], .b (Y);")
    assert len(d) == 2
    assert d[0].name == "a"
    assert d[0].array_bounds == ArrayBounds(0, 9)
    assert d[1].name == "b"
    assert d[1].array_bounds is None


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
