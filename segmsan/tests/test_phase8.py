"""Phase 8 tests: Complete procedure body parser.

Tests cover TAL Section 13 procedure declarations:
  - Minimal proc/external/forward
  - Proc attributes (MAIN, CALLABLE, EXTENSIBLE, etc.)
  - Parameter specifications (typed param declarations after SEMI)
  - Local variable declarations
  - ENTRY and LABEL declarations
  - DEFINE declarations (parsed and ignored)
  - Subprocedure declarations (full and FORWARD)
  - Body statements (smoke-tests complex stmts in proc context)
  - Nested subproc with locals
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from segmsan.transformers.proc_body import parse_procedure_src
from segmsan.ast_nodes import (
    Procedure, ParamDecl, ParamSpec, VarDecl, TalType,
    AssignStmt, ReturnStmt, IfStmt, WhileStmt, ForStmt,
    CaseStmt, CompoundStmt,
)


_PASS = []
_FAIL = []


def _run(name: str, fn):
    try:
        fn()
        _PASS.append(name)
    except Exception as e:
        _FAIL.append((name, e))


def _parse(src: str) -> Procedure:
    return parse_procedure_src(src)


# ─────────────────────────────────────────────────────────────────────────────
# Group 1: Minimal proc forms
# ─────────────────────────────────────────────────────────────────────────────

def test_minimal_void_proc():
    p = _parse("PROC foo; BEGIN END;")
    assert isinstance(p, Procedure)
    assert p.name == "foo"
    assert p.return_type is None
    assert p.body == []
_run("test_minimal_void_proc", test_minimal_void_proc)

def test_minimal_int_proc():
    p = _parse("INT PROC foo; BEGIN END;")
    assert p.name == "foo"
    assert p.return_type == TalType.INT
_run("test_minimal_int_proc", test_minimal_int_proc)

def test_minimal_string_proc():
    p = _parse("STRING PROC foo; BEGIN RETURN 0; END;")
    assert p.return_type == TalType.STRING
_run("test_minimal_string_proc", test_minimal_string_proc)

def test_proc_external():
    p = _parse("INT PROC foo; EXTERNAL;")
    assert p.is_external
    assert p.name == "foo"
    assert p.return_type == TalType.INT
_run("test_proc_external", test_proc_external)

def test_proc_external_void():
    p = _parse("PROC bar; EXTERNAL;")
    assert p.is_external
    assert p.return_type is None
_run("test_proc_external_void", test_proc_external_void)

def test_proc_forward():
    p = _parse("INT PROC foo; FORWARD;")
    assert p.is_forward
    assert not p.is_external
_run("test_proc_forward", test_proc_forward)

def test_proc_with_params_header():
    p = _parse("INT PROC foo(x, y); BEGIN RETURN x; END;")
    assert [pd.name for pd in p.params] == ["x", "y"]
_run("test_proc_with_params_header", test_proc_with_params_header)

def test_proc_public_name():
    p = _parse('INT PROC foo = "FOOBAZ"; BEGIN END;')
    assert p.public_name == "FOOBAZ"
_run("test_proc_public_name", test_proc_public_name)


# ─────────────────────────────────────────────────────────────────────────────
# Group 2: Proc attributes
# ─────────────────────────────────────────────────────────────────────────────

def test_attr_main():
    p = _parse("INT PROC foo MAIN; BEGIN END;")
    assert p.is_main
_run("test_attr_main", test_attr_main)

def test_attr_callable():
    p = _parse("PROC foo CALLABLE; BEGIN END;")
    assert p.is_callable
_run("test_attr_callable", test_attr_callable)

def test_attr_interrupt():
    p = _parse("PROC foo INTERRUPT; BEGIN END;")
    assert p.is_interrupt
_run("test_attr_interrupt", test_attr_interrupt)

def test_attr_priv():
    p = _parse("PROC foo PRIV; BEGIN END;")
    assert p.is_priv
_run("test_attr_priv", test_attr_priv)

def test_attr_resident():
    p = _parse("PROC foo RESIDENT; BEGIN END;")
    assert p.is_resident
_run("test_attr_resident", test_attr_resident)

def test_attr_extensible():
    p = _parse("PROC foo EXTENSIBLE; BEGIN END;")
    assert p.is_extensible
_run("test_attr_extensible", test_attr_extensible)

def test_attr_extensible_n():
    p = _parse("PROC foo EXTENSIBLE(4); BEGIN END;")
    assert p.is_extensible
    assert p.extensible_count == 4
_run("test_attr_extensible_n", test_attr_extensible_n)


# ─────────────────────────────────────────────────────────────────────────────
# Group 3: Parameter type specifications
# ─────────────────────────────────────────────────────────────────────────────

def test_param_spec_int():
    p = _parse("PROC foo(x); INT x; BEGIN END;")
    assert p.params[0].name == "x"
    # INT x; is a param type declaration — filtered from locals_
    assert not any(v.name == "x" for v in p.locals_)
_run("test_param_spec_int", test_param_spec_int)

def test_param_spec_string_ref():
    p = _parse("PROC foo(s); STRING .s; BEGIN END;")
    assert p.params[0].name == "s"
    # STRING .s; is a param type declaration — filtered from locals_
    assert not any(v.name == "s" for v in p.locals_)
_run("test_param_spec_string_ref", test_param_spec_string_ref)

def test_param_spec_proc():
    p = _parse("PROC foo(cb); PROC cb; BEGIN END;")
    assert len(p.param_specs) == 1
    assert p.param_specs[0].name == "cb"
    assert p.param_specs[0].param_type == "PROC"
_run("test_param_spec_proc", test_param_spec_proc)

def test_param_spec_typed_proc():
    p = _parse("PROC foo(cb); INT PROC cb; BEGIN END;")
    ps = p.param_specs[0]
    assert ps.param_type == "PROC"
    assert ps.return_type == "INT"
_run("test_param_spec_typed_proc", test_param_spec_typed_proc)

def test_param_spec_proc32():
    p = _parse("PROC foo(cb); PROC(32) cb; BEGIN END;")
    assert p.param_specs[0].param_type == "PROC"
_run("test_param_spec_proc32", test_param_spec_proc32)

def test_param_spec_multiple():
    p = _parse("PROC foo(a, b, c); INT a; STRING .b; INT c; BEGIN END;")
    # All three are param type declarations — filtered from locals_
    assert len(p.locals_) == 0
    assert len(p.params) == 3
    names = [v.name for v in p.params]
    assert "a" in names and "b" in names and "c" in names
_run("test_param_spec_multiple", test_param_spec_multiple)


# ─────────────────────────────────────────────────────────────────────────────
# Group 4: Local declarations
# ─────────────────────────────────────────────────────────────────────────────

def test_local_simple_var():
    p = _parse("PROC foo; INT x; BEGIN END;")
    assert len(p.locals_) == 1
    assert p.locals_[0].name == "x"
    assert p.locals_[0].tal_type == TalType.INT
_run("test_local_simple_var", test_local_simple_var)

def test_local_array():
    p = _parse("PROC foo; INT arr[0:9]; BEGIN END;")
    v = p.locals_[0]
    assert v.name == "arr"
    assert v.array_bounds.lo == 0
    assert v.array_bounds.hi == 9
_run("test_local_array", test_local_array)

def test_local_multiple_types():
    p = _parse("PROC foo; INT x; STRING s[0:63]; BEGIN END;")
    names = {v.name: v.tal_type for v in p.locals_}
    assert names["x"] == TalType.INT
    assert names["s"] == TalType.STRING
_run("test_local_multiple_types", test_local_multiple_types)

def test_local_pointer():
    p = _parse("PROC foo; INT .p; BEGIN END;")
    v = p.locals_[0]
    assert v.is_indirect
_run("test_local_pointer", test_local_pointer)

def test_local_struct():
    # Another decl after the struct forces struct_no_body to reduce before BEGIN
    p = _parse("PROC foo; STRUCT s(tmpl); INT x; BEGIN END;")
    assert any(v.name == "s" and v.tal_type == TalType.STRUCT for v in p.locals_)
_run("test_local_struct", test_local_struct)

def test_local_literal():
    p = _parse("PROC foo; LITERAL a = 1, b = 2; BEGIN END;")
    # literal_decl returns list of tuples → no VarDecl locals added, just silently consumed
    assert isinstance(p, Procedure)
_run("test_local_literal", test_local_literal)

def test_local_entry_point():
    p = _parse("PROC foo; ENTRY ep1, ep2; BEGIN END;")
    assert "ep1" in p.entry_points
    assert "ep2" in p.entry_points
_run("test_local_entry_point", test_local_entry_point)

def test_local_label_decl():
    p = _parse("PROC foo; LABEL lbl1, lbl2; BEGIN END;")
    assert "lbl1" in p.label_decls
    assert "lbl2" in p.label_decls
_run("test_local_label_decl", test_local_label_decl)


# ─────────────────────────────────────────────────────────────────────────────
# Group 5: Subprocedure declarations
# ─────────────────────────────────────────────────────────────────────────────

def test_subproc_minimal():
    p = _parse("""
