from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Program:
    statements: list["Stmt"]


class Stmt:
    pass


class Expr:
    pass


@dataclass(frozen=True)
class Param:
    name: str
    type_name: str  # "i32" | "bool"
    line: int
    col: int


@dataclass(frozen=True)
class FunctionDef(Stmt):
    name: str
    params: list[Param]
    return_type: str  # "i32" | "bool"
    body: list["Stmt"]
    line: int
    col: int


@dataclass(frozen=True)
class VarDecl(Stmt):
    name: str
    type_name: str  # "i32" | "bool"
    mutable: bool
    expr: Expr
    line: int
    col: int


@dataclass(frozen=True)
class Print(Stmt):
    expr: Expr
    line: int
    col: int


@dataclass(frozen=True)
class Assert(Stmt):
    expr: Expr  # must be bool
    line: int
    col: int


@dataclass(frozen=True)
class Assign(Stmt):
    name: str
    expr: Expr
    line: int
    col: int


@dataclass(frozen=True)
class If(Stmt):
    cond: Expr
    then_body: list[Stmt]
    else_body: list[Stmt] | None
    line: int
    col: int


@dataclass(frozen=True)
class While(Stmt):
    cond: Expr
    body: list[Stmt]
    line: int
    col: int


@dataclass(frozen=True)
class Return(Stmt):
    expr: Expr
    line: int
    col: int


@dataclass(frozen=True)
class Break(Stmt):
    line: int
    col: int


@dataclass(frozen=True)
class Continue(Stmt):
    line: int
    col: int


@dataclass(frozen=True)
class IntLit(Expr):
    value: int
    line: int
    col: int


@dataclass(frozen=True)
class BoolLit(Expr):
    value: bool
    line: int
    col: int


@dataclass(frozen=True)
class StrLit(Expr):
    value: str
    line: int
    col: int


@dataclass(frozen=True)
class Var(Expr):
    name: str
    line: int
    col: int


@dataclass(frozen=True)
class Binary(Expr):
    op: str
    left: Expr
    right: Expr
    line: int
    col: int


@dataclass(frozen=True)
class Unary(Expr):
    op: str
    expr: Expr
    line: int
    col: int


@dataclass(frozen=True)
class Call(Expr):
    name: str
    args: list[Expr]
    line: int
    col: int

