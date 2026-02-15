from __future__ import annotations

from . import ast
from .token import ParseError, Token, TokenType


class Parser:
    def __init__(self, tokens: list[Token], filename: str = "<input>", source: str | None = None) -> None:
        self.tokens = tokens
        self.filename = filename
        self._lines = source.splitlines() if source is not None else None
        self.i = 0

    def _line_text(self, line: int) -> str | None:
        if self._lines is None:
            return None
        if line <= 0 or line > len(self._lines):
            return None
        return self._lines[line - 1]

    def _cur(self) -> Token:
        return self.tokens[self.i]

    def _at(self, t: TokenType) -> bool:
        return self._cur().type == t

    def _eat(self, t: TokenType, message: str | None = None) -> Token:
        tok = self._cur()
        if tok.type != t:
            msg = message or f"Expected {t.value}, got {tok.type.value}"
            raise ParseError(msg, self.filename, tok.line, tok.col, line_text=self._line_text(tok.line))
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
                raise ParseError(
                    "Unexpected dedent",
                    self.filename,
                    tok.line,
                    tok.col,
                    line_text=self._line_text(tok.line),
                )
            stmts.append(self._parse_stmt())
        return ast.Program(stmts)

    def _parse_stmt(self) -> ast.Stmt:
        tok = self._cur()

        if self._match(TokenType.DEF):
            def_tok = tok
            name_tok = self._eat(TokenType.IDENT, "Expected function name after 'دالة'")
            self._eat(TokenType.LPAREN, "Expected '(' after function name")
            params: list[ast.Param] = []
            if not self._at(TokenType.RPAREN):
                while True:
                    p_tok = self._eat(TokenType.IDENT, "Expected parameter name")
                    self._eat(TokenType.COLON, "Expected ':' after parameter name")
                    tname = self._parse_type_name()
                    params.append(ast.Param(str(p_tok.value), tname, p_tok.line, p_tok.col))
                    if self._match(TokenType.COMMA):
                        continue
                    break
            self._eat(TokenType.RPAREN, "Expected ')'")
            self._eat(TokenType.ARROW, "Expected '->' before return type")
            return_type = self._parse_type_name()
            self._eat(TokenType.COLON, "Expected ':' after function signature")
            self._eat(TokenType.NEWLINE, "Expected newline after ':'")
            body = self._parse_block()
            return ast.FunctionDef(str(name_tok.value), params, return_type, body, def_tok.line, def_tok.col)

        if self._match(TokenType.PRINT):
            p_tok = tok
            expr = self._parse_expr()
            self._eat(TokenType.NEWLINE, "Expected end of line after print")
            return ast.Print(expr, p_tok.line, p_tok.col)

        if self._match(TokenType.ASSERT):
            a_tok = tok
            expr = self._parse_expr()
            self._eat(TokenType.NEWLINE, "Expected end of line after assert")
            return ast.Assert(expr, a_tok.line, a_tok.col)

        if self._match(TokenType.LET) or self._match(TokenType.VAR):
            decl_tok = tok
            mutable = decl_tok.type == TokenType.VAR
            name_tok = self._eat(TokenType.IDENT, "Expected identifier after declaration")
            self._eat(TokenType.COLON, "Expected ':' after identifier")
            tname = self._parse_type_name()
            self._eat(TokenType.ASSIGN, "Expected '=' in declaration")
            expr = self._parse_expr()
            self._eat(TokenType.NEWLINE, "Expected end of line after declaration")
            return ast.VarDecl(str(name_tok.value), tname, mutable, expr, decl_tok.line, decl_tok.col)

        if self._match(TokenType.RETURN):
            r_tok = tok
            expr = self._parse_expr()
            self._eat(TokenType.NEWLINE, "Expected end of line after return")
            return ast.Return(expr, r_tok.line, r_tok.col)

        if self._match(TokenType.BREAK):
            self._eat(TokenType.NEWLINE, "Expected end of line after break")
            return ast.Break(tok.line, tok.col)

        if self._match(TokenType.CONTINUE):
            self._eat(TokenType.NEWLINE, "Expected end of line after continue")
            return ast.Continue(tok.line, tok.col)

        if self._match(TokenType.IF):
            if_tok = tok
            cond = self._parse_expr()
            self._eat(TokenType.COLON, "Expected ':' after if condition")
            self._eat(TokenType.NEWLINE, "Expected newline after ':'")
            then_body = self._parse_block()

            else_body: list[ast.Stmt] | None = None
            if self._match(TokenType.ELSE):
                # Support "وإلا اذا" as elif by nesting an If inside else.
                if self._match(TokenType.IF):
                    elif_if_tok = self.tokens[self.i - 1]
                    elif_cond = self._parse_expr()
                    self._eat(TokenType.COLON, "Expected ':' after if condition")
                    self._eat(TokenType.NEWLINE, "Expected newline after ':'")
                    elif_then = self._parse_block()
                    elif_else: list[ast.Stmt] | None = None
                    if self._match(TokenType.ELSE):
                        self._eat(TokenType.COLON, "Expected ':' after else")
                        self._eat(TokenType.NEWLINE, "Expected newline after ':'")
                        elif_else = self._parse_block()
                    else_body = [ast.If(elif_cond, elif_then, elif_else, elif_if_tok.line, elif_if_tok.col)]
                else:
                    self._eat(TokenType.COLON, "Expected ':' after else")
                    self._eat(TokenType.NEWLINE, "Expected newline after ':'")
                    else_body = self._parse_block()
            return ast.If(cond, then_body, else_body, if_tok.line, if_tok.col)

        if self._match(TokenType.WHILE):
            w_tok = tok
            cond = self._parse_expr()
            self._eat(TokenType.COLON, "Expected ':' after while condition")
            self._eat(TokenType.NEWLINE, "Expected newline after ':'")
            body = self._parse_block()
            return ast.While(cond, body, w_tok.line, w_tok.col)

        # Assignment: IDENT '=' expr NEWLINE
        if self._at(TokenType.IDENT):
            name_tok = self._eat(TokenType.IDENT)
            if not self._match(TokenType.ASSIGN):
                raise ParseError(
                    "Expected '=' after identifier",
                    self.filename,
                    name_tok.line,
                    name_tok.col,
                    line_text=self._line_text(name_tok.line),
                )
            expr = self._parse_expr()
            self._eat(TokenType.NEWLINE, "Expected end of line after assignment")
            return ast.Assign(str(name_tok.value), expr, name_tok.line, name_tok.col)

        raise ParseError(
            f"Unexpected token: {tok.type.value}",
            self.filename,
            tok.line,
            tok.col,
            line_text=self._line_text(tok.line),
        )

    def _parse_block(self) -> list[ast.Stmt]:
        if not self._match(TokenType.INDENT):
            tok = self._cur()
            raise ParseError(
                "Expected an indented block",
                self.filename,
                tok.line,
                tok.col,
                line_text=self._line_text(tok.line),
            )

        stmts: list[ast.Stmt] = []
        while True:
            if self._match(TokenType.NEWLINE):
                continue
            if self._match(TokenType.DEDENT):
                break
            if self._at(TokenType.EOF):
                tok = self._cur()
                raise ParseError(
                    "Unexpected end of file in block",
                    self.filename,
                    tok.line,
                    tok.col,
                    line_text=self._line_text(tok.line),
                )
            stmts.append(self._parse_stmt())
        if not stmts:
            # Minimal language: empty blocks are likely a mistake.
            # Keep it as an error to help users.
            raise ParseError("Empty block is not allowed", self.filename, self._cur().line, self._cur().col)
        return stmts

    # Expression parsing (precedence climbing)
    #
    # precedence:
    #   or:  OR
    #   and: AND
    #   comparison: == != < > <= >=
    #   add: + -
    #   mul: * /
    #   unary: NOT
    #   primary: literals, vars, calls, (expr)

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
        return self._parse_or()

    def _parse_or(self) -> ast.Expr:
        expr = self._parse_and()
        while True:
            tok = self._match(TokenType.OR)
            if tok is None:
                break
            rhs = self._parse_and()
            expr = ast.Binary("or", expr, rhs, tok.line, tok.col)
        return expr

    def _parse_and(self) -> ast.Expr:
        expr = self._parse_cmp()
        while True:
            tok = self._match(TokenType.AND)
            if tok is None:
                break
            rhs = self._parse_cmp()
            expr = ast.Binary("and", expr, rhs, tok.line, tok.col)
        return expr

    def _parse_cmp(self) -> ast.Expr:
        left = self._parse_add()
        if self._cur().type in self._COMP:
            op_tok = self._cur()
            self.i += 1
            right = self._parse_add()
            return ast.Binary(self._op_str(op_tok), left, right, op_tok.line, op_tok.col)
        return left

    def _parse_add(self) -> ast.Expr:
        expr = self._parse_mul()
        while True:
            tok = self._match(TokenType.PLUS, TokenType.MINUS)
            if tok is None:
                break
            rhs = self._parse_mul()
            expr = ast.Binary(self._op_str(tok), expr, rhs, tok.line, tok.col)
        return expr

    def _parse_mul(self) -> ast.Expr:
        expr = self._parse_unary()
        while True:
            tok = self._match(TokenType.STAR, TokenType.SLASH)
            if tok is None:
                break
            rhs = self._parse_unary()
            expr = ast.Binary(self._op_str(tok), expr, rhs, tok.line, tok.col)
        return expr

    def _parse_unary(self) -> ast.Expr:
        not_tok = self._match(TokenType.NOT)
        if not_tok is not None:
            inner = self._parse_unary()
            return ast.Unary("not", inner, not_tok.line, not_tok.col)
        return self._parse_primary()

    def _parse_primary(self) -> ast.Expr:
        tok = self._cur()

        if self._match(TokenType.INT):
            return ast.IntLit(int(tok.value), tok.line, tok.col)  # type: ignore[arg-type]
        if self._match(TokenType.STRING):
            return ast.StrLit(str(tok.value), tok.line, tok.col)
        if self._match(TokenType.TRUE):
            return ast.BoolLit(True, tok.line, tok.col)
        if self._match(TokenType.FALSE):
            return ast.BoolLit(False, tok.line, tok.col)
        if self._match(TokenType.IDENT):
            name = str(tok.value)
            if self._match(TokenType.LPAREN):
                args: list[ast.Expr] = []
                if not self._at(TokenType.RPAREN):
                    while True:
                        args.append(self._parse_expr())
                        if self._match(TokenType.COMMA):
                            continue
                        break
                self._eat(TokenType.RPAREN, "Expected ')'")
                return ast.Call(name, args, tok.line, tok.col)
            return ast.Var(name, tok.line, tok.col)
        if self._match(TokenType.LPAREN):
            inner = self._parse_expr()
            self._eat(TokenType.RPAREN, "Expected ')'")
            return inner

        raise ParseError(
            f"Unexpected token in expression: {tok.type.value}",
            self.filename,
            tok.line,
            tok.col,
            line_text=self._line_text(tok.line),
        )

    def _parse_type_name(self) -> str:
        tok = self._cur()
        if self._match(TokenType.TYPE_I32):
            return "i32"
        if self._match(TokenType.TYPE_BOOL):
            return "bool"
        raise ParseError(
            "Expected type name (عدد32 or منطقي)",
            self.filename,
            tok.line,
            tok.col,
            line_text=self._line_text(tok.line),
        )

