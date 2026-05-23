"""Phase 4 transformer: Expressions and constant evaluator.

Handles TAL Section 4, Table 4-1 — 10 precedence levels.
Also provides eval_const_expr() for constant folding with LITERAL dict.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lark import Lark, Transformer
from lark.lexer import Token

from ..ast_nodes import (
    Expr, VarExpr, LiteralExpr, BinOpExpr, UnaryExpr, BitExtractExpr,
    AssignExpr, IfExpr, CaseExpr, ConditionCodeExpr,
    FieldExpr, IndexExpr, SubstringExpr, AddressOfExpr, DerefExpr,
    DollarFuncExpr, CallExpr,
    SourceLocation,
)
from .var_decl import _parse_int as _parse_int_literal

_GRAMMAR_PATH = Path(__file__).parent.parent / "grammar" / "expr.lark"

_lark_parser: Lark | None = None


def _get_lark_parser() -> Lark:
    global _lark_parser
    if _lark_parser is None:
        grammar = _GRAMMAR_PATH.read_text()
        _lark_parser = Lark(grammar, parser="lalr", lexer="basic", start="expr")
    return _lark_parser


def parse_expr(lark_token_iter) -> Expr:
    """Parse a complete expression from the token stream."""
    lp = _get_lark_parser()
    ip = lp.parse_interactive("")
    for tok in lark_token_iter:
        ip.feed_token(tok)
    tree = ip.feed_eof()
    return ExprTransformer().transform(tree)


# ─── Internal tail/branch wrappers ───────────────────────────────────────────

@dataclass
class _FieldTail:
    name: str

@dataclass
class _ForSliceTail:
    count: Expr
    unit: str = ""  # "BYTES", "WORDS", "ELEMENTS", or ""

@dataclass
class _IndexTail:
    index: Expr
    for_count: Expr | None = None
    for_unit: str = ""

@dataclass
class _BitExtractTail:
    left_bit: int
    right_bit: int

@dataclass
class _CallPostfixTail:
    args: list

@dataclass
class _CaseBranch:
    expr: Expr

@dataclass
class _OtherwiseBranch:
    expr: Expr


# ─── Transformer ─────────────────────────────────────────────────────────────

class ExprTransformer(Transformer):

    # ─── Pass-through rules (no alias → rule-name method called) ─────────────

    def expr(self, items) -> Expr:
        return items[0]

    def assign_expr(self, items) -> Expr:
        # or_expr ASSIGN assign_expr  (2 Exprs, 1 Token(ASSIGN))
        # | or_expr                   (1 Expr)
        exprs = [x for x in items if isinstance(x, Expr)]
        if len(exprs) == 1:
            return exprs[0]
        return AssignExpr(targets=[exprs[0]], value=exprs[1])

    def not_expr(self, items) -> Expr:
        return items[0]  # cmp_expr pass-through

    def cmp_expr(self, items) -> Expr:
        return items[0]  # add_expr pass-through

    def unary_expr(self, items) -> Expr:
        return items[0]  # postfix pass-through

    def primary(self, items) -> Expr:
        return items[0]  # if_expr / case_expr pass-through

    # ─── Level 9: Assignment ──────────────────────────────────────────────────

    def assign(self, items) -> AssignExpr:
        exprs = [x for x in items if isinstance(x, Expr)]
        return AssignExpr(targets=[exprs[0]], value=exprs[1])

    # ─── Level 8: OR ──────────────────────────────────────────────────────────

    def or_chain(self, items) -> Expr:
        exprs = [x for x in items if isinstance(x, Expr)]
        result = exprs[0]
        for right in exprs[1:]:
            result = BinOpExpr(op="OR", left=result, right=right)
        return result

    # ─── Level 7: AND ─────────────────────────────────────────────────────────

    def and_chain(self, items) -> Expr:
        exprs = [x for x in items if isinstance(x, Expr)]
        result = exprs[0]
        for right in exprs[1:]:
            result = BinOpExpr(op="AND", left=result, right=right)
        return result

    # ─── Level 6: NOT ─────────────────────────────────────────────────────────

    def bool_not(self, items) -> UnaryExpr:
        inner = next(x for x in items if isinstance(x, Expr))
        return UnaryExpr(op="NOT", inner=inner)

    # ─── Level 5: Comparison ──────────────────────────────────────────────────

    def cmp_binary(self, items) -> BinOpExpr:
        exprs = [x for x in items if isinstance(x, Expr)]
        ops = [x for x in items if isinstance(x, str)]
        return BinOpExpr(op=ops[0], left=exprs[0], right=exprs[1])

    def cmp_condition_code(self, items) -> ConditionCodeExpr:
        op = next(x for x in items if isinstance(x, str))
        return ConditionCodeExpr(op=op)

    def op_lt(self, _) -> str:  return "<"
    def op_gt(self, _) -> str:  return ">"
    def op_eq(self, _) -> str:  return "="
    def op_le(self, _) -> str:  return "<="
    def op_ge(self, _) -> str:  return ">="
    def op_ne(self, _) -> str:  return "<>"
    def op_ult(self, _) -> str: return "'<'"
    def op_ugt(self, _) -> str: return "'>'"
    def op_ueq(self, _) -> str: return "'='"
    def op_ule(self, _) -> str: return "'<='"
    def op_uge(self, _) -> str: return "'>='"
    def op_une(self, _) -> str: return "'<>'"

    # ─── Level 4: Additive + Bitwise ──────────────────────────────────────────

    def add_chain(self, items) -> Expr:
        exprs = [x for x in items if isinstance(x, Expr)]
        ops   = [x for x in items if isinstance(x, str)]
        result = exprs[0]
        for i, right in enumerate(exprs[1:]):
            result = BinOpExpr(op=ops[i], left=result, right=right)
        return result

    def op_plus(self, _) -> str:   return "+"
    def op_minus(self, _) -> str:  return "-"
    def op_uplus(self, _) -> str:  return "'+'"
    def op_uminus(self, _) -> str: return "'-'"
    def op_lor(self, _) -> str:    return "LOR"
    def op_land(self, _) -> str:   return "LAND"
    def op_xor(self, _) -> str:    return "XOR"
    def op_concat(self, _) -> str: return "&"

    # ─── Level 3: Multiplicative ──────────────────────────────────────────────

    def mul_chain(self, items) -> Expr:
        exprs = [x for x in items if isinstance(x, Expr)]
        ops   = [x for x in items if isinstance(x, str)]
        result = exprs[0]
        for i, right in enumerate(exprs[1:]):
            result = BinOpExpr(op=ops[i], left=result, right=right)
        return result

    def op_star(self, _) -> str:   return "*"
    def op_slash(self, _) -> str:  return "/"
    def op_ustar(self, _) -> str:  return "'*'"
    def op_uslash(self, _) -> str: return "'/'"
    def op_umod(self, _) -> str:   return "'\\'"

    # ─── Level 2: Bit shifts ──────────────────────────────────────────────────

    def shift_chain(self, items) -> Expr:
        exprs = [x for x in items if isinstance(x, Expr)]
        ops   = [x for x in items if isinstance(x, str)]
        result = exprs[0]
        for i, right in enumerate(exprs[1:]):
            result = BinOpExpr(op=ops[i], left=result, right=right)
        return result

    def op_shl(self, _) -> str:  return "<<"
    def op_shr(self, _) -> str:  return ">>"
    def op_ushl(self, _) -> str: return "'<<'"
    def op_ushr(self, _) -> str: return "'>>'"

    # ─── Level 0: Unary ───────────────────────────────────────────────────────

    def unary_plus(self, items) -> UnaryExpr:
        inner = next(x for x in items if isinstance(x, Expr))
        return UnaryExpr(op="+", inner=inner)

    def unary_minus(self, items) -> UnaryExpr:
        inner = next(x for x in items if isinstance(x, Expr))
        return UnaryExpr(op="-", inner=inner)

    # ─── Postfix ──────────────────────────────────────────────────────────────

    def postfix_chain(self, items) -> Expr:
        result = items[0]  # primary Expr
        for tail in items[1:]:
            if isinstance(tail, _FieldTail):
                result = FieldExpr(obj=result, field_name=tail.name)
            elif isinstance(tail, _IndexTail):
                if tail.for_count is not None:
                    result = SubstringExpr(base=result, index=tail.index, count=tail.for_count, unit=tail.for_unit)
                else:
                    result = IndexExpr(array=result, index=tail.index)
            elif isinstance(tail, _BitExtractTail):
                result = BitExtractExpr(
                    base=result, left_bit=tail.left_bit, right_bit=tail.right_bit
                )
            elif isinstance(tail, _CallPostfixTail):
                name = result.name if isinstance(result, VarExpr) else str(result)
                result = CallExpr(name=name, args=tail.args)
        return result

    def call_postfix(self, items) -> _CallPostfixTail:
        args = next((x for x in items if isinstance(x, list)), [])
        return _CallPostfixTail(args=args)

    def field_access(self, items) -> _FieldTail:
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        return _FieldTail(str(name_tok))

    def for_slice_(self, items) -> _ForSliceTail:
        count_expr = next(x for x in items if isinstance(x, Expr))
        unit = next((x for x in items if isinstance(x, str) and x in ("BYTES", "WORDS", "ELEMENTS")), "")
        return _ForSliceTail(count=count_expr, unit=unit)

    def index_access(self, items) -> _IndexTail:
        index_expr = next(x for x in items if isinstance(x, Expr))
        slice_tail = next((x for x in items if isinstance(x, _ForSliceTail)), None)
        return _IndexTail(
            index=index_expr,
            for_count=slice_tail.count if slice_tail else None,
            for_unit=slice_tail.unit if slice_tail else "",
        )

    def bit_extract(self, items) -> _BitExtractTail:
        nums = [t for t in items if isinstance(t, Token) and t.type == "NUMBER_INT"]
        left = _parse_int_literal(str(nums[0]))
        right = _parse_int_literal(str(nums[1])) if len(nums) > 1 else left
        return _BitExtractTail(left, right)

    # ─── Primary ──────────────────────────────────────────────────────────────

    def lit_int(self, items) -> LiteralExpr:
        return LiteralExpr(value=_parse_int_literal(str(items[0])))

    def lit_int32(self, items) -> LiteralExpr:
        s = str(items[0]).upper()
        s = s[:-2] if s.endswith("%D") else s.rstrip("D")
        return LiteralExpr(value=_parse_int_literal(s))

    def lit_fixed(self, items) -> LiteralExpr:
        s = str(items[0]).upper()
        s = s[:-2] if s.endswith("%F") else s.rstrip("F")
        if "." in s:
            s = s.split(".")[0]
        try:
            return LiteralExpr(value=_parse_int_literal(s))
        except ValueError:
            return LiteralExpr(value=0)

    def lit_real(self, items) -> LiteralExpr:
        return LiteralExpr(value=str(items[0]))

    def lit_real64(self, items) -> LiteralExpr:
        return LiteralExpr(value=str(items[0]))

    def lit_string(self, items) -> LiteralExpr:
        return LiteralExpr(value=str(items[0]).strip('"'))

    def lit_char(self, items) -> LiteralExpr:
        inner = str(items[0]).strip('"').strip("'")
        return LiteralExpr(value=ord(inner[0]) if inner else 0)

    def var_ref(self, items) -> VarExpr:
        return VarExpr(name=str(items[0]))

    def address_of(self, items) -> AddressOfExpr:
        inner = next(x for x in items if isinstance(x, Expr))
        return AddressOfExpr(inner=inner)

    def deref_expr(self, items) -> DerefExpr:
        inner = next(x for x in items if isinstance(x, Expr))
        return DerefExpr(inner=inner)

    def dollar_func(self, items) -> DollarFuncExpr:
        func_tok = next(t for t in items if isinstance(t, Token) and t.type == "DOLLAR_FUNC")
        args = next((x for x in items if isinstance(x, list)), [])
        name = str(func_tok).lstrip("$").upper()
        return DollarFuncExpr(name=name, args=args)

    def dollar_func_bare(self, items) -> DollarFuncExpr:
        name = str(items[0]).lstrip("$").upper()
        return DollarFuncExpr(name=name, args=[])

    def paren_expr(self, items) -> Expr:
        return next(x for x in items if isinstance(x, Expr))

    def base_addr(self, items) -> VarExpr:
        name_tok = next(t for t in items if isinstance(t, Token) and t.type == "NAME")
        return VarExpr(name=f"'{str(name_tok)}'")

    # ─── Special expressions ──────────────────────────────────────────────────

    def if_expression(self, items) -> IfExpr:
        exprs = [x for x in items if isinstance(x, Expr)]
        return IfExpr(condition=exprs[0], then_expr=exprs[1], else_expr=exprs[2])

    def case_expression(self, items) -> CaseExpr:
        mixed = [x for x in items if isinstance(x, (Expr, _CaseBranch, _OtherwiseBranch))]
        selector = mixed[0]  # first Expr
        branches = mixed[1:]
        alternatives = [b.expr for b in branches if isinstance(b, _CaseBranch)]
        otherwise = next((b.expr for b in branches if isinstance(b, _OtherwiseBranch)), None)
        return CaseExpr(selector=selector, alternatives=alternatives, otherwise=otherwise)

    def case_branch(self, items) -> _CaseBranch:
        return _CaseBranch(next(x for x in items if isinstance(x, Expr)))

    def case_otherwise(self, items) -> _OtherwiseBranch:
        return _OtherwiseBranch(next(x for x in items if isinstance(x, Expr)))

    # ─── call_args ────────────────────────────────────────────────────────────

    def call_substring(self, items) -> Expr:
        exprs = [x for x in items if isinstance(x, Expr)]
        return BinOpExpr(op=":", left=exprs[0], right=exprs[1])

    def call_plain_arg(self, items) -> Expr:
        return next(x for x in items if isinstance(x, Expr))

    def call_empty_arg(self, items) -> Expr:
        return LiteralExpr(value=0)

    def func_args(self, items) -> list:
        return [x for x in items if isinstance(x, Expr)]

    def func_no_args(self, items) -> list:
        return []


# ─── Constant evaluator ───────────────────────────────────────────────────────

def eval_const_expr(expr: Expr, literals: dict[str, int]) -> int | None:
    """Evaluate a constant expression. Returns None if not statically evaluable.

    Used for bound_expr resolution and LITERAL arithmetic.
    """
    if isinstance(expr, LiteralExpr) and isinstance(expr.value, int):
        return expr.value
    if isinstance(expr, VarExpr):
        return literals.get(expr.name.upper())
    if isinstance(expr, UnaryExpr):
        inner = eval_const_expr(expr.inner, literals)
        if inner is None:
            return None
        if expr.op == "-":
            return -inner
        return inner  # unary "+"
    if isinstance(expr, BinOpExpr):
        left = eval_const_expr(expr.left, literals)
        right = eval_const_expr(expr.right, literals)
        if left is None or right is None:
            return None
        return _eval_binop(expr.op, left, right)
    return None


def _eval_binop(op: str, left: int, right: int) -> int | None:
    match op:
        case "+":    return left + right
        case "-":    return left - right
        case "*":    return left * right
        case "/":    return left // right if right != 0 else 0
        case "'+'":  return (left + right) & 0xFFFF
        case "'-'":  return (left - right) & 0xFFFF
        case "'*'":  return (left * right) & 0xFFFF
        case "'/'":  return (left // right) & 0xFFFF if right != 0 else 0
        case "LOR":  return left | right
        case "LAND": return left & right
        case "XOR":  return left ^ right
        case "<<":   return (left << right) & 0xFFFFFFFF
        case ">>":   return left >> right
        case _:      return None
