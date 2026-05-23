"""TAL lexer/tokenizer - produces tokens from TAL source code.

Also contains Lark token stream adapters (migrated from lark_adapter.py).
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from lark.lexer import Token as LarkToken


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
    UMUL = auto()
    UDIV = auto()
    UMOD = auto()
    ULT = auto()
    UEQ = auto()
    UGT = auto()
    ULE = auto()
    UGE = auto()
    UNE = auto()
    BASE_P = auto()
    BASE_G = auto()
    BASE_L = auto()
    BASE_S = auto()
    BASE_SG = auto()
    DOT_SG = auto()
    DOT_DOT = auto()
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

            self._advance()
            while self.pos < len(self.source):
                c = self.source[self.pos]
                if c == "\n":
                    break
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
            self._emit(TokenType.UMUL, "'*'", line, col)
            return
        if self._ch() == "/":
            self._advance()
            if self._ch() == "'":
                self._advance()
            self._emit(TokenType.UDIV, "'/'", line, col)
            return
        if self._ch() == "\\":
            self._advance()
            if self._ch() == "'":
                self._advance()
            self._emit(TokenType.UMOD, "'\\'", line, col)
            return
        if self._ch() == "<":
            if self._ch(1) == ">" and self._ch(2) == "'":
                self._advance()
                self._advance()
                self._advance()
                self._emit(TokenType.UNE, "'<>'", line, col)
                return
            if self._ch(1) == "=" and self._ch(2) == "'":
                self._advance()
                self._advance()
                self._advance()
                self._emit(TokenType.ULE, "'<='", line, col)
                return
            if self._ch(1) == "'":
                self._advance()
                self._advance()
                self._emit(TokenType.ULT, "'<'", line, col)
                return
        if self._ch() == ">":
            if self._ch(1) == "=" and self._ch(2) == "'":
                self._advance()
                self._advance()
                self._advance()
                self._emit(TokenType.UGE, "'>='", line, col)
                return
            if self._ch(1) == "'":
                self._advance()
                self._advance()
                self._emit(TokenType.UGT, "'>'", line, col)
                return
        if self._ch() == "=" and self._ch(1) == "'":
            self._advance()
            self._advance()
            self._emit(TokenType.UEQ, "'='", line, col)
            return

        # Base address symbols: 'SG', 'S', 'G', 'L', 'P'
        next_ch = self._ch()
        if next_ch and next_ch.upper() in ("P", "G", "L", "S"):
            upper = next_ch.upper()
            if upper == "S" and self._ch(1) and self._ch(1).upper() == "G" and self._ch(2) == "'":
                self._advance()
                self._advance()
                self._advance()
                self._emit(TokenType.BASE_SG, "'SG'", line, col)
                return
            if self._ch(1) == "'":
                self._advance()
                self._advance()
                _base_map = {
                    "P": TokenType.BASE_P,
                    "G": TokenType.BASE_G,
                    "L": TokenType.BASE_L,
                    "S": TokenType.BASE_S,
                }
                self._emit(_base_map[upper], f"'{next_ch}'", line, col)
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

        # Prefixed: %, %B, %H — reads all alphanumeric chars
        if self.source[self.pos] == "%":
            self._advance()
            chars = []
            while self.pos < len(self.source) and self.source[self.pos].isalnum():
                chars.append(self._advance())
            num = "%" + "".join(chars)
            # INT(32) hex suffix: %H1234%D or %h1234%d
            if self._ch() == "%" and self._ch(1) and self._ch(1).lower() == "d":
                self._advance()
                num += "%" + self._advance()
            self._emit(TokenType.NUMBER, num, line, col)
            return

        # Decimal — lookahead to detect float: digit+ . digit+ (E|L|F) exponent?
        i = self.pos
        while i < len(self.source) and self.source[i].isdigit():
            i += 1
        is_float = False
        if i < len(self.source) and self.source[i] == ".":
            j = i + 1
            while j < len(self.source) and self.source[j].isdigit():
                j += 1
            if j > i + 1 and j < len(self.source) and self.source[j].lower() in ("e", "l", "f"):
                is_float = True

        num = ""
        while self.pos < len(self.source) and self.source[self.pos].isdigit():
            num += self._advance()

        if is_float:
            num += self._advance()  # "."
            while self.pos < len(self.source) and self.source[self.pos].isdigit():
                num += self._advance()

        # Type suffix: D=INT(32), F=FIXED, E=REAL, L=REAL(64)
        if self._ch() and self._ch().lower() in ("d", "f", "e", "l"):
            num += self._advance()
            # REAL / REAL(64): consume optional sign + exponent digits
            if num[-1].lower() in ("e", "l"):
                if self._ch() in ("+", "-"):
                    num += self._advance()
                while self.pos < len(self.source) and self.source[self.pos].isdigit():
                    num += self._advance()

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

        if upper == "INT":
            lookahead = self._ch()
            if lookahead == " ":
                j = self.pos + 1
                while j < len(self.source) and self.source[j] == " ":
                    j += 1
                if j < len(self.source) and self.source[j] == "(":
                    lookahead = "("
            if lookahead == "(":
                paren_chars = ["("]
                self._advance()
                while self.pos < len(self.source) and self.source[self.pos] != ")":
                    paren_chars.append(self._advance())
                if self._ch() == ")":
                    paren_chars.append(")")
                    self._advance()
                self._emit(TokenType.TYPE_KEYWORD, word + "".join(paren_chars), line, col)
                return

        if upper in ("FIXED", "UNSIGNED", "REAL"):
            la = self._ch()
            if la == " ":
                j = self.pos + 1
                while j < len(self.source) and self.source[j] == " ":
                    j += 1
                if j < len(self.source) and self.source[j] == "(":
                    la = "("
            if la == "(":
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
                if self._ch() == ".":
                    self._advance()
                    self._emit(TokenType.DOT_DOT, "..", line, col)
                elif (self._ch() and self._ch().upper() == "S"
                        and self._ch(1) and self._ch(1).upper() == "G"
                        and not (self._ch(2) and (self._ch(2).isalnum() or self._ch(2) in ("_", "^")))):
                    self._advance()
                    self._advance()
                    self._emit(TokenType.DOT_SG, ".SG", line, col)
                else:
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


# ---------------------------------------------------------------------------
# Lark token stream adapters
# ---------------------------------------------------------------------------

_RESERVED: frozenset[str] = frozenset({
    "AND", "ASSERT", "BEGIN", "BY",
    "CALL", "CALLABLE", "CASE", "CODE",
    "DEFINE", "DO", "DOWNTO", "DROP",
    "ELSE", "END", "ENTRY", "EXTERNAL",
    "FIXED", "FOR", "FORWARD",
    "GOTO",
    "IF", "INT", "INTERRUPT",
    "LABEL", "LAND", "LITERAL", "LOR",
    "MAIN",
    "NOT",
    "OF", "OR", "OTHERWISE",
    "PRIV", "PROC",
    "REAL", "RESIDENT", "RETURN", "RSCAN",
    "SCAN", "STACK", "STORE", "STRING", "STRUCT", "SUBPROC",
    "THEN", "TO",
    "UNSIGNED", "UNTIL", "USE",
    "VARIABLE",
    "WHILE",
    "XOR",
})

_NON_RESERVED: frozenset[str] = frozenset({
    "AT", "BELOW", "BIT_FILLER", "BLOCK", "BYTES",
    "C", "COBOL", "ELEMENTS", "EXT", "EXTENSIBLE",
    "FILLER", "FORTRAN", "LANGUAGE", "NAME",
    "PASCAL", "PRIVATE", "UNSPECIFIED", "WORDS",
})

_LEXER_EXTRAS: frozenset[str] = frozenset({
    "ENDBLOCK", "STRUCTURE", "SHL", "SHR",
    "MOD", "STEP", "INTO",
})

_PROMOTE_FROM_IDENT: frozenset[str] = frozenset({
    "ASSERT", "BY", "CALLABLE", "CODE", "DOWNTO",
    "ENTRY", "EXTERNAL", "INTERRUPT", "LABEL", "MAIN",
    "OTHERWISE", "PRIV", "RESIDENT", "STACK", "UNTIL", "USE",
    "FILLER", "BIT_FILLER",
})

_ALL_KEYWORDS: frozenset[str] = _RESERVED | _NON_RESERVED | _LEXER_EXTRAS


def _normalize_type(value: str) -> str:
    upper = value.upper().replace(" ", "")
    base = upper.split("(")[0]
    if base == "INT":
        if "(64)" in upper:
            return "TK_FIXED"
        if "(32)" in upper:
            return "TK_INT32"
        return "TK_INT"
    if base == "REAL":
        if "(64)" in upper:
            return "TK_REAL64"
        return "TK_REAL"
    if base == "FIXED":
        return "TK_FIXED"
    if base == "UNSIGNED":
        return "TK_UNSIGNED"
    if base == "STRING":
        return "TK_STRING"
    if base == "EXT":
        return "KW_EXT"
    return f"TK_{base}"


_PUNCT: dict[TokenType, str] = {
    TokenType.SEMI:       "SEMI",
    TokenType.COMMA:      "COMMA",
    TokenType.COLON:      "COLON",
    TokenType.LPAREN:     "LPAREN",
    TokenType.RPAREN:     "RPAREN",
    TokenType.LBRACK:     "LBRACK",
    TokenType.RBRACK:     "RBRACK",
    TokenType.ARROW:      "ARROW",
    TokenType.DOT:        "DOT",
    TokenType.AT:         "AT",
    TokenType.ASSIGN:     "ASSIGN",
    TokenType.MOVE_LR:    "MOVE_LR",
    TokenType.MOVE_RL:    "MOVE_RL",
    TokenType.AMP:        "AMP",
    TokenType.EQ:         "EQ",
    TokenType.NEQ:        "NEQ",
    TokenType.LT:         "LT",
    TokenType.GT:         "GT",
    TokenType.LE:         "LE",
    TokenType.GE:         "GE",
    TokenType.PLUS:       "PLUS",
    TokenType.MINUS:      "MINUS",
    TokenType.STAR:       "STAR",
    TokenType.SLASH:      "SLASH",
    TokenType.SHL:        "SHL",
    TokenType.SHR:        "SHR",
    TokenType.HASH:       "HASH",
    TokenType.CARET:      "CARET",
    TokenType.DOT_SG:     "DOT_SG",
    TokenType.DOT_DOT:    "DOT_DOT",
    TokenType.STRING_LIT: "STRING_LIT",
    TokenType.CHAR_LIT:   "CHAR_LIT",
    TokenType.DOLLAR_FUNC:"DOLLAR_FUNC",
    TokenType.DIRECTIVE:  "DIRECTIVE",
}

_PRIME_OPS: dict[TokenType, str] = {
    TokenType.UADD:  "UADD",
    TokenType.USUB:  "USUB",
    TokenType.UMUL:  "UMUL",
    TokenType.UDIV:  "UDIV",
    TokenType.UMOD:  "UMOD",
    TokenType.USHL:  "USHL",
    TokenType.USHR:  "USHR",
    TokenType.ULT:   "ULT",
    TokenType.UEQ:   "UEQ",
    TokenType.UGT:   "UGT",
    TokenType.ULE:   "ULE",
    TokenType.UGE:   "UGE",
    TokenType.UNE:   "UNE",
}

_BASE_ADDR_TYPES: frozenset[TokenType] = frozenset({
    TokenType.BASE_P,
    TokenType.BASE_G,
    TokenType.BASE_L,
    TokenType.BASE_S,
    TokenType.BASE_SG,
})


def _classify_number(value: str) -> str:
    v = value.upper()
    if v.endswith("%D"):
        return "NUMBER_INT32"
    if v.endswith("D") and not v.startswith("%H"):
        return "NUMBER_INT32"
    if v.endswith("%F"):
        return "NUMBER_FIXED"
    if v.endswith("F") and not v.startswith("%H"):
        return "NUMBER_FIXED"
    if "." in v and "E" in v:
        return "NUMBER_REAL"
    if "." in v and "L" in v:
        return "NUMBER_REAL64"
    return "NUMBER_INT"


def _skip_define(it) -> None:
    for t in it:
        if t.type == TokenType.HASH:
            for t2 in it:
                if t2.type in (TokenType.SEMI, TokenType.EOF):
                    return
            return
        if t.type == TokenType.IDENT and t.value.endswith("#"):
            for t2 in it:
                if t2.type in (TokenType.SEMI, TokenType.EOF):
                    return
            return
        if t.type == TokenType.EOF:
            return


def to_lark_stream(tokens: list[Token]):
    it = iter(tokens)
    for t in it:
        if t.type == TokenType.EOF:
            return
        if t.type == TokenType.KEYWORD and t.value.upper() == "DEFINE":
            _skip_define(it)
            continue
        if t.type == TokenType.KEYWORD:
            upper = t.value.upper()
            yield LarkToken(f"KW_{upper}", t.value, line=t.line, column=t.col)
        elif t.type == TokenType.TYPE_KEYWORD:
            terminal = _normalize_type(t.value)
            yield LarkToken(terminal, t.value, line=t.line, column=t.col)
        elif t.type in _PRIME_OPS:
            terminal = _PRIME_OPS[t.type]
            yield LarkToken(terminal, t.value, line=t.line, column=t.col)
        elif t.type == TokenType.NUMBER:
            terminal = _classify_number(t.value)
            yield LarkToken(terminal, t.value, line=t.line, column=t.col)
        elif t.type in _BASE_ADDR_TYPES:
            inner = t.value[1:-1]
            yield LarkToken("PRIME", "'",   line=t.line, column=t.col)
            yield LarkToken("NAME",  inner, line=t.line, column=t.col + 1)
            yield LarkToken("PRIME", "'",   line=t.line, column=t.col + len(t.value) - 1)
        elif t.type == TokenType.IDENT:
            upper = t.value.upper()
            if upper in _PROMOTE_FROM_IDENT:
                yield LarkToken(f"KW_{upper}", t.value, line=t.line, column=t.col)
            else:
                yield LarkToken("NAME", t.value, line=t.line, column=t.col)
        else:
            terminal = _PUNCT.get(t.type)
            if terminal is not None:
                yield LarkToken(terminal, t.value, line=t.line, column=t.col)


_PROC_HEADER_PROMOTE: dict[str, str] = {
    "VARIABLE":     "KW_VARIABLE",
    "EXTENSIBLE":   "KW_EXTENSIBLE",
    "LANGUAGE":     "KW_LANGUAGE",
    "EXTERN":       "KW_EXTERNAL",
}

_STMT_PROMOTE: dict[str, str] = {
    "BYTES":    "KW_BYTES",
    "WORDS":    "KW_WORDS",
    "ELEMENTS": "KW_ELEMENTS",
    "STEP":     "KW_STEP",
}

_PROC_BODY_PROMOTE: dict[str, str] = {
    **_PROC_HEADER_PROMOTE,
    **_STMT_PROMOTE,
}


def to_stmt_stream(tokens: list[Token]):
    for lark_tok in to_lark_stream(tokens):
        if lark_tok.type == "NAME":
            promoted = _STMT_PROMOTE.get(str(lark_tok).upper())
            if promoted is not None:
                yield LarkToken(promoted, lark_tok,
                                line=lark_tok.line, column=lark_tok.column)
                continue
        yield lark_tok


def to_proc_body_stream(tokens: list[Token]):
    it = iter(tokens)
    prev_type: str | None = None
    for t in it:
        if t.type == TokenType.EOF:
            return

        if t.type == TokenType.KEYWORD and t.value.upper() == "DEFINE":
            _skip_define(it)
            continue

        if t.type == TokenType.KEYWORD:
            upper = t.value.upper()
            tok = LarkToken(f"KW_{upper}", t.value, line=t.line, column=t.col)
        elif t.type == TokenType.TYPE_KEYWORD:
            terminal = _normalize_type(t.value)
            tok = LarkToken(terminal, t.value, line=t.line, column=t.col)
        elif t.type in _PRIME_OPS:
            terminal = _PRIME_OPS[t.type]
            tok = LarkToken(terminal, t.value, line=t.line, column=t.col)
        elif t.type == TokenType.NUMBER:
            terminal = _classify_number(t.value)
            tok = LarkToken(terminal, t.value, line=t.line, column=t.col)
        elif t.type in _BASE_ADDR_TYPES:
            inner = t.value[1:-1]
            yield LarkToken("PRIME", "'",   line=t.line, column=t.col)
            yield LarkToken("NAME",  inner, line=t.line, column=t.col + 1)
            yield LarkToken("PRIME", "'",   line=t.line, column=t.col + len(t.value) - 1)
            prev_type = "PRIME"
            continue
        elif t.type == TokenType.IDENT:
            upper = t.value.upper()
            if prev_type in ("KW_PROC", "KW_SUBPROC"):
                tok = LarkToken("NAME", t.value, line=t.line, column=t.col)
            elif upper in _PROMOTE_FROM_IDENT:
                tok = LarkToken(f"KW_{upper}", t.value, line=t.line, column=t.col)
            elif upper in _PROC_BODY_PROMOTE:
                tok = LarkToken(_PROC_BODY_PROMOTE[upper], t.value,
                                line=t.line, column=t.col)
            else:
                tok = LarkToken("NAME", t.value, line=t.line, column=t.col)
        else:
            terminal = _PUNCT.get(t.type)
            if terminal is None:
                continue
            tok = LarkToken(terminal, t.value, line=t.line, column=t.col)

        prev_type = tok.type
        yield tok


def _strip_semi_before_else(tokens):
    prev = None
    for tok in tokens:
        if prev is not None:
            if prev.type == "SEMI" and tok.type == "KW_ELSE":
                pass
            else:
                yield prev
        prev = tok
    if prev is not None:
        yield prev


def to_program_stream(tokens: list[Token]):
    yield from _strip_semi_before_else(to_proc_body_stream(tokens))


def to_proc_header_stream(tokens: list[Token]):
    for lark_tok in to_lark_stream(tokens):
        if lark_tok.type == "NAME":
            promoted = _PROC_HEADER_PROMOTE.get(str(lark_tok).upper())
            if promoted is not None:
                yield LarkToken(promoted, lark_tok,
                                line=lark_tok.line, column=lark_tok.column)
                continue
        yield lark_tok
