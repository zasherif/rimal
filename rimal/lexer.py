from __future__ import annotations

from dataclasses import dataclass

from .token import KEYWORDS, LexError, Token, TokenType


_BIDI_FORMAT_CHARS = {
    "\u200e",  # LRM
    "\u200f",  # RLM
    "\u202a",  # LRE
    "\u202b",  # RLE
    "\u202c",  # PDF
    "\u202d",  # LRO
    "\u202e",  # RLO
    "\u2066",  # LRI
    "\u2067",  # RLI
    "\u2068",  # FSI
    "\u2069",  # PDI
}


def _is_ignorable_format(ch: str) -> bool:
    return ch in _BIDI_FORMAT_CHARS


@dataclass
class _IndentState:
    stack: list[int]


class Lexer:
    """
    Unicode-aware lexer with indentation handling (spaces only).

    Emits NEWLINE tokens at end of each non-empty logical line.
    Emits INDENT/DEDENT tokens like Python (based on leading spaces).
    """

    def __init__(self, source: str, filename: str = "<input>") -> None:
        self.source = source
        self.filename = filename

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        indent = _IndentState(stack=[0])

        lines = self.source.splitlines()
        if self.source.endswith("\n"):
            # Preserve trailing newline as an extra empty line to correctly dedent at EOF.
            lines.append("")

        for line_idx, raw_line in enumerate(lines, start=1):
            if "\t" in raw_line:
                col = raw_line.index("\t") + 1
                raise LexError("Tabs are forbidden; use spaces for indentation", self.filename, line_idx, col)

            # Compute indentation (leading spaces).
            i = 0
            spaces = 0
            while i < len(raw_line) and (raw_line[i] == " " or _is_ignorable_format(raw_line[i])):
                if raw_line[i] == " ":
                    spaces += 1
                i += 1
            leading = spaces
            rest = raw_line[i:]

            # Skip empty/whitespace-only lines (but keep line numbers consistent).
            if rest.strip() == "":
                continue
            # Skip comment-only lines (do not affect indentation).
            rest_no_fmt = "".join(ch for ch in rest if not _is_ignorable_format(ch))
            if rest_no_fmt.lstrip().startswith("#"):
                continue

            # INDENT/DEDENT handling.
            if leading > indent.stack[-1]:
                indent.stack.append(leading)
                tokens.append(Token(TokenType.INDENT, None, line_idx, 1))
            elif leading < indent.stack[-1]:
                while leading < indent.stack[-1]:
                    indent.stack.pop()
                    tokens.append(Token(TokenType.DEDENT, None, line_idx, 1))
                if leading != indent.stack[-1]:
                    raise LexError(
                        "Unindent does not match any outer indentation level",
                        self.filename,
                        line_idx,
                        1,
                    )

            # Lex the content part.
            col = i + 1
            p = 0
            while p < len(rest):
                ch = rest[p]
                if ch in (" ", "\r") or _is_ignorable_format(ch):
                    p += 1
                    col += 1
                    continue
                # Comment (inline): ignore the rest of the line.
                if ch == "#":
                    break

                # Identifiers / keywords (Unicode letters allowed)
                if ch == "_" or ch.isalpha():
                    start_col = col
                    start = p
                    p += 1
                    col += 1
                    while p < len(rest) and (rest[p] == "_" or rest[p].isalnum()):
                        p += 1
                        col += 1
                    text = rest[start:p]
                    kw = KEYWORDS.get(text)
                    if kw is not None:
                        tokens.append(Token(kw, text, line_idx, start_col))
                    else:
                        tokens.append(Token(TokenType.IDENT, text, line_idx, start_col))
                    continue

                # Integer literal
                if ch.isdigit():
                    start_col = col
                    start = p
                    p += 1
                    col += 1
                    while p < len(rest) and rest[p].isdigit():
                        p += 1
                        col += 1
                    value = int(rest[start:p])
                    tokens.append(Token(TokenType.INT, value, line_idx, start_col))
                    continue

                # String literal (double quotes)
                if ch == '"':
                    start_col = col
                    p += 1
                    col += 1
                    out_chars: list[str] = []
                    while True:
                        if p >= len(rest):
                            raise LexError("Unterminated string literal", self.filename, line_idx, start_col)
                        c = rest[p]
                        if c == '"':
                            p += 1
                            col += 1
                            break
                        if c == "\\":
                            if p + 1 >= len(rest):
                                raise LexError("Unterminated string escape", self.filename, line_idx, col)
                            nxt = rest[p + 1]
                            if nxt == "n":
                                out_chars.append("\n")
                            elif nxt == '"':
                                out_chars.append('"')
                            elif nxt == "\\":
                                out_chars.append("\\")
                            else:
                                raise LexError(f"Unknown escape: \\{nxt}", self.filename, line_idx, col)
                            p += 2
                            col += 2
                            continue
                        out_chars.append(c)
                        p += 1
                        col += 1
                    tokens.append(Token(TokenType.STRING, "".join(out_chars), line_idx, start_col))
                    continue

                # Two-char operators
                two = rest[p : p + 2]
                if two in ("==", "!=", "<=", ">="):
                    t = {
                        "==": TokenType.EQEQ,
                        "!=": TokenType.NEQ,
                        "<=": TokenType.LTE,
                        ">=": TokenType.GTE,
                    }[two]
                    tokens.append(Token(t, two, line_idx, col))
                    p += 2
                    col += 2
                    continue

                # Single-char tokens
                single_map = {
                    "=": TokenType.ASSIGN,
                    "+": TokenType.PLUS,
                    "-": TokenType.MINUS,
                    "*": TokenType.STAR,
                    "/": TokenType.SLASH,
                    "<": TokenType.LT,
                    ">": TokenType.GT,
                    "(": TokenType.LPAREN,
                    ")": TokenType.RPAREN,
                    ":": TokenType.COLON,
                }
                ttype = single_map.get(ch)
                if ttype is not None:
                    tokens.append(Token(ttype, ch, line_idx, col))
                    p += 1
                    col += 1
                    continue

                raise LexError(f"Unexpected character: {ch!r}", self.filename, line_idx, col)

            tokens.append(Token(TokenType.NEWLINE, None, line_idx, len(raw_line) + 1))

        # Dedent to zero at EOF
        eof_line = len(lines) if lines else 1
        while len(indent.stack) > 1:
            indent.stack.pop()
            tokens.append(Token(TokenType.DEDENT, None, eof_line, 1))
        tokens.append(Token(TokenType.EOF, None, eof_line, 1))
        return tokens

