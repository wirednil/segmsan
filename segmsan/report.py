"""Warning types and diagnostic report formatting for TAL memory analyzer."""

from __future__ import annotations
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class Severity(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    @property
    def rank(self) -> int:
        match self:
            case Severity.CRITICAL: return 0
            case Severity.HIGH: return 1
            case Severity.MEDIUM: return 2
            case Severity.LOW: return 3

    def __lt__(self, other):
        return self.rank < other.rank

    def __str__(self) -> str:
        return self.value


class WarningKind(Enum):
    DANGLING_POINTER_STORE = auto()
    GLOBAL_OVERFLOW = auto()
    LOCAL_OVERFLOW = auto()
    SUBLOCAL_OVERFLOW = auto()
    EQUIVALENCE_TO_IMPLICIT_PTR = auto()
    STRING_VALUE_PARAM_MISMATCH = auto()
    UNINIT_POINTER_DEREF = auto()
    EXTENDED_POINTER_NEEDED = auto()
    FIXED_DIV_PRECISION_LOSS = auto()
    RECURSION_WITHOUT_LARGESTACK = auto()
    SCAN_WITHOUT_CARRY_CHECK = auto()
    READONLY_ARRAY_MODIFICATION = auto()
    UPPER_32K_WITHOUT_PTR = auto()
    COMP_USED_AS_COMPARISON = auto()
    EQUIVALENCE_CROSS_ADDRESSING = auto()
    INDEX_WITHOUT_BOUNDS_CHECK = auto()
    CONDITION_CODE_CLOBBER = auto()
    LITERAL_COULD_BE_USED = auto()
    MISSING_DEBUG_DIRECTIVE = auto()
    PADDING_WASTE_GLOBAL = auto()
    PADDING_WASTE_LOCAL = auto()
    PADDING_WASTE_SUBLOCAL = auto()
    PADDING_WASTE_STRUCT = auto()
    SECONDARY_OVERFLOW = auto()
    SUBLOCAL_INDIRECT = auto()
    UNRESOLVED_TEMPLATE = auto()


SEVERITY_MAP = {
    WarningKind.DANGLING_POINTER_STORE: Severity.CRITICAL,
    WarningKind.GLOBAL_OVERFLOW: Severity.CRITICAL,
    WarningKind.LOCAL_OVERFLOW: Severity.CRITICAL,
    WarningKind.SUBLOCAL_OVERFLOW: Severity.CRITICAL,
    WarningKind.EQUIVALENCE_TO_IMPLICIT_PTR: Severity.CRITICAL,
    WarningKind.STRING_VALUE_PARAM_MISMATCH: Severity.CRITICAL,
    WarningKind.UNINIT_POINTER_DEREF: Severity.HIGH,
    WarningKind.EXTENDED_POINTER_NEEDED: Severity.HIGH,
    WarningKind.FIXED_DIV_PRECISION_LOSS: Severity.HIGH,
    WarningKind.RECURSION_WITHOUT_LARGESTACK: Severity.HIGH,
    WarningKind.SCAN_WITHOUT_CARRY_CHECK: Severity.HIGH,
    WarningKind.READONLY_ARRAY_MODIFICATION: Severity.HIGH,
    WarningKind.UPPER_32K_WITHOUT_PTR: Severity.HIGH,
    WarningKind.COMP_USED_AS_COMPARISON: Severity.MEDIUM,
    WarningKind.EQUIVALENCE_CROSS_ADDRESSING: Severity.MEDIUM,
    WarningKind.INDEX_WITHOUT_BOUNDS_CHECK: Severity.MEDIUM,
    WarningKind.CONDITION_CODE_CLOBBER: Severity.MEDIUM,
    WarningKind.LITERAL_COULD_BE_USED: Severity.LOW,
    WarningKind.MISSING_DEBUG_DIRECTIVE: Severity.LOW,
    WarningKind.PADDING_WASTE_GLOBAL: Severity.LOW,
    WarningKind.PADDING_WASTE_LOCAL: Severity.LOW,
    WarningKind.PADDING_WASTE_SUBLOCAL: Severity.LOW,
    WarningKind.PADDING_WASTE_STRUCT: Severity.MEDIUM,
    WarningKind.SECONDARY_OVERFLOW: Severity.HIGH,
    WarningKind.SUBLOCAL_INDIRECT: Severity.MEDIUM,
    WarningKind.UNRESOLVED_TEMPLATE: Severity.MEDIUM,
}

RULE_NUMBERS = {
    WarningKind.DANGLING_POINTER_STORE: 1,
    WarningKind.GLOBAL_OVERFLOW: 2,
    WarningKind.LOCAL_OVERFLOW: 3,
    WarningKind.SUBLOCAL_OVERFLOW: 4,
    WarningKind.EQUIVALENCE_TO_IMPLICIT_PTR: 5,
    WarningKind.STRING_VALUE_PARAM_MISMATCH: 6,
    WarningKind.UNINIT_POINTER_DEREF: 7,
    WarningKind.EXTENDED_POINTER_NEEDED: 8,
    WarningKind.FIXED_DIV_PRECISION_LOSS: 9,
    WarningKind.RECURSION_WITHOUT_LARGESTACK: 10,
    WarningKind.SCAN_WITHOUT_CARRY_CHECK: 11,
    WarningKind.READONLY_ARRAY_MODIFICATION: 12,
    WarningKind.UPPER_32K_WITHOUT_PTR: 13,
    WarningKind.COMP_USED_AS_COMPARISON: 15,
    WarningKind.EQUIVALENCE_CROSS_ADDRESSING: 16,
    WarningKind.INDEX_WITHOUT_BOUNDS_CHECK: 17,
    WarningKind.CONDITION_CODE_CLOBBER: 18,
    WarningKind.LITERAL_COULD_BE_USED: 19,
    WarningKind.MISSING_DEBUG_DIRECTIVE: 20,
    WarningKind.PADDING_WASTE_GLOBAL: 21,
    WarningKind.PADDING_WASTE_LOCAL: 22,
    WarningKind.PADDING_WASTE_SUBLOCAL: 23,
    WarningKind.PADDING_WASTE_STRUCT: 24,
    WarningKind.SECONDARY_OVERFLOW: 25,
    WarningKind.SUBLOCAL_INDIRECT: 26,
    WarningKind.UNRESOLVED_TEMPLATE: 27,
}

RULE_DESCRIPTIONS = {
    WarningKind.DANGLING_POINTER_STORE: "Address of local variable stored in global pointer",
    WarningKind.GLOBAL_OVERFLOW: "Global primary storage exceeds 256 words",
    WarningKind.LOCAL_OVERFLOW: "Local primary storage exceeds 127 words",
    WarningKind.SUBLOCAL_OVERFLOW: "Sublocal storage exceeds 32 words",
    WarningKind.EQUIVALENCE_TO_IMPLICIT_PTR: "EQUIVALENCE to implicit pointer overlays the pointer itself",
    WarningKind.STRING_VALUE_PARAM_MISMATCH: "STRING passed by value — byte goes to wrong side",
    WarningKind.UNINIT_POINTER_DEREF: "Pointer dereferenced without prior assignment",
    WarningKind.EXTENDED_POINTER_NEEDED: "Address of >32K array stored in non-.EXT pointer (assignment-time)",
    WarningKind.FIXED_DIV_PRECISION_LOSS: "FIXED division loses all decimals — use $SCALE",
    WarningKind.RECURSION_WITHOUT_LARGESTACK: "Recursive procedure without ?LARGESTACK",
    WarningKind.SCAN_WITHOUT_CARRY_CHECK: "SCAN/RSCAN without subsequent $CARRY test",
    WarningKind.READONLY_ARRAY_MODIFICATION: "Attempt to modify read-only (= 'P') array",
    WarningKind.UPPER_32K_WITHOUT_PTR: "Direct array exceeds 32K words — needs indirect allocation (declaration-time)",
    WarningKind.COMP_USED_AS_COMPARISON: "$COMP used in IF — it inverts bits, does not compare",
    WarningKind.EQUIVALENCE_CROSS_ADDRESSING: "EQUIVALENCE across different addressing modes",
    WarningKind.INDEX_WITHOUT_BOUNDS_CHECK: "Array indexed without explicit bounds check",
    WarningKind.CONDITION_CODE_CLOBBER: "Operation between condition code set and test",
    WarningKind.LITERAL_COULD_BE_USED: "Hardcoded numeric constant — consider LITERAL",
    WarningKind.MISSING_DEBUG_DIRECTIVE: "Program missing ?INSPECT or ?SYMBOLS directive",
    WarningKind.PADDING_WASTE_GLOBAL: "Wasted bytes from padding in global declarations",
    WarningKind.PADDING_WASTE_LOCAL: "Wasted bytes from padding in local declarations",
    WarningKind.PADDING_WASTE_SUBLOCAL: "Wasted bytes from padding in sublocal declarations",
    WarningKind.PADDING_WASTE_STRUCT: "Wasted bytes from padding in struct field layout",
    WarningKind.SECONDARY_OVERFLOW: "Primary + secondary storage exceeds 32,768 words (64 KB)",
    WarningKind.SUBLOCAL_INDIRECT: "Indirect declaration in sublocal — compiler converts to direct (no secondary area)",
    WarningKind.UNRESOLVED_TEMPLATE: "Struct references template from unresolved import — size unknown, totals are lower bounds",
}

GROUPABLE_KINDS = {
    WarningKind.SCAN_WITHOUT_CARRY_CHECK,
    WarningKind.INDEX_WITHOUT_BOUNDS_CHECK,
    WarningKind.PADDING_WASTE_GLOBAL,
    WarningKind.PADDING_WASTE_LOCAL,
    WarningKind.PADDING_WASTE_SUBLOCAL,
    WarningKind.PADDING_WASTE_STRUCT,
}


_NO_COLOR = not os.isatty(1)

_RED = "\033[31m" if not _NO_COLOR else ""
_YELLOW = "\033[33m" if not _NO_COLOR else ""
_BLUE = "\033[34m" if not _NO_COLOR else ""
_WHITE = "\033[37m" if not _NO_COLOR else ""
_CYAN = "\033[36m" if not _NO_COLOR else ""
_BOLD = "\033[1m" if not _NO_COLOR else ""
_DIM = "\033[2m" if not _NO_COLOR else ""
_RESET = "\033[0m" if not _NO_COLOR else ""


def _severity_color(sev: Severity) -> str:
    match sev:
        case Severity.CRITICAL: return _RED
        case Severity.HIGH: return _YELLOW
        case Severity.MEDIUM: return _WHITE + _BLUE
        case Severity.LOW: return _BLUE
        case _: return ""


def _c(text: str, color: str) -> str:
    if _NO_COLOR or not color:
        return text
    return f"{color}{text}{_RESET}"


@dataclass
class Warning:
    kind: WarningKind
    message: str
    loc: Optional[str] = None
    suggestion: str = ""
    proc_name: str = ""

    @property
    def severity(self) -> Severity:
        return SEVERITY_MAP.get(self.kind, Severity.MEDIUM)

    @property
    def rule(self) -> int:
        return RULE_NUMBERS.get(self.kind, 0)

    @property
    def description(self) -> str:
        return RULE_DESCRIPTIONS.get(self.kind, "")

    def _parse_loc(self) -> tuple[str, int, int]:
        if not self.loc:
            return ("", 0, 0)
        m = re.match(r'^(.+?):(\d+)(?::(\d+))?$', self.loc)
        if not m:
            return (self.loc, 0, 0)
        return (m.group(1), int(m.group(2)), int(m.group(3) or 0))


def _get_source_lines(source_file: str) -> list[str]:
    try:
        with open(source_file) as f:
            return f.readlines()
    except (FileNotFoundError, OSError):
        return []


def _extract_token_at(line: str, col: int) -> str:
    if col <= 0 or col > len(line):
        return ""
    pos = col - 1
    token = ""
    while pos < len(line):
        ch = line[pos]
        if ch.isalnum() or ch in ('_', '^'):
            token += ch
            pos += 1
        else:
            break
    return token


def _format_context(source_lines: list[str], line_no: int, col: int,
                    source_text: str = "", context: int = 2) -> list[str]:
    out: list[str] = []
    start = max(0, line_no - context - 1)
    end = min(len(source_lines), line_no + context)
    width = len(str(end))

    for i in range(start, end):
        raw = source_lines[i].rstrip('\n')
        is_target = (i == line_no - 1)
        marker = ">" if is_target else " "
        prefix = f"    {marker} {i+1:>{width}} | "
        out.append(f"{prefix}{raw}")

        if is_target and col > 0:
            token = source_text or _extract_token_at(raw, col)
            caret_len = len(token) if token else 1
            caret_start = col - 1
            indent = " " * len(prefix)
            tildes = _c("~" * caret_len, _CYAN)
            out.append(f"{indent}{' ' * caret_start}{tildes}")

    return out


def _extract_proc_name(msg: str) -> str:
    m = re.search(r"procedure\s+'([^']+)'", msg, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"(?:in|overflow in)\s+(\S+)", msg, re.IGNORECASE)
    if m:
        return m.group(1).rstrip(":")
    return ""


def _extract_var_name(msg: str) -> str:
    m = re.search(r"(\S+)\s+\((\d+)\s+words?\)", msg)
    if m:
        return m.group(1)
    m = re.search(r"Variable\s+'([^']+)'", msg, re.IGNORECASE)
    if m:
        return m.group(1)
    return ""


def _extract_totals(msg: str) -> tuple[int, int]:
    m = re.search(r"total to (\d+) words \(max (\d+)\)", msg)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return (0, 0)


def _sort_key(w: Warning) -> tuple:
    _, line_no, col = w._parse_loc()
    return (w.severity.rank, w.kind.name, line_no, col)


def format_report(warnings: list[Warning], source_file: str,
                   source_lines: list[str] | None = None,
                   color: bool | None = None,
                   expansions: list | None = None,
                   original_lines: list[str] | None = None) -> str:
    global _NO_COLOR
    if color is not None:
        _NO_COLOR = not color
    if source_lines is None:
        source_lines = _get_source_lines(source_file)

    expansion_map: dict[int, object] = {}
    if expansions:
        for exp in expansions:
            for line in range(exp.expanded_start_line, exp.expanded_end_line + 1):
                expansion_map[line] = exp

    warnings.sort(key=_sort_key)

    n_crit = sum(1 for w in warnings if w.severity == Severity.CRITICAL)
    n_high = sum(1 for w in warnings if w.severity == Severity.HIGH)
    n_med = sum(1 for w in warnings if w.severity == Severity.MEDIUM)
    n_low = sum(1 for w in warnings if w.severity == Severity.LOW)

    out: list[str] = []
    out.append(f"TAL Memory Analysis: {source_file}")
    out.append("=" * 60)
    out.append(f"Found {len(warnings)} warnings "
               f"({_c(str(n_crit), _RED)} critical, "
               f"{_c(str(n_high), _YELLOW)} high, "
               f"{_c(str(n_med), _BLUE)} medium, "
               f"{_c(str(n_low), _BLUE)} low)")
    out.append("")

    by_kind: dict[WarningKind, list[Warning]] = defaultdict(list)
    for w in warnings:
        by_kind[w.kind].append(w)

    shown_grouped: set[WarningKind] = set()

    for w in warnings:
        kind = w.kind
        if kind in GROUPABLE_KINDS and kind in shown_grouped:
            continue

        _, line_no, col = w._parse_loc()
        var_name = _extract_var_name(w.message)
        proc_name = _extract_proc_name(w.message) or w.proc_name

        sev_tag = "error" if w.severity == Severity.CRITICAL else "warning"
        sev_color = _severity_color(w.severity)

        exp = expansion_map.get(line_no) if line_no else None
        if exp:
            header = f"{source_file}:{exp.orig_call_line}: {_c(sev_tag, sev_color)}: {_c(kind.name, _BOLD + sev_color)}"
        else:
            header = f"{w.loc}: {_c(sev_tag, sev_color)}: {_c(kind.name, _BOLD + sev_color)}"
        out.append(header)
        out.append(f"    {w.message}")

        if exp and source_lines:
            out.extend(_format_expansion_context(exp, source_lines,
                                                  original_lines, line_no, col))
        elif source_lines and line_no > 0:
            out.extend(_format_context(source_lines, line_no, col, var_name))

        total, limit = _extract_totals(w.message)
        if total and limit:
            out.append(f"    Total storage would be {total} words (limit = {limit}).")

        help_text = _format_help(kind, w, var_name, proc_name)
        if help_text:
            out.append("")
            help_lines = help_text.split("\n")
            first = help_lines[0]
            rest = "\n".join(help_lines[1:])
            out.append(f"    {_c('help:', _CYAN)} {_c(first, _CYAN)}")
            if rest:
                for rl in rest.split("\n"):
                    out.append(f"    {_c(rl, _CYAN)}")

        out.append("")

        if kind in GROUPABLE_KINDS:
            group = by_kind[kind]
            if len(group) > 1:
                _format_group_summary(group, out)
            shown_grouped.add(kind)

    return "\n".join(out)


def _format_expansion_context(exp, source_lines: list[str],
                              original_lines: list[str] | None,
                              line_no: int, col: int) -> list[str]:
    out: list[str] = []
    if original_lines and 0 < exp.orig_call_line <= len(original_lines):
        orig_text = original_lines[exp.orig_call_line - 1].rstrip('\n')
        width = len(str(exp.orig_call_line))
        out.append(f"    > {exp.orig_call_line:>{width}} | {orig_text}")
        out.append(f"      {' ' * width}   {_c(f'macro {exp.macro_name!r}', _DIM)}")
    out.append("")
    out.append(f"    {_c('Expanded:', _DIM)}")
    exp_start = exp.expanded_start_line - 1
    exp_end = min(exp.expanded_end_line, len(source_lines))
    n_lines = exp_end - exp_start
    rel_width = len(str(n_lines))
    for rel_idx, i in enumerate(range(exp_start, exp_end), 1):
        line_text = source_lines[i].rstrip('\n')
        is_target = (i + 1 == line_no)
        marker = ">" if is_target else " "
        prefix = f"    {marker} {rel_idx:>{rel_width}} | "
        out.append(f"{prefix}{line_text}")
        if is_target and col > 0:
            token = _extract_token_at(line_text, col)
            caret_len = len(token) if token else 1
            caret_start = col - 1
            indent = " " * len(prefix)
            tildes = _c("~" * caret_len, _CYAN)
            out.append(f"{indent}{' ' * caret_start}{tildes}")
    return out


def _format_help(kind: WarningKind, w: Warning, var_name: str,
                 proc_name: str) -> str:
    if kind == WarningKind.LOCAL_OVERFLOW:
        return (f"Use indirect allocation to avoid primary stack overflow\n"
                f"      INT .{var_name}  ; allocates from secondary area (recommended)\n"
                f"      or\n"
                f"      keep in primary if absolutely necessary (not recommended)")
    if kind == WarningKind.SUBLOCAL_OVERFLOW:
        return (f"Move to parent PROC scope or use indirect\n"
                f"      PROC {proc_name}\n"
                f"          LOCAL {var_name}  ; now in primary instead of sublocal")
    if kind == WarningKind.SCAN_WITHOUT_CARRY_CHECK:
        return (f"Always test $CARRY after SCAN/RSCAN\n"
                f"      RSCAN ...\n"
                f"      IF $CARRY THEN\n"
                f"          ... handle not-found case ...\n"
                f"      ENDIF")
    if kind == WarningKind.RECURSION_WITHOUT_LARGESTACK:
        return (f"Add ?LARGESTACK directive before the PROC\n"
                f"      ?LARGESTACK\n"
                f"      INT PROC {proc_name};")
    if kind == WarningKind.UNRESOLVED_TEMPLATE:
        return (f"Provide the missing ?SOURCE file so the template can be resolved\n"
                f"      or add the struct definition locally with STRUCT name (*); BEGIN ... END;")
    if w.suggestion:
        return w.suggestion
    return ""


def _format_group_summary(group: list[Warning], out: list[str]):
    kind = group[0].kind
    n = len(group)

    by_proc: dict[str, list[Warning]] = defaultdict(list)
    for w in group:
        pn = _extract_proc_name(w.message) or w.proc_name or "<unknown>"
        by_proc[pn].append(w)

    most_proc = max(by_proc, key=lambda k: len(by_proc[k]))
    most_count = len(by_proc[most_proc])

    out.append(f"---  {_c(kind.name, _DIM)} ({n} occurrences)  ---")
    out.append("")
    out.append(f"    {n - 1} more instances of the same issue were found.")
    out.append(f"    Most affected procedure: '{most_proc}' ({most_count} times)")
    out.append(f"    Procedures affected:")

    for proc_name, proc_warns in sorted(by_proc.items(), key=lambda x: -len(x[1])):
        line_nos = []
        for w in proc_warns:
            _, ln, _ = w._parse_loc()
            if ln:
                line_nos.append(ln)
        if len(line_nos) <= 3:
            lines_str = ", ".join(str(ln) for ln in line_nos)
        else:
            lines_str = f"{line_nos[0]}, {line_nos[1]}, ..., {line_nos[-1]}"
        out.append(f"      - {proc_name:30s} (lines {lines_str})")

    out.append("")
    help_for_group = _format_help(kind, group[0],
                                  _extract_var_name(group[0].message),
                                  _extract_proc_name(group[0].message))
    if help_for_group:
        out.append(f"    {_c('Quick bulk fix suggestion:', _CYAN)}")
        for hline in help_for_group.split("\n"):
            out.append(f"    {_c(hline, _CYAN)}")
        out.append("")
    out.append("")


def format_json(warnings: list[Warning]) -> list[dict]:
    return [
        {
            "rule": w.rule,
            "kind": w.kind.name,
            "severity": str(w.severity),
            "message": w.message,
            "location": w.loc,
            "suggestion": w.suggestion,
        }
        for w in warnings
    ]
