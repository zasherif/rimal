from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TokenType(str, Enum):
    # Structure
    NEWLINE = "NEWLINE"
    INDENT = "INDENT"
    DEDENT = "DEDENT"
    EOF = "EOF"

    # Literals / identifiers
    INT = "INT"
    STRING = "STRING"
    IDENT = "IDENT"

    # Keywords
    PRINT = "PRINT"  # اطبع
    IF = "IF"  # اذا
    ELSE = "ELSE"  # وإلا
    WHILE = "WHILE"  # بينما
    TRUE = "TRUE"  # صح
    FALSE = "FALSE"  # خطأ

    # Operators / punctuation
    ASSIGN = "="
    PLUS = "+"
    MINUS = "-"
    STAR = "*"
    SLASH = "/"

    EQEQ = "=="
    NEQ = "!="
    LT = "<"
    GT = ">"
    LTE = "<="
    GTE = ">="

    LPAREN = "("
    RPAREN = ")"
    COLON = ":"


KEYWORDS: dict[str, TokenType] = {
    "اطبع": TokenType.PRINT,
    "اذا": TokenType.IF,
    "وإلا": TokenType.ELSE,
    "بينما": TokenType.WHILE,
    "صح": TokenType.TRUE,
    "خطأ": TokenType.FALSE,
}


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: object | None
    line: int
    col: int

    def loc(self) -> str:
        return f"{self.line}:{self.col}"

    def __repr__(self) -> str:  # pragma: no cover
        if self.value is None:
            return f"Token({self.type}, {self.loc()})"
        return f"Token({self.type}, {self.value!r}, {self.loc()})"


class RimalError(Exception):
    pass


class LexError(RimalError):
    def __init__(self, message: str, filename: str, line: int, col: int) -> None:
        super().__init__(f"{filename}:{line}:{col}: {message}")


class ParseError(RimalError):
    def __init__(self, message: str, filename: str, line: int, col: int) -> None:
        super().__init__(f"{filename}:{line}:{col}: {message}")

