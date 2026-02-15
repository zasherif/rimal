from __future__ import annotations

from dataclasses import dataclass

import wasmtime

from . import ast
from .token import RimalError


class CompileError(RimalError):
    pass


def _wat_escape_bytes(b: bytes) -> str:
    # WAT string literal: use \xx for every byte (works for all UTF-8).
    return "".join(f"\\{byte:02x}" for byte in b)


@dataclass
class _StringData:
    offset: int
    data: bytes


class WasmCompiler:
    """
    Minimal WAT generator for Rimal v0.1.

    - One exported function: (func (export "run") ...)
    - All variables are i32 locals.
    - Strings are stored as data segments in linear memory.
    - Uses host imports:
        (import "host" "print_i32" (func $print_i32 (param i32)))
        (import "host" "print_str" (func $print_str (param i32 i32)))
    """

    def __init__(self) -> None:
        # Map source variable name -> safe WAT local identifier.
        # WAT identifiers are effectively ASCII; Arabic variable names must be lowered to $vN.
        self._locals: dict[str, str] = {}
        self._local_order: list[str] = []
        self._strings: dict[str, _StringData] = {}
        self._next_string_offset = 0
        self._next_local_id = 0

    def _get_or_create_local(self, name: str) -> str:
        local = self._locals.get(name)
        if local is not None:
            return local
        local = f"$v{self._next_local_id}"
        self._next_local_id += 1
        self._locals[name] = local
        self._local_order.append(name)
        return local

    def compile(self, program: ast.Program) -> tuple[str, bytes]:
        self._collect_locals(program)
        self._collect_strings(program)

        wat = self._emit_module(program)
        wasm = wasmtime.wat2wasm(wat)
        return wat, wasm

    def _collect_locals(self, program: ast.Program) -> None:
        # Locals are created on first assignment; using before assignment is an error.
        def walk_stmt(s: ast.Stmt) -> None:
            if isinstance(s, ast.Assign):
                self._get_or_create_local(s.name)
                walk_expr(s.expr)
            elif isinstance(s, ast.Print):
                walk_expr(s.expr)
            elif isinstance(s, ast.If):
                walk_expr(s.cond)
                for st in s.then_body:
                    walk_stmt(st)
                if s.else_body:
                    for st in s.else_body:
                        walk_stmt(st)
            elif isinstance(s, ast.While):
                walk_expr(s.cond)
                for st in s.body:
                    walk_stmt(st)
            else:
                raise CompileError(f"Unknown statement: {type(s).__name__}")

        def walk_expr(e: ast.Expr) -> None:
            if isinstance(e, (ast.IntLit, ast.BoolLit, ast.StrLit)):
                return
            if isinstance(e, ast.Var):
                return
            if isinstance(e, ast.Binary):
                walk_expr(e.left)
                walk_expr(e.right)
                return
            raise CompileError(f"Unknown expression: {type(e).__name__}")

        for s in program.statements:
            walk_stmt(s)

    def _collect_strings(self, program: ast.Program) -> None:
        def walk_stmt(s: ast.Stmt) -> None:
            if isinstance(s, ast.Print):
                if isinstance(s.expr, ast.StrLit):
                    self._intern_string(s.expr.value)
                else:
                    walk_expr(s.expr)
            elif isinstance(s, ast.Assign):
                walk_expr(s.expr)
            elif isinstance(s, ast.If):
                walk_expr(s.cond)
                for st in s.then_body:
                    walk_stmt(st)
                if s.else_body:
                    for st in s.else_body:
                        walk_stmt(st)
            elif isinstance(s, ast.While):
                walk_expr(s.cond)
                for st in s.body:
                    walk_stmt(st)
            else:
                raise CompileError(f"Unknown statement: {type(s).__name__}")

        def walk_expr(e: ast.Expr) -> None:
            if isinstance(e, ast.StrLit):
                # Strings are only supported in `اطبع`.
                return
            if isinstance(e, ast.Binary):
                walk_expr(e.left)
                walk_expr(e.right)
                return
            if isinstance(e, (ast.IntLit, ast.BoolLit, ast.Var)):
                return
            raise CompileError(f"Unknown expression: {type(e).__name__}")

        for s in program.statements:
            walk_stmt(s)

    def _intern_string(self, s: str) -> _StringData:
        existing = self._strings.get(s)
        if existing is not None:
            return existing
        data = s.encode("utf-8")
        entry = _StringData(offset=self._next_string_offset, data=data)
        # Simple bump allocator. Align to 1 byte (fine).
        self._next_string_offset += len(data)
        self._strings[s] = entry
        return entry

    def _emit_module(self, program: ast.Program) -> str:
        lines: list[str] = []
        emit = lines.append

        emit("(module")
        emit('  (import "host" "print_i32" (func $print_i32 (param i32)))')
        emit('  (import "host" "print_str" (func $print_str (param i32 i32)))')
        emit("  (memory $mem 1)")
        emit('  (export "memory" (memory $mem))')

        # Data segments for strings
        for s, entry in self._strings.items():
            escaped = _wat_escape_bytes(entry.data)
            emit(f'  (data (i32.const {entry.offset}) "{escaped}")')

        # Function header with locals
        emit('  (func (export "run")')
        for name in self._local_order:
            emit(f"    (local {self._locals[name]} i32)")

        # Body
        body_instrs: list[str] = []
        self._emit_stmts(program.statements, body_instrs, indent="    ")
        if body_instrs:
            lines.extend(body_instrs)

        emit("  )")
        emit(")")
        return "\n".join(lines) + "\n"

    def _emit_stmts(self, stmts: list[ast.Stmt], out: list[str], indent: str) -> None:
        for s in stmts:
            if isinstance(s, ast.Print):
                self._emit_print(s, out, indent)
            elif isinstance(s, ast.Assign):
                self._emit_assign(s, out, indent)
            elif isinstance(s, ast.If):
                self._emit_if(s, out, indent)
            elif isinstance(s, ast.While):
                self._emit_while(s, out, indent)
            else:
                raise CompileError(f"Unknown statement: {type(s).__name__}")

    def _emit_print(self, s: ast.Print, out: list[str], indent: str) -> None:
        if isinstance(s.expr, ast.StrLit):
            entry = self._intern_string(s.expr.value)
            out.append(f"{indent}i32.const {entry.offset}")
            out.append(f"{indent}i32.const {len(entry.data)}")
            out.append(f"{indent}call $print_str")
            return

        if self._expr_type(s.expr) == "i32":
            self._emit_expr(s.expr, out, indent)
            out.append(f"{indent}call $print_i32")
            return

        raise CompileError("Only integers/booleans or string literals can be printed")

    def _emit_assign(self, s: ast.Assign, out: list[str], indent: str) -> None:
        if self._expr_type(s.expr) != "i32":
            raise CompileError("Only i32 values can be assigned to variables")
        self._emit_expr(s.expr, out, indent)
        local = self._get_or_create_local(s.name)
        out.append(f"{indent}local.set {local}")

    def _emit_if(self, s: ast.If, out: list[str], indent: str) -> None:
        if self._expr_type(s.cond) != "i32":
            raise CompileError("If condition must be i32/boolean")
        self._emit_expr(s.cond, out, indent)
        out.append(f"{indent}(if")
        out.append(f"{indent}  (then")
        self._emit_stmts(s.then_body, out, indent + "    ")
        out.append(f"{indent}  )")
        if s.else_body is not None:
            out.append(f"{indent}  (else")
            self._emit_stmts(s.else_body, out, indent + "    ")
            out.append(f"{indent}  )")
        out.append(f"{indent})")

    def _emit_while(self, s: ast.While, out: list[str], indent: str) -> None:
        if self._expr_type(s.cond) != "i32":
            raise CompileError("While condition must be i32/boolean")
        out.append(f"{indent}(block $while_exit")
        out.append(f"{indent}  (loop $while_loop")
        self._emit_expr(s.cond, out, indent + "    ")
        out.append(f"{indent}    i32.eqz")
        out.append(f"{indent}    br_if $while_exit")
        self._emit_stmts(s.body, out, indent + "    ")
        out.append(f"{indent}    br $while_loop")
        out.append(f"{indent}  )")
        out.append(f"{indent})")

    def _expr_type(self, e: ast.Expr) -> str:
        if isinstance(e, (ast.IntLit, ast.BoolLit)):
            return "i32"
        if isinstance(e, ast.StrLit):
            return "str"
        if isinstance(e, ast.Var):
            # Variables are i32 locals, but ensure declared (assigned) before use:
            if e.name not in self._locals:
                raise CompileError(f"Use of undefined variable: {e.name}")
            return "i32"
        if isinstance(e, ast.Binary):
            lt = self._expr_type(e.left)
            rt = self._expr_type(e.right)
            if lt != "i32" or rt != "i32":
                raise CompileError("Binary operators only support i32 operands")
            return "i32"
        raise CompileError(f"Unknown expression: {type(e).__name__}")

    def _emit_expr(self, e: ast.Expr, out: list[str], indent: str) -> None:
        if isinstance(e, ast.IntLit):
            out.append(f"{indent}i32.const {int(e.value)}")
            return
        if isinstance(e, ast.BoolLit):
            out.append(f"{indent}i32.const {1 if e.value else 0}")
            return
        if isinstance(e, ast.Var):
            if e.name not in self._locals:
                raise CompileError(f"Use of undefined variable: {e.name}")
            out.append(f"{indent}local.get {self._locals[e.name]}")
            return
        if isinstance(e, ast.Binary):
            self._emit_expr(e.left, out, indent)
            self._emit_expr(e.right, out, indent)
            op = e.op
            op_map = {
                "+": "i32.add",
                "-": "i32.sub",
                "*": "i32.mul",
                "/": "i32.div_s",
                "==": "i32.eq",
                "!=": "i32.ne",
                "<": "i32.lt_s",
                ">": "i32.gt_s",
                "<=": "i32.le_s",
                ">=": "i32.ge_s",
            }
            ins = op_map.get(op)
            if ins is None:
                raise CompileError(f"Unknown operator: {op}")
            out.append(f"{indent}{ins}")
            return

        if isinstance(e, ast.StrLit):
            raise CompileError("String literals are only supported in `اطبع`")

        raise CompileError(f"Unknown expression: {type(e).__name__}")

