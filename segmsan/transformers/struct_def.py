"""Phase 2 transformer: struct declarations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lark import Lark, Transformer
from lark.lexer import Token

from ..ast_nodes import ArrayBounds, SourceLocation, TalType, VarDecl

_GRAMMAR_COMMON = Path(__file__).parent.parent / "grammar" / "common_decl.lark"
_GRAMMAR_PATH = Path(__file__).parent.parent / "grammar" / "struct_def.lark"

_lark_parser: Lark | None = None


def _get_lark_parser() -> Lark:
    global _lark_parser
    if _lark_parser is None:
        grammar = _GRAMMAR_COMMON.read_text() + "\n" + _GRAMMAR_PATH.read_text()
        _lark_parser = Lark(grammar, parser="lalr", lexer="basic", start="struct_decl")
    return _lark_parser


def parse_struct_decl(lark_token_iter) -> list[VarDecl]:
    """Parse a single struct_decl token stream. Returns list[VarDecl] (1..N items)."""
    lp = _get_lark_parser()
    ip = lp.parse_interactive("")
    for tok in lark_token_iter:
        ip.feed_token(tok)
    tree = ip.feed_eof()
    result = StructDeclTransformer().transform(tree)
    if isinstance(result, VarDecl):
        return [result]
    return result


# ---------------------------------------------------------------------------
# Internal dataclasses

@dataclass
class _StructHead:
    name: str
    loc: SourceLocation
    is_indirect: bool
    is_extended: bool
    paren_content: str        # "" | "*" | template_name
    array_bounds: ArrayBounds | None
    redef_target: str         # "" | previous_identifier


@dataclass
class _FieldItem:
    name: str
    loc: SourceLocation
    is_indirect: bool
    is_extended: bool
    template_name: str        # "" if no struct_ptr_ref
    array_bounds: ArrayBounds | None
    redef_target: str         # "" if no redefinition


# Sentinel wrappers to distinguish two str-valued optionals in the same items list.

@dataclass
class _ParenContent:
    value: str


@dataclass
class _RedefTarget:
    name: str


def _parse_int(s: str) -> int:
    s = s.strip().upper()
    if s.startswith("%H"):
        return int(s[2:], 16)
    if s.startswith("%B"):
        return int(s[2:], 2)
    if s.startswith("%"):
        return int(s[1:], 8)
    return int(s)


def _build_struct_head(items) -> _StructHead:
    is_indirect = False
    is_extended = False
    name_tok: Token | None = None
    paren_content = ""
    ab: ArrayBounds | None = None
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
    loc = (
        SourceLocation(name_tok.line or 0, name_tok.column or 0)
        if name_tok
        else SourceLocation(0)
    )
    return _StructHead(
        name=name,
        loc=loc,
        is_indirect=is_indirect,
        is_extended=is_extended,
        paren_content=paren_content,
        array_bounds=ab,
        redef_target=redef,
    )


# ---------------------------------------------------------------------------

class StructDeclTransformer(Transformer):

    def struct_kw(self, items) -> str:
        return str(items[0])

    def struct_with_body(self, items) -> VarDecl:
        head = next(item for item in items if isinstance(item, _StructHead))
        body = next((item for item in items if isinstance(item, list)), [])
        is_template = (head.paren_content == "*")
        return VarDecl(
            name=head.name,
            tal_type=TalType.STRUCT,
            loc=head.loc,
            is_indirect=head.is_indirect,
            is_extended=head.is_extended,
            array_bounds=head.array_bounds,
            struct_fields=body,
            is_template=is_template,
            template_name="" if is_template else head.paren_content,
            is_equivalence=bool(head.redef_target),
            equivalence_target=head.redef_target or None,
        )

    def struct_no_body(self, items) -> VarDecl:
        head = next(item for item in items if isinstance(item, _StructHead))
        return VarDecl(
            name=head.name,
            tal_type=TalType.STRUCT,
            loc=head.loc,
            is_indirect=head.is_indirect,
            is_extended=head.is_extended,
            array_bounds=head.array_bounds,
            struct_fields=None,
            is_template=False,
            template_name="",
            is_equivalence=bool(head.redef_target),
            equivalence_target=head.redef_target or None,
        )

    def struct_var_list(self, items) -> list[VarDecl]:
        heads = [x for x in items if isinstance(x, _StructHead)]
        return [
            VarDecl(
                name=h.name,
                tal_type=TalType.STRUCT,
                loc=h.loc,
                is_indirect=h.is_indirect,
                is_extended=h.is_extended,
                array_bounds=h.array_bounds,
                struct_fields=None,
                is_template=False,
                template_name=h.paren_content,
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

    def template_marker(self, _items) -> _ParenContent:
        return _ParenContent("*")

    def referral_marker(self, items) -> _ParenContent:
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        return _ParenContent(str(name_tok))

    def struct_body(self, items) -> list[VarDecl]:
        result: list[VarDecl] = []
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
        dt = next((x for x in items if isinstance(x, tuple) and len(x) == 3 and not isinstance(x[0], bool)), None)
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

    def data_type(self, items) -> tuple[TalType, int, int]:
        t = items[0].type
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

    def struct_field_list(self, items) -> list[_FieldItem]:
        return [item for item in items if isinstance(item, _FieldItem)]

    def struct_field_item(self, items) -> _FieldItem:
        is_indirect = False
        is_extended = False
        name_tok: Token | None = None
        template_name = ""
        ab: ArrayBounds | None = None
        redef = ""

        for item in items:
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], bool):
                is_indirect, is_extended = item
            elif isinstance(item, Token) and item.type == "NAME":
                name_tok = item
            elif isinstance(item, str):
                # struct_ptr_ref returns str (template name)
                template_name = item
            elif isinstance(item, _RedefTarget):
                redef = item.name
            elif isinstance(item, ArrayBounds):
                ab = item

        name = str(name_tok) if name_tok else ""
        loc = (
            SourceLocation(name_tok.line or 0, name_tok.column or 0)
            if name_tok
            else SourceLocation(0)
        )
        return _FieldItem(
            name=name,
            loc=loc,
            is_indirect=is_indirect,
            is_extended=is_extended,
            template_name=template_name,
            array_bounds=ab,
            redef_target=redef,
        )

    def struct_ptr_ref(self, items) -> str:
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        return str(name_tok)

    def redef_target(self, items) -> _RedefTarget:
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        return _RedefTarget(str(name_tok))

    def filler_item(self, _items) -> None:
        return None

    def bit_filler_item(self, _items) -> None:
        return None

    def ind_standard(self, _items) -> tuple[bool, bool]:
        return (True, False)

    def ind_extended(self, _items) -> tuple[bool, bool]:
        return (True, True)

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


# ---------------------------------------------------------------------------
# Build VarDecl list from struct_item when it's the fields case
# (data_type + list[_FieldItem] → list[VarDecl])

def _build_field_decls(
    tal_type: TalType,
    fpoint: int,
    width: int,
    field_items: list[_FieldItem],
) -> list[VarDecl]:
    return [
        VarDecl(
            name=fi.name,
            tal_type=tal_type,
            loc=fi.loc,
            is_indirect=fi.is_indirect,
            is_extended=fi.is_extended,
            array_bounds=fi.array_bounds,
            template_name=fi.template_name,
            is_equivalence=bool(fi.redef_target),
            equivalence_target=fi.redef_target or None,
            fpoint=fpoint,
            width=width,
        )
        for fi in field_items
    ]