INT PROC foo;
  INT SUBPROC bar;
  BEGIN
    RETURN 0;
  END;
BEGIN
  RETURN bar;
END;
""")
    assert len(p.subprocs) == 1
    sub = p.subprocs[0]
    assert sub.name == "bar"
    assert sub.return_type == TalType.INT
    assert sub.is_subproc
_run("test_subproc_minimal", test_subproc_minimal)

def test_subproc_void():
    p = _parse("""
PROC foo;
  SUBPROC helper;
  BEGIN END;
BEGIN END;
""")
    assert p.subprocs[0].name == "helper"
    assert p.subprocs[0].return_type is None
_run("test_subproc_void", test_subproc_void)

def test_subproc_forward():
    p = _parse("""
PROC foo;
  INT SUBPROC bar; FORWARD;
BEGIN
  RETURN 0;
END;
""")
    assert p.subprocs[0].is_forward
_run("test_subproc_forward", test_subproc_forward)

def test_subproc_with_params():
    p = _parse("""
PROC foo;
  INT SUBPROC bar(x, y);
  BEGIN RETURN x; END;
BEGIN END;
""")
    sub = p.subprocs[0]
    assert [pd.name for pd in sub.params] == ["x", "y"]
_run("test_subproc_with_params", test_subproc_with_params)

def test_subproc_with_locals():
    p = _parse("""
PROC foo;
  SUBPROC bar;
  INT tmp;
  BEGIN tmp := 1; END;
BEGIN END;
""")
    sub = p.subprocs[0]
    assert sub.locals_[0].name == "tmp"
_run("test_subproc_with_locals", test_subproc_with_locals)

def test_subproc_variable():
    p = _parse("""
PROC foo;
  SUBPROC bar VARIABLE;
  BEGIN END;
BEGIN END;
""")
    assert p.subprocs[0].is_variable
_run("test_subproc_variable", test_subproc_variable)

def test_two_subprocs():
    p = _parse("""
PROC foo;
  SUBPROC a; BEGIN END;
  SUBPROC b; BEGIN END;
BEGIN END;
""")
    names = [s.name for s in p.subprocs]
    assert "a" in names and "b" in names
_run("test_two_subprocs", test_two_subprocs)


# ─────────────────────────────────────────────────────────────────────────────
# Group 6: Body statements in proc context
# ─────────────────────────────────────────────────────────────────────────────

def test_body_assign():
    p = _parse("PROC foo; INT x; BEGIN x := 1; END;")
    assert len(p.body) == 1
    assert isinstance(p.body[0], AssignStmt)
_run("test_body_assign", test_body_assign)

def test_body_return():
    p = _parse("INT PROC foo; BEGIN RETURN 42; END;")
    assert isinstance(p.body[0], ReturnStmt)
_run("test_body_return", test_body_return)

def test_body_if():
    p = _parse("PROC foo; BEGIN IF x > 0 THEN x := 1; END;")
    assert isinstance(p.body[0], IfStmt)
_run("test_body_if", test_body_if)

def test_body_while():
    p = _parse("PROC foo; BEGIN WHILE x > 0 DO x := x - 1; END;")
    assert isinstance(p.body[0], WhileStmt)
_run("test_body_while", test_body_while)

def test_body_for():
    p = _parse("PROC foo; BEGIN FOR i := 0 TO 9 DO arr[i] := 0; END;")
    assert isinstance(p.body[0], ForStmt)
_run("test_body_for", test_body_for)

def test_body_compound():
    p = _parse("PROC foo; BEGIN BEGIN x := 1; y := 2; END; END;")
    assert isinstance(p.body[0], CompoundStmt)
_run("test_body_compound", test_body_compound)

def test_body_multiple_stmts():
    p = _parse("PROC foo; INT x; BEGIN x := 1; x := x + 1; RETURN x; END;")
    assert len(p.body) == 3
_run("test_body_multiple_stmts", test_body_multiple_stmts)


# ─────────────────────────────────────────────────────────────────────────────
# Group 7: Complete realistic procedures
# ─────────────────────────────────────────────────────────────────────────────

def test_complete_proc_sum():
    p = _parse("""
INT PROC sum(a, b);
INT a;
INT b;
BEGIN
  RETURN a + b;
END;
""")
    assert p.name == "sum"
    assert p.return_type == TalType.INT
    assert len(p.params) == 2
    assert len(p.locals_) == 0  # INT a; INT b; are param type decls, filtered
    assert len(p.body) == 1
    assert isinstance(p.body[0], ReturnStmt)
_run("test_complete_proc_sum", test_complete_proc_sum)

def test_complete_proc_with_subproc():
    p = _parse("""
INT PROC outer(n);
INT n;
  INT SUBPROC helper;
  BEGIN
    RETURN n + 1;
  END;
BEGIN
  RETURN helper;
