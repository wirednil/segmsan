"""Phase 6/7 transformer: Simple and complex statements.

Phase 6: expr.lark + stmt_simple.lark (CALL, RETURN, GOTO, assign, MOVE, etc.)
Phase 7: adds IF, WHILE, FOR, DO...UNTIL, CASE via stmt_complex.lark
StmtTransformer inherits ExprTransformer so expression sub-trees are handled
without delegation.
"""

from __future__ import annotations

from pathlib import Path

from lark import Lark, Transformer
from lark.lexer import Token

from ..ast_nodes import (
    Expr, Statement, SourceLocation,
    AssignStmt, CallStmt, CompoundStmt, GotoStmt, LabelStmt,
    ReturnStmt, ScanStmt, StackStmt, StoreStmt, UseStmt, DropStmt,
    CodeStmt, AssertStmt, MoveStmt, OtherStmt,
    AssignCondExpr,
    IfStmt, WhileStmt, ForStmt, DoStmt, CaseStmt, CaseAlternative, CaseLabel,
    VarExpr, CallExpr,
)
from .expr import ExprTransformer
from .var_decl import _parse_int as _parse_int_literal

_GRAMMAR_EXPR = Path(__file__).parent.parent / "grammar" / "expr.lark"
_GRAMMAR_STMT = Path(__file__).parent.parent / "grammar" / "stmt_simple.lark"
_GRAMMAR_COMPLEX = Path(__file__).parent.parent / "grammar" / "stmt_complex.lark"

_PHASE7_MARKER = "// ─── Phase 7 placeholders"

_lark_parser: Lark | None = None
_lark_parser_complex: Lark | None = None


def _get_lark_parser() -> Lark:
    global _lark_parser
    if _lark_parser is None:
        expr_text = _GRAMMAR_EXPR.read_text()
        stmt_text = _GRAMMAR_STMT.read_text()
        combined = expr_text + "\n" + stmt_text
        _lark_parser = Lark(combined, parser="lalr", lexer="basic", start="stmt_list")
    return _lark_parser


def _get_lark_parser_complex() -> Lark:
    global _lark_parser_complex
    if _lark_parser_complex is None:
        expr_text = _GRAMMAR_EXPR.read_text()
        stmt_text = _GRAMMAR_STMT.read_text()
        complex_text = _GRAMMAR_COMPLEX.read_text()
        stmt_base = stmt_text.split(_PHASE7_MARKER)[0]
        combined = expr_text + "\n" + stmt_base + "\n" + complex_text
        _lark_parser_complex = Lark(combined, parser="lalr", lexer="basic", start="stmt_list")
    return _lark_parser_complex


def _run_parser(lp: Lark, lark_token_iter) -> list[Statement]:
    ip = lp.parse_interactive("")
    for tok in lark_token_iter:
        ip.feed_token(tok)
    tree = ip.feed_eof()
    result = StmtTransformer().transform(tree)
    if isinstance(result, list):
        return result
    return [result] if isinstance(result, Statement) else []


def parse_stmts(lark_token_iter) -> list[Statement]:
    """Parse a statement list using the Phase 6 grammar."""
    return _run_parser(_get_lark_parser(), lark_token_iter)


def parse_stmts_complex(lark_token_iter) -> list[Statement]:
    """Parse a statement list using the Phase 7 grammar (IF/WHILE/FOR/DO/CASE)."""
    return _run_parser(_get_lark_parser_complex(), lark_token_iter)


# ─── Location helper ─────────────────────────────────────────────────────────

def _tok_loc(items) -> SourceLocation:
    """Return SourceLocation from the first Token in items that has a real line."""
    for item in items:
        if isinstance(item, Token) and item.line:
            return SourceLocation(item.line, item.column or 0)
    return SourceLocation(0)


# ─── Transformer ─────────────────────────────────────────────────────────────

