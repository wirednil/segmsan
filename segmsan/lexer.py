"""TAL lexer/tokenizer - produces tokens from TAL source code."""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


class TokenType(Enum):
    KEYWORD = auto()
    TYPE_KEYWORD = auto()
    DIRECTIVE = auto()
    DOLLAR_FUNC = auto()
    IDENT = auto()
    NUMBER = auto()
    CHAR_LIT = auto()
    STRING_LIT = auto()
    DOT = auto()
    AT = auto()
    ASSIGN = auto()
    MOVE_LR = auto()
    MOVE_RL = auto()
    EQ = auto()
    NEQ = auto()
    LT = auto()
    GT = auto()
    LE = auto()
    GE = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACK = auto()
    RBRACK = auto()
    SEMI = auto()
    COMMA = auto()
    COLON = auto()
    ARROW = auto()
    AMP = auto()
    HASH = auto()
    CARET = auto()
    USHL = auto()
    USHR = auto()
    USUB = auto()
    UADD = auto()
    SHL = auto()
    SHR = auto()
    NEWLINE = auto()
    EOF = auto()


KEYWORDS = {
    "PROC", "SUBPROC", "BEGIN", "END", "BLOCK", "ENDBLOCK",
    "CALL", "RETURN", "IF", "THEN", "ELSE", "WHILE", "FOR",
    "DO", "TO", "GOTO", "CASE", "OF",
    "STRUCT", "STRUCTURE", "LITERAL", "DEFINE", "STORE",
    "AND", "OR", "NOT", "XOR",
    "SCAN", "RSCAN",
    "LAND", "LOR",
    "SHL", "SHR",
    "MOD",
    "DROP", "INTO",
    "STEP",
    "FALSE", "TRUE",
    "BYTES",
    "FORWARD",
}

TYPE_KEYWORDS = {
    "INT", "STRING", "REAL", "FIXED", "UNSIGNED",
    "EXT",
}


@dataclass
class Token:
    type: TokenType
    value: str
    line: int
    col: int


