"""Phase 9 transformer: complete TAL program (compilation unit).

Extends ProcBodyTransformer with top-level rules for NAME, BLOCK,
directives, and the program entry point.  Start rule: program.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from lark import Lark
from lark.lexer import Token

from ..ast_nodes import (
    BlockDecl, Program, Procedure, SourceImport, VarDecl,
    Statement, AssignStmt, CallStmt, IfStmt, WhileStmt, ForStmt,
    CompoundStmt, DoStmt, CaseStmt, Expr, CallExpr, BinOpExpr,
)
from .proc_body import ProcBodyTransformer
from ..lexer import to_program_stream

_GRAMMAR_DIR = Path(__file__).parent.parent / "grammar"

_GRAMMAR_TAL_TOP = _GRAMMAR_DIR / "tal_top.lark"

_PHASE9_DECLARES = """\
%declare SEMI COMMA COLON ASSIGN MINUS STAR SLASH
%declare LPAREN RPAREN LBRACK RBRACK DOT AT KW_EXT
%declare EQ NEQ LT GT LE GE PLUS SHL SHR PRIME
%declare NAME NUMBER_INT NUMBER_INT32 NUMBER_FIXED NUMBER_REAL NUMBER_REAL64
%declare STRING_LIT CHAR_LIT DOLLAR_FUNC
%declare UADD USUB UMUL UDIV UMOD USHL USHR
%declare ULT UGT UEQ ULE UGE UNE
%declare KW_AND KW_OR KW_NOT KW_XOR KW_LAND KW_LOR
%declare KW_IF KW_THEN KW_ELSE KW_CASE KW_OF KW_BEGIN KW_END KW_OTHERWISE
%declare MOVE_LR MOVE_RL AMP ARROW
%declare KW_CALL KW_RETURN KW_GOTO
%declare KW_SCAN KW_RSCAN KW_WHILE KW_UNTIL
%declare KW_STACK KW_STORE KW_USE KW_DROP
%declare KW_CODE KW_ASSERT
%declare KW_DO KW_FOR KW_TO KW_DOWNTO KW_BY KW_STEP
%declare KW_BYTES KW_WORDS KW_ELEMENTS
%declare DOT_DOT
%declare TK_INT TK_INT32 TK_REAL TK_REAL64 TK_FIXED TK_UNSIGNED TK_STRING
%declare KW_MAIN KW_VARIABLE KW_CALLABLE KW_INTERRUPT
%declare KW_PRIV KW_RESIDENT KW_EXTENSIBLE KW_LANGUAGE
%declare KW_EXTERNAL KW_FORWARD
%declare KW_STRUCT KW_STRUCTURE KW_FILLER KW_BIT_FILLER
%declare KW_LITERAL KW_ENTRY KW_LABEL KW_DEFINE
%declare KW_PROC KW_SUBPROC
%declare KW_BLOCK
%declare DIRECTIVE
"""

_lark_parser_program: Lark | None = None


def _strip_declares(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("%declare")
    )


def _get_program_parser() -> Lark:
    global _lark_parser_program
    if _lark_parser_program is None:
        from .stmt import _PHASE7_MARKER
        expr    = (_GRAMMAR_DIR / "expr.lark").read_text()
        common  = (_GRAMMAR_DIR / "common_decl.lark").read_text()
        var     = (_GRAMMAR_DIR / "var_decl.lark").read_text()
        struct  = (_GRAMMAR_DIR / "struct_def.lark").read_text()
        literal = (_GRAMMAR_DIR / "literal_decl.lark").read_text()
        stmt    = (_GRAMMAR_DIR / "stmt_simple.lark").read_text()
        stmt_base = stmt.split(_PHASE7_MARKER)[0]
        complex_ = (_GRAMMAR_DIR / "stmt_complex.lark").read_text()
        proc    = (_GRAMMAR_DIR / "proc_body.lark").read_text()
        tal_top = _GRAMMAR_TAL_TOP.read_text()
        parts = [expr, common, var, struct, literal, stmt_base, complex_, proc, tal_top]
        combined = _PHASE9_DECLARES + "\n" + "\n".join(_strip_declares(t) for t in parts)
        _lark_parser_program = Lark(combined, parser="lalr", lexer="basic", start="program")
    return _lark_parser_program


def parse_program(lark_token_iter, source_file: str = "") -> Program:
    lp = _get_program_parser()
    ip = lp.parse_interactive("")
    for tok in lark_token_iter:
        ip.feed_token(tok)
    tree = ip.feed_eof()
    result = ProgramTransformer().transform(tree)
    if isinstance(result, Program):
        result.source_file = source_file
        return result
    raise ValueError(f"Expected Program, got {type(result)}")


def parse_program_src(src: str) -> Program:
    from ..lexer import Lexer
    raw = Lexer(src).tokenize()
    lark_tokens = list(to_program_stream(raw))
    return parse_program(iter(lark_tokens))


def _process_directives(program: Program):
    combined = "\n".join(program.directives)
    for m in re.finditer(
        r'SOURCE\s+([^\s,(]+)\s*(?:\(([^)]*)\))?',
        combined, re.IGNORECASE
    ):
        path = m.group(1).strip()
        names_raw = m.group(2) or ""
        names = [n.strip().lstrip("?") for n in names_raw.split(",") if n.strip()]
        is_system = path.upper().startswith("$SYSTEM.") or path.upper().startswith("$RTL")
        si = SourceImport(path=path, names=names, is_system=is_system)
        program.source_imports.append(si)


# ─── Internal sentinels ────────────────────────────────────────────────────────

class _BlockModifier:
    __slots__ = ('name', 'is_private', 'at_zero', 'below')

    def __init__(self, name="", is_private=False, at_zero=False, below=0):
        self.name = name
        self.is_private = is_private
        self.at_zero = at_zero
        self.below = below


class _BlockBody:
    __slots__ = ('globals_', 'directives')

    def __init__(self, globals_=None, directives=None):
        self.globals_ = globals_ or []
        self.directives = directives or []


class ProgramTransformer(ProcBodyTransformer):
    """Handles all grammar rules from Phases 1-9 in one transformer."""

    def program_(self, items) -> Program:
        program = Program()
        for item in items:
            if item is None:
                continue
            if isinstance(item, Procedure):
                program.procedures.append(item)
            elif isinstance(item, BlockDecl):
                program.blocks.append(item)
                program.globals_.extend(item.globals_)
            elif isinstance(item, VarDecl):
                program.globals_.append(item)
            elif isinstance(item, list) and item:
                if isinstance(item[0], VarDecl):
                    program.globals_.extend(item)
                elif isinstance(item[0], tuple):
                    program.literals.update(item)
            elif isinstance(item, str) and item.startswith("\x00DIR:"):
                program.directives.append(item[5:])
            elif isinstance(item, str) and item.startswith("\x00NAME:"):
                program.name = item[6:]
        _process_directives(program)
        for proc in program.procedures:
            _detect_largestack(proc, program.directives)
            _detect_calls_self(proc)
        return program

    def top_proc(self, items):
        return items[0]

    def top_var(self, items):
        return items[0]

    def top_struct(self, items):
        return items[0]

    def top_literal(self, items):
        return items[0]

    def top_block(self, items):
        return items[0]

    def top_name(self, items):
        return items[0]

    def top_define(self, items):
        return None

    def top_directive(self, items) -> str:
        tok = next((t for t in items if isinstance(t, Token) and t.type == "DIRECTIVE"), None)
        return f"\x00DIR:{tok}" if tok else None

    def top_semi(self, items):
        return None

    def top_end(self, items):
        return None

    def name_decl_(self, items) -> str:
        # Rule: NAME NAME SEMI — first NAME is the keyword "NAME", second is the identifier
        name_toks = [t for t in items if isinstance(t, Token) and t.type == "NAME"]
        identifier = name_toks[1] if len(name_toks) >= 2 else name_toks[0]
        return f"\x00NAME:{str(identifier)}"

    def block_decl_(self, items) -> BlockDecl:
        modifier = next((x for x in items if isinstance(x, _BlockModifier)), _BlockModifier())
        body = next((x for x in items if isinstance(x, _BlockBody)), _BlockBody([], []))
        return BlockDecl(
            name=modifier.name,
            is_private=modifier.is_private,
            at_zero=modifier.at_zero,
            below=modifier.below,
            globals_=body.globals_,
            directives=body.directives,
        )

    def block_named(self, items) -> _BlockModifier:
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        name_val = str(name_tok).upper()
        is_private = (name_val == "PRIVATE")
        loc_item = next((x for x in items if isinstance(x, tuple) and len(x) == 2), None)
        at_zero = False
        below = 0
        if loc_item:
            loc_name, loc_val = loc_item
            if loc_name == "AT":
                at_zero = True
            elif loc_name == "BELOW":
                below = loc_val
        return _BlockModifier(
            name="" if is_private else str(name_tok),
            is_private=is_private,
            at_zero=at_zero,
            below=below,
        )

    def block_plain(self, items) -> _BlockModifier:
        loc_item = next((x for x in items if isinstance(x, tuple) and len(x) == 2), None)
        at_zero = False
        below = 0
        if loc_item:
            loc_name, loc_val = loc_item
            if loc_name == "AT":
                at_zero = True
            elif loc_name == "BELOW":
                below = loc_val
        return _BlockModifier(at_zero=at_zero, below=below)

    def block_loc_(self, items) -> tuple:
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        num_tok = next(t for t in items if isinstance(t, Token) and t.type == "NUMBER_INT")
        loc_name = str(name_tok).upper()
        try:
            loc_val = int(str(num_tok))
        except (ValueError, AttributeError):
            loc_val = 0
        return (loc_name, loc_val)

    def block_body(self, items) -> _BlockBody:
        globals_: list = []
        directives: list = []
        for item in items:
            if item is None:
                continue
            if isinstance(item, VarDecl):
                globals_.append(item)
            elif isinstance(item, list) and item:
                if isinstance(item[0], VarDecl):
                    globals_.extend(item)
                elif isinstance(item[0], tuple):
                    pass
            elif isinstance(item, str) and item.startswith("\x00DIR:"):
                directives.append(item[5:])
        return _BlockBody(globals_=globals_, directives=directives)

    def block_directive(self, items) -> str:
        tok = next((t for t in items if isinstance(t, Token) and t.type == "DIRECTIVE"), None)
        return f"\x00DIR:{tok}" if tok else None

    def block_item(self, items):
        return items[0] if items else None

    def block_semi(self, items):
        return None


def _detect_calls_self(proc: Procedure) -> None:
    name = proc.name.upper()
    proc.calls_self = any(_stmt_calls(s, name) for s in proc.body)
    for sp in proc.subprocs:
        _detect_calls_self(sp)


def _stmt_calls(stmt: Statement, name: str) -> bool:
    if isinstance(stmt, CallStmt):
        if stmt.name.upper() == name:
            return True
    if isinstance(stmt, AssignStmt):
        if _expr_calls(stmt.source, name):
            return True
    if isinstance(stmt, IfStmt):
        if _expr_calls(stmt.condition, name):
            return True
        for s in stmt.then_body + stmt.else_body:
            if _stmt_calls(s, name):
                return True
    if isinstance(stmt, (WhileStmt, ForStmt, CompoundStmt, DoStmt)):
        for s in stmt.body:
            if _stmt_calls(s, name):
                return True
    if isinstance(stmt, CaseStmt):
        for alt in stmt.alternatives:
            for s in alt.body:
                if _stmt_calls(s, name):
                    return True
        for s in stmt.otherwise_body:
            if _stmt_calls(s, name):
                return True
    return False


def _expr_calls(expr: Expr, name: str) -> bool:
    if isinstance(expr, CallExpr):
        if expr.name.upper() == name:
            return True
        for a in expr.args:
            if _expr_calls(a, name):
                return True
    if isinstance(expr, BinOpExpr):
        return _expr_calls(expr.left, name) or _expr_calls(expr.right, name)
    return False


def _detect_largestack(proc: Procedure, directives: list[str]):
    combined = "\n".join(directives).upper()
    proc.has_largestack = "LARGESTACK" in combined
