"""Phase 5 transformer: procedure and subprocedure headers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lark import Lark, Transformer
from lark.lexer import Token

from ..ast_nodes import ArrayBounds, ParamDecl, ProcHeader, SourceLocation, TalType
from .var_decl import _parse_int

_GRAMMAR_COMMON = Path(__file__).parent.parent / "grammar" / "common_decl.lark"
_GRAMMAR_PATH = Path(__file__).parent.parent / "grammar" / "proc_header.lark"

_lark_parser: Lark | None = None


def _get_lark_parser() -> Lark:
    global _lark_parser
    if _lark_parser is None:
        grammar = _GRAMMAR_COMMON.read_text() + "\n" + _GRAMMAR_PATH.read_text()
        _lark_parser = Lark(grammar, parser="lalr", lexer="basic", start="proc_header")
    return _lark_parser


def parse_proc_header(lark_token_iter) -> ProcHeader:
    """Parse a single proc/subproc header token stream."""
    lp = _get_lark_parser()
    ip = lp.parse_interactive("")
    for tok in lark_token_iter:
        ip.feed_token(tok)
    tree = ip.feed_eof()
    return ProcHeaderTransformer().transform(tree)


# ---------------------------------------------------------------------------
# Internal sentinels
# ---------------------------------------------------------------------------

@dataclass
class _PublicName:
    value: str


@dataclass
class _ExtFwd:
    is_external: bool   # True = EXTERNAL, False = FORWARD


@dataclass
class _Attrs:
    main: bool = False
    variable: bool = False
    callable_: bool = False
    interrupt: bool = False
    priv: bool = False
    resident: bool = False
    extensible: bool = False
    extensible_count: int | None = None
    language: str = ""


# ---------------------------------------------------------------------------

class ProcHeaderTransformer(Transformer):

    # ─── Entry points ──────────────────────────────────────────────────────

    def proc_def(self, items) -> ProcHeader:
        return_type = next((x for x in items if isinstance(x, TalType)), None)
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        pub = next((x.value for x in items if isinstance(x, _PublicName)), "")
        params_raw = next((x for x in items if isinstance(x, list)), [])
        params = [p for p in params_raw if isinstance(p, ParamDecl)]
        pairs  = [p for p in params_raw if isinstance(p, tuple)]
        attrs  = next((x for x in items if isinstance(x, _Attrs)), _Attrs())
        ef     = next((x for x in items if isinstance(x, _ExtFwd)), None)
        return ProcHeader(
            name=str(name_tok),
            loc=SourceLocation(name_tok.line or 0, name_tok.column or 0),
            return_type=return_type,
            public_name=pub,
            params=params,
            param_pairs=pairs,
            is_subproc=False,
            is_main=attrs.main,
            is_variable=attrs.variable,
            is_callable=attrs.callable_,
            is_extensible=attrs.extensible,
            extensible_count=attrs.extensible_count,
            is_interrupt=attrs.interrupt,
            is_priv=attrs.priv,
            is_resident=attrs.resident,
            language=attrs.language,
            is_external=ef is not None and ef.is_external,
            is_forward=ef is not None and not ef.is_external,
        )

    def subproc_def(self, items) -> ProcHeader:
        return_type = next((x for x in items if isinstance(x, TalType)), None)
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        params_raw = next((x for x in items if isinstance(x, list)), [])
        params = [p for p in params_raw if isinstance(p, ParamDecl)]
        pairs  = [p for p in params_raw if isinstance(p, tuple)]
        is_variable = any(isinstance(x, Token) and x.type == "KW_VARIABLE" for x in items)
        return ProcHeader(
            name=str(name_tok),
            loc=SourceLocation(name_tok.line or 0, name_tok.column or 0),
            return_type=return_type,
            public_name="",
            params=params,
            param_pairs=pairs,
            is_subproc=True,
            is_main=False,
            is_variable=is_variable,
            is_callable=False,
            is_extensible=False,
            extensible_count=None,
            is_interrupt=False,
            is_priv=False,
            is_resident=False,
            language="",
            is_external=False,
            is_forward=False,
        )

    # ─── Return type ───────────────────────────────────────────────────────

    def return_type(self, items) -> TalType:
        t = items[0].type
        if t == "TK_INT":      return TalType.INT
        if t == "TK_INT32":    return TalType.INT32
        if t == "TK_REAL":     return TalType.REAL
        if t == "TK_REAL64":   return TalType.REAL64
        if t == "TK_FIXED":    return TalType.FIXED
        if t == "TK_UNSIGNED": return TalType.UNSIGNED
        if t == "TK_STRING":   return TalType.STRING
        return TalType.INT

    # ─── Public name ───────────────────────────────────────────────────────

    def pub_name(self, items) -> _PublicName:
        tok = next(t for t in items if isinstance(t, Token) and t.type == "STRING_LIT")
        return _PublicName(str(tok).strip('"'))

    # ─── Parameter list ────────────────────────────────────────────────────

    def param_list(self, items) -> list:
        return [x for x in items if isinstance(x, (ParamDecl, tuple))]

    def param_name(self, items) -> ParamDecl:
        tok = items[0]
        return ParamDecl(
            name=str(tok), tal_type=TalType.INT,
            loc=SourceLocation(tok.line or 0, tok.column or 0) if isinstance(tok, Token) else SourceLocation(0),
        )

    def param_pair(self, items) -> tuple[str, str]:
        names = [str(t) for t in items if isinstance(t, Token) and t.type == "NAME"]
        return (names[0], names[1]) if len(names) >= 2 else ("", "")

    def typed_param_ext(self, items) -> ParamDecl:
        tal_type = next((x for x in items if isinstance(x, TalType)), TalType.INT)
        indir = next((x for x in items if isinstance(x, tuple) and len(x) == 2
                      and isinstance(x[0], bool)), None)
        is_ref = indir is not None
        is_ext = indir == (True, True) if indir else False
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        return ParamDecl(
            name=str(name_tok), tal_type=tal_type,
            is_reference=is_ref, is_extended=is_ext,
            loc=SourceLocation(name_tok.line or 0, name_tok.column or 0),
        )

    def p_ext(self, _) -> tuple[bool, bool]: return (True, True)
    def p_std(self, _) -> tuple[bool, bool]: return (True, False)

    # ─── Proc attribute accumulator ────────────────────────────────────────

    def attr_list(self, items) -> _Attrs:
        result = _Attrs()
        for a in items:
            if not isinstance(a, _Attrs):
                continue
            if a.main:      result.main = True
            if a.variable:  result.variable = True
            if a.callable_: result.callable_ = True
            if a.interrupt: result.interrupt = True
            if a.priv:      result.priv = True
            if a.resident:  result.resident = True
            if a.extensible:result.extensible = True
            if a.extensible_count is not None:
                result.extensible_count = a.extensible_count
            if a.language:  result.language = a.language
        return result

    def no_attrs(self, _) -> _Attrs: return _Attrs()

    def attr_main(self, _) -> _Attrs:      return _Attrs(main=True)
    def attr_variable(self, _) -> _Attrs:  return _Attrs(variable=True)
    def attr_callable(self, _) -> _Attrs:  return _Attrs(callable_=True)
    def attr_interrupt(self, _) -> _Attrs: return _Attrs(interrupt=True)
    def attr_priv(self, _) -> _Attrs:      return _Attrs(priv=True)
    def attr_resident(self, _) -> _Attrs:  return _Attrs(resident=True)
    def attr_extensible(self, _) -> _Attrs: return _Attrs(extensible=True)

    def attr_extensible_n(self, items) -> _Attrs:
        tok = next(t for t in items if isinstance(t, Token) and t.type == "NUMBER_INT")
        try:
            count = _parse_int(str(tok))
        except (ValueError, AttributeError):
            count = 0
        return _Attrs(extensible=True, extensible_count=count)

    def attr_language(self, items) -> _Attrs:
        # Token is a str subclass — use exact type check to get only the plain str
        # returned by lang_spec, not the KW_LANGUAGE Token.
        lang = next((x for x in items if type(x) is str), "")
        return _Attrs(language=lang)

    def lang_spec(self, items) -> str:
        return str(items[0]).upper()

    # ─── EXTERNAL / FORWARD ────────────────────────────────────────────────

    def is_external(self, _) -> _ExtFwd: return _ExtFwd(is_external=True)
    def is_forward(self, _) -> _ExtFwd:  return _ExtFwd(is_external=False)

    # ─── bound_expr (same int-returning pattern as var_decl) ───────────────

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
            return -(items[1] if isinstance(items[1], int) else 0)
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
        return 0
