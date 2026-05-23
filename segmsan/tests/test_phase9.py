"""Phase 9 tests: complete TAL program (compilation unit).

Parser: grammar/tal_top.lark + all preceding grammars.
Transformer: ProgramTransformer (extends ProcBodyTransformer).
Helper: parse_program_src(src) → Program.
"""

from ..transformers.program import parse_program_src
from ..transformers.proc_body import parse_procedure_src
from ..ast_nodes import (
    AssignStmt, BlockDecl, CompoundStmt, IfStmt,
    Procedure, Program, SourceImport, VarDecl,
)


def _parse(src: str) -> Program:
    return parse_program_src(src)


# ─── Group 1: Basic program structure ────────────────────────────────────────

def test_empty_program():
    p = _parse("")
    assert isinstance(p, Program)
    assert p.procedures == []
    assert p.globals_ == []


def test_single_proc():
    p = _parse("PROC foo; BEGIN END;")
    assert len(p.procedures) == 1
    assert p.procedures[0].name == "foo"


def test_multiple_procs():
    p = _parse("PROC foo; BEGIN END; PROC bar; BEGIN END; PROC baz; BEGIN END;")
    names = [pr.name for pr in p.procedures]
    assert names == ["foo", "bar", "baz"]


def test_proc_with_main():
    p = _parse("PROC main_proc MAIN; BEGIN END;")
    assert p.procedures[0].is_main is True


def test_proc_with_return_type():
    p = _parse("INT PROC compute; BEGIN RETURN 0; END;")
    pr = p.procedures[0]
    assert pr.name == "compute"
    assert pr.return_type is not None


def test_proc_with_body():
    p = _parse("PROC do_work; INT x; BEGIN x := 42; END;")
    pr = p.procedures[0]
    assert pr.locals_[0].name == "x"
    assert isinstance(pr.body[0], AssignStmt)


# ─── Group 2: Global declarations ────────────────────────────────────────────

def test_global_int():
    p = _parse("INT x; PROC foo; BEGIN END;")
    assert any(g.name == "x" for g in p.globals_)


def test_global_string_array():
    p = _parse("STRING buf[0:79]; PROC foo; BEGIN END;")
    g = next(g for g in p.globals_ if g.name == "buf")
    assert g.array_bounds is not None
    assert g.array_bounds.lo == 0
    assert g.array_bounds.hi == 79


def test_multiple_globals():
    p = _parse("INT a; INT b; INT c; PROC foo; BEGIN END;")
    names = [g.name for g in p.globals_]
    assert "a" in names and "b" in names and "c" in names


def test_global_literal():
    p = _parse("LITERAL MAX = 100; PROC foo; BEGIN END;")
    assert p.literals.get("MAX") == 100


def test_multiple_literals():
    p = _parse("LITERAL X = 1, Y = 2, Z = 3; PROC foo; BEGIN END;")
    assert p.literals.get("X") == 1
    assert p.literals.get("Y") == 2
    assert p.literals.get("Z") == 3


def test_global_define_consumed():
    p = _parse("DEFINE DEBUG = 1#; INT x; PROC foo; BEGIN END;")
    assert any(g.name == "x" for g in p.globals_)


# ─── Group 3: BLOCK declarations ─────────────────────────────────────────────

def test_named_block():
    p = _parse("BLOCK myblock; INT x; INT y; END BLOCK; PROC foo; BEGIN END;")
    assert len(p.blocks) == 1
    assert p.blocks[0].name == "myblock"
    assert len(p.blocks[0].globals_) == 2


def test_private_block():
    p = _parse("BLOCK PRIVATE; INT secret; END BLOCK; PROC foo; BEGIN END;")
    assert p.blocks[0].is_private is True
    assert p.blocks[0].name == ""


def test_anonymous_block():
    p = _parse("BLOCK; INT x; END BLOCK; PROC foo; BEGIN END;")
    assert len(p.blocks) == 1
    assert p.blocks[0].name == ""
    assert p.blocks[0].is_private is False


def test_block_at_zero():
    p = _parse("BLOCK myblock AT(0); INT x; END BLOCK; PROC foo; BEGIN END;")
    assert p.blocks[0].name == "myblock"
    assert p.blocks[0].at_zero is True


def test_block_vars_propagate_to_globals():
    p = _parse("BLOCK myblock; INT x; INT y; END BLOCK; PROC foo; BEGIN END;")
    global_names = [g.name for g in p.globals_]
    assert "x" in global_names and "y" in global_names


def test_multiple_blocks():
    p = _parse(
        "BLOCK ablock; INT a; END BLOCK; "
        "BLOCK bblock; INT b; END BLOCK; "
        "PROC foo; BEGIN END;"
    )
    assert len(p.blocks) == 2
    names = [b.name for b in p.blocks]
    assert "ablock" in names and "bblock" in names


def test_block_with_literal():
    p = _parse("BLOCK myblock; LITERAL X = 7; INT arr[0:9]; END BLOCK; PROC foo; BEGIN END;")
    assert p.blocks[0].globals_[0].name == "arr"


# ─── Group 4: NAME declaration ────────────────────────────────────────────────

