# Rimal Language Specification (Draft)

This document is the normative language specification for **Rimal**.

- **v0.2**: implemented (tagged by git commit history)
- **v0.3**: draft below

## 1. Goals (v0.3)

- Keep the language minimal and Arabic-first.
- Move toward Rust/Zig-style clarity: **explicit declarations**, **types**, **scopes**, **compile-time errors**.
- Remain compatible with **WebAssembly 1.0** (WAT/Wasm) without WASI.

## 2. Non-goals (v0.3)

- Floats, 64-bit ints, structs/enums, arrays/slices, heap allocation, GC
- Modules/imports
- Exceptions/try-catch
- Strings as a general runtime type (still “print-literal only”)

## 3. Lexical Structure

### 3.1 Source encoding

- Source files MUST be UTF-8.
- Identifiers MAY use Unicode letters and digits (Arabic supported).

### 3.2 Whitespace and indentation

- Blocks are indentation-based using **spaces only**.
- Tabs are forbidden and MUST produce a lexer error.

### 3.3 Comments

- `#` starts a comment and continues to end-of-line.
- Comments are allowed on their own line or inline.

### 3.4 Line continuation

- Newlines inside parentheses `(` ... `)` do not terminate a statement.

## 4. Types (v0.3)

Rimal v0.3 introduces a minimal static type system.

### 4.1 Primitive types

- `عدد٣٢` — 32-bit signed integer (maps to Wasm `i32`)
- `منطقي` — boolean (maps to Wasm `i32`, values restricted to 0/1)
- `نص` — **not a general runtime type**; only string literals used with `اطبع`

## 5. Declarations, Mutability, Scopes

### 5.1 Declarations

Variables MUST be declared before use. Implicit declaration on assignment is removed.

- Immutable binding:

```
دع الاسم: النوع = تعبير
```

- Mutable binding:

```
متغير الاسم: النوع = تعبير
```

### 5.2 Assignment

Assignment is only allowed to mutable bindings:

```
الاسم = تعبير
```

Assigning to an immutable binding MUST be a compile-time error.

### 5.3 Scopes

- Function bodies and block bodies introduce a new lexical scope.
- Names resolve to the nearest enclosing declaration.

### 5.4 Shadowing (minimal compromise)

- Shadowing is allowed **only across scopes**.
  - Declaring `دع س: عدد٣٢ = ...` inside a nested block is allowed even if `س` exists in an outer scope.
- Redeclaring the same name within the **same scope** is a compile-time error.

## 6. Statements

### 6.1 Print

```
اطبع <expr>
اطبع "<string literal>"
```

- If printing an expression, the expression type MUST be `عدد٣٢` or `منطقي`.
- When printing `منطقي`, the implementation SHOULD print `صح` for true and `خطأ` for false (presentation only; runtime representation remains `i32`).

### 6.2 If / Elif / Else

```
اذا <cond>:
    <statements>
وإلا اذا <cond>:
    <statements>
وإلا:
    <statements>
```

- `<cond>` MUST be `منطقي`.

### 6.3 While

```
بينما <cond>:
    <statements>
```

- `<cond>` MUST be `منطقي`.

### 6.4 Break / Continue

- `اكسر` exits the nearest loop.
- `تابع` continues the nearest loop.

Using either outside a loop MUST be a compile-time error.

### 6.5 Return

```
ارجع <expr>
```

- `<expr>` type MUST match the function return type.

### 6.6 Assert (test-friendly)

```
تأكد <cond>
```

- `<cond>` MUST be `منطقي`.
- If `<cond>` is false, execution MUST trap.

## 7. Functions

### 7.1 Definition

Python-style definition:

```
دالة الاسم(ا: عدد٣٢, ب: عدد٣٢) -> عدد٣٢:
    <statements>
```

Rules:
- Parameter names MUST be unique.
- Function names MUST be unique at top level.
- Nested function definitions are not supported.

### 7.2 Calls

```
الاسم(<args...>)
```

- Argument count MUST match.
- Argument types MUST match parameter types.

## 8. Expressions

### 8.1 Literals

- Integer literals (ASCII digits `0-9` and Arabic-Indic `٠١٢٣٤٥٦٧٨٩`)
- `صح` and `خطأ`
- String literals `"..."` (print-only)

### 8.2 Operators

Arithmetic (only `عدد٣٢` operands):
- `+ - * /`

Comparisons (only `عدد٣٢` operands, result is `منطقي`):
- `== != < > <= >=`

Boolean operators (only `منطقي` operands, result is `منطقي`):
- `و` (and)
- `أو` / `او` (or)
- `ليس` (not)

## 9. Numeric Semantics

- Arithmetic uses Wasm `i32` behavior (wrap-around).
- Division by zero traps (Wasm semantics).

## 10. Wasm Mapping (WAT-compatible)

- `عدد٣٢` and `منطقي` compile to Wasm `i32`.
- Each Rimal function compiles to a Wasm function with `(param i32 ...)` and optional `(result i32)`.
- Control flow uses structured Wasm constructs: `if`, `block`, `loop`, `br`, `br_if`.
- Printing uses host imports:
  - `host.print_i32(i32)`
  - `host.print_str(i32 ptr, i32 len)`

## 11. Diagnostics (required)

Compiler errors MUST include:
- filename, line, column
- the source line
- a caret pointing to the column

Type errors SHOULD explain expected vs actual type.

## 12. Test Requirements (v0.3)

At minimum, tests must cover:
- declarations + assignment rules (`دع` vs `متغير`)
- scope + shadowing across blocks
- boolean-only conditions
- function signatures + argument checks
- return type checks

