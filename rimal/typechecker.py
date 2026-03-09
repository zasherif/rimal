from __future__ import annotations

from dataclasses import dataclass

from . import ast
from .token import SemanticError


TypeName = str  # "i32" | "bool" | "str"


@dataclass(frozen=True)
class Binding:
    type_name: TypeName
    mutable: bool


@dataclass(frozen=True)
class FuncSig:
    params: list[TypeName]
    ret: TypeName


class TypeChecker:
    def __init__(self, program: ast.Program, filename: str, source: str) -> None:
        self.program = program
        self.filename = filename
        self.lines = source.splitlines()
        self.funcs: dict[str, FuncSig] = {}
        self.expr_types: dict[int, TypeName] = {}
        self.print_types: dict[int, TypeName] = {}

    def _line_text(self, line: int) -> str | None:
        if line <= 0 or line > len(self.lines):
            return None
        return self.lines[line - 1]

    def error(self, msg: str, line: int, col: int) -> None:
        raise SemanticError(msg, self.filename, line, col, line_text=self._line_text(line))

    def check(self) -> None:
        # Collect function signatures
        for s in self.program.statements:
            if isinstance(s, ast.FunctionDef):
                if s.name in self.funcs:
                    self.error(f"Duplicate function name: {s.name}", s.line, s.col)
                self.funcs[s.name] = FuncSig([p.type_name for p in s.params], s.return_type)

        # Typecheck top-level statements (in an implicit scope)
        self._check_block(self.program.statements, scopes=[{}], in_loop=0, current_func=None)

        # Typecheck each function body with params in scope
        for s in self.program.statements:
            if isinstance(s, ast.FunctionDef):
                scope: dict[str, Binding] = {}
                for p in s.params:
                    if p.name in scope:
                        self.error(f"Duplicate parameter name: {p.name}", p.line, p.col)
                    scope[p.name] = Binding(p.type_name, mutable=False)
                self._check_block(s.body, scopes=[scope], in_loop=0, current_func=self.funcs[s.name])

    def _declare(self, name: str, binding: Binding, line: int, col: int, scopes: list[dict[str, Binding]]) -> None:
        cur = scopes[-1]
        if name in cur:
            self.error(f"Redeclaration in same scope: {name}", line, col)
        cur[name] = binding

    def _lookup(self, name: str, line: int, col: int, scopes: list[dict[str, Binding]]) -> Binding:
        for scope in reversed(scopes):
            if name in scope:
                return scope[name]
        self.error(f"Use of undeclared variable: {name}", line, col)
        raise AssertionError("unreachable")

    def _check_block(
        self,
        stmts: list[ast.Stmt],
        *,
        scopes: list[dict[str, Binding]],
        in_loop: int,
        current_func: FuncSig | None,
    ) -> None:
        # New lexical scope for the block
        scopes.append({})
        try:
            for s in stmts:
                self._check_stmt(s, scopes=scopes, in_loop=in_loop, current_func=current_func)
        finally:
            scopes.pop()

    def _check_stmt(
        self,
        s: ast.Stmt,
        *,
        scopes: list[dict[str, Binding]],
        in_loop: int,
        current_func: FuncSig | None,
    ) -> None:
        if isinstance(s, ast.FunctionDef):
            # Functions are checked separately in check()
            return

        if isinstance(s, ast.VarDecl):
            t = self._check_expr(s.expr, scopes=scopes)
            if t != s.type_name:
                self.error(f"Type mismatch in declaration '{s.name}': expected {s.type_name}, got {t}", s.line, s.col)
            self._declare(s.name, Binding(s.type_name, mutable=s.mutable), s.line, s.col, scopes)
            return

        if isinstance(s, ast.Assign):
            b = self._lookup(s.name, s.line, s.col, scopes)
            if not b.mutable:
                self.error(f"Cannot assign to immutable binding: {s.name}", s.line, s.col)
            t = self._check_expr(s.expr, scopes=scopes)
            if t != b.type_name:
                self.error(f"Type mismatch in assignment '{s.name}': expected {b.type_name}, got {t}", s.line, s.col)
            return

        if isinstance(s, ast.Print):
            t = self._check_expr(s.expr, scopes=scopes)
            self.print_types[id(s)] = t
            if t not in ("i32", "bool", "str"):
                self.error(f"Unsupported print type: {t}", s.line, s.col)
            if t == "str" and not isinstance(s.expr, ast.StrLit):
                self.error("Only string literals can be printed", s.line, s.col)
            return

        if isinstance(s, ast.Assert):
            t = self._check_expr(s.expr, scopes=scopes)
            if t != "bool":
                self.error("تأكد expects منطقي", s.line, s.col)
            return

        if isinstance(s, ast.Return):
            if current_func is None:
                self.error("ارجع is only valid inside a function", s.line, s.col)
            t = self._check_expr(s.expr, scopes=scopes)
            assert current_func is not None
            if t != current_func.ret:
                self.error(f"Return type mismatch: expected {current_func.ret}, got {t}", s.line, s.col)
            return

        if isinstance(s, ast.If):
            cond_t = self._check_expr(s.cond, scopes=scopes)
            if cond_t != "bool":
                self.error("If condition must be منطقي", s.line, s.col)
            self._check_block(s.then_body, scopes=scopes, in_loop=in_loop, current_func=current_func)
            if s.else_body is not None:
                self._check_block(s.else_body, scopes=scopes, in_loop=in_loop, current_func=current_func)
            return

        if isinstance(s, ast.While):
            cond_t = self._check_expr(s.cond, scopes=scopes)
            if cond_t != "bool":
                self.error("While condition must be منطقي", s.line, s.col)
            self._check_block(s.body, scopes=scopes, in_loop=in_loop + 1, current_func=current_func)
            return

        if isinstance(s, ast.Break):
            if in_loop <= 0:
                self.error("اكسر is only valid inside a loop", s.line, s.col)
            return

        if isinstance(s, ast.Continue):
            if in_loop <= 0:
                self.error("تابع is only valid inside a loop", s.line, s.col)
            return

        raise SemanticError(f"Unknown statement: {type(s).__name__}", self.filename, 1, 1)

    def _check_expr(self, e: ast.Expr, *, scopes: list[dict[str, Binding]]) -> TypeName:
        if isinstance(e, ast.IntLit):
            self.expr_types[id(e)] = "i32"
            return "i32"
        if isinstance(e, ast.BoolLit):
            self.expr_types[id(e)] = "bool"
            return "bool"
        if isinstance(e, ast.StrLit):
            self.expr_types[id(e)] = "str"
            return "str"
        if isinstance(e, ast.Var):
            t = self._lookup(e.name, e.line, e.col, scopes).type_name
            self.expr_types[id(e)] = t
            return t
        if isinstance(e, ast.Unary):
            if e.op != "not":
                self.error(f"Unknown unary operator: {e.op}", e.line, e.col)
            t = self._check_expr(e.expr, scopes=scopes)
            if t != "bool":
                self.error("ليس expects منطقي", e.line, e.col)
            self.expr_types[id(e)] = "bool"
            return "bool"
        if isinstance(e, ast.Call):
            sig = self.funcs.get(e.name)
            if sig is None:
                self.error(f"Call to undefined function: {e.name}", e.line, e.col)
            assert sig is not None
            if len(e.args) != len(sig.params):
                self.error(
                    f"Wrong number of arguments to {e.name}: expected {len(sig.params)}, got {len(e.args)}",
                    e.line,
                    e.col,
                )
            for i, (arg, expected) in enumerate(zip(e.args, sig.params, strict=False)):
                t = self._check_expr(arg, scopes=scopes)
                if t != expected:
                    self.error(f"Argument {i+1} type mismatch: expected {expected}, got {t}", arg.line, arg.col)
            self.expr_types[id(e)] = sig.ret
            return sig.ret
        if isinstance(e, ast.Binary):
            op = e.op
            if op in ("and", "or"):
                lt = self._check_expr(e.left, scopes=scopes)
                rt = self._check_expr(e.right, scopes=scopes)
                if lt != "bool" or rt != "bool":
                    self.error("Boolean operators expect منطقي operands", e.line, e.col)
                self.expr_types[id(e)] = "bool"
                return "bool"
            if op in ("+", "-", "*", "/"):
                lt = self._check_expr(e.left, scopes=scopes)
                rt = self._check_expr(e.right, scopes=scopes)
                if lt != "i32" or rt != "i32":
                    self.error("Arithmetic operators expect عدد٣٢ operands", e.line, e.col)
                self.expr_types[id(e)] = "i32"
                return "i32"
            if op in ("==", "!=", "<", ">", "<=", ">="):
                lt = self._check_expr(e.left, scopes=scopes)
                rt = self._check_expr(e.right, scopes=scopes)
                if lt != "i32" or rt != "i32":
                    self.error("Comparison operators expect عدد٣٢ operands", e.line, e.col)
                self.expr_types[id(e)] = "bool"
                return "bool"
            self.error(f"Unknown operator: {op}", e.line, e.col)
        raise SemanticError(f"Unknown expression: {type(e).__name__}", self.filename, 1, 1)

