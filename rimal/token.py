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
    DEF = "DEF"  # دالة
    RETURN = "RETURN"  # ارجع
    BREAK = "BREAK"  # اكسر
    CONTINUE = "CONTINUE"  # تابع
    TRUE = "TRUE"  # صح
    FALSE = "FALSE"  # خطأ
    AND = "AND"  # و
    OR = "OR"  # أو / او
    NOT = "NOT"  # ليس
    LET = "LET"  # دع
    VAR = "VAR"  # متغير
    TYPE_I32 = "TYPE_I32"  # عدد32
    TYPE_BOOL = "TYPE_BOOL"  # منطقي
    ASSERT = "ASSERT"  # تأكد

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
    COMMA = ","
    ARROW = "->"


KEYWORDS: dict[str, TokenType] = {
    "اطبع": TokenType.PRINT,
    "اذا": TokenType.IF,
    "وإلا": TokenType.ELSE,
    "بينما": TokenType.WHILE,
    "دالة": TokenType.DEF,
    "ارجع": TokenType.RETURN,
    "اكسر": TokenType.BREAK,
    "تابع": TokenType.CONTINUE,
    "صح": TokenType.TRUE,
    "خطأ": TokenType.FALSE,
    "و": TokenType.AND,
    "او": TokenType.OR,
    "أو": TokenType.OR,
    "ليس": TokenType.NOT,
    "دع": TokenType.LET,
    "متغير": TokenType.VAR,
    "عدد32": TokenType.TYPE_I32,
    "منطقي": TokenType.TYPE_BOOL,
    "تأكد": TokenType.ASSERT,
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
    def __init__(self, message: str, filename: str, line: int, col: int, line_text: str | None = None) -> None:
        col = max(1, int(col))
        base = f"{filename}:{line}:{col}: {message}"
        if line_text is not None:
            base += f"\n  {line_text}\n  {' ' * (col - 1)}^"
        super().__init__(base)


class ParseError(RimalError):
    def __init__(self, message: str, filename: str, line: int, col: int, line_text: str | None = None) -> None:
        col = max(1, int(col))
        base = f"{filename}:{line}:{col}: {message}"
        if line_text is not None:
            base += f"\n  {line_text}\n  {' ' * (col - 1)}^"
        super().__init__(base)


class SemanticError(RimalError):
    def __init__(self, message: str, filename: str, line: int, col: int, line_text: str | None = None) -> None:
        col = max(1, int(col))
        base = f"{filename}:{line}:{col}: {message}"
        if line_text is not None:
            base += f"\n  {line_text}\n  {' ' * (col - 1)}^"
        super().__init__(base)

