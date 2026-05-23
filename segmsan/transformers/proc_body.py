"""Phase 8 transformer: complete procedure bodies.

Combines all grammar phases (1-7) into a single parser whose start rule is
proc_unit.  ProcBodyTransformer inherits StmtTransformer (→ ExprTransformer)
and adds methods for var_decl, struct_decl, literal_decl, proc_header, and
proc_body grammar rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from lark import Lark, Transformer
from lark.lexer import Token

from ..ast_nodes import (
    ArrayBounds, Expr, LiteralExpr, VarExpr, BinOpExpr, UnaryExpr,
    SourceLocation, TalType, VarDecl, ParamDecl, ParamSpec,
    Statement, OtherStmt,
    Procedure, GroupCmpExpr, SubstringExpr,
)
from .stmt import StmtTransformer, _PHASE7_MARKER
from .var_decl import _parse_int as _parse_int_literal, _VarInit
from .literal_decl import (
    LiteralDeclTransformer as _LitT,
    _LiteralEntry, _parse_int32, _parse_fixed, _parse_char_lit, _parse_string_lit,
)
from .expr import eval_const_expr
from ..lexer import to_proc_body_stream

# ─── Grammar file paths ────────────────────────────────────────────────────────

_GRAMMAR_DIR = Path(__file__).parent.parent / "grammar"
_GRAMMAR_EXPR     = _GRAMMAR_DIR / "expr.lark"
_GRAMMAR_COMMON   = _GRAMMAR_DIR / "common_decl.lark"
_GRAMMAR_VAR      = _GRAMMAR_DIR / "var_decl.lark"
_GRAMMAR_STRUCT   = _GRAMMAR_DIR / "struct_def.lark"
_GRAMMAR_LITERAL  = _GRAMMAR_DIR / "literal_decl.lark"
_GRAMMAR_STMT     = _GRAMMAR_DIR / "stmt_simple.lark"
_GRAMMAR_COMPLEX  = _GRAMMAR_DIR / "stmt_complex.lark"
_GRAMMAR_PROC     = _GRAMMAR_DIR / "proc_body.lark"

# ─── Master %declare for Phase 8 combined grammar ─────────────────────────────
# Replaces all %declare lines stripped from individual component files.
_PHASE8_DECLARES = """\
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
%declare DIRECTIVE
"""

_lark_parser_proc_body: Lark | None = None


def _strip_declares(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("%declare")
    )


def _get_proc_body_parser() -> Lark:
    global _lark_parser_proc_body
    if _lark_parser_proc_body is None:
        expr    = _GRAMMAR_EXPR.read_text()
        common  = _GRAMMAR_COMMON.read_text()
        var     = _GRAMMAR_VAR.read_text()
        struct  = _GRAMMAR_STRUCT.read_text()
        literal = _GRAMMAR_LITERAL.read_text()
        stmt    = _GRAMMAR_STMT.read_text()
        stmt_base = stmt.split(_PHASE7_MARKER)[0]
        complex_ = _GRAMMAR_COMPLEX.read_text()
        proc    = _GRAMMAR_PROC.read_text()
        parts = [expr, common, var, struct, literal, stmt_base, complex_, proc]
        combined = _PHASE8_DECLARES + "\n" + "\n".join(_strip_declares(t) for t in parts)
        _lark_parser_proc_body = Lark(combined, parser="lalr", lexer="basic", start="proc_unit")
    return _lark_parser_proc_body


def parse_procedure(lark_token_iter) -> Procedure:
    """Parse a proc_unit from a pre-converted Lark token stream."""
    lp = _get_proc_body_parser()
    ip = lp.parse_interactive("")
    for tok in lark_token_iter:
        ip.feed_token(tok)
    tree = ip.feed_eof()
    result = ProcBodyTransformer().transform(tree)
    if isinstance(result, Procedure):
        return result
    raise ValueError(f"Expected Procedure, got {type(result)}")


def parse_procedure_src(src: str) -> Procedure:
    """Parse a complete proc_unit from TAL source text (for testing)."""
    from ..lexer import Lexer
    raw = Lexer(src).tokenize()
    lark_tokens = list(to_proc_body_stream(raw))
    return parse_procedure(iter(lark_tokens))


# ─── Internal sentinels (shared with proc_header logic) ───────────────────────

@dataclass
class _PublicName:
    value: str

@dataclass
class _ExtFwd:
    is_external: bool

@dataclass
class _Attrs:
    main: bool = False
    variable: bool = False
    callable_: bool = False
    interrupt: bool = False
    priv: bool = False
    resident: bool = False
    extensible: bool = False
    extensible_count: Optional[int] = None
    language: str = ""

@dataclass
class _VarItem:
    name: str
    loc: SourceLocation
    is_indirect: bool
    is_extended: bool
    array_bounds: Optional[ArrayBounds]
    has_initializer: bool
    public_name: str = ""
    template_name: str = ""

@dataclass
class _StructHead:
    name: str
    loc: SourceLocation
    is_indirect: bool
    is_extended: bool
    paren_content: str
    array_bounds: Optional[ArrayBounds]
    redef_target: str

@dataclass
class _FieldItem:
    name: str
    loc: SourceLocation
    is_indirect: bool
    is_extended: bool
    template_name: str
    array_bounds: Optional[ArrayBounds]
    redef_target: str

@dataclass
class _ParenContent:
    value: str

@dataclass
class _RedefTarget:
    name: str

def _build_struct_head(items) -> _StructHead:
    is_indirect = False
    is_extended = False
    name_tok = None
    paren_content = ""
    ab = None
    redef = ""
    for item in items:
        if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], bool):
            is_indirect, is_extended = item
        elif isinstance(item, Token) and item.type == "NAME":
            name_tok = item
        elif isinstance(item, _ParenContent):
            paren_content = item.value
        elif isinstance(item, _RedefTarget):
            redef = item.name
        elif isinstance(item, ArrayBounds):
            ab = item
    name = str(name_tok) if name_tok else ""
    loc = (SourceLocation(name_tok.line or 0, name_tok.column or 0)
           if name_tok else SourceLocation(0))
    return _StructHead(name=name, loc=loc, is_indirect=is_indirect,
                       is_extended=is_extended, paren_content=paren_content,
                       array_bounds=ab, redef_target=redef)


@dataclass
class _ProcHdr:
    name: str
    loc: SourceLocation
    return_type: Optional[TalType]
    public_name: str
    params: list
    param_pairs: list
    attrs: _Attrs

@dataclass
class _SubHdr:
    name: str
    loc: SourceLocation
    return_type: Optional[TalType]
    params: list
    param_pairs: list
    is_variable: bool

@dataclass
class _ProcBody:
    locals_: list
    entry_points: list
    label_decls: list
    subprocs: list
    body: list
    param_specs: list = field(default_factory=list)
    is_forward: bool = False
    is_external: bool = False

@dataclass
class _LiteralEntry:
    name: str
    value: Optional[Expr]


def _build_field_decls(tal_type, fpoint, width, field_items):
    """Build VarDecl list from struct_field_list items."""
    result = []
    for fi in field_items:
        if not isinstance(fi, _FieldItem):
            continue
        result.append(VarDecl(
            name=fi.name,
            tal_type=tal_type,
            loc=fi.loc,
            is_indirect=fi.is_indirect,
            is_extended=fi.is_extended,
            array_bounds=fi.array_bounds,
            fpoint=fpoint,
            width=width,
            template_name=fi.template_name,
            is_equivalence=bool(fi.redef_target),
            equivalence_target=fi.redef_target or None,
        ))
    return result


# ─── Transformer ──────────────────────────────────────────────────────────────

class ProcBodyTransformer(StmtTransformer):
    """Handles all grammar rules from Phases 1-8 in one transformer."""

    # ─── Phase 8: proc_unit ───────────────────────────────────────────────────

    def _collect_flat_items(self, items) -> _ProcBody:
        """Collect proc body items by type from a flattened transformer items list."""
        locals_: list = []
        subprocs: list = []
        entry_points: list = []
        label_decls: list = []
        param_specs: list = []
        body: list = []
        for item in items:
            if isinstance(item, VarDecl):
                locals_.append(item)
            elif isinstance(item, Procedure):
                subprocs.append(item)
            elif isinstance(item, _EntryPoint):
                entry_points.extend(item.names)
            elif isinstance(item, _LabelDecl):
                label_decls.extend(item.names)
            elif isinstance(item, ParamSpec):
                param_specs.append(item)
            elif isinstance(item, list) and item:
                if isinstance(item[0], VarDecl):
                    locals_.extend(item)
                elif isinstance(item[0], Statement):
                    body = item
            # Tokens (KW_BEGIN, KW_END, SEMI), None (define_), tuples (literal_decl) → ignored
        return _ProcBody(locals_=locals_, entry_points=entry_points,
                         label_decls=label_decls, subprocs=subprocs,
                         body=body, param_specs=param_specs)

    def pre_begin_decl(self, items):
        return items[0] if items else None

    def proc_item(self, items):
        return items[0] if items else None

    def proc_body_begin(self, items) -> _ProcBody:
        return self._collect_flat_items(items)

    def proc_body_no_begin(self, items) -> _ProcBody:
        return self._collect_flat_items(items)

    def proc_body_forward(self, items) -> _ProcBody:
        body = self._collect_flat_items(items)
        body.is_forward = True
        return body

    def proc_body_external(self, items) -> _ProcBody:
        body = self._collect_flat_items(items)
        body.is_external = True
        return body

    def proc_full(self, items) -> Procedure:
        hdr = next(x for x in items if isinstance(x, _ProcHdr))
        body = next((x for x in items if isinstance(x, _ProcBody)),
                    _ProcBody([], [], [], [], []))
        param_names = {p.name.upper() for p in hdr.params if isinstance(p, ParamDecl)}
        if param_names:
            body.locals_ = [v for v in body.locals_ if v.name.upper() not in param_names]
        return Procedure(
            name=hdr.name,
            loc=hdr.loc,
            return_type=hdr.return_type,
            public_name=hdr.public_name,
            params=hdr.params,
            param_pairs=hdr.param_pairs,
            param_specs=body.param_specs,
            is_main=hdr.attrs.main,
            is_variable=hdr.attrs.variable,
            is_callable=hdr.attrs.callable_,
            is_extensible=hdr.attrs.extensible,
            extensible_count=hdr.attrs.extensible_count,
            is_interrupt=hdr.attrs.interrupt,
            is_priv=hdr.attrs.priv,
            is_resident=hdr.attrs.resident,
            language=hdr.attrs.language,
            locals_=body.locals_,
            entry_points=body.entry_points,
            label_decls=body.label_decls,
            subprocs=body.subprocs,
            body=body.body,
            is_forward=body.is_forward,
            is_external=body.is_external,
        )

    def proc_external(self, items) -> Procedure:
        hdr = next(x for x in items if isinstance(x, _ProcHdr))
        return Procedure(
            name=hdr.name, loc=hdr.loc,
            return_type=hdr.return_type,
            params=hdr.params,
            is_external=True,
        )

    def proc_forward(self, items) -> Procedure:
        hdr = next(x for x in items if isinstance(x, _ProcHdr))
        return Procedure(
            name=hdr.name, loc=hdr.loc,
            return_type=hdr.return_type,
            params=hdr.params,
            is_forward=True,
        )

    def proc_hdr_(self, items) -> _ProcHdr:
        return self._build_proc_hdr(items)

    def proc_hdr_nosemi(self, items) -> _ProcHdr:
        return self._build_proc_hdr(items)

    def _build_proc_hdr(self, items) -> _ProcHdr:
        rt = next((x for x in items if isinstance(x, TalType)), None)
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        pub = next((x.value for x in items if isinstance(x, _PublicName)), "")
        params_raw = next((x for x in items if isinstance(x, list)), [])
        params = [p for p in params_raw if isinstance(p, ParamDecl)]
        pairs  = [p for p in params_raw if isinstance(p, tuple)]
        attrs  = next((x for x in items if isinstance(x, _Attrs)), _Attrs())
        return _ProcHdr(
            name=str(name_tok),
            loc=SourceLocation(name_tok.line or 0, name_tok.column or 0),
            return_type=rt,
            public_name=pub,
            params=params,
            param_pairs=pairs,
            attrs=attrs,
        )

    # ─── Phase 8: subproc_decl ────────────────────────────────────────────────

    def sub_body_begin(self, items) -> _ProcBody:
        return self._collect_flat_items(items)

    def sub_body_no_begin(self, items) -> _ProcBody:
        return self._collect_flat_items(items)

    def subproc_full(self, items) -> Procedure:
        hdr = next(x for x in items if isinstance(x, _SubHdr))
        body = next((x for x in items if isinstance(x, _ProcBody)),
                    _ProcBody([], [], [], [], []))
        param_names = {p.name.upper() for p in hdr.params if isinstance(p, ParamDecl)}
        if param_names:
            body.locals_ = [v for v in body.locals_ if v.name.upper() not in param_names]
        return Procedure(
            name=hdr.name, loc=hdr.loc,
            return_type=hdr.return_type,
            params=hdr.params,
            param_pairs=hdr.param_pairs,
            param_specs=body.param_specs,
            is_subproc=True,
            is_variable=hdr.is_variable,
            locals_=body.locals_,
            entry_points=body.entry_points,
            label_decls=body.label_decls,
            subprocs=[],
            body=body.body,
        )

    def subproc_forward(self, items) -> Procedure:
        hdr = next(x for x in items if isinstance(x, _SubHdr))
        return Procedure(
            name=hdr.name, loc=hdr.loc,
            return_type=hdr.return_type,
            params=hdr.params,
            is_subproc=True,
            is_forward=True,
        )

    def sub_hdr_(self, items) -> _SubHdr:
        rt = next((x for x in items if isinstance(x, TalType)), None)
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        params_raw = next((x for x in items if isinstance(x, list)), [])
        params = [p for p in params_raw if isinstance(p, ParamDecl)]
        pairs  = [p for p in params_raw if isinstance(p, tuple)]
        is_var = any(isinstance(x, Token) and x.type == "KW_VARIABLE" for x in items)
        return _SubHdr(
            name=str(name_tok),
            loc=SourceLocation(name_tok.line or 0, name_tok.column or 0),
            return_type=rt,
            params=params,
            param_pairs=pairs,
            is_variable=is_var,
        )

    # ─── Phase 8: pre_begin_decl dispatch ─────────────────────────────────────
    # These rules reduce to their child type naturally — no explicit handler needed
    # for pre_begin_decl / sublocal_decl / local_decl.

    def proc_param_typed32(self, items) -> ParamSpec:
        rt = next((x for x in items if isinstance(x, TalType)), None)
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        indir = next((x for x in items if isinstance(x, tuple) and len(x) == 2), None)
        return ParamSpec(
            name=str(name_tok),
            param_type="PROC",
            return_type=rt.value if rt else None,
            is_reference=indir is not None,
            is_extended=(indir == (True, True)) if indir else False,
        )

    def proc_param_typed(self, items) -> ParamSpec:
        rt = next((x for x in items if isinstance(x, TalType)), None)
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        indir = next((x for x in items if isinstance(x, tuple) and len(x) == 2), None)
        return ParamSpec(
            name=str(name_tok),
            param_type="PROC",
            return_type=rt.value if rt else None,
            is_reference=indir is not None,
            is_extended=(indir == (True, True)) if indir else False,
        )

    def proc_param32(self, items) -> ParamSpec:
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        indir = next((x for x in items if isinstance(x, tuple) and len(x) == 2), None)
        return ParamSpec(
            name=str(name_tok), param_type="PROC",
            is_reference=indir is not None,
            is_extended=(indir == (True, True)) if indir else False,
        )

    def proc_param(self, items) -> ParamSpec:
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        indir = next((x for x in items if isinstance(x, tuple) and len(x) == 2), None)
        return ParamSpec(
            name=str(name_tok), param_type="PROC",
            is_reference=indir is not None,
            is_extended=(indir == (True, True)) if indir else False,
        )

    def define_(self, items) -> None:
        return None

    def proc_directive(self, items) -> None:
        return None

    def entry_point(self, items) -> _EntryPoint:
        names = [str(t) for t in items if isinstance(t, Token) and t.type == "NAME"]
        return _EntryPoint(names)

    def label_decl_(self, items) -> _LabelDecl:
        names = [str(t) for t in items if isinstance(t, Token) and t.type == "NAME"]
        return _LabelDecl(names)

    # ─── From ProcHeaderTransformer (common_decl rules) ───────────────────────

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

    def pub_name(self, items) -> _PublicName:
        tok = next(t for t in items if isinstance(t, Token) and t.type == "STRING_LIT")
        return _PublicName(str(tok).strip('"'))

    def param_list(self, items) -> list:
        result = []
        for x in items:
            if isinstance(x, ParamDecl):
                result.append(x)
            elif isinstance(x, list):  # variable_param_pair returns list of ParamDecl
                result.extend(p for p in x if isinstance(p, ParamDecl))
            elif isinstance(x, tuple):
                result.append(x)
        return result

    def param_name(self, items) -> ParamDecl:
        tok = items[0]
        return ParamDecl(
            name=str(tok), tal_type=TalType.INT,
            loc=SourceLocation(tok.line or 0, tok.column or 0) if isinstance(tok, Token) else SourceLocation(0),
        )

    def variable_param_pair(self, items) -> list:
        # KW_VARIABLE param_indir NAME — "VARIABLE" is a keyword, not a param name
        tok = next(t for t in items if isinstance(t, Token) and t.type == "KW_VARIABLE")
        indir = next((x for x in items if isinstance(x, tuple) and len(x) == 2
                      and isinstance(x[0], bool)), None)
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        return [
            ParamDecl(name="VARIABLE", tal_type=TalType.INT,
                      loc=SourceLocation(tok.line or 0, tok.column or 0)),
            ParamDecl(name=str(name_tok), tal_type=TalType.INT,
                      is_reference=True,
                      is_extended=(indir == (True, True)) if indir else False,
                      loc=SourceLocation(name_tok.line or 0, name_tok.column or 0)),
        ]

    def typed_param_ptr(self, items) -> ParamDecl:
        indir = next((x for x in items if isinstance(x, tuple) and len(x) == 2
                      and isinstance(x[0], bool)), None)
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        return ParamDecl(
            name=str(name_tok), tal_type=TalType.INT,
            is_reference=True,
            is_extended=(indir == (True, True)) if indir else False,
            loc=SourceLocation(name_tok.line or 0, name_tok.column or 0),
        )

    def param_pair(self, items) -> tuple:
        names = [str(t) for t in items if isinstance(t, Token) and t.type == "NAME"]
        return (names[0], names[1]) if len(names) >= 2 else ("", "")

    def typed_param_ext(self, items) -> ParamDecl:
        tal_type = next((x for x in items if isinstance(x, TalType)), TalType.INT)
        indir = next((x for x in items if isinstance(x, tuple) and len(x) == 2
                      and isinstance(x[0], bool)), None)
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        return ParamDecl(
            name=str(name_tok), tal_type=tal_type,
            is_reference=indir is not None,
            is_extended=(indir == (True, True)) if indir else False,
            loc=SourceLocation(name_tok.line or 0, name_tok.column or 0),
        )

    def p_ext(self, _) -> tuple: return (True, True)
    def p_std(self, _) -> tuple: return (True, False)

    def attr_list(self, items) -> _Attrs:
        result = _Attrs()
        for a in items:
            if not isinstance(a, _Attrs):
                continue
            if a.main:       result.main = True
            if a.variable:   result.variable = True
            if a.callable_:  result.callable_ = True
            if a.interrupt:  result.interrupt = True
            if a.priv:       result.priv = True
            if a.resident:   result.resident = True
            if a.extensible: result.extensible = True
            if a.extensible_count is not None:
                result.extensible_count = a.extensible_count
            if a.language:   result.language = a.language
        return result

    def no_attrs(self, _)    -> _Attrs: return _Attrs()
    def attr_main(self, _)       -> _Attrs: return _Attrs(main=True)
    def attr_variable(self, _)   -> _Attrs: return _Attrs(variable=True)
    def attr_callable(self, _)   -> _Attrs: return _Attrs(callable_=True)
    def attr_interrupt(self, _)  -> _Attrs: return _Attrs(interrupt=True)
    def attr_priv(self, _)       -> _Attrs: return _Attrs(priv=True)
    def attr_resident(self, _)   -> _Attrs: return _Attrs(resident=True)
    def attr_extensible(self, _) -> _Attrs: return _Attrs(extensible=True)

    def attr_extensible_n(self, items) -> _Attrs:
        tok = next(t for t in items if isinstance(t, Token) and t.type == "NUMBER_INT")
        try:
            count = _parse_int_literal(str(tok))
        except (ValueError, AttributeError):
            count = 0
        return _Attrs(extensible=True, extensible_count=count)

    def attr_language(self, items) -> _Attrs:
        lang = next((x for x in items if type(x) is str), "")
        return _Attrs(language=lang)

    def lang_spec(self, items) -> str:
        return str(items[0]).upper()

    def is_external(self, _) -> _ExtFwd: return _ExtFwd(is_external=True)
    def is_forward(self, _)  -> _ExtFwd: return _ExtFwd(is_external=False)

    def param_bounds(self, items) -> ArrayBounds:
        ints = [x for x in items if isinstance(x, int)]
        return ArrayBounds(lo=ints[0], hi=ints[1]) if len(ints) >= 2 else ArrayBounds(0, 0)

    # ─── From VarDeclTransformer ──────────────────────────────────────────────

    def var_decl(self, items) -> list:
        tal_type, fpoint, width = items[0]
        return [
            VarDecl(
                name=vi.name, tal_type=tal_type, loc=vi.loc,
                is_indirect=vi.is_indirect, is_extended=vi.is_extended,
                array_bounds=vi.array_bounds, has_initializer=vi.has_initializer,
                public_name=vi.public_name,
                fpoint=fpoint, width=width, template_name=vi.template_name,
            )
            for vi in items[1:] if isinstance(vi, _VarItem)
        ]

    def data_type(self, items) -> tuple:
        t = items[0].type
        if t == "TK_INT":      return (TalType.INT, 0, 0)
        if t == "TK_INT32":    return (TalType.INT32, 0, 0)
        if t == "TK_REAL":     return (TalType.REAL, 0, 0)
        if t == "TK_REAL64":   return (TalType.REAL64, 0, 0)
        if t == "TK_STRING":   return (TalType.STRING, 0, 0)
        if t == "TK_FIXED":    return (TalType.FIXED, 0, 0)
        if t == "TK_UNSIGNED": return (TalType.UNSIGNED, 0, 0)
        return (TalType.INT, 0, 0)

    def ind_standard(self, _) -> tuple: return (True, False)
    def ind_extended(self, _) -> tuple: return (True, True)

    def var_item(self, items) -> _VarItem:
        is_indirect = False
        is_extended = False
        name_tok = None
        ab = None
        has_init = False
        pub_name = ""
        template_name = ""
        for item in items:
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], bool):
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
        loc = (SourceLocation(name_tok.line or 0, name_tok.column or 0)
               if name_tok else SourceLocation(0))
        return _VarItem(name=name, loc=loc, is_indirect=is_indirect,
                        is_extended=is_extended, array_bounds=ab,
                        has_initializer=has_init, public_name=pub_name,
                        template_name=template_name)

    def struct_ptr_ref(self, items) -> str:
        return str(next(t for t in items if isinstance(t, Token) and t.type == "NAME"))

    def array_bounds(self, items) -> ArrayBounds:
        ints = [x for x in items if isinstance(x, int)]
        return ArrayBounds(lo=ints[0], hi=ints[1]) if len(ints) >= 2 else ArrayBounds(0, 0)

    def bound_expr(self, items) -> int:
        return items[0] if isinstance(items[0], int) else 0

    def be_expr(self, items) -> int:
        result = None
        pending_op = None
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
        result = None
        pending_op = None
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
                    return _parse_int_literal(str(item))
                except (ValueError, AttributeError):
                    return 0
        return 0

    # ─── Group Comparison Expression (RefMan §4.15) ────────────────────────────

    _UNITS = frozenset(("BYTES", "WORDS", "ELEMENTS"))

    def cmp_group_for(self, items) -> GroupCmpExpr:
        exprs = [x for x in items if isinstance(x, Expr)]
        op = next((x for x in items if isinstance(x, str) and x not in self._UNITS), "=")
        unit = next((x for x in items if isinstance(x, str) and x in self._UNITS), "")
        # exprs: [left, right, count, ?next_addr]
        return GroupCmpExpr(
            left=exprs[0], op=op, right=exprs[1],
            count=exprs[2] if len(exprs) > 2 else LiteralExpr(value=0),
            unit=unit,
            next_addr=exprs[3] if len(exprs) > 3 else None,
            is_bracketed_const=False,
        )

    def cmp_group_list(self, items) -> GroupCmpExpr:
        exprs = [x for x in items if isinstance(x, Expr)]
        op = next((x for x in items if isinstance(x, str)), "=")
        return GroupCmpExpr(
            left=exprs[0], op=op, right=LiteralExpr(value=0),
            count=None, unit="",
            next_addr=exprs[1] if len(exprs) > 1 else None,
            is_bracketed_const=True,
        )

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
        return str(tok)

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
        result = []
        for item in items:
            if isinstance(item, list):
                result.extend(item)
            elif not isinstance(item, Token):
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

    def repetition(self, items) -> list:
        count_tok = None
        inner = []
        for item in items:
            if isinstance(item, Token) and item.type == "NUMBER_INT" and count_tok is None:
                count_tok = item
            elif isinstance(item, list):
                inner = item
        count = 0
        if count_tok is not None:
            try:
                count = _parse_int_literal(str(count_tok))
            except ValueError:
                count = 0
        return inner * count

    # ─── From StructDeclTransformer ───────────────────────────────────────────

    def struct_kw(self, items) -> str:
        return str(items[0])

    def struct_with_body(self, items) -> VarDecl:
        head = next(x for x in items if isinstance(x, _StructHead))
        body = next((x for x in items if isinstance(x, list)), [])
        is_tmpl = (head.paren_content == "*")
        return VarDecl(
            name=head.name, tal_type=TalType.STRUCT, loc=head.loc,
            is_indirect=head.is_indirect, is_extended=head.is_extended,
            array_bounds=head.array_bounds, struct_fields=body,
            is_template=is_tmpl,
            template_name="" if is_tmpl else head.paren_content,
            is_equivalence=bool(head.redef_target),
            equivalence_target=head.redef_target or None,
        )

    def struct_no_body(self, items) -> VarDecl:
        head = next(x for x in items if isinstance(x, _StructHead))
        return VarDecl(
            name=head.name, tal_type=TalType.STRUCT, loc=head.loc,
            is_indirect=head.is_indirect, is_extended=head.is_extended,
            array_bounds=head.array_bounds, struct_fields=None,
            is_template=False, template_name="",
            is_equivalence=bool(head.redef_target),
            equivalence_target=head.redef_target or None,
        )

    def struct_var_list(self, items) -> list[VarDecl]:
        heads = [x for x in items if isinstance(x, _StructHead)]
        return [
            VarDecl(
                name=h.name, tal_type=TalType.STRUCT, loc=h.loc,
                is_indirect=h.is_indirect, is_extended=h.is_extended,
                array_bounds=h.array_bounds, struct_fields=None,
                is_template=False, template_name=h.paren_content,
                is_equivalence=bool(h.redef_target),
                equivalence_target=h.redef_target or None,
            )
            for h in heads
        ]

    def struct_var_item(self, items) -> _StructHead:
        return next(x for x in items if isinstance(x, _StructHead))

    def struct_head_def(self, items) -> _StructHead:
        return _build_struct_head(items)

    def struct_head_ref(self, items) -> _StructHead:
        return _build_struct_head(items)

    def template_marker(self, _) -> _ParenContent:  return _ParenContent("*")
    def referral_marker(self, items) -> _ParenContent:
        return _ParenContent(str(next(t for t in items if isinstance(t, Token) and t.type == "NAME")))

    def struct_body(self, items) -> list:
        result = []
        for item in items:
            if item is None:
                continue
            if isinstance(item, list):
                result.extend(item)
            elif isinstance(item, VarDecl):
                result.append(item)
        return result

    def struct_item(self, items):
        if not items:
            return None
        dt = next((x for x in items if isinstance(x, tuple) and len(x) == 3
                   and not isinstance(x[0], bool)), None)
        if dt is not None:
            tal_type, fpoint, width = dt
            field_items = next((x for x in items if isinstance(x, list)), [])
            return _build_field_decls(tal_type, fpoint, width, field_items)
        # struct_decl: single VarDecl or list[VarDecl] (struct_var_list)
        for x in items:
            if isinstance(x, list):
                return x
            if isinstance(x, VarDecl):
                return x
        return None

    def struct_field_list(self, items) -> list:
        return [x for x in items if isinstance(x, _FieldItem)]

    def struct_field_item(self, items) -> _FieldItem:
        is_indirect = False
        is_extended = False
        name_tok = None
        template_name = ""
        ab = None
        redef = ""
        for item in items:
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], bool):
                is_indirect, is_extended = item
            elif isinstance(item, Token) and item.type == "NAME":
                name_tok = item
            elif isinstance(item, str):
                template_name = item
            elif isinstance(item, _RedefTarget):
                redef = item.name
            elif isinstance(item, ArrayBounds):
                ab = item
        name = str(name_tok) if name_tok else ""
        loc = (SourceLocation(name_tok.line or 0, name_tok.column or 0)
               if name_tok else SourceLocation(0))
        return _FieldItem(name=name, loc=loc, is_indirect=is_indirect,
                          is_extended=is_extended, template_name=template_name,
                          array_bounds=ab, redef_target=redef)

    def redef_target(self, items) -> _RedefTarget:
        return _RedefTarget(str(next(t for t in items if isinstance(t, Token) and t.type == "NAME")))

    def filler_item(self, _)     -> None: return None
    def bit_filler_item(self, _) -> None: return None

    # ─── From LiteralDeclTransformer ──────────────────────────────────────────

    def literal_decl(self, items) -> list:
        entries = [x for x in items if isinstance(x, _LiteralEntry)]
        result = []
        accumulated = {}
        prev_value = -1
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
        result = None
        pending_op = None
        for item in items:
            if isinstance(item, Token):
                pending_op = "-" if item.type == "MINUS" else "+"
            elif isinstance(item, Expr):
                if result is None:
                    result = item
                else:
                    result = BinOpExpr(op=pending_op or "+", left=result, right=item)
        return result if result is not None else LiteralExpr(value=0)

    def lv_term(self, items) -> Expr:
        result = None
        pending_op = None
        for item in items:
            if isinstance(item, Token):
                pending_op = "/" if item.type == "SLASH" else "*"
            elif isinstance(item, Expr):
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
                    if t == "NUMBER_INT":    return LiteralExpr(value=_parse_int_literal(str(item)))
                    if t == "NUMBER_INT32":  return LiteralExpr(value=_parse_int32(str(item)))
                    if t == "NUMBER_FIXED":  return LiteralExpr(value=_parse_fixed(str(item)))
                    if t == "CHAR_LIT":      return LiteralExpr(value=_parse_char_lit(str(item)))
                    if t == "STRING_LIT":    return LiteralExpr(value=_parse_string_lit(str(item)))
                    if t == "NAME":          return VarExpr(name=str(item).upper())
                except (ValueError, AttributeError):
                    return LiteralExpr(value=0)
        return LiteralExpr(value=0)


# ─── Sentinels for entry/label declarations ────────────────────────────────────

@dataclass
class _EntryPoint:
    names: list

@dataclass
class _LabelDecl:
    names: list
