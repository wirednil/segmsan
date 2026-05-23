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
    public_name: str = ""
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
class SubstringExpr(Expr):
    """name[offset] FOR count [unit] — substring/move source."""
    base: Expr
    index: Expr
    count: Expr
    unit: str = ""  # "BYTES", "WORDS", "ELEMENTS", or ""
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
class UnaryExpr(Expr):
    op: str          # "+", "-", "NOT"
    inner: Expr
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class BitExtractExpr(Expr):
    base: Expr
    left_bit: int
    right_bit: int   # equals left_bit when single-bit form .<n>
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class AssignExpr(Expr):
    targets: list    # list[Expr] — single target; multi-target handled by Phase 6 stmt parser
    value: Expr
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class IfExpr(Expr):
    condition: Expr
    then_expr: Expr
    else_expr: Expr
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class CaseExpr(Expr):
    selector: Expr
    alternatives: list   # list[Expr]
    otherwise: Optional[Expr]
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class GroupCmpExpr(Expr):
    left: Expr
    op: str
    right: Expr
    count: Optional[Expr]       # None when bracketed-constant form
    unit: str                   # "" | "BYTES" | "WORDS" | "ELEMENTS"
    next_addr: Optional[Expr]
    is_bracketed_const: bool
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class ConditionCodeExpr(Expr):
    op: str          # "<", ">", "=", "<=", ">=", "<>", "'<'", etc.
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class Statement:
    pass


@dataclass
class AssignStmt(Statement):
    targets: list      # list[Expr] — multi-target assign; single-target is targets=[expr]
    source: Expr
    is_bit_deposit: bool = False
    bit_left: int = 0
    bit_right: int = 0
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class CallStmt(Statement):
    name: str
    args: list = field(default_factory=list)        # list[Expr]
    param_pairs: list = field(default_factory=list) # list[tuple[Expr, Expr]]
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class CompoundStmt(Statement):
    body: list = field(default_factory=list)  # list[Statement]
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class AssignCondExpr(Expr):
    """var := expr used as an IF condition — assigns and evaluates condition code."""
    target: Expr
    value: Expr
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
    direction: str = "TO"
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class ScanStmt(Statement):
    direction: str    # "SCAN" or "RSCAN"
    variable: Expr
    mode: str         # "WHILE" or "UNTIL"
    test_char: Expr
    next_addr: Optional[Expr] = None
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class ReturnStmt(Statement):
    value: Optional[Expr] = None
    cc_expression: Optional[Expr] = None
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
class DoStmt(Statement):
    body: list = field(default_factory=list)    # list[Statement]
    condition: object = None                     # Expr
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class CaseLabel:
    value: object                               # int | str
    is_range: bool = False
    range_high: object = ""                     # int | str — only when is_range


@dataclass
class CaseAlternative:
    labels: list = field(default_factory=list)  # list[CaseLabel]
    body: list = field(default_factory=list)    # list[Statement]


@dataclass
class CaseStmt(Statement):
    selector: object = None
    body: list = field(default_factory=list)          # legacy unlabeled form
    alternatives: list = field(default_factory=list)  # list[CaseAlternative]
    otherwise_body: list = field(default_factory=list) # list[Statement]
    is_labeled: bool = True
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class StackStmt(Statement):
    values: list = field(default_factory=list)  # list[Expr]
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class StoreStmt(Statement):
    variables: list = field(default_factory=list)  # list[Expr]
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class UseStmt(Statement):
    identifiers: list = field(default_factory=list)  # list[str]
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class DropStmt(Statement):
    identifiers: list = field(default_factory=list)  # list[str]
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class CodeStmt(Statement):
    instructions: list = field(default_factory=list)  # list[str]
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class AssertStmt(Statement):
    level: object = None   # Expr
    condition: object = None  # Expr
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class MoveStmt(Statement):
    direction: str = ""   # "LR" or "RL"
    source: object = None  # Expr
    dest: object = None    # Expr
    count: object = None   # Expr or None
    unit: str = ""         # "" | "BYTES" | "WORDS" | "ELEMENTS"
    next_addr: object = None  # Expr or None
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
class ParamSpec:
    """Typed parameter declaration appearing after the proc header SEMI and before BEGIN."""
    name: str
    param_type: str         # "INT" "INT32" "REAL" "REAL64" "STRING" "FIXED" "UNSIGNED" "STRUCT" "PROC"
    is_reference: bool = False
    is_extended: bool = False
    referral: str = ""      # struct template name for struct params
    return_type: Optional[str] = None   # for typed PROC params (e.g. INT PROC)
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0))


@dataclass
class Procedure:
    name: str
    loc: SourceLocation
    # Header fields (populated by Phase 8 transformer)
    return_type: Optional[TalType] = None
    public_name: str = ""
    param_specs: list = field(default_factory=list)    # list[ParamSpec]
    param_pairs: list = field(default_factory=list)    # list[tuple[str,str]]
    is_subproc: bool = False
    is_callable: bool = False
    is_extensible: bool = False
    extensible_count: Optional[int] = None
    is_interrupt: bool = False
    is_priv: bool = False
    is_resident: bool = False
    language: str = ""
    entry_points: list = field(default_factory=list)   # list[str]
    label_decls: list = field(default_factory=list)    # list[str]
    # Core fields
    params: list = field(default_factory=list)         # list[ParamDecl]
    locals_: list = field(default_factory=list)        # list[VarDecl]
    body: list = field(default_factory=list)           # list[Statement]
    subprocs: list = field(default_factory=list)       # list[Procedure]
    is_main: bool = False
    is_variable: bool = False
    has_largestack: bool = False
    calls_self: bool = False
    is_external: bool = False
    is_forward: bool = False


@dataclass
class ProcHeader:
    name: str
    loc: SourceLocation
    return_type: Optional[TalType] = None
    public_name: str = ""
    params: list[ParamDecl] = field(default_factory=list)
    param_pairs: list[tuple] = field(default_factory=list)
    is_subproc: bool = False
    is_main: bool = False
    is_variable: bool = False
    is_callable: bool = False
    is_extensible: bool = False
    extensible_count: Optional[int] = None
    is_interrupt: bool = False
    is_priv: bool = False
    is_resident: bool = False
    language: str = ""
    is_external: bool = False
    is_forward: bool = False


@dataclass
class Program:
    globals_: list[VarDecl] = field(default_factory=list)
    directives: list[str] = field(default_factory=list)
    procedures: list[Procedure] = field(default_factory=list)
    source_file: str = ""
    literals: dict[str, int] = field(default_factory=dict)
    source_imports: list[SourceImport] = field(default_factory=list)
    name: str = ""
    blocks: list[BlockDecl] = field(default_factory=list)


@dataclass
class BlockDecl:
    name: str
    is_private: bool = False
    at_zero: bool = False
    below: int = 0
    globals_: list[VarDecl] = field(default_factory=list)
    directives: list[str] = field(default_factory=list)