END;
""")
    assert p.name == "outer"
    assert len(p.locals_) == 0  # INT n; is a param type decl, filtered
    assert p.subprocs[0].name == "helper"
    assert len(p.body) == 1
_run("test_complete_proc_with_subproc", test_complete_proc_with_subproc)

def test_complete_proc_main():
    p = _parse("""
INT PROC talproc MAIN;
INT x;
BEGIN
  x := 0;
  WHILE x < 10 DO
    x := x + 1;
  RETURN x;
END;
""")
    assert p.is_main
    assert p.locals_[0].name == "x"
    assert isinstance(p.body[1], WhileStmt)
_run("test_complete_proc_main", test_complete_proc_main)

def test_proc_with_entry_and_labels():
    p = _parse("""
PROC foo;
ENTRY alt_entry;
LABEL loop_top;
INT i;
BEGIN
  i := 0;
END;
""")
    assert "alt_entry" in p.entry_points
    assert "loop_top" in p.label_decls
    assert p.locals_[0].name == "i"
_run("test_proc_with_entry_and_labels", test_proc_with_entry_and_labels)


# ─────────────────────────────────────────────────────────────────────────────
# Group 8: BUG fixes — flexible BEGIN placement
# ─────────────────────────────────────────────────────────────────────────────

def test_locals_inside_begin():
    # BUG 1 fix: spec says locals go inside BEGIN...END
    p = _parse("PROC foo; BEGIN INT x; x := 1; END;")
    assert len(p.locals_) == 1
    assert p.locals_[0].name == "x"
    assert len(p.body) == 1
    assert isinstance(p.body[0], AssignStmt)
_run("test_locals_inside_begin", test_locals_inside_begin)

def test_begin_optional():
    # TAL files allow omitting BEGIN
    p = _parse("PROC foo; INT x; x := 1; END;")
    assert len(p.locals_) == 1
    assert p.locals_[0].name == "x"
    assert len(p.body) == 1
    assert isinstance(p.body[0], AssignStmt)
_run("test_begin_optional", test_begin_optional)

def test_locals_before_and_after_begin():
    p = _parse("PROC foo; INT a; BEGIN INT b; a := 1; b := 2; END;")
    names = [v.name for v in p.locals_]
    assert "a" in names and "b" in names
    assert len(p.body) == 2
_run("test_locals_before_and_after_begin", test_locals_before_and_after_begin)

def test_compound_stmt_after_begin_separator():
    # compound stmt (BEGIN...END) still works inside proc body after section BEGIN
    p = _parse("PROC foo; BEGIN BEGIN x := 1; END; END;")
    assert isinstance(p.body[0], CompoundStmt)
_run("test_compound_stmt_after_begin_separator", test_compound_stmt_after_begin_separator)

def test_subproc_begin_optional():
    p = _parse("PROC foo; SUBPROC bar; INT x; x := 1; END; BEGIN END;")
    sub = p.subprocs[0]
    assert sub.locals_[0].name == "x"
    assert isinstance(sub.body[0], AssignStmt)
_run("test_subproc_begin_optional", test_subproc_begin_optional)


# ─────────────────────────────────────────────────────────────────────────────
# Group 9: Regression — proc-local var initializers with runtime expressions
#   Fix: %override init_val : constant_list | add_expr  (proc_body.lark)
#   Phase 1 (global var_decl) is unaffected; these tests target Phase 8 only.
# ─────────────────────────────────────────────────────────────────────────────

def test_local_init_proc_call():
    # RTL_strlen_(input) raised: Unexpected token Token('NAME', 'RTL_strlen_')
    # Root cause: init_val accepted only literals, not NAME call_args.
    p = _parse("INT PROC foo(buf); INT n := RTL_strlen_(buf); BEGIN END;")
    local = p.locals_[0]
    assert local.name == "n"
    assert local.has_initializer
_run("test_local_init_proc_call", test_local_init_proc_call)

def test_local_init_name_ref():
    # Bare NAME (LITERAL / named constant reference) as initializer.
    p = _parse("INT PROC foo; INT n := some_const; BEGIN END;")
    assert p.locals_[0].has_initializer
_run("test_local_init_name_ref", test_local_init_name_ref)

def test_local_init_address_of():
    # @ptr (address-of) as initializer — add_expr -> unary_expr -> primary(AT).
    # Covers the @recname '<<' 1 pattern from simlogs.tal line 210.
    p = _parse("INT PROC foo(buf); INT .p := @buf; BEGIN END;")
    assert p.locals_[0].has_initializer
_run("test_local_init_address_of", test_local_init_address_of)

def test_local_init_arithmetic():
    # Arithmetic expression: a + b covered by add_expr.
    p = _parse("INT PROC foo(a, b); INT n := a + b; BEGIN END;")
    assert p.locals_[0].has_initializer
_run("test_local_init_arithmetic", test_local_init_arithmetic)

def test_local_init_negated_call():
    # Unary minus applied to a function call result.
    p = _parse("INT PROC foo(s); INT n := -strlen_(s); BEGIN END;")
    assert p.locals_[0].has_initializer
_run("test_local_init_negated_call", test_local_init_negated_call)

def test_local_init_multi_var_with_call():
    # Multiple vars in one decl; first has call initializer, second does not.
    # Verifies COMMA still separates var_items after add_expr reduces.
    p = _parse("INT PROC foo(buf); INT n := RTL_strlen_(buf), m; BEGIN END;")
    by_name = {v.name: v for v in p.locals_}
    assert by_name["n"].has_initializer
    assert not by_name["m"].has_initializer
_run("test_local_init_multi_var_with_call", test_local_init_multi_var_with_call)

def test_local_init_literal_eq_form():
    # EQ initializer form (int x = 5) still works — EQ must not be consumed
    # inside add_expr, which stops before the cmp_expr level.
    p = _parse("INT PROC foo; INT x = 5; BEGIN END;")
    assert p.locals_[0].has_initializer
_run("test_local_init_literal_eq_form", test_local_init_literal_eq_form)

def test_local_init_literal_assign_form():
    # ASSIGN initializer form (int x := 5) still works — ASSIGN must not be
    # consumed inside add_expr, which stops before the assign_expr level.
    p = _parse("INT PROC foo; INT x := 5; BEGIN END;")
    assert p.locals_[0].has_initializer
_run("test_local_init_literal_assign_form", test_local_init_literal_assign_form)

def test_local_init_false():
    # int x := false; in a proc-local context — same NAME path as the global fix.
    p = _parse("INT PROC foo; INT x := false; BEGIN END;")
    assert p.locals_[0].has_initializer
_run("test_local_init_false", test_local_init_false)

def test_local_init_true():
    p = _parse("INT PROC foo; INT x := true; BEGIN END;")
    assert p.locals_[0].has_initializer
_run("test_local_init_true", test_local_init_true)


# ─────────────────────────────────────────────────────────────────────────────
# Group 10: Regression — struct referral before proc BEGIN
#   Fix: split struct_head into struct_head_def (may have body) and
#        struct_head_ref (referral paren NAME, never has body).
#   Root cause: LALR(1) S/R on SEMI after struct_head when KW_BEGIN follows.
#   Shift wins → parser consumed proc BEGIN as struct body start → var_decl
#   with := initializer was parsed as struct_field_item → ASSIGN not expected.
# ─────────────────────────────────────────────────────────────────────────────

def test_struct_referral_before_begin_then_init():
    # struct .args(args_def); followed by proc BEGIN, then var with :=
    # Used to raise: Unexpected token Token('ASSIGN', ':=')
    p = _parse("""