def test_name_declaration():
    p = _parse("NAME mymodule; PROC foo; BEGIN END;")
    assert p.name == "mymodule"


def test_name_with_block():
    p = _parse("NAME mymod; BLOCK myblock; INT x; END BLOCK; PROC foo; BEGIN END;")
    assert p.name == "mymod"
    assert p.blocks[0].name == "myblock"


def test_name_default_empty():
    p = _parse("PROC foo; BEGIN END;")
    assert p.name == ""


# ─── Group 5: Directives ─────────────────────────────────────────────────────

def test_directive_stored():
    p = _parse("?INSPECT\nPROC foo; BEGIN END;")
    assert any("INSPECT" in d.upper() for d in p.directives)


def test_largestack_directive():
    p = _parse("?LARGESTACK\nPROC foo MAIN; BEGIN END;")
    assert p.procedures[0].has_largestack is True


def test_largestack_applies_to_all_procs():
    p = _parse("?LARGESTACK\nPROC foo; BEGIN END; PROC bar; BEGIN END;")
    assert all(pr.has_largestack for pr in p.procedures)


def test_source_directive_creates_import():
    p = _parse("?SOURCE mylib.tal\nPROC foo; BEGIN END;")
    assert len(p.source_imports) == 1
    assert p.source_imports[0].path == "mylib.tal"


def test_system_source_import():
    p = _parse("?SOURCE $SYSTEM.ZSYSCALL\nPROC foo; BEGIN END;")
    si = p.source_imports[0]
    assert si.is_system is True


def test_no_directives():
    p = _parse("PROC foo; BEGIN END;")
    assert p.directives == []
    assert p.source_imports == []


# ─── Group 6: Combined / full program ────────────────────────────────────────

def test_typical_program():
    src = (
        "NAME mymod;\n"
        "BLOCK globals;\n"
        "  INT counter;\n"
        "  STRING buf[0:79];\n"
        "END BLOCK;\n"
        "PROC main_proc MAIN;\n"
        "BEGIN\n"
        "  counter := 0;\n"
        "END;\n"
    )
    p = _parse(src)
    assert p.name == "mymod"
    assert len(p.blocks) == 1
    assert len(p.procedures) == 1
    assert p.procedures[0].is_main is True
    assert any(g.name == "counter" for g in p.globals_)


def test_globals_before_block():
    src = (
        "INT global_var;\n"
        "BLOCK myblock;\n"
        "  INT block_var;\n"
        "END BLOCK;\n"
        "PROC foo; BEGIN END;\n"
    )
    p = _parse(src)
    names = [g.name for g in p.globals_]
    assert "global_var" in names
    assert "block_var" in names


def test_proc_with_subproc():
    src = (
        "PROC outer;\n"
        "  SUBPROC inner;\n"
        "  BEGIN\n"
        "    RETURN;\n"
        "  END;\n"
        "BEGIN\n"
        "END;\n"
    )
    p = _parse(src)
    assert len(p.procedures) == 1
    assert len(p.procedures[0].subprocs) == 1
    assert p.procedures[0].subprocs[0].name == "inner"


def test_forward_proc_then_full():
    # proc_hdr ends in SEMI; FORWARD adds a second SEMI: "PROC foo; FORWARD;"
    src = (
        "PROC helper; FORWARD;\n"
        "PROC main_proc MAIN;\n"
        "BEGIN\n"
        "END;\n"
        "PROC helper;\n"
        "BEGIN\n"
        "END;\n"
    )
    p = _parse(src)
    names = [pr.name for pr in p.procedures]
    assert "main_proc" in names
    assert "helper" in names


def test_proc_with_compound_body():
    # compound stmt (BEGIN...END inside body) contains statements, not declarations
    src = (
        "PROC foo;\n"
        "INT x;\n"
        "BEGIN\n"
        "  BEGIN\n"
        "    x := 1;\n"
        "  END;\n"
        "END;\n"
    )
    p = _parse(src)
    assert isinstance(p.procedures[0].body[0], CompoundStmt)


# ─── Group 7: Regression ─────────────────────────────────────────────────────

def test_phase8_parse_procedure_still_works():
    pr = parse_procedure_src("PROC foo; INT x; BEGIN x := 1; END;")
    assert isinstance(pr, Procedure)
    assert pr.locals_[0].name == "x"


def test_phase9_matches_phase8_for_single_proc():
    src = "PROC bar; INT a; BEGIN a := 2; END;"
    p9 = _parse(src)
    p8 = parse_procedure_src("PROC bar; INT a; BEGIN a := 2; END;")
    assert p9.procedures[0].name == p8.name
    assert len(p9.procedures[0].locals_) == len(p8.locals_)


def test_program_is_program_instance():
    p = _parse("PROC foo; BEGIN END;")
    assert isinstance(p, Program)


def test_multiple_parse_calls_are_consistent():
    src = "INT x; PROC foo MAIN; BEGIN END;"
    p1 = _parse(src)
    p2 = _parse(src)
    assert len(p1.globals_) == len(p2.globals_)
    assert len(p1.procedures) == len(p2.procedures)
