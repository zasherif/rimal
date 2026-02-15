from __future__ import annotations

from dataclasses import dataclass

import wasmtime

from . import ast
from .token import RimalError


class CompileError(RimalError):
    pass


def _wat_escape_bytes(b: bytes) -> str:
    return "".join(f"\\{byte:02x}" for byte in b)


@dataclass
class _StringData:
    offset: int
    data: bytes


@dataclass
class _LoopLabels:
    exit_label: str
    loop_label: str


class _Allocator:
    """
    Deterministic local-slot allocator with lexical scopes.

    - Params are mapped to $pN in base scope.
    - VarDecl allocates $vN and is recorded for local declarations.
    - Shadowing is represented by scope maps.
    """

    def __init__(self, param_names: list[str]) -> None:
        self.next_local_id = 0
        self.local_slots: list[str] = []
        self.scopes: list[dict[str, str]] = [{}]
        for i, p in enumerate(param_names):
            self.scopes[0][p] = f"$p{i}"

    def enter(self) -> None:
        self.scopes.append({})

    def exit(self) -> None:
        self.scopes.pop()

    def declare(self, name: str) -> str:
        slot = f"$v{self.next_local_id}"
        self.next_local_id += 1
        self.scopes[-1][name] = slot
        self.local_slots.append(slot)
        return slot

    def resolve(self, name: str) -> str:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        raise CompileError(f"Internal error: unresolved name in codegen: {name}")


