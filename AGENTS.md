## Goal
Static memory analyzer for HP NonStop TAL/Guardian code in Python. Lark LALR(1) parser.

## Constraints
- Python 3.10+ stdlib only, zero external deps
- TAL on HP NonStop Guardian (TNS/X, TNS/R), no dynamic memory
- User is experienced C programmer; docs oriented C→TAL
- TAL case-insensitive for identifiers
- `TRUE`/`FALSE` are NOT TAL keywords — user-defined LITERALs, arrive as `NAME`
- `tal_analyzer/` is source of truth; `segmsan/` is distributed package — manual sync via rsync
- `MOVE` is NOT a TAL keyword — MOVE statement uses `':='` or `'=:'` operators
- Cycle: test with productive .tal → error → fix → full test → repeat

## Architecture
- Pipeline: `TAL source → preprocessor (text) → lexer.py (tokens) → Lark grammar → AST → checks`
- Grammar files: `grammar/*.lark` (common_decl, var_decl, expr, stmt_simple, stmt_complex, struct_def, proc_body, proc_header, literal_decl, tal_top)
- Transformers: `transformers/*.py` (var_decl, expr, stmt, proc_body, struct_def, proc_header, program)
- `lexer.py`: token stream + `to_lark_stream`, `to_stmt_stream`, `to_proc_body_stream`, `to_program_stream`
- `preprocessor.py`: DEFINE expansion on plain text before lexer
- 28 rules implemented in `checks/`
- `data/system_procs.json`: ~350 Guardian proc signatures

## Key Grammar Decisions
- `for_slice : KW_FOR expr move_unit?` in proc_body.lark — resolves KW_BYTES conflict
- `move_part : expr move_for_clause? arrow_expr? | AMP | LBRACK const_fill RBRACK arrow_expr?` — fill inline in move chain
- `if_stmt` has assign-as-condition: `KW_IF or_expr ASSIGN or_expr KW_THEN ...`
- `struct_decl` supports COMMA multi-declaration: `struct .a(X), .b(Y);`
- `var_initializer : EQ PRIME NAME PRIME ASSIGN init_val | EQ init_val | ASSIGN init_val` — public name support
- Group comparison: `cmp_group_for` / `cmp_group_list` in proc_body.lark
- CALL empty args: `call_param_empty` — `foo(a,,,b)`
- FORWARD/EXTERNAL: `proc_body_forward` / `proc_body_external`

## Test & Sync
- Tests in `segmsan/tests/` — imports use `from segmsan.`
- Tests in `tal_analyzer/tests/` — imports use `from tal_analyzer.`
- Sync: `rsync -av --delete --exclude='__pycache__' --exclude='*.pyc' --exclude='tests/' tal_analyzer/ segmsan/` then `rsync` tests + `sed -i 's/from tal_analyzer\./from segmsan./g'`
- 571 tests passing, 13/13 productive .tal files parse with 0 errors

## Known Gaps (bautils 34K lines fails at L3008)
- `bautils` fails at L3008 — `stack 7; code(sete);` pattern
- **STACK statement** (RefMan L9314): `stack_statement ::= 'STACK' expression (',' expression)*` — loads values onto register stack
- **CODE statement** (RefMan L8439): `code_statement = "CODE", "(", instruction, { ";", instruction }, ")"` — machine-level instructions
- **ARMTRAP pattern** (RefMan L12153-12165): common idiom to disable/enable arithmetic overflow traps:
  ```tal
  stack 7;                    -- load mask onto register stack
  code( sete );               -- SETE instruction (set enable trap)
  -- ... critical operations ...
  code( ANRI $COMP(%200);     -- turn off overflow trap bit
        SETE );
  ```
- `KW_STACK` and `KW_CODE` are declared in `_PHASE8_DECLARES` but the grammar rules
  `stack_stmt` and `code_stmt` are not connected in `move_or_assign` or `statement` dispatch

## Productive Test Files
Located in `/home/cibo/Documents/B24-docs/mantxt/*.tal`:
- test_define_multi.tal (18L), stdgbl.tal (45L), test_stringlib.tal (292L), vrfacts.tal (306L)
- simlogs.tal (319L), test_printf.tal (385L), ecoreps.tal (475L), fwebs.tal (480L)
- facpwems.tal (710L), facpweds.tal (1017L), facter2s.tal (1018L), genlibs.tal (1065L)
- seekfs.tal (6503L) — 91 warnings, largest file

## Reference
- `/home/cibo/Documents/B24-docs/mantxt/RefMan.txt` — TAL spec with EBNF (29163 lines)
