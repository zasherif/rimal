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
class Print(Stmt):
    expr: Expr


@dataclass(frozen=True)
class Assign(Stmt):
    name: str
    expr: Expr


@dataclass(frozen=True)
class If(Stmt):
    cond: Expr
    then_body: list[Stmt]
    else_body: list[Stmt] | None


@dataclass(frozen=True)
class While(Stmt):
    cond: Expr
    body: list[Stmt]


@dataclass(frozen=True)
class IntLit(Expr):
    value: int


@dataclass(frozen=True)
class BoolLit(Expr):
    value: bool


@dataclass(frozen=True)
class StrLit(Expr):
    value: str


@dataclass(frozen=True)
class Var(Expr):
    name: str


@dataclass(frozen=True)
class Binary(Expr):
    op: str
    left: Expr
    right: Expr