class WasmCompiler:
    """
    Minimal WAT generator for Rimal v0.3 (typed surface, lowered to i32).

    - One exported function: (func (export "run") ...)
    - User-defined functions: (func $fN (param ...) (result i32) ...)
    - Vars compile to i32 locals; shadowing is compiled via distinct locals.
    - Strings are data segments; only string literals may be printed.
    """

    def __init__(self) -> None:
        self._strings: dict[str, _StringData] = {}
        self._next_string_offset = 0
        self._func_ids: dict[str, str] = {}

    def compile(self, program: ast.Program, *, print_types: dict[int, str] | None = None) -> tuple[str, bytes]:
        funcs: list[ast.FunctionDef] = []
        main: list[ast.Stmt] = []
        for s in program.statements:
            if isinstance(s, ast.FunctionDef):
                funcs.append(s)
            else:
                main.append(s)

        self._func_ids = {}
        for idx, f in enumerate(funcs):
            if f.name in self._func_ids:
                raise CompileError(f"Duplicate function name: {f.name}")
            self._func_ids[f.name] = f"$f{idx}"

        # Always include boolean string literals for bool printing.
        self._intern_string("صح")
        self._intern_string("خطأ")

        self._collect_strings(funcs, main)
        wat = self._emit_module(funcs, main, print_types=print_types or {})
        return wat, wasmtime.wat2wasm(wat)

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
            if isinstance(s, ast.Assert):
                walk_expr(s.expr)
                return
            if isinstance(s, (ast.VarDecl, ast.Assign, ast.Return)):
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

    def _emit_module(self, funcs: list[ast.FunctionDef], main: list[ast.Stmt], *, print_types: dict[int, str]) -> str:
        lines: list[str] = []
        emit = lines.append

        emit("(module")
        emit('  (import "host" "print_i32" (func $print_i32 (param i32)))')
        emit('  (import "host" "print_str" (func $print_str (param i32 i32)))')
        emit("  (memory $mem 1)")
        emit('  (export "memory" (memory $mem))')

        for _s, entry in self._strings.items():
            emit(f'  (data (i32.const {entry.offset}) "{_wat_escape_bytes(entry.data)}")')

        # Functions
        for f in funcs:
            fid = self._func_ids[f.name]
            param_names = [p.name for p in f.params]

            alloc1 = _Allocator(param_names)
            self._collect_locals(alloc1, f.body)
            emit(
                f"  (func {fid}"
                + "".join(f" (param $p{i} i32)" for i in range(len(param_names)))
                + " (result i32)"
            )
            for slot in alloc1.local_slots:
                emit(f"    (local {slot} i32)")

            alloc2 = _Allocator(param_names)
            body: list[str] = []
            self._emit_stmts(
                alloc2,
                f.body,
                body,
                indent="    ",
                loop_stack=[],
                loop_id=[0],
                print_types=print_types,
            )
            body.append("    i32.const 0")
            body.append("    return")
            lines.extend(body)
            emit("  )")

        # run
        alloc1 = _Allocator([])
        self._collect_locals(alloc1, main)
        emit('  (func (export "run")')
        for slot in alloc1.local_slots:
            emit(f"    (local {slot} i32)")
        alloc2 = _Allocator([])
        run_body: list[str] = []
        self._emit_stmts(
            alloc2,
            main,
            run_body,
            indent="    ",
            loop_stack=[],
            loop_id=[0],
            print_types=print_types,
        )
        lines.extend(run_body)
        emit("  )")

        emit(")")
        return "\n".join(lines) + "\n"

    def _collect_locals(self, alloc: _Allocator, stmts: list[ast.Stmt]) -> None:
        alloc.enter()
        try:
            for s in stmts:
                if isinstance(s, ast.VarDecl):
                    alloc.declare(s.name)
                elif isinstance(s, ast.If):
                    self._collect_locals(alloc, s.then_body)
                    if s.else_body:
                        self._collect_locals(alloc, s.else_body)
                elif isinstance(s, ast.While):
                    self._collect_locals(alloc, s.body)
                elif isinstance(s, ast.FunctionDef):
                    raise CompileError("Nested function definitions are not supported")
                else:
                    # other statements do not allocate locals
                    pass
        finally:
            alloc.exit()

    def _emit_stmts(
        self,
        alloc: _Allocator,
        stmts: list[ast.Stmt],
        out: list[str],
        *,
        indent: str,
        loop_stack: list[_LoopLabels],
        loop_id: list[int],
        print_types: dict[int, str],
    ) -> None:
        alloc.enter()
        try:
            for s in stmts:
                if isinstance(s, ast.FunctionDef):
                    raise CompileError("Function definitions are only allowed at top level")
                if isinstance(s, ast.VarDecl):
                    slot = alloc.declare(s.name)
                    self._emit_expr(alloc, s.expr, out, indent)
                    out.append(f"{indent}local.set {slot}")
                elif isinstance(s, ast.Assign):
                    slot = alloc.resolve(s.name)
                    self._emit_expr(alloc, s.expr, out, indent)
                    out.append(f"{indent}local.set {slot}")
                elif isinstance(s, ast.Print):
                    if isinstance(s.expr, ast.StrLit):
                        entry = self._intern_string(s.expr.value)
                        out.append(f"{indent}i32.const {entry.offset}")
                        out.append(f"{indent}i32.const {len(entry.data)}")
                        out.append(f"{indent}call $print_str")
                    else:
                        # Type-directed printing: bool prints صح/خطأ, i32 prints number.
                        if print_types.get(id(s)) == "bool":
                            true_s = self._strings["صح"]
                            false_s = self._strings["خطأ"]
                            self._emit_expr(alloc, s.expr, out, indent)
                            out.append(f"{indent}(if")
                            out.append(f"{indent}  (then")
                            out.append(f"{indent}    i32.const {true_s.offset}")
                            out.append(f"{indent}    i32.const {len(true_s.data)}")
                            out.append(f"{indent}    call $print_str")
                            out.append(f"{indent}  )")
                            out.append(f"{indent}  (else")
                            out.append(f"{indent}    i32.const {false_s.offset}")
                            out.append(f"{indent}    i32.const {len(false_s.data)}")
                            out.append(f"{indent}    call $print_str")
                            out.append(f"{indent}  )")
                            out.append(f"{indent})")
                        else:
                            self._emit_expr(alloc, s.expr, out, indent)
                            out.append(f"{indent}call $print_i32")
                elif isinstance(s, ast.Assert):
                    # Trap if condition is false.
                    self._emit_expr(alloc, s.expr, out, indent)
                    out.append(f"{indent}i32.eqz")
                    out.append(f"{indent}(if (then unreachable))")
                elif isinstance(s, ast.Return):
                    self._emit_expr(alloc, s.expr, out, indent)
                    out.append(f"{indent}return")
                elif isinstance(s, ast.If):
                    self._emit_expr(alloc, s.cond, out, indent)
                    out.append(f"{indent}(if")
                    out.append(f"{indent}  (then")
                    self._emit_stmts(
                        alloc,
                        s.then_body,
                        out,
                        indent=indent + "    ",
                        loop_stack=loop_stack,
                        loop_id=loop_id,
                        print_types=print_types,
                    )
                    out.append(f"{indent}  )")
                    if s.else_body is not None:
                        out.append(f"{indent}  (else")
                        self._emit_stmts(
                            alloc,
                            s.else_body,
                            out,
                            indent=indent + "    ",
                            loop_stack=loop_stack,
                            loop_id=loop_id,
                            print_types=print_types,
                        )
                        out.append(f"{indent}  )")
                    out.append(f"{indent})")
                elif isinstance(s, ast.While):
                    exit_label = f"$while_exit{loop_id[0]}"
                    loop_label = f"$while_loop{loop_id[0]}"
                    loop_id[0] += 1
                    loop_stack.append(_LoopLabels(exit_label=exit_label, loop_label=loop_label))
                    out.append(f"{indent}(block {exit_label}")
                    out.append(f"{indent}  (loop {loop_label}")
                    self._emit_expr(alloc, s.cond, out, indent + "    ")
                    out.append(f"{indent}    i32.eqz")
                    out.append(f"{indent}    br_if {exit_label}")
                    self._emit_stmts(
                        alloc,
                        s.body,
                        out,
                        indent=indent + "    ",
                        loop_stack=loop_stack,
                        loop_id=loop_id,
                        print_types=print_types,
                    )
                    out.append(f"{indent}    br {loop_label}")
                    out.append(f"{indent}  )")
                    out.append(f"{indent})")
                    loop_stack.pop()
                elif isinstance(s, ast.Break):
                    if not loop_stack:
                        raise CompileError("اكسر is only valid inside a loop")
                    out.append(f"{indent}br {loop_stack[-1].exit_label}")
                elif isinstance(s, ast.Continue):
                    if not loop_stack:
                        raise CompileError("تابع is only valid inside a loop")
                    out.append(f"{indent}br {loop_stack[-1].loop_label}")
                else:
                    raise CompileError(f"Unknown statement: {type(s).__name__}")
        finally:
            alloc.exit()

    def _emit_expr(self, alloc: _Allocator, e: ast.Expr, out: list[str], indent: str) -> None:
        if isinstance(e, ast.IntLit):
            out.append(f"{indent}i32.const {int(e.value)}")
            return
        if isinstance(e, ast.BoolLit):
            out.append(f"{indent}i32.const {1 if e.value else 0}")
            return
        if isinstance(e, ast.Var):
            out.append(f"{indent}local.get {alloc.resolve(e.name)}")
            return
        if isinstance(e, ast.Unary):
            if e.op != "not":
                raise CompileError(f"Unknown unary operator: {e.op}")
            self._emit_expr(alloc, e.expr, out, indent)
            out.append(f"{indent}i32.eqz")
            return
        if isinstance(e, ast.Call):
            fid = self._func_ids.get(e.name)
            if fid is None:
                raise CompileError(f"Call to undefined function: {e.name}")
            for a in e.args:
                self._emit_expr(alloc, a, out, indent)
            out.append(f"{indent}call {fid}")
            return
        if isinstance(e, ast.Binary):
            op = e.op
            self._emit_expr(alloc, e.left, out, indent)
            self._emit_expr(alloc, e.right, out, indent)
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
                "and": "i32.and",
                "or": "i32.or",
            }
            ins = op_map.get(op)
            if ins is None:
                raise CompileError(f"Unknown operator: {op}")
            out.append(f"{indent}{ins}")
            return
        if isinstance(e, ast.StrLit):
            raise CompileError("String literals are only supported in `اطبع`")
        raise CompileError(f"Unknown expression: {type(e).__name__}")

