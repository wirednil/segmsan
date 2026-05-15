# SEGMSAN — SegmentSanitizer

Static segment/memory bug detector for TAL (Transaction Application Language) on HP NonStop Guardian (TNS/X, TNS/R).

Inspired by LLVM sanitizers (ASan, MSan, TSan), SEGMSAN detects memory errors in TAL source code **at compile time** — no execution required.

## What It Detects

| Category | Checks |
|---|---|
| **Storage overflow** | Global >256w, local >127w, sublocal >32w, upper 32K boundary |
| **Pointer errors** | Dangling pointers, uninitialized deref, address-of-local to global |
| **Extended memory** | Missing .EXT for >32K addresses, EQUIVALENCE to implicit pointer |
| **Control flow** | Recursion without ?LARGESTACK, SCAN without $CARRY check |
| **Type safety** | FIXED precision loss, STRING by-value mismatch, readonly modification |
| **Other** | $COMP misuse, condition code clobber, array bounds, padding waste |

 26 rules across 4 severity levels (CRITICAL, HIGH, MEDIUM, LOW).

## Usage

```bash
python3 -m segmsan source.tal                  # analyze with all checks
python3 -m segmsan source.tal --strict         # only CRITICAL + HIGH
python3 -m segmsan source.tal --padding        # include padding waste (LOW)
python3 -m segmsan source.tal -f json          # machine-readable output
python3 -m segmsan source.tal --no-preprocess  # skip DEFINE expansion
python3 -m segmsan source.tal --skip-missing-sources  # suppress missing SOURCE warnings
```

Output includes:
- Colored diagnostic-style warnings with source carets
- DEFINE macro expansion context (original call + expanded code)
- Per-procedure storage summary (primary/secondary/extended/combined words)
- Grouped warning counts by severity

## Requirements

- Python 3.10+
- No external dependencies (stdlib only)

## Architecture

```
segmsan/
  __main__.py       CLI entry point
  preprocessor.py   DEFINE expansion + SOURCE import + macro tracking
  lexer.py          TAL tokenizer
  parser.py         Hand-written recursive descent parser
  ast_nodes.py      AST types + storage calculation (primary/secondary/extended)
  scope.py          Scope tracking (global/local/sublocal)
  dataflow.py       Taint analysis for pointer lifetime tracking
  interproc.py      Interprocedural call graph + procedure summaries
  resolver.py       Import resolution for external SOURCE files
  system_stubs.py   System procedure signatures
  report.py         Diagnostic output formatting + expansion context
  checks/           Individual rule implementations (12 modules)
    bounds.py       Rule 17: array bounds (IF/WHILE-guarded suppression)
    storage.py      Rules 3/4/5/25/26: overflow + secondary + sublocal indirect
    equivalence.py  Rule 18: EQUIVALENCE cross-addressing
    cc_clobber.py   Rule 21: condition code clobber
    ext_ptr.py      Rule 23: extended pointer misuse
    fixed.py        Rule 15: FIXED precision loss
    dangling.py     Rule 12: dangling pointers
    readonly.py     Rule 14: readonly modification
    control_flow.py Rules 9/13: recursion + missing debug
    misc.py         Rules 1/16/22: misc checks
    padding.py      Rules 19/20: padding waste (off by default)
  data/             system_procs.json (609 Guardian procedure signatures)
  tests/            Test suite + sample TAL files
```

## Running Tests

```bash
python3 run_custom_tests.py    # 5/5 expected
```

## TAL Memory Model

TAL processes on TNS have three memory areas:

1. **User Data Segment** (128 KB) — direct vars + indirect secondary data (shared 64 KB limit)
2. **Automatic Extended Segment** (up to 127.5 MB) — `.EXT` data, auto-managed by compiler
3. **Explicit Extended Segments** — manual via SEGMENT_ALLOCATE_

Key limits SEGMSAN checks:
- Global primary: 256 words
- Local primary: 127 words
- Sublocal primary: 32 words
- Combined primary + secondary: 32,768 words (64 KB)

## Sanitizer Comparison

| Sanitizer | Language | Target | Method |
|---|---|---|---|
| ASan | C/C++ | Buffer overflows, use-after-free | Runtime instrumentation |
| MSan | C/C++ | Uninitialized memory reads | Runtime instrumentation |
| TSan | C/C++ | Data races | Runtime instrumentation |
| **SEGMSAN** | **TAL** | **Segment/stack overflow, dangling pointers** | **Static analysis** |

## License

MIT