INT PROC foo(params, args);
STRUCT .args(args_def);
BEGIN
    STRING .s, sep := 0;
    RETURN 0;
END;
""")
    assert p.name == "foo"
    sep = next(v for v in p.locals_ if v.name == "sep")
    assert sep.has_initializer
_run("test_struct_referral_before_begin_then_init", test_struct_referral_before_begin_then_init)

def test_struct_referral_multi_var_with_list_init():
    # Full reproduce of simlogs.tal pattern: sep:=[" "] and next_param:=0
    p = _parse("""
INT PROC get_value(params, args);
STRUCT .args(args_def);
BEGIN
    STRING .start_s, .end_s, sep := 0;
    INT key_len, value_len, next_param := 0;
    RETURN 0;
END;
""")
    sep = next(v for v in p.locals_ if v.name == "sep")
    next_param = next(v for v in p.locals_ if v.name == "next_param")
    assert sep.has_initializer
    assert next_param.has_initializer
_run("test_struct_referral_multi_var_with_list_init", test_struct_referral_multi_var_with_list_init)

def test_struct_referral_does_not_consume_begin():
    # Verifies that struct .v(tmpl); is a referral (no body) and proc BEGIN is
    # left for the proc_body rule, not consumed as struct body start.
    p = _parse("""
PROC foo;
STRUCT .v(tmpl_def);
BEGIN
    x := 1;
END;
""")
    assert len(p.body) == 1
_run("test_struct_referral_does_not_consume_begin", test_struct_referral_does_not_consume_begin)


# Group 11: Regression — MOVE fill list with repetition patterns
# Bug: [ 80 * [" "] ] failed with "Unexpected token STAR" because
# const_fill only accepted flat fill_item literals, not repetition forms.
# Fix: fill_item now supports fill_repetition (N * [...]) and fill_short_rep (N * scalar).
# ─────────────────────────────────────────────────────────────────────────────

def test_move_fill_short_repetition():
    # s ':= [ 80 * [" "] ];  — fill_repetition form (the original bug)
    p = _parse("""
PROC test;
STRING .s[0:80];
BEGIN
    s ':=' [ 80 * [" "] ];
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_fill_short_repetition", test_move_fill_short_repetition)

