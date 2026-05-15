"""AST node types for TAL static memory analyzer."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class TalType(Enum):
    INT = "INT"
    INT32 = "INT(32)"
    STRING = "STRING"
    REAL = "REAL"
    REAL64 = "REAL(64)"
    FIXED = "FIXED"
    UNSIGNED = "UNSIGNED"
    PROC = "PROC"
    STRUCT = "STRUCT"


class ScopeKind(Enum):
    GLOBAL = "global"
    LOCAL = "local"
    SUBLOCAL = "sublocal"


@dataclass
class SourceLocation:
    line: int
    col: int = 0

    def __str__(self) -> str:
        if self.col:
            return f":{self.line}:{self.col}"
        return f":{self.line}"


@dataclass
class ArrayBounds:
    lo: int
    hi: int

    @property
    def size(self) -> int:
        return self.hi - self.lo + 1


@dataclass
class VarDecl:
    name: str
    tal_type: TalType
    loc: SourceLocation
    is_indirect: bool = False
    is_extended: bool = False
    array_bounds: Optional[ArrayBounds] = None
    is_readonly: bool = False
    is_equivalence: bool = False
    equivalence_target: Optional[str] = None
    fpoint: int = 0
    width: int = 0
    struct_fields: Optional[list[VarDecl]] = None
    has_initializer: bool = False
    is_template: bool = False
    template_name: str = ""

    def word_size(self) -> int:
        if self.is_template:
            return 0
        if self.is_indirect:
            return 2 if self.is_extended else 1
        base = self._base_word_size()
        if self.array_bounds:
            return base * self.array_bounds.size
        return base

    def pointer_word_size(self) -> int:
        if self.is_template or not self.is_indirect:
            return 0
        return 2 if self.is_extended else 1

    def data_word_size(self) -> int:
        if self.is_template:
            return 0
        if self.is_indirect:
            base = self._base_data_word_size()
            if self.array_bounds:
                return base * self.array_bounds.size
            return base
        return self.word_size()

    def _base_data_word_size(self) -> int:
        if self.tal_type == TalType.STRUCT:
            if self.struct_fields is not None:
                return sum(f.word_size() for f in self.struct_fields if not f.is_indirect)
            return 0
        return self._base_word_size()

    def _base_word_size(self) -> int:
        match self.tal_type:
            case TalType.INT | TalType.STRING | TalType.PROC:
                return 1
            case TalType.INT32 | TalType.REAL:
                return 2
            case TalType.REAL64 | TalType.FIXED:
                return 4
            case TalType.UNSIGNED:
                if self.width > 0:
                    return (self.width + 15) // 16
                return 1
            case TalType.STRUCT:
                if self.is_indirect:
                    return 2 if self.is_extended else 1
                if self.struct_fields is not None:
                    return sum(f.word_size() for f in self.struct_fields if not f.is_indirect)
                return 0

    def byte_size(self) -> int:
        if self.is_indirect:
            return 4 if self.is_extended else 2
        base = self._base_byte_size()
        if self.array_bounds:
            return base * self.array_bounds.size
        return base

    def _base_byte_size(self) -> int:
        match self.tal_type:
            case TalType.INT | TalType.PROC:
                return 2
            case TalType.STRING:
                return 1
            case TalType.INT32 | TalType.REAL:
                return 4
            case TalType.REAL64 | TalType.FIXED:
                return 8
            case TalType.UNSIGNED:
                if self.width > 0:
                    return (self.width + 7) // 8
                return 2
            case TalType.STRUCT:
                if self.is_indirect:
                    return 4 if self.is_extended else 2
                if self.struct_fields is not None:
                    total = 0
                    for f in self.struct_fields:
                        if not f.is_indirect:
                            total = _align_offset(total, f.alignment()) + f.byte_size()
                    return total
                return 0

    def alignment(self) -> int:
        if self.is_indirect:
            return 2
        match self.tal_type:
            case TalType.STRING:
                return 1
            case TalType.INT | TalType.PROC | TalType.UNSIGNED:
                return 2
            case TalType.INT32 | TalType.REAL:
                return 2
            case TalType.REAL64 | TalType.FIXED:
                return 2
            case TalType.STRUCT:
                return 2


def _align_offset(offset: int, alignment: int) -> int:
    if alignment <= 1:
        return offset
    remainder = offset % alignment
    if remainder:
        return offset + (alignment - remainder)
    return offset


@dataclass
class ParamDecl:
    name: str
    tal_type: TalType
    is_reference: bool = False
    is_extended: bool = False
    fpoint: int = 0
    width: int = 0
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class Expr:
    pass


@dataclass
class VarExpr(Expr):
    name: str
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class DerefExpr(Expr):
    inner: Expr
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class IndexExpr(Expr):
    array: Expr
    index: Expr
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class AddressOfExpr(Expr):
    inner: Expr
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class LiteralExpr(Expr):
    value: int | str
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class BinOpExpr(Expr):
    op: str
    left: Expr
    right: Expr
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class DollarFuncExpr(Expr):
    name: str
    args: list[Expr]
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class CallExpr(Expr):
    name: str
    args: list[Expr]
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class FieldExpr(Expr):
    obj: Expr
    field_name: str
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class Statement:
    pass


@dataclass
class AssignStmt(Statement):
    target: Expr
    source: Expr
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class CallStmt(Statement):
    expr: CallExpr
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class IfStmt(Statement):
    condition: Expr
    then_body: list[Statement]
    else_body: list[Statement]
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class WhileStmt(Statement):
    condition: Expr
    body: list[Statement]
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class ForStmt(Statement):
    var: str
    from_expr: Expr
    to_expr: Expr
    step: Optional[Expr]
    body: list[Statement]
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class ScanStmt(Statement):
    direction: str
    array: Expr
    while_expr: Expr
    next_addr: Optional[Expr]
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class ReturnStmt(Statement):
    value: Optional[Expr]
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class GotoStmt(Statement):
    label: str
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class LabelStmt(Statement):
    name: str
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class OtherStmt(Statement):
    raw: str = ""
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class SourceImport:
    path: str
    names: list[str] = field(default_factory=list)
    is_system: bool = False
    resolved: bool = False


@dataclass
class ImportNode:
    source_path: str
    resolved_path: str | None = None
    names: list[str] = field(default_factory=list)
    is_system: bool = False
    n_procs: int = 0
    n_globals: int = 0
    n_literals: int = 0
    n_defines: int = 0
    children: list[ImportNode] = field(default_factory=list)


@dataclass
class Procedure:
    name: str
    loc: SourceLocation
    params: list[ParamDecl] = field(default_factory=list)
    locals_: list[VarDecl] = field(default_factory=list)
    body: list[Statement] = field(default_factory=list)
    subprocs: list[Procedure] = field(default_factory=list)
    is_main: bool = False
    is_variable: bool = False
    has_largestack: bool = False
    calls_self: bool = False
    is_extern: bool = False
    is_forward: bool = False


@dataclass
class Program:
    globals_: list[VarDecl] = field(default_factory=list)
    directives: list[str] = field(default_factory=list)
    procedures: list[Procedure] = field(default_factory=list)
    source_file: str = ""
    literals: dict[str, int] = field(default_factory=dict)
    source_imports: list[SourceImport] = field(default_factory=list)
