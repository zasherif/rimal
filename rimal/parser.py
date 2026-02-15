from __future__ import annotations

from . import ast
from .token import ParseError, Token, TokenType


class Parser:
    def __init__(self, tokens: list[Token], filename: str = "<input>") -> None:
        self.tokens = tokens
        self.filename = filename
        self.i = 0

    def _cur(self) -> Token:
        return self.tokens[self.i]

    def _at(self, t: TokenType) -> bool:
        return self._cur().type == t

    def _eat(self, t: TokenType, message: str | None = None) -> Token:
        tok = self._cur()
        if tok.type != t:
            msg = message or f"Expected {t.value}, got {tok.type.value}"
            raise ParseError(msg, self.filename, tok.line, tok.col)
        self.i += 1
        return tok

    def _match(self, *types: TokenType) -> Token | None:
        if self._cur().type in types:
            tok = self._cur()
            self.i += 1
            return tok
        return None

    def parse_program(self) -> ast.Program:
        stmts: list[ast.Stmt] = []
        while not self._at(TokenType.EOF):
            if self._match(TokenType.NEWLINE):
                continue
            if self._at(TokenType.DEDENT):
                # Defensive: blocks consume DEDENT, top-level should not see it.
                tok = self._cur()
                raise ParseError("Unexpected dedent", self.filename, tok.line, tok.col)
            stmts.append(self._parse_stmt())
        return ast.Program(stmts)

    def _parse_stmt(self) -> ast.Stmt:
        tok = self._cur()

        if self._match(TokenType.PRINT):
            expr = self._parse_expr()
            self._eat(TokenType.NEWLINE, "Expected end of line after print")
            return ast.Print(expr)

        if self._match(TokenType.IF):
            cond = self._parse_expr()
            self._eat(TokenType.COLON, "Expected ':' after if condition")
            self._eat(TokenType.NEWLINE, "Expected newline after ':'")
            then_body = self._parse_block()

            else_body: list[ast.Stmt] | None = None
            if self._match(TokenType.ELSE):
                self._eat(TokenType.COLON, "Expected ':' after else")
                self._eat(TokenType.NEWLINE, "Expected newline after ':'")
                else_body = self._parse_block()
            return ast.If(cond, then_body, else_body)

        if self._match(TokenType.WHILE):
            cond = self._parse_expr()
            self._eat(TokenType.COLON, "Expected ':' after while condition")
            self._eat(TokenType.NEWLINE, "Expected newline after ':'")
            body = self._parse_block()
            return ast.While(cond, body)

        # Assignment: IDENT '=' expr NEWLINE
        if self._at(TokenType.IDENT):
            name_tok = self._eat(TokenType.IDENT)
            if not self._match(TokenType.ASSIGN):
                raise ParseError("Expected '=' after identifier", self.filename, name_tok.line, name_tok.col)
            expr = self._parse_expr()
            self._eat(TokenType.NEWLINE, "Expected end of line after assignment")
            return ast.Assign(str(name_tok.value), expr)

        raise ParseError(f"Unexpected token: {tok.type.value}", self.filename, tok.line, tok.col)

    def _parse_block(self) -> list[ast.Stmt]:
        if not self._match(TokenType.INDENT):
            tok = self._cur()
            raise ParseError("Expected an indented block", self.filename, tok.line, tok.col)

        stmts: list[ast.Stmt] = []
        while True:
            if self._match(TokenType.NEWLINE):
                continue
            if self._match(TokenType.DEDENT):
                break
            if self._at(TokenType.EOF):
                tok = self._cur()
                raise ParseError("Unexpected end of file in block", self.filename, tok.line, tok.col)
            stmts.append(self._parse_stmt())
        if not stmts:
            # Minimal language: empty blocks are likely a mistake.
            # Keep it as an error to help users.
            raise ParseError("Empty block is not allowed", self.filename, self._cur().line, self._cur().col)
        return stmts

    # Expression parsing (precedence climbing)
    #
    # precedence:
    #   comparison: == != < > <= >=
    #   add: + -
    #   mul: * /
    #   primary: literals, vars, (expr)

    _COMP = {
        TokenType.EQEQ,
        TokenType.NEQ,
        TokenType.LT,
        TokenType.GT,
        TokenType.LTE,
        TokenType.GTE,
    }

    _OP_CANONICAL = {
        TokenType.PLUS: "+",
        TokenType.MINUS: "-",
        TokenType.STAR: "*",
        TokenType.SLASH: "/",
        TokenType.EQEQ: "==",
        TokenType.NEQ: "!=",
        TokenType.LT: "<",
        TokenType.GT: ">",
        TokenType.LTE: "<=",
        TokenType.GTE: ">=",
    }

    def _op_str(self, tok: Token) -> str:
        # Token value may be Arabic keyword text (e.g. "ضرب") or the symbol itself ("*").
        # Canonicalize to the symbol representation used by the Wasm backend.
        s = self._OP_CANONICAL.get(tok.type)
        if s is None:
            return str(tok.value)
        return s

    def _parse_expr(self) -> ast.Expr:
        left = self._parse_add()
        if self._cur().type in self._COMP:
            op_tok = self._cur()
            self.i += 1
            right = self._parse_add()
            return ast.Binary(self._op_str(op_tok), left, right)
        return left

    def _parse_add(self) -> ast.Expr:
        expr = self._parse_mul()
        while True:
            tok = self._match(TokenType.PLUS, TokenType.MINUS)
            if tok is None:
                break
            rhs = self._parse_mul()
            expr = ast.Binary(self._op_str(tok), expr, rhs)
        return expr

    def _parse_mul(self) -> ast.Expr:
        expr = self._parse_primary()
        while True:
            tok = self._match(TokenType.STAR, TokenType.SLASH)
            if tok is None:
                break
            rhs = self._parse_primary()
            expr = ast.Binary(self._op_str(tok), expr, rhs)
        return expr

    def _parse_primary(self) -> ast.Expr:
        tok = self._cur()

        if self._match(TokenType.INT):
            return ast.IntLit(int(tok.value))  # type: ignore[arg-type]
        if self._match(TokenType.STRING):
            return ast.StrLit(str(tok.value))
        if self._match(TokenType.TRUE):
            return ast.BoolLit(True)
        if self._match(TokenType.FALSE):
            return ast.BoolLit(False)
        if self._match(TokenType.IDENT):
            return ast.Var(str(tok.value))
        if self._match(TokenType.LPAREN):
            inner = self._parse_expr()
            self._eat(TokenType.RPAREN, "Expected ')'")
            return inner

        raise ParseError(f"Unexpected token in expression: {tok.type.value}", self.filename, tok.line, tok.col)

