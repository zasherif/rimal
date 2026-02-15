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


@dataclass
class _LoopLabels:
    exit_label: str
    loop_label: str


@dataclass
class _FuncCtx:
    name: str
    wat_name: str
    params: list[str]
    locals_map: dict[str, str]
    local_order: list[str]
    next_local_id: int
    loop_stack: list[_LoopLabels]
    loop_id: int


class WasmCompiler:
    """
    Minimal WAT generator for Rimal v0.2.

    - One exported function: (func (export "run") ...)
    - User-defined functions: (func $fN (param ...) (result i32) ...)
    - All variables are i32 locals (per function scope).
    - Strings are stored as data segments in linear memory.
    - Uses host imports:
        (import "host" "print_i32" (func $print_i32 (param i32)))
        (import "host" "print_str" (func $print_str (param i32 i32)))
    """

    def __init__(self) -> None:
        self._strings: dict[str, _StringData] = {}
        self._next_string_offset = 0
        self._func_ids: dict[str, str] = {}

    def compile(self, program: ast.Program) -> tuple[str, bytes]:
        func_defs: list[ast.FunctionDef] = []
        main_stmts: list[ast.Stmt] = []
        for s in program.statements:
            if isinstance(s, ast.FunctionDef):
                func_defs.append(s)
            else:
                main_stmts.append(s)

        self._func_ids = {}
        for idx, f in enumerate(func_defs):
            if f.name in self._func_ids:
                raise CompileError(f"Duplicate function name: {f.name}")
            self._func_ids[f.name] = f"$f{idx}"

        self._collect_strings(func_defs, main_stmts)

        wat = self._emit_module(func_defs, main_stmts)
        wasm = wasmtime.wat2wasm(wat)
        return wat, wasm

    def _intern_string(self, s: str) -> _StringData:
        existing = self._strings.get(s)
        if existing is not None:
            return existing
        data = s.encode("utf-8")
        entry = _StringData(offset=self._next_string_offset, data=data)
        self._next_string_offset += len(data)
        self._strings[s] = entry
        return entry

    def _collect_strings(self, funcs: list[ast.FunctionDef], main: list[ast.Stmt]) -> None:
        def walk_stmt(s: ast.Stmt) -> None:
            if isinstance(s, ast.Print):
                if isinstance(s.expr, ast.StrLit):
                    self._intern_string(s.expr.value)
                else:
                    walk_expr(s.expr)
                return
            if isinstance(s, ast.Assign):
                walk_expr(s.expr)
                return
            if isinstance(s, ast.Return):
                walk_expr(s.expr)
                return
            if isinstance(s, ast.If):
                walk_expr(s.cond)
                for st in s.then_body:
                    walk_stmt(st)
                if s.else_body:
                    for st in s.else_body:
                        walk_stmt(st)
                return
            if isinstance(s, ast.While):
                walk_expr(s.cond)
                for st in s.body:
                    walk_stmt(st)
                return
            if isinstance(s, (ast.Break, ast.Continue)):
                return
            if isinstance(s, ast.FunctionDef):
                for st in s.body:
                    walk_stmt(st)
                return
            raise CompileError(f"Unknown statement: {type(s).__name__}")

        def walk_expr(e: ast.Expr) -> None:
            if isinstance(e, ast.StrLit):
                return
            if isinstance(e, ast.Binary):
                walk_expr(e.left)
                walk_expr(e.right)
                return
            if isinstance(e, ast.Unary):
                walk_expr(e.expr)
                return
            if isinstance(e, ast.Call):
                for a in e.args:
                    walk_expr(a)
                return
            if isinstance(e, (ast.IntLit, ast.BoolLit, ast.Var)):
                return
            raise CompileError(f"Unknown expression: {type(e).__name__}")

        for f in funcs:
            walk_stmt(f)
        for s in main:
            walk_stmt(s)

    def _new_func_ctx(self, name: str, wat_name: str, params: list[str]) -> _FuncCtx:
        locals_map: dict[str, str] = {}
        local_order: list[str] = []
        for idx, p in enumerate(params):
            locals_map[p] = f"$p{idx}"
        return _FuncCtx(
            name=name,
            wat_name=wat_name,
            params=params,
            locals_map=locals_map,
            local_order=local_order,
            next_local_id=0,
            loop_stack=[],
            loop_id=0,
        )

    def _get_or_create_local(self, ctx: _FuncCtx, name: str) -> str:
        local = ctx.locals_map.get(name)
        if local is not None:
            return local
        local = f"$v{ctx.next_local_id}"
        ctx.next_local_id += 1
        ctx.locals_map[name] = local
        ctx.local_order.append(name)
        return local

    def _emit_module(self, funcs: list[ast.FunctionDef], main: list[ast.Stmt]) -> str:
        lines: list[str] = []
        emit = lines.append

        emit("(module")
        emit('  (import "host" "print_i32" (func $print_i32 (param i32)))')
        emit('  (import "host" "print_str" (func $print_str (param i32 i32)))')
        emit("  (memory $mem 1)")
        emit('  (export "memory" (memory $mem))')

        for s, entry in self._strings.items():
            escaped = _wat_escape_bytes(entry.data)
            emit(f'  (data (i32.const {entry.offset}) "{escaped}")')

        # User-defined functions
        for f in funcs:
            fid = self._func_ids[f.name]
            ctx = self._new_func_ctx(f.name, fid, f.params)
            self._collect_locals_in_body(ctx, f.body)
            emit(f"  (func {fid}" + "".join(f" (param $p{i} i32)" for i in range(len(f.params))) + " (result i32)")
            for name in ctx.local_order:
                emit(f"    (local {ctx.locals_map[name]} i32)")
            body: list[str] = []
            self._emit_stmts(ctx, f.body, body, indent="    ")
            # Default return 0 if no explicit return executed.
            body.append("    i32.const 0")
            body.append("    return")
            lines.extend(body)
            emit("  )")

        # Exported run
        run_ctx = self._new_func_ctx("run", "$run", [])
        self._collect_locals_in_body(run_ctx, main)
        emit('  (func (export "run")')
        for name in run_ctx.local_order:
            emit(f"    (local {run_ctx.locals_map[name]} i32)")
        run_body: list[str] = []
        self._emit_stmts(run_ctx, main, run_body, indent="    ")
        lines.extend(run_body)
        emit("  )")

        emit(")")
        return "\n".join(lines) + "\n"

    def _collect_locals_in_body(self, ctx: _FuncCtx, stmts: list[ast.Stmt]) -> None:
        def walk_stmt(s: ast.Stmt) -> None:
            if isinstance(s, ast.Assign):
                self._get_or_create_local(ctx, s.name)
                walk_expr(s.expr)
                return
            if isinstance(s, ast.Print):
                walk_expr(s.expr)
                return
            if isinstance(s, ast.Return):
                walk_expr(s.expr)
                return
            if isinstance(s, ast.If):
                walk_expr(s.cond)
                for st in s.then_body:
                    walk_stmt(st)
                if s.else_body:
                    for st in s.else_body:
                        walk_stmt(st)
                return
            if isinstance(s, ast.While):
                walk_expr(s.cond)
                for st in s.body:
                    walk_stmt(st)
                return
            if isinstance(s, (ast.Break, ast.Continue)):
                return
            if isinstance(s, ast.FunctionDef):
                raise CompileError("Nested function definitions are not supported")
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
            if isinstance(e, ast.Unary):
                walk_expr(e.expr)
                return
            if isinstance(e, ast.Call):
                for a in e.args:
                    walk_expr(a)
                return
            raise CompileError(f"Unknown expression: {type(e).__name__}")

        for s in stmts:
            walk_stmt(s)

    def _emit_stmts(self, ctx: _FuncCtx, stmts: list[ast.Stmt], out: list[str], indent: str) -> None:
        for s in stmts:
            if isinstance(s, ast.FunctionDef):
                raise CompileError("Function definitions are only allowed at top level")
            if isinstance(s, ast.Print):
                self._emit_print(ctx, s, out, indent)
            elif isinstance(s, ast.Assign):
                self._emit_assign(ctx, s, out, indent)
            elif isinstance(s, ast.Return):
                self._emit_expr(ctx, s.expr, out, indent)
                out.append(f"{indent}return")
            elif isinstance(s, ast.If):
                self._emit_if(ctx, s, out, indent)
            elif isinstance(s, ast.While):
                self._emit_while(ctx, s, out, indent)
            elif isinstance(s, ast.Break):
                if not ctx.loop_stack:
                    raise CompileError("اكسر is only valid inside a loop")
                out.append(f"{indent}br {ctx.loop_stack[-1].exit_label}")
            elif isinstance(s, ast.Continue):
                if not ctx.loop_stack:
                    raise CompileError("تابع is only valid inside a loop")
                out.append(f"{indent}br {ctx.loop_stack[-1].loop_label}")
            else:
                raise CompileError(f"Unknown statement: {type(s).__name__}")

    def _emit_print(self, ctx: _FuncCtx, s: ast.Print, out: list[str], indent: str) -> None:
        if isinstance(s.expr, ast.StrLit):
            entry = self._intern_string(s.expr.value)
            out.append(f"{indent}i32.const {entry.offset}")
            out.append(f"{indent}i32.const {len(entry.data)}")
            out.append(f"{indent}call $print_str")
            return
        self._emit_expr(ctx, s.expr, out, indent)
        out.append(f"{indent}call $print_i32")

    def _emit_assign(self, ctx: _FuncCtx, s: ast.Assign, out: list[str], indent: str) -> None:
        self._emit_expr(ctx, s.expr, out, indent)
        local = self._get_or_create_local(ctx, s.name)
        out.append(f"{indent}local.set {local}")

    def _emit_if(self, ctx: _FuncCtx, s: ast.If, out: list[str], indent: str) -> None:
        self._emit_truthy(ctx, s.cond, out, indent)
        out.append(f"{indent}(if")
        out.append(f"{indent}  (then")
        self._emit_stmts(ctx, s.then_body, out, indent + "    ")
        out.append(f"{indent}  )")
        if s.else_body is not None:
            out.append(f"{indent}  (else")
            self._emit_stmts(ctx, s.else_body, out, indent + "    ")
            out.append(f"{indent}  )")
        out.append(f"{indent})")

    def _emit_while(self, ctx: _FuncCtx, s: ast.While, out: list[str], indent: str) -> None:
        exit_label = f"$while_exit{ctx.loop_id}"
        loop_label = f"$while_loop{ctx.loop_id}"
        ctx.loop_id += 1
        ctx.loop_stack.append(_LoopLabels(exit_label=exit_label, loop_label=loop_label))
        out.append(f"{indent}(block {exit_label}")
        out.append(f"{indent}  (loop {loop_label}")
        self._emit_truthy(ctx, s.cond, out, indent + "    ")
        out.append(f"{indent}    i32.eqz")
        out.append(f"{indent}    br_if {exit_label}")
        self._emit_stmts(ctx, s.body, out, indent + "    ")
        out.append(f"{indent}    br {loop_label}")
        out.append(f"{indent}  )")
        out.append(f"{indent})")
        ctx.loop_stack.pop()

    def _emit_truthy(self, ctx: _FuncCtx, e: ast.Expr, out: list[str], indent: str) -> None:
        # Normalize to 0/1.
        self._emit_expr(ctx, e, out, indent)
        out.append(f"{indent}i32.const 0")
        out.append(f"{indent}i32.ne")

    def _emit_expr(self, ctx: _FuncCtx, e: ast.Expr, out: list[str], indent: str) -> None:
        if isinstance(e, ast.IntLit):
            out.append(f"{indent}i32.const {int(e.value)}")
            return
        if isinstance(e, ast.BoolLit):
            out.append(f"{indent}i32.const {1 if e.value else 0}")
            return
        if isinstance(e, ast.Var):
            local = ctx.locals_map.get(e.name)
            if local is None:
                raise CompileError(f"Use of undefined variable: {e.name}")
            out.append(f"{indent}local.get {local}")
            return
        if isinstance(e, ast.Unary):
            if e.op != "not":
                raise CompileError(f"Unknown unary operator: {e.op}")
            self._emit_truthy(ctx, e.expr, out, indent)
            out.append(f"{indent}i32.eqz")
            return
        if isinstance(e, ast.Call):
            fid = self._func_ids.get(e.name)
            if fid is None:
                raise CompileError(f"Call to undefined function: {e.name}")
            for a in e.args:
                self._emit_expr(ctx, a, out, indent)
            out.append(f"{indent}call {fid}")
            return
        if isinstance(e, ast.Binary):
            op = e.op
            if op in ("and", "or"):
                self._emit_truthy(ctx, e.left, out, indent)
                self._emit_truthy(ctx, e.right, out, indent)
                out.append(f"{indent}{'i32.and' if op == 'and' else 'i32.or'}")
                return
            self._emit_expr(ctx, e.left, out, indent)
            self._emit_expr(ctx, e.right, out, indent)
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

