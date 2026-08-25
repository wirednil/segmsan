"""TAL DEFINE pre-processor.

Collects DEFINE macros from source text and expands invocations inline.
Runs on raw text BEFORE lexing, simulating what the TAL compiler does.

DEFINE syntax:
  define NAME = replacement#;
  define NAME(p1, p2, ...) = replacement#;
  define NAME1 = replacement1#, NAME2 = replacement2#, ... , NAMEn = replacementn#;

A single DEFINE statement can declare multiple macros, each terminated by '#'
and separated by ','; the whole statement ends at the ';' after the last '#'.
Parameters are substituted textually. Expansion is repeated until no more
macros are found (handles nesting).
"""

from __future__ import annotations
import os
import re
from dataclasses import dataclass, field


@dataclass
class DefineMacro:
    name: str
    params: list[str] = field(default_factory=list)
    body: str = ""
    line: int = 0
    body_start_line: int = 0
    body_lines: int = 0


@dataclass
class ExpansionRecord:
    macro_name: str
    orig_call_line: int
    orig_call_text: str
    expanded_start_line: int
    expanded_end_line: int


_DEFINE_START_RE = re.compile(r'^\s*define\s+', re.IGNORECASE | re.MULTILINE)

_DEFINE_ENTRY_RE = re.compile(
    r'\s*([A-Za-z_][\w^]*)\s*'
    r'(?:\(([^)]*)\)\s*)?'
    r'=\s*'
    r'(.*?)#',
    re.DOTALL,
)

_WS_RE = re.compile(r'\s*', re.DOTALL)


def collect_defines(source: str) -> tuple[list[DefineMacro], str]:
    macros: list[DefineMacro] = []
    spans: list[tuple[int, int]] = []

    for start_m in _DEFINE_START_RE.finditer(source):
        stmt_start = start_m.start()
        if spans and stmt_start < spans[-1][1]:
            continue  # inside a define statement already consumed
        pos = start_m.end()
        stmt_end = pos
        while True:
            m = _DEFINE_ENTRY_RE.match(source, pos)
            if not m:
                break
            name = m.group(1)
            params_raw = m.group(2) or ""
            params = [p.strip() for p in params_raw.split(",") if p.strip()]
            body = m.group(3).strip()
            def_line = source[:m.start(1)].count('\n') + 1
            body_start = source[:m.start(3)].count('\n') + 1
            body_line_count = body.count('\n') + 1 if body else 1
            macros.append(DefineMacro(
                name=name, params=params, body=body,
                line=def_line, body_start_line=body_start,
                body_lines=body_line_count,
            ))
            pos = m.end()
            stmt_end = pos
            ws_end = pos + _WS_RE.match(source, pos).end() - pos
            if ws_end < len(source) and source[ws_end] == ',':
                pos = ws_end + 1
                stmt_end = pos
                continue
            if ws_end < len(source) and source[ws_end] == ';':
                stmt_end = ws_end + 1
            break
        spans.append((stmt_start, stmt_end))

    cleaned_parts = []
    last = 0
    for start, end in spans:
        cleaned_parts.append(source[last:start])
        cleaned_parts.append('\n' * source[start:end].count('\n'))
        last = end
    cleaned_parts.append(source[last:])
    cleaned = "".join(cleaned_parts)

    return macros, cleaned


def _pad_to_match_lines(replacement: str, original: str) -> str:
    orig_nl = original.count('\n')
    repl_nl = replacement.count('\n')
    if repl_nl > orig_nl:
        replacement = replacement.replace('\n', ' ') + '\n' * orig_nl
    elif repl_nl < orig_nl:
        replacement += '\n' * (orig_nl - repl_nl)
    return replacement


def _find_balanced_parens(text: str, start: int) -> int:
    depth = 0
    i = start
    while i < len(text):
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
            if depth == 0:
                return i
        elif text[i] == '"':
            i += 1
            while i < len(text) and text[i] != '"':
                i += 1
        i += 1
    return -1


def _split_args(text: str) -> list[str]:
    args: list[str] = []
    depth = 0
    current: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"':
            current.append(ch)
            i += 1
            while i < len(text) and text[i] != '"':
                current.append(text[i])
                i += 1
            if i < len(text):
                current.append(text[i])
                i += 1
            continue
        if ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            args.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
        i += 1
    last = "".join(current).strip()
    if last:
        args.append(last)
    return args


def _substitute_params(body: str, params: list[str], args: list[str]) -> str:
    if not params:
        return body
    result = body
    for param, arg in zip(params, args):
        param_stripped = param.strip()
        arg_stripped = arg.strip()
        escaped = re.escape(param_stripped)
        result = re.sub(
            r'(?<![A-Za-z0-9_^])' + escaped + r'(?![A-Za-z0-9_^])',
            lambda _m, _r=arg_stripped: _r,  # literal replacement — arg text may
                                              # contain '\' sequences (e.g. \F, \E
                                              # format placeholders) that re.sub
                                              # would otherwise mis-parse as regex
                                              # backreferences and raise re.error
            result,
        )
    return result


