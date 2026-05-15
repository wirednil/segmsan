"""Scope tracking for TAL static memory analysis."""

from __future__ import annotations
from dataclasses import dataclass, field
from .ast_nodes import (
    VarDecl, ParamDecl, ScopeKind, TalType,
)


@dataclass
class VarInfo:
    decl: VarDecl | ParamDecl
    scope_kind: ScopeKind
    scope_depth: int
    is_assigned: bool = False
    address_taken: bool = False
    stored_in_higher_scope: bool = False

    @property
    def name(self) -> str:
        return self.decl.name

    @property
    def is_pointer(self) -> bool:
        if isinstance(self.decl, VarDecl):
            return self.decl.is_indirect
        return self.decl.is_reference

    @property
    def is_local(self) -> bool:
        return self.scope_kind in (ScopeKind.LOCAL, ScopeKind.SUBLOCAL)


SCOPE_LIMITS = {
    ScopeKind.GLOBAL: 256,
    ScopeKind.LOCAL: 127,
    ScopeKind.SUBLOCAL: 32,
}


@dataclass
class ScopeLevel:
    kind: ScopeKind
    variables: dict[str, VarInfo] = field(default_factory=dict)
    primary_words: int = 0
    secondary_words: int = 0
    extended_words: int = 0

    @property
    def allocated_words(self) -> int:
        return self.primary_words

    @property
    def max_words(self) -> int:
        return SCOPE_LIMITS[self.kind]

    @property
    def combined_words(self) -> int:
        return self.primary_words + self.secondary_words


class ScopeStack:
    def __init__(self):
        self.levels: list[ScopeLevel] = []

    def push(self, kind: ScopeKind):
        self.levels.append(ScopeLevel(kind=kind))

    def pop(self):
        if self.levels:
            self.levels.pop()

    @property
    def current(self) -> ScopeLevel | None:
        return self.levels[-1] if self.levels else None

    @property
    def depth(self) -> int:
        return len(self.levels)

    def declare(self, decl: VarDecl, scope_kind: ScopeKind) -> VarInfo:
        info = VarInfo(
            decl=decl,
            scope_kind=scope_kind,
            scope_depth=self.depth,
        )
        if self.current:
            self.current.variables[decl.name.upper()] = info
            if not decl.is_equivalence:
                if decl.is_indirect:
                    self.current.primary_words += decl.pointer_word_size()
                    if decl.is_extended:
                        self.current.extended_words += decl.data_word_size()
                    else:
                        self.current.secondary_words += decl.data_word_size()
                else:
                    self.current.primary_words += decl.word_size()
        return info

    def declare_param(self, param: ParamDecl, scope_kind: ScopeKind):
        info = VarInfo(
            decl=param,
            scope_kind=scope_kind,
            scope_depth=self.depth,
        )
        if self.current:
            self.current.variables[param.name.upper()] = info

    def lookup(self, name: str) -> VarInfo | None:
        upper = name.upper()
        for level in reversed(self.levels):
            if upper in level.variables:
                return level.variables[upper]
        return None

    def scope_of(self, name: str) -> ScopeKind | None:
        info = self.lookup(name)
        if info:
            return info.scope_kind
        return None

    def is_local(self, name: str) -> bool:
        info = self.lookup(name)
        if info:
            return info.scope_kind in (ScopeKind.LOCAL, ScopeKind.SUBLOCAL)
        return False

    def is_global(self, name: str) -> bool:
        info = self.lookup(name)
        if info:
            return info.scope_kind == ScopeKind.GLOBAL
        return False

    def is_pointer(self, name: str) -> bool:
        info = self.lookup(name)
        if info:
            return info.is_pointer
        return False

    def mark_assigned(self, name: str):
        info = self.lookup(name)
        if info:
            info.is_assigned = True

    def mark_address_taken(self, name: str):
        info = self.lookup(name)
        if info:
            info.address_taken = True

    def mark_stored_in_higher_scope(self, name: str):
        info = self.lookup(name)
        if info:
            info.stored_in_higher_scope = True

    def global_allocated(self) -> int:
        for level in self.levels:
            if level.kind == ScopeKind.GLOBAL:
                return level.primary_words
        return 0

    def global_secondary(self) -> int:
        for level in self.levels:
            if level.kind == ScopeKind.GLOBAL:
                return level.secondary_words
        return 0

    def global_extended(self) -> int:
        for level in self.levels:
            if level.kind == ScopeKind.GLOBAL:
                return level.extended_words
        return 0

    def local_allocated(self) -> int:
        if self.current and self.current.kind in (ScopeKind.LOCAL, ScopeKind.SUBLOCAL):
            return self.current.primary_words
        return 0

    def local_secondary(self) -> int:
        if self.current and self.current.kind in (ScopeKind.LOCAL, ScopeKind.SUBLOCAL):
            return self.current.secondary_words
        return 0

    def local_extended(self) -> int:
        if self.current and self.current.kind in (ScopeKind.LOCAL, ScopeKind.SUBLOCAL):
            return self.current.extended_words
        return 0
