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

24 rules across 4 severity levels (CRITICAL, HIGH, MEDIUM, LOW).

## Usage

```bash
python3 -m segmsan source.tal
python3 -m segmsan source.tal --strict   # include LOW severity
```

Output is diagnostic-style with colors, carets, grouped summaries, and fix suggestions.

## Requirements

- Python 3.10+
- No external dependencies (stdlib only)

## Architecture

```
src/
  __main__.py       CLI entry point
  preprocessor.py   DEFINE expansion + SOURCE import + macro tracking
  lexer.py          TAL tokenizer
  parser.py         Hand-written recursive descent parser
  ast_nodes.py      AST types + storage calculation
  scope.py          Scope tracking (global/local/sublocal)
  dataflow.py       Taint analysis for pointer lifetime tracking
  interproc.py      Interprocedural call graph + procedure summaries
  resolver.py       Import resolution for external SOURCE files
  system_stubs.py   System procedure signatures
  report.py         Diagnostic output formatting
  checks/           Individual rule implementations (11 modules)
  data/             system_procs.json (609 Guardian procedure signatures)
  tests/            Test suite + sample TAL files
```

## Running Tests

```bash
python3 run_custom_tests.py
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