def expand_macros(source: str, macros: list[DefineMacro],
                  max_passes: int = 20) -> tuple[str, list[ExpansionRecord]]:
    macro_map: dict[str, DefineMacro] = {}
    for m in macros:
        macro_map[m.name.upper()] = m

    if not macro_map:
        return source, []

    all_expansions: list[ExpansionRecord] = []
    result = source
    for _ in range(max_passes):
        prev = result
        result, pass_expansions = _expand_one_pass(result, macro_map)
        all_expansions.extend(pass_expansions)
        if result == prev:
            break

    return result, all_expansions


def _expand_one_pass(source: str, macro_map: dict[str, DefineMacro]) -> tuple[str, list[ExpansionRecord]]:
    name_pattern = "|".join(re.escape(m.name) for m in macro_map.values())
    find_re = re.compile(
        r'\b(' + name_pattern + r')(?:\s*\(|(?=\s*[;\n]))',
        re.IGNORECASE,
    )

    result_parts: list[str] = []
    pos = 0
    total_len = 0
    raw_expansions: list[tuple[int, str, int, str, str]] = []

    source_lines_list = source.split('\n')

    for m in find_re.finditer(source):
        name = m.group(1)
        start = m.start()
        if start < pos:
            continue

        macro = macro_map.get(name.upper())
        if not macro:
            continue

        if not macro.params and m.group(0).endswith('('):
            continue

        # Macro has params but regex matched without '(' — name reference, not a call.
        # Without this guard, expand_macros finds the next '(' anywhere in the file
        # and wrongly treats it as the argument list (e.g. 'log' in '?section log'
        # stealing the '(' of the next proc declaration).
        if macro.params and not m.group(0).endswith('('):
            continue

        if macro.params:
            paren_match = re.search(r'\(', source[start:])
            if not paren_match:
                continue
            paren_start = start + paren_match.start()
            paren_end = _find_balanced_parens(source, paren_start)
            if paren_end < 0:
                continue
            args_text = source[paren_start + 1:paren_end]
            args = _split_args(args_text)
            expanded = _substitute_params(macro.body, macro.params, args)
            original = source[start:paren_end + 1]
            expanded = _pad_to_match_lines(expanded, original)
            end_pos = paren_end + 1
        else:
            original = source[start:m.end()]
            expanded = _pad_to_match_lines(macro.body, original)
            end_pos = m.end()

        prefix = source[pos:start]
        result_parts.append(prefix)
        total_len += len(prefix)
        char_offset = total_len

        orig_call_line = source[:start].count('\n') + 1
        orig_call_text = source_lines_list[orig_call_line - 1] if orig_call_line <= len(source_lines_list) else ""

        raw_expansions.append((char_offset, expanded, orig_call_line, macro.name, orig_call_text))
        result_parts.append(expanded)
        total_len += len(expanded)
        pos = end_pos

    result_parts.append(source[pos:])
    result = "".join(result_parts)

    expansions: list[ExpansionRecord] = []
    for char_offset, exp_text, orig_line, macro_name, orig_text in raw_expansions:
        start_line = result[:char_offset].count('\n') + 1
        end_line = start_line + exp_text.count('\n')
        expansions.append(ExpansionRecord(
            macro_name=macro_name,
            orig_call_line=orig_line,
            orig_call_text=orig_text,
            expanded_start_line=start_line,
            expanded_end_line=end_line,
        ))

    return result, expansions


def collect_defines_from_file(filepath: str) -> tuple[list[DefineMacro], str]:
    try:
        with open(filepath) as f:
            source = f.read()
    except OSError:
        return [], ""
    macros, _ = collect_defines(source)
    return macros, source


def collect_defines_recursive(source: str, base_dir: str,
                              search_dirs: list[str] | None = None,
                              _visited: set[str] | None = None) -> list[DefineMacro]:
    all_dirs = [base_dir] + (search_dirs or [])
    if _visited is None:
        _visited = set()

    macros, _ = collect_defines(source)

    for m in re.finditer(r'SOURCE\s+([^\s,(]+)', source, re.IGNORECASE):
        path = m.group(1).strip()
        if path.upper().startswith("$SYSTEM.") or path.upper().startswith("$RTL"):
            continue
        name = path.split(".")[-1]
        for d in all_dirs:
            found = False
            for ext in [".tal", ""]:
                for c in [
                    os.path.join(d, name.lower() + ext),
                    os.path.join(d, name + ext),
                ]:
                    if os.path.isfile(c):
                        abs_c = os.path.abspath(c)
                        if abs_c not in _visited:
                            _visited.add(abs_c)
                            sub_macros, sub_source = collect_defines_from_file(c)
                            macros.extend(sub_macros)
                            if sub_source:
                                macros.extend(
                                    collect_defines_recursive(
                                        sub_source, os.path.dirname(abs_c),
                                        search_dirs, _visited))
                        found = True
                        break
                if found:
                    break
            if found:
                break

    return macros


def preprocess(source: str, import_dirs: list[str] | None = None) -> str:
    macros, cleaned = collect_defines(source)

    if import_dirs:
        for dir_path in import_dirs:
            try:
                import os
                for fname in os.listdir(dir_path):
                    if fname.lower().endswith(".tal"):
                        fpath = os.path.join(dir_path, fname)
                        macros.extend(collect_defines_from_file(fpath)[0])
            except OSError:
                pass

    expanded, _ = expand_macros(cleaned, macros)
    return expanded