@dataclass
class LexerError:
    message: str
    line: int
    col: int


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens: list[Token] = []
        self.errors: list[LexerError] = []

    def _ch(self, offset: int = 0) -> Optional[str]:
        p = self.pos + offset
        if p < len(self.source):
            return self.source[p]
        return None

    def _advance(self) -> str:
        ch = self.source[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _skip_whitespace(self):
        while self.pos < len(self.source) and self.source[self.pos] in " \t\r":
            self._advance()

    def _skip_comment(self) -> bool:
        ch = self._ch()
        if ch == "!":
            next_ch = self._ch(1)
            if next_ch and (next_ch.isalpha() or next_ch == "_"):
                i = self.pos + 1
                paren_depth = 0
                valid_id = True
                while i < len(self.source) and self.source[i] != "\n":
                    c = self.source[i]
                    if c == "(":
                        paren_depth += 1
                        i += 1
                        continue
                    if c == ")":
                        paren_depth -= 1
                        i += 1
                        continue
                    if c == "!" and paren_depth == 0:
                        if valid_id:
                            self._lex_bang_define()
                            return True
                        break
                    if not (c.isalnum() or c in ("_", "^", "#")):
                        valid_id = False
                    i += 1
            while self.pos < len(self.source) and self.source[self.pos] != "\n":
                self._advance()
            return True
        if ch == "-" and self._ch(1) == "-":
            while self.pos < len(self.source) and self.source[self.pos] != "\n":
                self._advance()
            return True
        return False

    def _lex_bang_define(self):
        line, col = self.line, self.col
        self._advance()
        chars = []
        paren_depth = 0
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch == "(":
                paren_depth += 1
                chars.append(self._advance())
            elif ch == ")":
                paren_depth -= 1
                chars.append(self._advance())
            elif ch == "!" and paren_depth == 0:
                self._advance()
                break
            elif ch == "\n":
                break
            else:
                chars.append(self._advance())
        self._emit(TokenType.IDENT, "".join(chars), line, col)

    def _emit(self, ttype: TokenType, value: str, line: int, col: int):
        self.tokens.append(Token(ttype, value, line, col))

    def _lex_string(self):
        line, col = self.line, self.col
        self._advance()
        result = []
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch == '"':
                self._advance()
                self._emit(TokenType.STRING_LIT, "".join(result), line, col)
                return
            if ch == "\n":
                self.errors.append(LexerError("Unterminated string literal", line, col))
                return
            result.append(ch)
            self._advance()
        self.errors.append(LexerError("Unterminated string literal", line, col))

    def _lex_char_or_prime_op(self):
        line, col = self.line, self.col
        self._advance()

        if self._ch() == ":":
            if self._ch(1) == "=":
                self._advance()
                self._advance()
                if self._ch() == "'":
                    self._advance()
                self._emit(TokenType.MOVE_LR, "':=", line, col)
                return
        if self._ch() == "=":
            if self._ch(1) == ":":
                self._advance()
                self._advance()
                self._advance()
                self._emit(TokenType.MOVE_RL, "'=:", line, col)
                return
        if self._ch() == "<" and self._ch(1) == "<":
            self._advance()
            self._advance()
            if self._ch() == "'":
                self._advance()
            self._emit(TokenType.USHL, "'<<'", line, col)
            return
        if self._ch() == ">" and self._ch(1) == ">":
            self._advance()
            self._advance()
            if self._ch() == "'":
                self._advance()
            self._emit(TokenType.USHR, "'>>'", line, col)
            return
        if self._ch() == "-":
            self._advance()
            if self._ch() == "'":
                self._advance()
            self._emit(TokenType.USUB, "'-'", line, col)
            return
        if self._ch() == "+":
            self._advance()
            if self._ch() == "'":
                self._advance()
            self._emit(TokenType.UADD, "'+'", line, col)
            return
        if self._ch() == "*":
            self._advance()
            if self._ch() == "'":
                self._advance()
            self._emit(TokenType.STAR, "'*'", line, col)
            return
        if self._ch() == "/":
            self._advance()
            if self._ch() == "'":
                self._advance()
            self._emit(TokenType.SLASH, "'/'", line, col)
            return
        if self._ch() == "\\":
            self._advance()
            if self._ch() == "'":
                self._advance()
            self._emit(TokenType.SLASH, "'\\'", line, col)
            return
        if self._ch() == "<":
            if self._ch(1) == ">" and self._ch(2) == "'":
                self._advance()
                self._advance()
                self._advance()
                self._emit(TokenType.NEQ, "'<>'", line, col)
                return
            if self._ch(1) == "=" and self._ch(2) == "'":
                self._advance()
                self._advance()
                self._advance()
                self._emit(TokenType.LE, "'<='", line, col)
                return
            if self._ch(1) == "'":
                self._advance()
                self._advance()
                self._emit(TokenType.LT, "'<'", line, col)
                return
        if self._ch() == ">":
            if self._ch(1) == "=" and self._ch(2) == "'":
                self._advance()
                self._advance()
                self._advance()
                self._emit(TokenType.GE, "'>='", line, col)
                return
            if self._ch(1) == "'":
                self._advance()
                self._advance()
                self._emit(TokenType.GT, "'>'", line, col)
                return
        if self._ch() == "=" and self._ch(1) == "'":
            self._advance()
            self._advance()
            self._emit(TokenType.EQ, "'='", line, col)
            return

        char_val = []
        if self.pos < len(self.source) and self.source[self.pos] not in ("'", "\n"):
            char_val.append(self._advance())
        if self._ch() == "'":
            self._advance()
            self._emit(TokenType.CHAR_LIT, "".join(char_val), line, col)
        else:
            if char_val:
                self._emit(TokenType.CHAR_LIT, char_val[0], line, col)
            else:
                self.errors.append(LexerError("Unexpected '", line, col))

    def _lex_number(self):
        line, col = self.line, self.col
        if self.source[self.pos] == "%":
            self._advance()
            digits = []
            while self.pos < len(self.source) and (self.source[self.pos].isalnum() or self.source[self.pos] == "_"):
                digits.append(self._advance())
            self._emit(TokenType.NUMBER, "%" + "".join(digits), line, col)
            return
        digits = []
        while self.pos < len(self.source) and self.source[self.pos].isdigit():
            digits.append(self._advance())
        num = "".join(digits)
        if self._ch() and self._ch().lower() in ("f", "r", "e", "l"):
            suffix = self._advance()
            self._emit(TokenType.NUMBER, num + suffix, line, col)
            return
        self._emit(TokenType.NUMBER, num, line, col)

    def _lex_ident_or_keyword(self):
        line, col = self.line, self.col
        chars = []
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch.isalnum() or ch == "_" or ch == "^" or ch == "#":
                chars.append(self._advance())
            else:
                break
        word = "".join(chars)
        upper = word.upper()

        if "^" in word or "#" in word:
            self._emit(TokenType.IDENT, word, line, col)
            return

        if upper == "INT" and self._ch() == "(":
            paren_chars = ["("]
            self._advance()
            while self.pos < len(self.source) and self.source[self.pos] != ")":
                paren_chars.append(self._advance())
            if self._ch() == ")":
                paren_chars.append(")")
                self._advance()
            self._emit(TokenType.TYPE_KEYWORD, word + "".join(paren_chars), line, col)
            return

        if upper in ("FIXED", "UNSIGNED") and self._ch() == "(":
            paren_chars = ["("]
            self._advance()
            while self.pos < len(self.source) and self.source[self.pos] != ")":
                paren_chars.append(self._advance())
            if self._ch() == ")":
                paren_chars.append(")")
                self._advance()
            self._emit(TokenType.TYPE_KEYWORD, word + "".join(paren_chars), line, col)
            return

        if upper in TYPE_KEYWORDS:
            self._emit(TokenType.TYPE_KEYWORD, word, line, col)
        elif upper in KEYWORDS:
            self._emit(TokenType.KEYWORD, word, line, col)
        else:
            self._emit(TokenType.IDENT, word, line, col)

    def _lex_directive(self):
        line, col = self.line, self.col
        self._advance()
        rest = []
        while self.pos < len(self.source) and self.source[self.pos] != "\n":
            rest.append(self._advance())
        self._emit(TokenType.DIRECTIVE, "".join(rest).rstrip(), line, col)

    def _lex_dollar(self):
        line, col = self.line, self.col
        self._advance()
        chars = []
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch.isalnum() or ch == "_" or ch == "^":
                chars.append(self._advance())
            else:
                break
        self._emit(TokenType.DOLLAR_FUNC, "".join(chars), line, col)

    def tokenize(self) -> list[Token]:
        while self.pos < len(self.source):
            self._skip_whitespace()
            if self.pos >= len(self.source):
                break
            if self._skip_comment():
                continue

            ch = self.source[self.pos]
            line, col = self.line, self.col

            if ch == "\n":
                self._advance()
                continue

            if ch == "?":
                self._lex_directive()
                continue
            if ch == "$":
                self._lex_dollar()
                continue
            if ch == '"':
                self._lex_string()
                continue
            if ch == "'":
                self._lex_char_or_prime_op()
                continue
            if ch == "@":
                self._advance()
                self._emit(TokenType.AT, "@", line, col)
                continue
            if ch == ".":
                self._advance()
                self._emit(TokenType.DOT, ".", line, col)
                continue
            if ch == ";":
                self._advance()
                self._emit(TokenType.SEMI, ";", line, col)
                continue
            if ch == ",":
                self._advance()
                self._emit(TokenType.COMMA, ",", line, col)
                continue
            if ch == "(":
                self._advance()
                self._emit(TokenType.LPAREN, "(", line, col)
                continue
            if ch == ")":
                self._advance()
                self._emit(TokenType.RPAREN, ")", line, col)
                continue
            if ch == "[":
                self._advance()
                self._emit(TokenType.LBRACK, "[", line, col)
                continue
            if ch == "]":
                self._advance()
                self._emit(TokenType.RBRACK, "]", line, col)
                continue
            if ch == "+":
                self._advance()
                self._emit(TokenType.PLUS, "+", line, col)
                continue
            if ch == "*":
                self._advance()
                self._emit(TokenType.STAR, "*", line, col)
                continue
            if ch == "/":
                self._advance()
                self._emit(TokenType.SLASH, "/", line, col)
                continue
            if ch == "&":
                self._advance()
                self._emit(TokenType.AMP, "&", line, col)
                continue
            if ch == "#":
                self._advance()
                self._emit(TokenType.HASH, "#", line, col)
                continue
            if ch == "-":
                if self._ch(1) == "-":
                    self._skip_comment()
                    continue
                if self._ch(1) == ">":
                    self._advance()
                    self._advance()
                    self._emit(TokenType.ARROW, "->", line, col)
                    continue
                self._advance()
                self._emit(TokenType.MINUS, "-", line, col)
                continue
            if ch == ":":
                if self._ch(1) == "=":
                    self._advance()
                    self._advance()
                    self._emit(TokenType.ASSIGN, ":=", line, col)
                    continue
                self._advance()
                self._emit(TokenType.COLON, ":", line, col)
                continue
            if ch == "=":
                self._advance()
                self._emit(TokenType.EQ, "=", line, col)
                continue
            if ch == "<":
                self._advance()
                if self._ch() == ">":
                    self._advance()
                    self._emit(TokenType.NEQ, "<>", line, col)
                elif self._ch() == "=":
                    self._advance()
                    self._emit(TokenType.LE, "<=", line, col)
                elif self._ch() == "<":
                    self._advance()
                    self._emit(TokenType.SHL, "<<", line, col)
                else:
                    self._emit(TokenType.LT, "<", line, col)
                continue
            if ch == ">":
                self._advance()
                if self._ch() == "=":
                    self._advance()
                    self._emit(TokenType.GE, ">=", line, col)
                elif self._ch() == ">":
                    self._advance()
                    self._emit(TokenType.SHR, ">>", line, col)
                else:
                    self._emit(TokenType.GT, ">", line, col)
                continue
            if ch == "^":
                self._advance()
                if self.pos < len(self.source) and (self.source[self.pos].isalnum() or self.source[self.pos] == "_"):
                    chars = ["^"]
                    while self.pos < len(self.source) and (self.source[self.pos].isalnum() or self.source[self.pos] == "_"):
                        chars.append(self._advance())
                    if self.tokens:
                        last = self.tokens[-1]
                        if last.type == TokenType.IDENT:
                            self.tokens[-1] = Token(TokenType.IDENT, last.value + "".join(chars), last.line, last.col)
                            continue
                    self._emit(TokenType.IDENT, "".join(chars), line, col)
                else:
                    self._emit(TokenType.CARET, "^", line, col)
                continue
            if ch == "%":
                self._lex_number()
                continue
            if ch.isdigit():
                self._lex_number()
                continue
            if ch.isalpha() or ch == "_":
                self._lex_ident_or_keyword()
                continue

            self.errors.append(LexerError(f"Unexpected character: {ch!r}", line, col))
            self._advance()

        self._emit(TokenType.EOF, "", self.line, self.col)
        return self.tokens