def test_move_fill_scalar_repetition():
    # s ':= [ 5 * "x" ];  — fill_short_rep form
    p = _parse("""
PROC test;
STRING .s[0:10];
BEGIN
    s ':=' [ 5 * "x" ];
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_fill_scalar_repetition", test_move_fill_scalar_repetition)

def test_move_fill_int_repetition():
    # s ':= [ 4 * 0 ];  — fill_short_rep with INTEGER
    p = _parse("""
PROC test;
INT .s[0:4];
BEGIN
    s ':=' [ 4 * 0 ];
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_fill_int_repetition", test_move_fill_int_repetition)

def test_move_fill_plain_list_still_works():
    # Regression: [ 1, 2, 3 ] — existing flat form must still parse
    p = _parse("""
PROC test;
INT .s[0:3];
BEGIN
    s ':=' [ 1, 2, 3 ];
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_fill_plain_list_still_works", test_move_fill_plain_list_still_works)

def test_move_fill_nested_repetition():
    # [ 3 * [1, 2] ]  — repetition containing a multi-element const_fill
    p = _parse("""
PROC test;
INT .s[0:6];
BEGIN
    s ':=' [ 3 * [1, 2] ];
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_fill_nested_repetition", test_move_fill_nested_repetition)

# Group 12: Regression — $FUNC() as repetition multiplier in MOVE fill list
# Bug: [ $LEN(s) * [" "] ] failed with "Unexpected DOLLAR_FUNC" because
# const_fill and const_item only accepted NUMBER_INT as the multiplier.
# Fix: fill_count / mul_count rules accept NUMBER_INT | DOLLAR_FUNC(NAME).
# ─────────────────────────────────────────────────────────────────────────────

def test_dollar_func_repetition_in_move():
    # s ':=' [ $LEN(s) * [" "] ];  — fill_repetition with $FUNC multiplier
    p = _parse("""
PROC test;
STRING .s[0:80];
BEGIN
    s ':=' [ $LEN(s) * [" "] ];
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_dollar_func_repetition_in_move", test_dollar_func_repetition_in_move)

def test_dollar_func_short_rep_in_move():
    # s ':=' [ $LEN(s) * " " ];  — fill_short_rep with $FUNC multiplier
    p = _parse("""
PROC test;
STRING .s[0:80];
BEGIN
    s ':=' [ $LEN(s) * " " ];
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_dollar_func_short_rep_in_move", test_dollar_func_short_rep_in_move)

def test_number_int_repetition_still_works():
    # Regression: 80 * [" "] (plain NUMBER_INT multiplier must still parse)
    p = _parse("""
PROC test;
STRING .s[0:80];
BEGIN
    s ':=' [ 80 * [" "] ];
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_number_int_repetition_still_works", test_number_int_repetition_still_works)

def test_const_fill_numbers_still_works():
    # Regression: [ 1, 2, 3 ] (plain flat list must still parse)
    p = _parse("""
PROC test;
INT .s[0:3];
BEGIN
    s ':=' [ 1, 2, 3 ];
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_const_fill_numbers_still_works", test_const_fill_numbers_still_works)

# Group 13: Regression — CALL with empty/omitted parameters
# Bug: CALL foo(a, , b) and CALL KEYPOSITION(a, b,,, 2) failed because
# stmt_call_arg had no empty alternative.
# Fix: stmt_call_arg adds -> call_param_empty; stmt_call_args uses explicit
# LPAREN RPAREN -> call_no_args to avoid S/R conflict (same pattern as expr.lark).
# Note: permitting empty args is a grammar-level decision; the semantic
# validator is responsible for ensuring the target proc is VARIABLE or EXTENSIBLE
# (per TAL RefMan §12.2.2).
# ─────────────────────────────────────────────────────────────────────────────

def test_call_one_empty_arg():
    # CALL foo(a, , b);  — middle param omitted
    p = _parse("""
PROC test;
BEGIN
    CALL foo(a, , b);
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_call_one_empty_arg", test_call_one_empty_arg)

def test_call_multiple_consecutive_empty_args():
    # CALL KEYPOSITION(a, b,,, 2);  — seekfs.tal pattern: two empty in a row
    p = _parse("""
PROC test;
BEGIN
    CALL KEYPOSITION(a, b,,, 2);
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_call_multiple_consecutive_empty_args", test_call_multiple_consecutive_empty_args)

def test_call_trailing_empty_arg():
    # CALL foo(a, b, );  — trailing empty param
    p = _parse("""
PROC test;
BEGIN
    CALL foo(a, b, );
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_call_trailing_empty_arg", test_call_trailing_empty_arg)

def test_call_no_args_still_works():
    # CALL foo;  — no parens, regression
    p = _parse("""
PROC test;
BEGIN
    CALL foo;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_call_no_args_still_works", test_call_no_args_still_works)

def test_call_empty_parens_still_works():
    # CALL foo();  — empty parens, regression
    p = _parse("""
PROC test;
BEGIN
    CALL foo();
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_call_empty_parens_still_works", test_call_empty_parens_still_works)

def test_call_all_args_still_works():
    # CALL foo(a, b, c);  — all params present, regression
    p = _parse("""
PROC test;
BEGIN
    CALL foo(a, b, c);
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_call_all_args_still_works", test_call_all_args_still_works)

def test_call_param_pair_still_works():
    # CALL foo(a : b);  — param pair (substring), regression
    p = _parse("""
PROC test;
BEGIN
    CALL foo(a : b);
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_call_param_pair_still_works", test_call_param_pair_still_works)

# Group 14: Regression — FORWARD/EXTERNAL with param-specs
# Bug: FORWARD/EXTERNAL after param-spec declarations failed because
# proc_unit matched KW_FORWARD/KW_EXTERNAL only immediately after proc_hdr.
# Fix: proc_body gains proc_body_forward / proc_body_external alternatives
# (proc_item* KW_FORWARD/EXTERNAL SEMI); proc_unit reduced to single rule.
# ─────────────────────────────────────────────────────────────────────────────

def test_forward_with_param_specs():
    p = _parse("""
INT PROC init^arch(aux, aux^len, modo);
STRING .aux;
INT    .aux^len;
INT     modo;
FORWARD;
""")
    assert p.name == "init^arch"
    assert p.is_forward
_run("test_forward_with_param_specs", test_forward_with_param_specs)

def test_external_with_param_specs():
    p = _parse("""
INT PROC foo(a, b);
INT a;
INT b;
EXTERNAL;
""")
    assert p.name == "foo"
    assert p.is_external
_run("test_external_with_param_specs", test_external_with_param_specs)

def test_forward_without_param_specs():
    # Regression: FORWARD with no param-specs must still work
    p = _parse("INT PROC foo(a, b);\nFORWARD;")
    assert p.name == "foo"
    assert p.is_forward
_run("test_forward_without_param_specs", test_forward_without_param_specs)

def test_external_without_param_specs():
    # Regression: EXTERNAL with no param-specs must still work
    p = _parse("INT PROC foo(a, b);\nEXTERNAL;")
    assert p.name == "foo"
    assert p.is_external
_run("test_external_without_param_specs", test_external_without_param_specs)

def test_forward_with_struct_param():
    p = _parse("""
PROC foo(rec);
STRUCT .rec(def);
FORWARD;
""")
    assert p.name == "foo"
    assert p.is_forward
_run("test_forward_with_struct_param", test_forward_with_struct_param)

def test_normal_proc_body_still_works_after_forward_fix():
    # Regression: normal proc body must still parse after grammar restructure
    p = _parse("""
INT PROC foo(a);
INT a;
BEGIN
    RETURN a;
END;
""")
    assert p.name == "foo"
    assert not p.is_forward
    assert not p.is_external
_run("test_normal_proc_body_still_works_after_forward_fix", test_normal_proc_body_still_works_after_forward_fix)

# Group 15: Regression — SCAN/RSCAN with <> (NEQ) as test-char modifier
# Bug: SCAN str WHILE <> target failed because NEQ is not FIRST(expr), so
# the grammar couldn't parse it as the start of the test_char expression.
# Fix: added scan_while_neq / rscan_while_neq alternatives with NEQ before expr.
# Semantic note: WHILE <> target means "while char != target"; mode stored as
# "WHILE_NEQ" so the semantic analyzer can validate the target proc is EXTENSIBLE.
# ─────────────────────────────────────────────────────────────────────────────

def test_scan_while_neq():
    # SCAN str WHILE <> target -> position;
    p = _parse("""
PROC test;
BEGIN
    SCAN str WHILE <> target -> position;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_scan_while_neq", test_scan_while_neq)

def test_scan_while_neq_no_arrow():
    # SCAN str WHILE <> target;  (no -> next_addr)
    p = _parse("""
PROC test;
BEGIN
    SCAN str WHILE <> target;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_scan_while_neq_no_arrow", test_scan_while_neq_no_arrow)

def test_rscan_while_neq():
    # RSCAN str WHILE <> target -> pos;
    p = _parse("""
PROC test;
BEGIN
    RSCAN str WHILE <> target -> pos;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_rscan_while_neq", test_rscan_while_neq)

def test_scan_while_normal_still_works():
    # Regression: SCAN str WHILE " " -> position;
    p = _parse("""
PROC test;
BEGIN
    SCAN str WHILE " " -> position;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_scan_while_normal_still_works", test_scan_while_normal_still_works)

def test_scan_until_normal_still_works():
    # Regression: SCAN str UNTIL "," -> position;
    p = _parse("""
PROC test;
BEGIN
    SCAN str UNTIL "," -> position;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_scan_until_normal_still_works", test_scan_until_normal_still_works)

# Group 16: Group Comparison Expression (RefMan §4.15)
# Bug: expr1 = expr2 FOR count [UNIT] and expr = [const_seq] failed because
# cmp_expr had no alternatives accepting KW_FOR or LBRACK after the rhs.
# Fix: %extend cmp_expr in proc_body.lark (kept out of expr.lark to avoid
# breaking Phase 6/7 parsers that don't load var_decl.lark/const_seq).
# ─────────────────────────────────────────────────────────────────────────────

def test_cmp_for_count():
    # IF a = b FOR 6 THEN  (facpweds pattern)
    p = _parse("""
PROC test;
BEGIN
    IF a = b FOR 6 THEN
    BEGIN
        x := 1;
    END;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_cmp_for_count", test_cmp_for_count)

def test_cmp_for_count_bytes():
    # IF a = b FOR 10 BYTES THEN  (ecoreps macro-expanded pattern)
    p = _parse("""
PROC test;
BEGIN
    IF a = b FOR 10 BYTES THEN
    BEGIN
        x := 1;
    END;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_cmp_for_count_bytes", test_cmp_for_count_bytes)

def test_cmp_bracket_constant():
    # IF a = ["  "] THEN  (seekfs pattern)
    p = _parse("""
PROC test;
BEGIN
    IF a = ["  "] THEN
    BEGIN
        x := 1;
    END;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_cmp_bracket_constant", test_cmp_bracket_constant)

def test_cmp_bracket_constant_list():
    # IF a = [0, 1] THEN  (multiple constants in list)
    p = _parse("""
PROC test;
BEGIN
    IF a = [0, 1] THEN
    BEGIN
        x := 1;
    END;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_cmp_bracket_constant_list", test_cmp_bracket_constant_list)

def test_cmp_for_with_arrow():
    # IF a = b FOR 4 -> next_addr THEN
    p = _parse("""
PROC test;
BEGIN
    IF a = b FOR 4 -> next_addr THEN
    BEGIN
        x := 1;
    END;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_cmp_for_with_arrow", test_cmp_for_with_arrow)

def test_cmp_normal_still_works():
    # Regression: IF a = b THEN — plain comparison
    p = _parse("""
PROC test;
BEGIN
    IF a = b THEN
    BEGIN
        x := 1;
    END;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_cmp_normal_still_works", test_cmp_normal_still_works)

def test_cmp_condition_code_still_works():
    # Regression: IF < THEN — condition code form
    p = _parse("""
PROC test;
BEGIN
    IF < THEN
    BEGIN
        x := 1;
    END;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_cmp_condition_code_still_works", test_cmp_condition_code_still_works)

# Group 17: CASE OTHERWISE before END (facpweds L881, seekfs L620)
# Bug: case_stmt expected OTHERWISE *after* KW_END per the grammar rule
#   case_stmt : ... KW_END case_otherwise?
# but production TAL files place OTHERWISE before END:
#   CASE x OF BEGIN ... OTHERWISE -> stmt; END;
# Fix: reorder grammar to case_body case_otherwise? KW_END.
# ─────────────────────────────────────────────────────────────────────────────

def test_case_otherwise_before_end():
    # OTHERWISE before END — facpweds/seekfs pattern
    p = _parse("""
PROC test;
BEGIN
    CASE err OF
    BEGIN
        1 -> puts("one");
        2 -> puts("two");
        OTHERWISE -> BEGIN
            puts("default");
        END;
    END;
    RETURN;
END;
""")
    stmts = [s for s in p.body if hasattr(s, "otherwise_body")]
    assert len(stmts) == 1
    assert len(stmts[0].otherwise_body) >= 1
_run("test_case_otherwise_before_end", test_case_otherwise_before_end)

def test_case_otherwise_no_arrow_before_end():
    # OTHERWISE without arrow before END
    p = _parse("""
PROC test;
BEGIN
    CASE x OF
    BEGIN
        0 -> y := 0;
        OTHERWISE y := 1;
    END;
    RETURN;
END;
""")
    stmts = [s for s in p.body if hasattr(s, "otherwise_body")]
    assert len(stmts) == 1
_run("test_case_otherwise_no_arrow_before_end", test_case_otherwise_no_arrow_before_end)

def test_case_without_otherwise_still_works():
    # Regression: CASE without OTHERWISE must still parse
    p = _parse("""
PROC test;
BEGIN
    CASE x OF
    BEGIN
        0 -> y := 0;
        1 -> y := 1;
    END;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_case_without_otherwise_still_works", test_case_without_otherwise_still_works)

# Group 18: Substring FOR in expressions (facpwems L224)
# Bug: clave[4] for 2 — substring postfix — failed because KW_FOR was not
# a valid postfix_tail in expr.lark.  The pattern appears in string
# concatenations: name[offset] FOR count.
# Fix: %override postfix_tail in proc_body.lark adds for_slice? to index_access.
# Transformer: _IndexTail.for_count drives SubstringExpr creation in postfix_chain.
# ─────────────────────────────────────────────────────────────────────────────

def test_substring_for_in_assign():
    # int len := clave[4] FOR 2;  — substring initializer
    from segmsan.ast_nodes import SubstringExpr
    p = _parse("""
PROC test;
BEGIN
    x := clave[4] FOR 2;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_substring_for_in_assign", test_substring_for_in_assign)

def test_substring_for_in_concat():
    # linea := "A" & clave[4] FOR 2 & "/" & clave[2] FOR 2;  — facpwems pattern
    p = _parse("""
PROC test;
BEGIN
    linea := "A" & clave[4] FOR 2 & "/" & clave[2] FOR 2;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_substring_for_in_concat", test_substring_for_in_concat)

def test_substring_for_chained():
    # x := arr[0] FOR 6;  — simple substring
    from segmsan.ast_nodes import SubstringExpr
    p = _parse("""
PROC test;
BEGIN
    x := arr[0] FOR 6;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_substring_for_chained", test_substring_for_chained)

def test_array_index_without_for_still_works():
    # Regression: arr[4] with no FOR must still parse as IndexExpr
    from segmsan.ast_nodes import IndexExpr
    p = _parse("""
PROC test;
BEGIN
    x := arr[4];
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_array_index_without_for_still_works", test_array_index_without_for_still_works)

def test_group_cmp_for_regression():
    # Regression: IF a = b FOR 6 THEN — group comparison (plain names, no index)
    # must still produce a parse without consuming FOR as substring.
    p = _parse("""
PROC test;
BEGIN
    IF a = b FOR 6 THEN
    BEGIN
        x := 1;
    END;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_group_cmp_for_regression", test_group_cmp_for_regression)

# ─────────────────────────────────────────────────────────────────────────────
# Group 20: MOVE ':=' with source ending in [idx] FOR count BYTES/WORDS/ELEMENTS
# Bug: for_slice in postfix_tail consumed KW_FOR expr, leaving KW_BYTES stranded.
# Fix: for_slice : KW_FOR expr move_unit? absorbs the unit token too, so
#      byte[0] for 6 bytes parses as SubstringExpr(unit="BYTES") inside the expr.
# ─────────────────────────────────────────────────────────────────────────────

def test_move_lr_indexed_for_bytes():
    # out ':=' fact.fecha.byte[0] for 6 bytes;  — ecoreps L405 pattern
    p = _parse("""
PROC test;
BEGIN
    out ':=' fact.fecha.byte[0] for 6 bytes;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_lr_indexed_for_bytes", test_move_lr_indexed_for_bytes)

def test_move_lr_indexed_for_words():
    p = _parse("""
PROC test;
BEGIN
    dst ':=' src[0] for 4 words;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_lr_indexed_for_words", test_move_lr_indexed_for_words)

def test_move_lr_indexed_for_elements():
    p = _parse("""
PROC test;
BEGIN
    dst ':=' src[0] for 3 elements;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_lr_indexed_for_elements", test_move_lr_indexed_for_elements)

def test_move_lr_indexed_for_no_unit():
    # Regression: x := arr[4] FOR 6;  (Group 18) — no unit, still works
    p = _parse("""
PROC test;
BEGIN
    x := clave[4] FOR 2;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_lr_indexed_for_no_unit", test_move_lr_indexed_for_no_unit)

def test_move_lr_indexed_for_bytes_concat():
    # dia[0] ':=' mes[0] for 4 bytes & "01";  — facpwems L207 pattern
    p = _parse("""
PROC test;
BEGIN
    dia[0] ':=' mes[0] for 4 bytes & "01";
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_lr_indexed_for_bytes_concat", test_move_lr_indexed_for_bytes_concat)

def test_move_lr_indexed_for_var_count():
    # aux ':=' s_fact.fecha.byte[0] for len bytes;  — fwebs L140 pattern (count is var)
    p = _parse("""
PROC test;
BEGIN
    aux ':=' s_fact.fecha.byte[0] for len bytes;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_lr_indexed_for_var_count", test_move_lr_indexed_for_var_count)

def test_move_lr_unindexed_source_for_bytes_still_works():
    # Regression: source is plain var (not indexed) — move_for_clause path
    p = _parse("""
PROC test;
BEGIN
    buffer[0] ':=' fecha for 6 bytes;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_lr_unindexed_source_for_bytes_still_works", test_move_lr_unindexed_source_for_bytes_still_works)

def test_move_lr_concat_with_for_bytes():
    # fact_out ':=' "$PREFIX." & name for len bytes;  — vrfacts L128 pattern
    p = _parse("""
PROC test;
BEGIN
    fact_out ':=' "$PREFIX." & name for len bytes;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_lr_concat_with_for_bytes", test_move_lr_concat_with_for_bytes)

# ─────────────────────────────────────────────────────────────────────────────
# Group 22: IF assign-as-condition  (IF var := proc_call(...) THEN ...)
# Bug: parser expected comparison operator after ), but THEN is valid because
#      the assignment itself is the condition (evaluates the condition code).
# Fix: two new if_stmt alternatives — if_assign_else / if_assign_no_else.
# ─────────────────────────────────────────────────────────────────────────────

def test_if_assign_cond_then_return():
    # IF error := file_open_(name, fd) THEN return 1;
    p = _parse("""
PROC test;
BEGIN
    IF error := file_open_(name, fd) THEN
        RETURN 1;
    RETURN 0;
END;
""")
    from segmsan.ast_nodes import IfStmt, AssignCondExpr
    if_stmt = next(s for s in p.body if isinstance(s, IfStmt))
    assert isinstance(if_stmt.condition, AssignCondExpr)
    assert len(if_stmt.then_body) == 1
    assert len(if_stmt.else_body) == 0
_run("test_if_assign_cond_then_return", test_if_assign_cond_then_return)

def test_if_assign_cond_then_else():
    # IF error := open_(name, fd) THEN BEGIN RETURN 1; END ELSE RETURN 0;
    p = _parse("""
PROC test;
BEGIN
    IF error := open_(name, fd) THEN
    BEGIN
        RETURN 1;
    END
    ELSE
        RETURN 0;
END;
""")
    from segmsan.ast_nodes import IfStmt, AssignCondExpr
    if_stmt = next(s for s in p.body if isinstance(s, IfStmt))
    assert isinstance(if_stmt.condition, AssignCondExpr)
    assert len(if_stmt.then_body) == 1
    assert len(if_stmt.else_body) == 1
_run("test_if_assign_cond_then_else", test_if_assign_cond_then_else)

def test_if_assign_cond_complex_call():
    # IF x := tmpl^create^like(a, b, c, d, e) THEN return False;  — facpwems L312
    p = _parse("""
PROC test;
BEGIN
    IF x := tmpl^create^like(a, b, c, d, e) THEN
        RETURN False;
    RETURN True;
END;
""")
    from segmsan.ast_nodes import IfStmt, AssignCondExpr
    if_stmt = next(s for s in p.body if isinstance(s, IfStmt))
    assert isinstance(if_stmt.condition, AssignCondExpr)
_run("test_if_assign_cond_complex_call", test_if_assign_cond_complex_call)

def test_if_plain_condition_regression():
    # Regression: IF a = b THEN ... — plain condition still works
    p = _parse("""
PROC test;
BEGIN
    IF a = b THEN
        RETURN 1;
    RETURN 0;
END;
""")
    from segmsan.ast_nodes import IfStmt, AssignCondExpr
    if_stmt = next(s for s in p.body if isinstance(s, IfStmt))
    assert not isinstance(if_stmt.condition, AssignCondExpr)
_run("test_if_plain_condition_regression", test_if_plain_condition_regression)

# ─────────────────────────────────────────────────────────────────────────────
# Group 23: MOVE ':=' with ARROW (->) without FOR clause
# Bug: dest ':=' source -> @ptr; failed — ARROW not accepted in move_part.
# Fix: arrow_expr? added directly to move_part and move_fill_list.
#      When FOR present, move_for_clause still owns the ARROW (shift preference).
# ─────────────────────────────────────────────────────────────────────────────

def test_move_lr_string_literal_arrow():
    # SBUFFER ':=' "ERROR: ..." -> @S^PTR;  — genlibs L76 pattern
    p = _parse("""
PROC test;
BEGIN
    SBUFFER ':=' "hello world" -> @S^PTR;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_lr_string_literal_arrow", test_move_lr_string_literal_arrow)

def test_move_lr_expr_arrow():
    # dest ':=' source -> @next;  — plain var source + arrow
    p = _parse("""
PROC test;
BEGIN
    dest ':=' source -> @next;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_lr_expr_arrow", test_move_lr_expr_arrow)

def test_move_lr_for_bytes_arrow_regression():
    # Regression: dest ':=' src FOR 6 BYTES -> @next;  — arrow inside FOR still works
    p = _parse("""
PROC test;
BEGIN
    dest ':=' src[0] for 6 bytes -> @next;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_lr_for_bytes_arrow_regression", test_move_lr_for_bytes_arrow_regression)

def test_move_lr_fill_list_arrow():
    # arr[0] ':=' [0] -> @ptr;  — fill list + arrow
    p = _parse("""
PROC test;
BEGIN
    arr[0] ':=' [0] -> @ptr;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_lr_fill_list_arrow", test_move_lr_fill_list_arrow)

# ─────────────────────────────────────────────────────────────────────────────
# Group 24: MOVE ':=' bracketed-const + AMP concat
# Bug: dest ':=' [" "] & src FOR count; failed — move_fill_list was terminal,
#      no AMP allowed after it.
# Fix: LBRACK const_fill RBRACK moved into move_part as move_fill_inline,
#      so it participates in move_chain like any other part.
# ─────────────────────────────────────────────────────────────────────────────

def test_move_fill_concat_for():
    # LOG.TDATE[0] ':=' [" "] & LOG.TDATE[0] FOR ($LEN(LOG) - 1);  — seekfs L662
    p = _parse("""
PROC test;
BEGIN
    arr[0] ':=' [" "] & arr[0] FOR ($LEN(arr) - 1);
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_fill_concat_for", test_move_fill_concat_for)

def test_move_fill_concat_expr():
    # arr[0] ':=' [" "] & "hello";
    p = _parse("""
PROC test;
BEGIN
    arr[0] ':=' [" "] & "hello";
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_fill_concat_expr", test_move_fill_concat_expr)

def test_move_fill_standalone_regression():
    # Regression: arr[0] ':=' [0];  — standalone fill still works via single-part chain
    p = _parse("""
PROC test;
BEGIN
    arr[0] ':=' [0];
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_fill_standalone_regression", test_move_fill_standalone_regression)

def test_move_fill_concat_for_bytes():
    # arr[0] ':=' ["-"] & src FOR 6 bytes;
    p = _parse("""
PROC test;
BEGIN
    arr[0] ':=' ["-"] & src FOR 6 bytes;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_fill_concat_for_bytes", test_move_fill_concat_for_bytes)

# ─────────────────────────────────────────────────────────────────────────────
# Group 25: MOVE ':=' concat with intermediate FOR clauses  (genlibs L497-498)
# Bug: move_for_clause : KW_FOR expr — the expr greedily consumed AMP (at
#      add_expr level) turning "count & next_seg" into a single expression, so
#      "for prsp_len" after it was unexpected.
# Fix: move_for_clause and for_slice now use mul_expr for the count; AMP is not
#      in mul_op so the count expression stops at & and the next segment starts.
# ─────────────────────────────────────────────────────────────────────────────

def test_move_concat_with_for_intermediate():
    # file_name ':=' volumen for count & ".DLLS";  — genlibs L497
    p = _parse("""
PROC test;
BEGIN
    file_name ':=' volumen FOR count & ".DLLS";
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_concat_with_for_intermediate", test_move_concat_with_for_intermediate)

def test_move_concat_multi_for():
    # dest ':=' src1 FOR n1 & src2 FOR n2;
    p = _parse("""
PROC test;
BEGIN
    dest ':=' src1 FOR n1 & src2 FOR n2;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_concat_multi_for", test_move_concat_multi_for)

def test_move_concat_for_lit_for():
    # dest ':=' src1 FOR n1 & "lit" & src2 FOR n2 & ".ext";  — genlibs L498 pattern
    p = _parse("""
PROC test;
BEGIN
    dest ':=' src1 FOR n1 & "lit" & src2 FOR n2 & ".ext";
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_concat_for_lit_for", test_move_concat_for_lit_for)

def test_move_concat_no_for_regression():
    # Regression: dest ':=' "A" & "B" & "C";  — no FOR, concat still works
    p = _parse("""
PROC test;
BEGIN
    dest ':=' "A" & "B" & "C";
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_concat_no_for_regression", test_move_concat_no_for_regression)

def test_move_single_for_bytes_regression():
    # Regression: dest ':=' src FOR 6 BYTES;  — single source with FOR
    p = _parse("""
PROC test;
BEGIN
    dest ':=' src FOR 6 BYTES;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_single_for_bytes_regression", test_move_single_for_bytes_regression)

# ─────────────────────────────────────────────────────────────────────────────
# Group 26: MOVE ':=' expr-source & [fill] concat  (seekfs L908)
# Bug: move_data used `expr` for the source — AMP at add_expr level greedily
#      consumed "& [fill]", then LBRACK was unexpected (not in FIRST(mul_expr)).
# Fix: move_data now uses mul_expr for the source; AMP stops the source expr
#      and the following move_part (fill_inline or concat) dispatches correctly.
# ─────────────────────────────────────────────────────────────────────────────

def test_move_concat_src_then_fill():
    # idtf.pk.term^id.byte ':=' arch.rec.terminal.byte[0] FOR 8 & [8*[" "]];
    p = _parse("""
PROC test;
BEGIN
    dest ':=' src[0] FOR 8 & [8 * [" "]];
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_concat_src_then_fill", test_move_concat_src_then_fill)

def test_move_concat_str_then_fill():
    # dest ':=' "hello" & [0];
    p = _parse("""
PROC test;
BEGIN
    dest ':=' "hello" & [0];
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_concat_str_then_fill", test_move_concat_str_then_fill)

def test_move_fill_standalone_regression2():
    # Regression: dest ':=' [0];  — standalone fill, no concat
    p = _parse("""
PROC test;
BEGIN
    dest ':=' [0];
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_fill_standalone_regression2", test_move_fill_standalone_regression2)

def test_move_fill_with_arrow_regression():
    # Regression: dest ':=' [" "] -> @next;
    p = _parse("""
PROC test;
BEGIN
    dest ':=' [" "] -> @next;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_fill_with_arrow_regression", test_move_fill_with_arrow_regression)

def test_move_src_fill_src():
    # dest ':=' src1 & [0] & src2;  — fill between two sources
    p = _parse("""
PROC test;
BEGIN
    dest ':=' src1 & [0] & src2;
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_move_src_fill_src", test_move_src_fill_src)

# ─────────────────────────────────────────────────────────────────────────────
# Group 27: $FUNC(field-access) as fill_count in MOVE fill patterns (seekfs L1548)
# Bug: fill_count : DOLLAR_FUNC LPAREN NAME RPAREN — only allowed a bare NAME;
#      $len(ptdd1.data^area) has dots and produced "Unexpected token DOT".
# Fix: changed to DOLLAR_FUNC LPAREN mul_expr RPAREN so field-access chains,
#      indexed references, and nested calls are all valid fill_count arguments.
# ─────────────────────────────────────────────────────────────────────────────

def test_fill_count_field_access():
    # ptdd1.data^area.byte[0] ':=' [$len(ptdd1.data^area) * [" "]];  — seekfs L1548
    p = _parse("""
PROC test;
BEGIN
    dest ':=' [$len(rec.field) * [" "]];
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_fill_count_field_access", test_fill_count_field_access)

def test_fill_count_deep_field_access():
    # $len with deeply nested field access
    p = _parse("""
PROC test;
BEGIN
    dest ':=' [$len(a.b.c.d) * [0]];
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_fill_count_deep_field_access", test_fill_count_deep_field_access)

def test_fill_count_indexed_field():
    # $len with indexed + field access
    p = _parse("""
PROC test;
BEGIN
    dest ':=' [$len(arr[0].field) * [" "]];
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_fill_count_indexed_field", test_fill_count_indexed_field)

def test_fill_count_simple_name_regression():
    # Regression: $len(buffer) — bare NAME still works
    p = _parse("""
PROC test;
BEGIN
    dest ':=' [$len(buffer) * [" "]];
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_fill_count_simple_name_regression", test_fill_count_simple_name_regression)

def test_fill_count_dollar_func_field():
    # $FUNC with field access as arg
    p = _parse("""
PROC test;
BEGIN
    dest ':=' [$OFFSET(rec.field) * [0]];
    RETURN;
END;
""")
    assert len(p.body) >= 1
_run("test_fill_count_dollar_func_field", test_fill_count_dollar_func_field)

# ─────────────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\nPhase 8 — {len(_PASS)} passed, {len(_FAIL)} failed")
    for name, exc in _FAIL:
        print(f"  FAIL: {name}")
        print(f"        {type(exc).__name__}: {exc}")
    if not _FAIL:
        print("  All Phase 8 tests passed!")
