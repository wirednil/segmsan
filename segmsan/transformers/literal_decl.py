"""Phase 3 transformer: LITERAL declarations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lark import Lark, Transformer
from lark.lexer import Token

from ..ast_nodes import Expr, LiteralExpr, VarExpr, BinOpExpr, UnaryExpr
from .var_decl import _parse_int as _parse_int_literal  # reuse Phase 1 parser
from .expr import eval_const_expr

_GRAMMAR_PATH = Path(__file__).parent.parent / "grammar" / "literal_decl.lark"

_lark_parser: Lark | None = None


def _get_lark_parser() -> Lark:
    global _lark_parser
    if _lark_parser is None:
        grammar = _GRAMMAR_PATH.read_text()
        _lark_parser = Lark(grammar, parser="lalr", lexer="basic", start="literal_decl")
    return _lark_parser


def parse_literal_decl(lark_token_iter) -> list[tuple[str, int]]:
    """Parse a single literal_decl token stream.

    Returns list of (name_uppercase, int_value) pairs with auto-increment applied.
    Arithmetic in literal values (e.g. LITERAL x = a + 1) is supported using
    previously-declared literals as the resolution context.
    """
    lp = _get_lark_parser()
    ip = lp.parse_interactive("")
    for tok in lark_token_iter:
        ip.feed_token(tok)
    tree = ip.feed_eof()
    return LiteralDeclTransformer().transform(tree)


# ---------------------------------------------------------------------------

@dataclass
class _LiteralEntry:
    name: str
    value: Expr | None   # None = auto-increment


def _parse_int32(s: str) -> int:
    """Parse NUMBER_INT32 token value to int (strips D or %D suffix)."""
    s = s.strip().upper()
    if s.endswith("%D"):
        return _parse_int_literal(s[:-2])
    return _parse_int_literal(s[:-1])


def _parse_fixed(s: str) -> int:
    """Parse NUMBER_FIXED token value to int (strips F or %F suffix, ignores decimal part)."""
    s = s.strip().upper()
    if s.endswith("%F"):
        return _parse_int_literal(s[:-2])
    stripped = s[:-1]
    if "." in stripped:
        stripped = stripped.split(".")[0]
    try:
        return _parse_int_literal(stripped)
    except ValueError:
        return 0


def _parse_char_lit(s: str) -> int:
    """Parse a CHAR_LIT (e.g. '"A"') to the ordinal of its first character."""
    inner = s.strip().strip('"').strip("'")
    return ord(inner[0]) if inner else 0


def _parse_string_lit(s: str) -> int:
    """Parse a STRING_LIT to the ordinal of its first character (for LITERAL context)."""
    inner = s.strip().strip('"')
    return ord(inner[0]) if inner else 0


# ---------------------------------------------------------------------------

class LiteralDeclTransformer(Transformer):

    def literal_decl(self, items) -> list[tuple[str, int]]:
        entries = [item for item in items if isinstance(item, _LiteralEntry)]
        result: list[tuple[str, int]] = []
        accumulated: dict[str, int] = {}
        prev_value = -1    # first auto-increment → prev + 1 = 0
        for entry in entries:
            if entry.value is not None:
                val = eval_const_expr(entry.value, accumulated)
                prev_value = val if val is not None else 0
            else:
                prev_value = prev_value + 1
            result.append((entry.name.upper(), prev_value))
            accumulated[entry.name.upper()] = prev_value
        return result

    def literal_assigned(self, items) -> _LiteralEntry:
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        expr_val = next(x for x in items if isinstance(x, Expr))
        return _LiteralEntry(name=str(name_tok), value=expr_val)

    def literal_auto(self, items) -> _LiteralEntry:
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        return _LiteralEntry(name=str(name_tok), value=None)

    def literal_value(self, items) -> Expr:
        return items[0]

    def lv_expr(self, items) -> Expr:
        result: Expr | None = None
        pending_op: str | None = None
        for item in items:
            if isinstance(item, Token):
                pending_op = "-" if item.type == "MINUS" else "+"
            else:
                if not isinstance(item, Expr):
                    continue
                if result is None:
                    result = item
                else:
                    result = BinOpExpr(op=pending_op or "+", left=result, right=item)
        return result if result is not None else LiteralExpr(value=0)

    def lv_term(self, items) -> Expr:
        result: Expr | None = None
        pending_op: str | None = None
        for item in items:
            if isinstance(item, Token):
                pending_op = "/" if item.type == "SLASH" else "*"
            else:
                if not isinstance(item, Expr):
                    continue
                if result is None:
                    result = item
                else:
                    result = BinOpExpr(op=pending_op or "*", left=result, right=item)
        return result if result is not None else LiteralExpr(value=0)

    def lv_unary(self, items) -> Expr:
        if len(items) == 2:
            inner = items[1] if isinstance(items[1], Expr) else LiteralExpr(value=0)
            return UnaryExpr(op="-", inner=inner)
        return items[0] if isinstance(items[0], Expr) else LiteralExpr(value=0)

    def lv_atom(self, items) -> Expr:
        for item in items:
            if isinstance(item, Expr):
                return item
            if isinstance(item, Token):
                t = item.type
                try:
                    if t == "NUMBER_INT":
                        return LiteralExpr(value=_parse_int_literal(str(item)))
                    if t == "NUMBER_INT32":
                        return LiteralExpr(value=_parse_int32(str(item)))
                    if t == "NUMBER_FIXED":
                        return LiteralExpr(value=_parse_fixed(str(item)))
                    if t == "CHAR_LIT":
                        return LiteralExpr(value=_parse_char_lit(str(item)))
                    if t == "STRING_LIT":
                        return LiteralExpr(value=_parse_string_lit(str(item)))
                    if t == "NAME":
                        return VarExpr(name=str(item).upper())
                except (ValueError, AttributeError):
                    return LiteralExpr(value=0)
        return LiteralExpr(value=0)