class StmtTransformer(ExprTransformer):

    # ─── stmt_list ────────────────────────────────────────────────────────────

    def stmt_list(self, items) -> list[Statement]:
        result = []
        for item in items:
            if isinstance(item, Statement):
                result.append(item)
            elif isinstance(item, list):
                result.extend(s for s in item if isinstance(s, Statement))
        return result

    # ─── Compound ─────────────────────────────────────────────────────────────

    def compound(self, items) -> CompoundStmt:
        body = next((x for x in items if isinstance(x, list)), [])
        return CompoundStmt(body=[s for s in body if isinstance(s, Statement)])

    # ─── RETURN ───────────────────────────────────────────────────────────────

    def return_bare(self, items) -> ReturnStmt:
        return ReturnStmt(loc=_tok_loc(items))

    def return_value(self, items) -> ReturnStmt:
        exprs = [x for x in items if isinstance(x, Expr)]
        return ReturnStmt(value=exprs[0] if exprs else None, loc=_tok_loc(items))

    def return_cc_only(self, items) -> ReturnStmt:
        exprs = [x for x in items if isinstance(x, Expr)]
        return ReturnStmt(value=None, cc_expression=exprs[0] if exprs else None,
                          loc=_tok_loc(items))

    def return_value_cc(self, items) -> ReturnStmt:
        exprs = [x for x in items if isinstance(x, Expr)]
        return ReturnStmt(
            value=exprs[0] if exprs else None,
            cc_expression=exprs[1] if len(exprs) > 1 else None,
            loc=_tok_loc(items),
        )

    # ─── GOTO ─────────────────────────────────────────────────────────────────

    def goto_(self, items) -> GotoStmt:
        name = str(next(t for t in items if isinstance(t, Token) and t.type == "NAME"))
        return GotoStmt(label=name, loc=_tok_loc(items))

    # ─── CALL ─────────────────────────────────────────────────────────────────

    def call_explicit(self, items) -> CallStmt:
        name = str(next(t for t in items if isinstance(t, Token) and t.type == "NAME"))
        args_and_pairs = next((x for x in items if isinstance(x, list)), [])
        args = [x for x in args_and_pairs if isinstance(x, Expr)]
        pairs = [x for x in args_and_pairs if isinstance(x, tuple)]
        return CallStmt(name=name, args=args, param_pairs=pairs, loc=_tok_loc(items))

    def stmt_call_args(self, items) -> list:
        arg_list = next((x for x in items if isinstance(x, list)), [])
        return arg_list

    def call_no_args(self, items) -> list:
        return []

    def stmt_call_arg_list(self, items) -> list:
        return [x for x in items if isinstance(x, (Expr, tuple))]

    def call_param(self, items) -> Expr:
        return next(x for x in items if isinstance(x, Expr))

    def call_param_pair(self, items) -> tuple:
        exprs = [x for x in items if isinstance(x, Expr)]
        return (exprs[0], exprs[1])

    def call_param_empty(self, items) -> None:
        return None

    # ─── SCAN / RSCAN ─────────────────────────────────────────────────────────

    def _make_scan(self, items, direction: str, mode: str) -> ScanStmt:
        exprs = [x for x in items if isinstance(x, Expr)]
        return ScanStmt(
            direction=direction,
            variable=exprs[0],
            mode=mode,
            test_char=exprs[1],
            next_addr=exprs[2] if len(exprs) > 2 else None,
            loc=_tok_loc(items),
        )

    def scan_while(self, items)      -> ScanStmt: return self._make_scan(items, "SCAN",  "WHILE")
    def scan_while_neq(self, items)  -> ScanStmt: return self._make_scan(items, "SCAN",  "WHILE_NEQ")
    def scan_until(self, items)      -> ScanStmt: return self._make_scan(items, "SCAN",  "UNTIL")
    def rscan_while(self, items)     -> ScanStmt: return self._make_scan(items, "RSCAN", "WHILE")
    def rscan_while_neq(self, items) -> ScanStmt: return self._make_scan(items, "RSCAN", "WHILE_NEQ")
    def rscan_until(self, items)     -> ScanStmt: return self._make_scan(items, "RSCAN", "UNTIL")

    def arrow_expr(self, items) -> Expr:
        return next(x for x in items if isinstance(x, Expr))

    # ─── STACK / STORE ────────────────────────────────────────────────────────

    def stack_(self, items) -> StackStmt:
        return StackStmt(values=[x for x in items if isinstance(x, Expr)])

    def store_(self, items) -> StoreStmt:
        return StoreStmt(variables=[x for x in items if isinstance(x, Expr)])

    # ─── USE / DROP ───────────────────────────────────────────────────────────

    def use_(self, items) -> UseStmt:
        names = [str(t) for t in items if isinstance(t, Token) and t.type == "NAME"]
        return UseStmt(identifiers=names)

    def drop_(self, items) -> DropStmt:
        names = [str(t) for t in items if isinstance(t, Token) and t.type == "NAME"]
        return DropStmt(identifiers=names)

    # ─── ASSERT ───────────────────────────────────────────────────────────────

    def assert_(self, items) -> AssertStmt:
        exprs = [x for x in items if isinstance(x, Expr)]
        return AssertStmt(level=exprs[0] if exprs else None,
                          condition=exprs[1] if len(exprs) > 1 else None)

    # ─── CODE ─────────────────────────────────────────────────────────────────

    def code_(self, items) -> CodeStmt:
        instr_list = next((x for x in items if isinstance(x, list)), [])
        return CodeStmt(instructions=instr_list)

    def code_body(self, items) -> list:
        # Token is a subclass of str — exclude Token objects, keep plain str
        return [x for x in items if isinstance(x, str) and not isinstance(x, Token)]

    def code_instr(self, items) -> str:
        return " ".join(str(t) for t in items if isinstance(t, Token))

    # ─── Assignment ───────────────────────────────────────────────────────────

    def assign_single(self, items) -> AssignStmt:
        exprs = [x for x in items if isinstance(x, Expr)]
        return AssignStmt(targets=[exprs[0]], source=exprs[1], loc=_tok_loc(items))

    def assign_call(self, items) -> AssignStmt:
        exprs = [x for x in items if isinstance(x, Expr)]
        targets = exprs[:-1] if len(exprs) > 1 else exprs
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        args_and_pairs = next((x for x in items if isinstance(x, list)), [])
        args = [x for x in args_and_pairs if isinstance(x, Expr)]
        pairs = [x for x in args_and_pairs if isinstance(x, tuple)]
        source = CallExpr(name=str(name_tok), args=args)
        return AssignStmt(targets=targets, source=source, loc=_tok_loc(items))

    def assign_multi(self, items) -> AssignStmt:
        first = next(x for x in items if isinstance(x, Expr))
        targets = [first]
        source = None
        for x in items:
            if isinstance(x, list):
                targets.extend(x)
            elif isinstance(x, Expr) and x is not first:
                source = x
        return AssignStmt(targets=targets, source=source, loc=_tok_loc(items))

    # ─── MOVE ─────────────────────────────────────────────────────────────────

    def move_lr(self, items) -> MoveStmt:
        return self._make_move(items, "LR")

    def move_rl(self, items) -> MoveStmt:
        return self._make_move(items, "RL")

    def _make_move(self, items, direction: str) -> MoveStmt:
        dest = next(x for x in items if isinstance(x, Expr))
        move = next((x for x in items if isinstance(x, _MoveRhs)), None)
        if move is None:
            return MoveStmt(direction=direction, source=dest, dest=None)
        return MoveStmt(
            direction=direction,
            source=move.source,
            dest=dest,
            count=move.count,
            unit=move.unit,
            next_addr=move.next_addr,
        )

    def move_chain(self, items) -> _MoveRhs:
        parts = [x for x in items if isinstance(x, _MoveRhs)]
        if not parts:
            return _MoveRhs(source=None, count=None, unit="", next_addr=None)
        if len(parts) == 1:
            return parts[0]
        return _MoveRhs(source=parts, count=None, unit="", next_addr=None)

    def move_data(self, items) -> _MoveRhs:
        exprs = [x for x in items if isinstance(x, Expr)]
        clause = next((x for x in items if isinstance(x, _MoveForClause)), None)
        src = exprs[0] if exprs else None
        count = clause.count if clause else None
        unit = clause.unit if clause else ""
        if clause:
            next_addr = clause.next_addr  # arrow was inside move_for_clause
        elif len(exprs) > 1:
            next_addr = exprs[1]  # arrow directly on move_part (no FOR clause)
        else:
            next_addr = None
        return _MoveRhs(source=src, count=count, unit=unit, next_addr=next_addr)

    def move_fill_inline(self, items) -> _MoveRhs:
        fill = next((x for x in items if isinstance(x, list)), [])
        next_addr = next((x for x in items if isinstance(x, Expr)), None)
        return _MoveRhs(source=fill, count=None, unit="", next_addr=next_addr)

    def move_concat(self, items) -> _MoveRhs:
        return _MoveRhs(source="&", count=None, unit="", next_addr=None)

    def move_for_clause(self, items) -> _MoveForClause:
        exprs = [x for x in items if isinstance(x, Expr)]
        unit_str = next((x for x in items if isinstance(x, str) and x in ("BYTES", "WORDS", "ELEMENTS")), "")
        next_addr = exprs[1] if len(exprs) > 1 else None
        return _MoveForClause(count=exprs[0] if exprs else None, unit=unit_str, next_addr=next_addr)

    def unit_bytes(self, _)    -> str: return "BYTES"
    def unit_words(self, _)    -> str: return "WORDS"
    def unit_elements(self, _) -> str: return "ELEMENTS"

    def const_fill(self, items) -> list:
        return list(items)

    def fill_item(self, items) -> object:
        return items[0] if items else None

    def fill_count(self, items) -> object:
        return items[0] if items else None

    def dollar_count(self, items) -> str:
        func = next((t for t in items if isinstance(t, Token) and t.type == "DOLLAR_FUNC"), None)
        # arg is now an Expr (from mul_expr) or a NAME Token (legacy path)
        arg = next((x for x in items if not isinstance(x, Token)), None) or \
              next((t for t in items if isinstance(t, Token) and t.type == "NAME"), None)
        return f"{func}({arg})" if func else "$unknown"

    def fill_repetition(self, items) -> tuple:
        # items[0] is fill_count result (Token or str); find list for inner
        count_val = items[0] if items else None
        inner = next((x for x in items if isinstance(x, list)), [])
        return (str(count_val) if count_val is not None else "0", inner)

    def fill_short_rep(self, items) -> tuple:
        # items[0] = fill_count result; items[-1] = scalar Token
        count_val = items[0] if items else "0"
        val_tok = items[-1] if len(items) >= 2 else None
        return (str(count_val), str(val_tok) if val_tok is not None else "")

    # ─── or_expr_list ─────────────────────────────────────────────────────────

    def or_expr_list(self, items) -> list:
        return [x for x in items if isinstance(x, Expr)]

    # ─── expr_stmt (bare call or expression-as-statement) ────────────────────

    def expr_stmt(self, items) -> Statement:
        expr = next((x for x in items if isinstance(x, Expr)), None)
        loc = _tok_loc(items)
        if expr is None:
            return OtherStmt(raw="", loc=loc)
        if isinstance(expr, CallExpr):
            return CallStmt(name=expr.name, args=expr.args, loc=loc)
        if isinstance(expr, VarExpr):
            return CallStmt(name=expr.name, args=[], loc=loc)
        return OtherStmt(raw=repr(expr), loc=loc)

    # ─── Label ────────────────────────────────────────────────────────────────

    def label(self, items) -> CompoundStmt:
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        sub = next((x for x in items if isinstance(x, Statement)), None)
        label_node = LabelStmt(name=str(name_tok))
        if sub is not None:
            return CompoundStmt(body=[label_node, sub])
        return CompoundStmt(body=[label_node])

    # ─── Phase 7 placeholders (Phase 6 grammar only) ─────────────────────────

    def _placeholder_if(self, items)    -> OtherStmt: return OtherStmt(raw="IF")
    def _placeholder_while(self, items) -> OtherStmt: return OtherStmt(raw="WHILE")
    def _placeholder_for(self, items)   -> OtherStmt: return OtherStmt(raw="FOR")
    def _placeholder_do(self, items)    -> OtherStmt: return OtherStmt(raw="DO")
    def _placeholder_case(self, items)  -> OtherStmt: return OtherStmt(raw="CASE")

    # ─── Phase 7: IF ──────────────────────────────────────────────────────────

    def if_else(self, items) -> IfStmt:
        exprs = [x for x in items if isinstance(x, Expr)]
        stmts = [x for x in items if isinstance(x, Statement)]
        return IfStmt(condition=exprs[0], then_body=[stmts[0]], else_body=[stmts[1]],
                      loc=_tok_loc(items))

    def if_no_else(self, items) -> IfStmt:
        exprs = [x for x in items if isinstance(x, Expr)]
        stmts = [x for x in items if isinstance(x, Statement)]
        return IfStmt(condition=exprs[0], then_body=[stmts[0]], else_body=[],
                      loc=_tok_loc(items))

    def if_assign_else(self, items) -> IfStmt:
        exprs = [x for x in items if isinstance(x, Expr)]
        stmts = [x for x in items if isinstance(x, Statement)]
        cond = AssignCondExpr(target=exprs[0], value=exprs[1], loc=_tok_loc(items))
        return IfStmt(condition=cond, then_body=[stmts[0]], else_body=[stmts[1]],
                      loc=_tok_loc(items))

    def if_assign_no_else(self, items) -> IfStmt:
        exprs = [x for x in items if isinstance(x, Expr)]
        stmts = [x for x in items if isinstance(x, Statement)]
        cond = AssignCondExpr(target=exprs[0], value=exprs[1], loc=_tok_loc(items))
        return IfStmt(condition=cond, then_body=[stmts[0]], else_body=[],
                      loc=_tok_loc(items))

    # ─── Phase 7: WHILE ───────────────────────────────────────────────────────

    def while_(self, items) -> WhileStmt:
        exprs = [x for x in items if isinstance(x, Expr)]
        stmts = [x for x in items if isinstance(x, Statement)]
        return WhileStmt(condition=exprs[0], body=stmts, loc=_tok_loc(items))

    # ─── Phase 7: FOR ─────────────────────────────────────────────────────────

    def for_with_step(self, items) -> ForStmt:
        return self._make_for(items, with_step=True)

    def for_no_step(self, items) -> ForStmt:
        return self._make_for(items, with_step=False)

    def _make_for(self, items, *, with_step: bool) -> ForStmt:
        var_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        exprs = [x for x in items if isinstance(x, Expr)]
        direction = next((x for x in items if isinstance(x, str) and x in ("TO", "DOWNTO")), "TO")
        stmts = [x for x in items if isinstance(x, Statement)]
        # exprs: [from_expr, to_expr] or [from_expr, to_expr, step_expr]
        return ForStmt(
            var=str(var_tok),
            from_expr=exprs[0],
            to_expr=exprs[1],
            step=exprs[2] if with_step and len(exprs) > 2 else None,
            direction=direction,
            body=stmts,
            loc=_tok_loc(items),
        )

    def to_(self, _) -> str:     return "TO"
    def downto_(self, _) -> str: return "DOWNTO"

    def by_step(self, items) -> Expr:
        return next(x for x in items if isinstance(x, Expr))

    def step_alt(self, items) -> Expr:
        return next(x for x in items if isinstance(x, Expr))

    # ─── Phase 7: DO...UNTIL ──────────────────────────────────────────────────

    def do_until(self, items) -> DoStmt:
        stmts = [x for x in items if isinstance(x, Statement)]
        exprs = [x for x in items if isinstance(x, Expr)]
        return DoStmt(body=stmts, condition=exprs[0] if exprs else None, loc=_tok_loc(items))

    # ─── Phase 7: CASE ────────────────────────────────────────────────────────

    def case_(self, items) -> CaseStmt:
        exprs = [x for x in items if isinstance(x, Expr)]
        selector = exprs[0] if exprs else None
        lists = [x for x in items if isinstance(x, list)]
        body_items = lists[0] if lists else []
        otherwise = lists[1] if len(lists) > 1 else []
        alternatives = [x for x in body_items if isinstance(x, CaseAlternative)]
        unlabeled_stmts = [x for x in body_items if isinstance(x, Statement)]
        is_labeled = len(alternatives) > 0
        if not is_labeled:
            alternatives = [
                CaseAlternative(labels=[CaseLabel(value=i)], body=[s])
                for i, s in enumerate(unlabeled_stmts)
            ]
        return CaseStmt(
            selector=selector,
            alternatives=alternatives,
            otherwise_body=otherwise,
            is_labeled=is_labeled,
            loc=_tok_loc(items),
        )

    def case_body_items(self, items) -> list:
        return [x for x in items if isinstance(x, (CaseAlternative, Statement))]

    def case_num1_item(self, items) -> CaseAlternative:
        tok = next(t for t in items if isinstance(t, Token) and t.type == "NUMBER_INT")
        stmt = next(x for x in items if isinstance(x, Statement))
        return CaseAlternative(labels=[CaseLabel(value=_parse_int_literal(str(tok)))], body=[stmt])

    def case_neg1_item(self, items) -> CaseAlternative:
        tok = next(t for t in items if isinstance(t, Token) and t.type == "NUMBER_INT")
        stmt = next(x for x in items if isinstance(x, Statement))
        return CaseAlternative(labels=[CaseLabel(value=-_parse_int_literal(str(tok)))], body=[stmt])

    def case_name1_item(self, items) -> CaseAlternative:
        tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        stmt = next(x for x in items if isinstance(x, Statement))
        return CaseAlternative(labels=[CaseLabel(value=str(tok))], body=[stmt])

    def case_int_range_item(self, items) -> CaseAlternative:
        nums = [t for t in items if isinstance(t, Token) and t.type == "NUMBER_INT"]
        stmt = next(x for x in items if isinstance(x, Statement))
        lbl = CaseLabel(
            value=_parse_int_literal(str(nums[0])),
            is_range=True,
            range_high=_parse_int_literal(str(nums[1])),
        )
        return CaseAlternative(labels=[lbl], body=[stmt])

    def case_name_range_item(self, items) -> CaseAlternative:
        names = [str(t) for t in items if isinstance(t, Token) and t.type == "NAME"]
        stmt = next(x for x in items if isinstance(x, Statement))
        lbl = CaseLabel(value=names[0], is_range=True, range_high=names[1])
        return CaseAlternative(labels=[lbl], body=[stmt])

    def case_multi_int_item(self, items) -> CaseAlternative:
        first_tok = next(t for t in items if isinstance(t, Token) and t.type == "NUMBER_INT")
        rest = next((x for x in items if isinstance(x, list)), [])
        stmt = next(x for x in items if isinstance(x, Statement))
        first_label = CaseLabel(value=_parse_int_literal(str(first_tok)))
        return CaseAlternative(labels=[first_label] + rest, body=[stmt])

    def case_int_more(self, items) -> list:
        return [x for x in items if isinstance(x, CaseLabel)]

    def case_stmt_item(self, items) -> Statement:
        return next((x for x in items if isinstance(x, Statement)), OtherStmt(raw=""))

    def case_int_label(self, items) -> CaseLabel:
        tok = next(t for t in items if isinstance(t, Token) and t.type == "NUMBER_INT")
        return CaseLabel(value=_parse_int_literal(str(tok)))

    def case_neg_label(self, items) -> CaseLabel:
        tok = next(t for t in items if isinstance(t, Token) and t.type == "NUMBER_INT")
        return CaseLabel(value=-_parse_int_literal(str(tok)))

    def case_int_range(self, items) -> CaseLabel:
        nums = [t for t in items if isinstance(t, Token) and t.type == "NUMBER_INT"]
        return CaseLabel(
            value=_parse_int_literal(str(nums[0])),
            is_range=True,
            range_high=_parse_int_literal(str(nums[1])),
        )

    def case_otherwise_body(self, items) -> list:
        return next((x for x in items if isinstance(x, list)), [])


# ─── Internal data transfer objects ──────────────────────────────────────────

from dataclasses import dataclass
from typing import Optional

@dataclass
class _MoveRhs:
    source: object
    count: Optional[Expr]
    unit: str
    next_addr: Optional[Expr]

@dataclass
class _MoveForClause:
    count: Optional[Expr]
    unit: str
    next_addr: Optional[Expr]
