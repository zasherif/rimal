# Rimal (v0.3)

Rimal is a minimal Arabic language that compiles to WebAssembly.

## Overview

- **Language**: Rimal (`.rml`)
- **Target**: WebAssembly 1.0
- **Runtime**: Wasmtime (no WASI)
- **Types**: `i32`, booleans, string literals (print-only)

## Language (v0.3) — Grammar Summary

### Statements

- **Function definition**:

```
دالة <name>(<params...>) -> <type>:
    <statements>
```

- **Print**: `اطبع <expr-or-string>`
- **Assert**: `تأكد <expr>` (traps if false; useful for tests)
- **Declaration (immutable)**: `دع <identifier>: <type> = <expr>`
- **Declaration (mutable)**: `متغير <identifier>: <type> = <expr>`
- **Assignment**: `<identifier> = <expr>` (mutable bindings only)
- **Return**: `ارجع <expr>`
- **If/Else**:

```
اذا <expr>:
    <statements>
وإلا:
    <statements>
```

- **Elif**:

```
وإلا اذا <expr>:
    <statements>
```

- **While**:

```
بينما <expr>:
    <statements>
```

- **Loop control**:
  - `اكسر` (break)
  - `تابع` (continue)

### Expressions

- Literals: integers, `صح`, `خطأ`, string literals (`"..."` only for `اطبع`)
- Variables: must be declared before use
- Operators: `+ - * /` and comparisons `== != < > <= >=`
- Parentheses: `( ... )`
- Boolean ops: `و` (and), `أو`/`او` (or), `ليس` (not)
- Function calls: `<name>(<args...>)`
- **Digits**: Arabic-Indic digits are supported in source (e.g. `١٢٣`). For readability, printed `i32` values are also rendered using Arabic-Indic digits.

Notes:
- Printing `منطقي` values displays `صح` / `خطأ` (while they are still represented as `i32` internally).

### Blocks / Indentation

- Indentation-based blocks using **spaces only**
- **Tabs are forbidden**
- Newlines inside parentheses do not end statements (line continuation).
- **RTL display tip**: RTL/LTR rendering is controlled by your editor/terminal. Rimal ignores Unicode bidi formatting marks (LRM/RLM/etc.) if you need to insert them for display, but the recommended approach is enabling RTL editing support in your editor for `.rml` files.

## Architecture

- `rimal/token.py`: token types + error types (lexer/parser errors include file:line:col)
- `rimal/lexer.py`: Unicode-aware lexer + INDENT/DEDENT emission
- `rimal/ast.py`: minimal AST nodes
- `rimal/parser.py`: recursive descent parser + precedence handling
- `rimal/wasm_compiler.py`: WAT emitter + `.wasm` generation via `wasmtime.wat2wasm`
- `rml.py`: CLI (`rml build`, `rml run`) + Wasmtime execution

## Compilation Pipeline

`.rml` → **tokens** → **AST** → **WAT** → **WASM** → Wasmtime instantiate → call exported `run`

The generated module imports host functions:

- `(import "host" "print_i32" (func $print_i32 (param i32)))`
- `(import "host" "print_str" (func $print_str (param i32 i32)))`

Strings are stored as UTF-8 bytes in linear memory as data segments. `اطبع "..."` passes `(ptr, len)` to `print_str`.

## Install

Python 3.11+ required.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install wasmtime
```

## Run

From the `rimal/` directory:

```bash
./rml run examples/hello.rml
./rml build examples/hello.rml

# or:
python3.11 rml.py run examples/hello.rml
python3.11 rml.py build examples/hello.rml
```

### Verbose compilation/execution logs

Use `-v/--verbose` to print internal steps to **stderr** (stdout stays reserved for program output):

```bash
./rml run -v examples/hello.rml
./rml build -v examples/hello.rml
```

## Tests

```bash
python3.11 -m tests.test_runner
```

## Cursor/VS Code RTL Editing (optional)

Cursor/VS Code does not natively force RTL layout for code editors. This repo includes a tiny local extension at `vscode-rtl-editor/` that provides a dedicated **RTL editor** for `*.rml` files (webview-based).

- **Install (Cursor)**: copy `vscode-rtl-editor/` to `~/.cursor/extensions/rimal.rml-rtl-editor-0.0.1/` and reload window.
- **Use**: open a `.rml` file → **Reopen Editor With...** → **RML RTL Editor**

## Known Limitations (by design)

- No functions, no floats, no arrays, no user-defined types
- All variables are `i32` locals
- Strings are only allowed as literals in `اطبع`
- Comments: supported as `# ...` (line or inline)
- No WASI / file I/O


