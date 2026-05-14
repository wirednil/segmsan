"""Padding analysis — Rules 21-24.

Simulates TAL compiler memory layout to detect wasted bytes from alignment
padding at global, local, sublocal, and struct-field levels.

TAL layout rules (from TALProgramming.txt):
  - STRING: byte-aligned, 1 byte per element, array starts on word boundary
  - INT/PROC: word-aligned, 1 word (2 bytes)
  - INT(32)/REAL: word-aligned, 2 words (4 bytes, doubleword)
  - REAL(64)/FIXED: word-aligned, 4 words (8 bytes, quadrupleword)
  - UNSIGNED: bit-packed, consecutive vars share words
  - Within structs: STRING byte-aligned, others word-aligned
  - Pad byte after STRING ending on odd byte before word-aligned item
  - Top-level: each variable starts on word boundary
"""

from __future__ import annotations
from dataclasses import dataclass
from ..ast_nodes import (
    Program, Procedure, VarDecl, TalType,
    _align_offset,
)
from ..report import Warning, WarningKind


def check_padding(program: Program) -> list[Warning]:
    warnings: list[Warning] = []
    _check_scope_padding(
        program.globals_, "global", program.source_file,
        WarningKind.PADDING_WASTE_GLOBAL, 256, warnings,
    )
    for proc in program.procedures:
        _check_proc_padding(proc, program.source_file, warnings)
    return warnings


def _check_proc_padding(
    proc: Procedure, source_file: str, warnings: list[Warning],
):
    _check_scope_padding(
        proc.locals_, f"local({proc.name})", source_file,
        WarningKind.PADDING_WASTE_LOCAL, 127, warnings,
    )
    for sp in proc.subprocs:
        _check_scope_padding(
            sp.locals_, f"sublocal({sp.name})", source_file,
            WarningKind.PADDING_WASTE_SUBLOCAL, 32, warnings,
        )
        for nested in sp.subprocs:
            _check_proc_padding(nested, source_file, warnings)


@dataclass
class _LayoutEntry:
    name: str
    type_str: str
    offset_bytes: int
    size_bytes: int
    pad_before: int


def _simulate_scope_layout(decls: list[VarDecl]) -> tuple[list[_LayoutEntry], int]:
    entries: list[_LayoutEntry] = []
    byte_offset = 0

    for d in decls:
        if d.is_indirect:
            entries.append(_LayoutEntry(
                name=d.name,
                type_str=f"{d.tal_type.value} (indirect)",
                offset_bytes=byte_offset,
                size_bytes=d.byte_size(),
                pad_before=0,
            ))
            byte_offset += d.byte_size()
            continue

        align = d.alignment()
        aligned = _align_offset(byte_offset, align)
        pad = aligned - byte_offset
        sz = d.byte_size()

        entries.append(_LayoutEntry(
            name=d.name,
            type_str=d.tal_type.value,
            offset_bytes=aligned,
            size_bytes=sz,
            pad_before=pad,
        ))
        byte_offset = aligned + sz

    return entries, byte_offset


def _check_scope_padding(
    decls: list[VarDecl],
    scope_label: str,
    source_file: str,
    kind: WarningKind,
    word_limit: int,
    warnings: list[Warning],
):
    primary = [d for d in decls if not d.is_indirect]
    if not primary:
        return

    entries, total_bytes = _simulate_scope_layout(primary)
    total_words = (total_bytes + 1) // 2
    total_pad = sum(e.pad_before for e in entries)

    struct_entries: dict[str, list[_LayoutEntry]] = {}
    for d in primary:
        if d.tal_type == TalType.STRUCT and d.struct_fields:
            sentries, _ = _simulate_scope_layout(d.struct_fields)
            struct_entries[d.name] = sentries

    if total_pad == 0 and not struct_entries:
        return

    useful = total_bytes - total_pad
    pct = (total_pad / total_bytes * 100) if total_bytes else 0

    parts: list[str] = []
    parts.append(f"Padding analysis for {scope_label}:")
    parts.append(f"  Total: {total_bytes} bytes ({total_words} words, limit {word_limit}w)")
    parts.append(f"  Useful: {useful} bytes, Padding: {total_pad} bytes ({pct:.1f}%)")

    if total_pad > 0:
        parts.append("  Layout:")
        for e in entries:
            if e.pad_before > 0:
                parts.append(
                    f"    [+{e.pad_before}B pad] {e.name}: {e.type_str} "
                    f"@{e.offset_bytes}B ({e.size_bytes}B)"
                )

    for sname, sentries in struct_entries.items():
        struct_pad = sum(e.pad_before for e in sentries)
        if struct_pad > 0:
            struct_total = sum(e.size_bytes + e.pad_before for e in sentries)
            struct_useful = struct_total - struct_pad
            spct = (struct_pad / struct_total * 100) if struct_total else 0
            parts.append(f"  Struct '{sname}': {struct_pad}B padding / {struct_total}B ({spct:.1f}%)")
            for e in sentries:
                if e.pad_before > 0:
                    parts.append(
                        f"    [+{e.pad_before}B pad] {e.name}: {e.type_str} "
                        f"@{e.offset_bytes}B ({e.size_bytes}B)"
                    )
            _suggest_reorder(sname, sentries, source_file, warnings)

    suggestion = ""
    if total_pad > 0 and pct > 15:
        suggestion = (
            "Reorder declarations to minimize padding: "
            "group STRING (byte-aligned) together, then INT/word-aligned. "
            "Place larger-aligned types (INT(32), REAL, FIXED) first."
        )

    first_loc = next(
        (f"{source_file}{d.loc}" for d in primary),
        source_file,
    )
    warnings.append(Warning(
        kind=kind,
        message="\n".join(parts),
        loc=first_loc,
        suggestion=suggestion,
    ))


def _suggest_reorder(
    struct_name: str,
    entries: list[_LayoutEntry],
    source_file: str,
    warnings: list[Warning],
):
    sorted_entries = sorted(entries, key=lambda e: (-e.size_bytes, e.name))
    reordered_pad = 0
    off = 0
    for e in sorted_entries:
        align = 2 if e.size_bytes > 1 else 1
        aligned = _align_offset(off, align)
        reordered_pad += aligned - off
        off = aligned + e.size_bytes
    original_pad = sum(e.pad_before for e in entries)
    if reordered_pad < original_pad:
        order = ", ".join(e.name for e in sorted_entries)
        warnings.append(Warning(
            kind=WarningKind.PADDING_WASTE_STRUCT,
            message=(
                f"Struct '{struct_name}': reordering fields can reduce padding "
                f"from {original_pad}B to {reordered_pad}B (save {original_pad - reordered_pad}B). "
                f"Suggested order: {order}"
            ),
            loc=source_file,
            suggestion="Sort fields by descending size to minimize alignment gaps",
        ))
