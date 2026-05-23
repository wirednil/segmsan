"""Phase 1 transformer: variable declarations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lark import Lark, Transformer
from lark.lexer import Token

from ..ast_nodes import (
    ArrayBounds, Expr, LiteralExpr, VarExpr, BinOpExpr, UnaryExpr,
    SourceLocation, TalType, VarDecl,
)

_GRAMMAR_COMMON = Path(__file__).parent.parent / "grammar" / "common_decl.lark"
_GRAMMAR_PATH = Path(__file__).parent.parent / "grammar" / "var_decl.lark"

_lark_parser: Lark | None = None


def _get_lark_parser() -> Lark:
    global _lark_parser
    if _lark_parser is None:
        grammar = _GRAMMAR_COMMON.read_text() + "\n" + _GRAMMAR_PATH.read_text()
        _lark_parser = Lark(grammar, parser="lalr", lexer="basic", start="var_decl")
    return _lark_parser


def parse_var_decl(lark_token_iter) -> list[VarDecl]:
    """Parse a single var_decl token stream. Expects tokens through SEMI inclusive."""
    lp = _get_lark_parser()
    ip = lp.parse_interactive("")
    for tok in lark_token_iter:
        ip.feed_token(tok)
    tree = ip.feed_eof()
    return VarDeclTransformer().transform(tree)


# ---------------------------------------------------------------------------

@dataclass
class _VarInit:
    public_name: str = ""  # non-empty only for pub_name_init form

@dataclass
class _VarItem:
    name: str
    loc: SourceLocation
    is_indirect: bool
    is_extended: bool
    array_bounds: ArrayBounds | None
    has_initializer: bool
    public_name: str = ""
    template_name: str = ""


def _parse_int(s: str) -> int:
    """Parse a TAL integer literal string (decimal, octal %, binary %B, hex %H)."""
    s = s.strip().upper()
    if s.startswith("%H"):
        return int(s[2:], 16)
    if s.startswith("%B"):
        return int(s[2:], 2)
    if s.startswith("%"):
        return int(s[1:], 8)
    return int(s)


class VarDeclTransformer(Transformer):

    def var_decl(self, items) -> list[VarDecl]:
        tal_type, fpoint, width = items[0]
        return [
            VarDecl(
                name=vi.name,
                tal_type=tal_type,
                loc=vi.loc,
                is_indirect=vi.is_indirect,
                is_extended=vi.is_extended,
                array_bounds=vi.array_bounds,
                has_initializer=vi.has_initializer,
                public_name=vi.public_name,
                fpoint=fpoint,
                width=width,
                template_name=vi.template_name,
            )
            for vi in items[1:]
            if isinstance(vi, _VarItem)
        ]

    def data_type(self, items) -> tuple[TalType, int, int]:
        t = items[0].type
        # fpoint and width always 0 (ptype_fpoint/ptype_width = 0)
        if t == "TK_INT":
            return (TalType.INT, 0, 0)
        if t == "TK_INT32":
            return (TalType.INT32, 0, 0)
        if t == "TK_REAL":
            return (TalType.REAL, 0, 0)
        if t == "TK_REAL64":
            return (TalType.REAL64, 0, 0)
        if t == "TK_STRING":
            return (TalType.STRING, 0, 0)
        if t == "TK_FIXED":
            return (TalType.FIXED, 0, 0)
        if t == "TK_UNSIGNED":
            return (TalType.UNSIGNED, 0, 0)
        return (TalType.INT, 0, 0)

    def ind_standard(self, _items) -> tuple[bool, bool]:
        return (True, False)

    def ind_extended(self, _items) -> tuple[bool, bool]:
        return (True, True)

    def var_item(self, items) -> _VarItem:
        is_indirect = False
        is_extended = False
        name_tok: Token | None = None
        ab: ArrayBounds | None = None
        has_init = False
        pub_name = ""
        template_name = ""

        for item in items:
            if isinstance(item, tuple) and len(item) == 2:
                is_indirect, is_extended = item
            elif isinstance(item, Token) and item.type == "NAME":
                name_tok = item
            elif isinstance(item, _VarInit):
                has_init = True
                pub_name = item.public_name
            elif isinstance(item, str):
                template_name = item
            elif isinstance(item, ArrayBounds):
                ab = item

        name = str(name_tok) if name_tok else ""
        loc = (
            SourceLocation(name_tok.line or 0, name_tok.column or 0)
            if name_tok
            else SourceLocation(0)
        )
        return _VarItem(
            name=name,
            loc=loc,
            is_indirect=is_indirect,
            is_extended=is_extended,
            array_bounds=ab,
            has_initializer=has_init,
            public_name=pub_name,
            template_name=template_name,
        )

    def struct_ptr_ref(self, items) -> str:
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        return str(name_tok)

    def array_bounds(self, items) -> ArrayBounds:
        ints = [x for x in items if isinstance(x, int)]
        return ArrayBounds(lo=ints[0], hi=ints[1]) if len(ints) >= 2 else ArrayBounds(0, 0)

    def bound_expr(self, items) -> int:
        return items[0] if isinstance(items[0], int) else 0

    def be_expr(self, items) -> int:
        result: int | None = None
        pending_op: str | None = None
        for item in items:
            if isinstance(item, Token):
                pending_op = item.type
            else:
                val = item if isinstance(item, int) else 0
                if result is None:
                    result = val
                elif pending_op == "MINUS":
                    result -= val
                else:
                    result += val
        return result if result is not None else 0

    def be_term(self, items) -> int:
        result: int | None = None
        pending_op: str | None = None
        for item in items:
            if isinstance(item, Token):
                pending_op = item.type
            else:
                val = item if isinstance(item, int) else 0
                if result is None:
                    result = val
                elif pending_op == "SLASH":
                    result = result // val if val != 0 else 0
                else:
                    result *= val
        return result if result is not None else 0

    def be_unary(self, items) -> int:
        if len(items) == 2:
            val = items[1] if isinstance(items[1], int) else 0
            return -val
        return items[0] if isinstance(items[0], int) else 0

    def be_atom(self, items) -> int:
        for item in items:
            if isinstance(item, int):
                return item
            if isinstance(item, Token) and item.type == "NUMBER_INT":
                try:
                    return _parse_int(str(item))
                except (ValueError, AttributeError):
                    return 0
        return 0  # NAME or unresolvable

    def pub_name_init(self, items) -> _VarInit:
        tok = next((t for t in items if isinstance(t, Token) and t.type == "NAME"), None)
        return _VarInit(public_name=str(tok) if tok else "")

    def eq_init(self, _items) -> _VarInit:
        return _VarInit()

    def assign_init(self, _items) -> _VarInit:
        return _VarInit()

    def init_val(self, items):
        return items[0] if items else None

    def literal_val(self, items) -> str:
        tok = items[0]
        return str(tok) if isinstance(tok, Token) else str(tok)

    def neg_int(self, items) -> str:
        for item in items:
            if isinstance(item, Token) and item.type == "NUMBER_INT":
                return f"-{item}"
        return "0"

    def neg_int32(self, items) -> str:
        for item in items:
            if isinstance(item, Token) and item.type == "NUMBER_INT32":
                return f"-{item}"
        return "0"

    def neg_fixed(self, items) -> str:
        for item in items:
            if isinstance(item, Token) and item.type == "NUMBER_FIXED":
                return f"-{item}"
        return "0"

    def constant_list(self, items) -> list:
        for item in items:
            if isinstance(item, list):
                return item
        return []

    def const_seq(self, items) -> list:
        result: list = []
        for item in items:
            if isinstance(item, list):
                result.extend(item)
            elif isinstance(item, Token):
                pass  # COMMA
            else:
                result.append(item)
        return result

    def const_item(self, items):
        return items[0] if items else None

    def mul_count(self, items):
        return items[0]

    def dollar_func_call(self, items) -> str:
        func = next((t for t in items if isinstance(t, Token) and t.type == "DOLLAR_FUNC"), None)
        name = next((t for t in items if isinstance(t, Token) and t.type == "NAME"), None)
        return f"{func}({name})" if func and name else "$unknown"

    def top_repetition(self, items) -> list:
        return self.repetition(items)

    def top_short_repetition(self, items) -> list:
        return self.repetition(items)

    def short_repetition(self, items) -> list:
        return self.repetition(items)

    def repetition(self, items) -> list:
        count_tok: Token | None = None
        inner: list = []
        for item in items:
            if isinstance(item, Token) and item.type == "NUMBER_INT" and count_tok is None:
                count_tok = item
            elif isinstance(item, list):
                inner = item
            elif isinstance(item, (int, float, str)) and not count_tok:
                pass
        if not inner:
            single = [x for x in items if not isinstance(x, Token)]
            if single:
                inner = [single[0]]
        count = 0
        if count_tok is not None:
            try:
                count = _parse_int(str(count_tok))
            except ValueError:
                count = 0
        return inner * count
