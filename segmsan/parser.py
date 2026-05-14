"""Minimal TAL parser - extracts declarations, assignments, procedures, and scope."""

from __future__ import annotations
from .lexer import Lexer, Token, TokenType
from .ast_nodes import *


class ParseError(Exception):
    def __init__(self, msg: str, line: int = 0, col: int = 0):
        super().__init__(f"{msg} (line {line}, col {col})")
        self.line = line
        self.col = col


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = [t for t in tokens if t.type != TokenType.NEWLINE]
        self.pos = 0

    def _cur(self) -> Token:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return Token(TokenType.EOF, "", 0, 0)

    def _peek(self, offset: int = 1) -> Token:
        p = self.pos + offset
        if p < len(self.tokens):
            return self.tokens[p]
        return Token(TokenType.EOF, "", 0, 0)

    def _advance(self) -> Token:
        t = self._cur()
        if self.pos < len(self.tokens):
            self.pos += 1
        return t

    def _match_keyword(self, kw: str) -> bool:
        t = self._cur()
        return t.type in (TokenType.KEYWORD, TokenType.TYPE_KEYWORD) and t.value.upper() == kw.upper()

    def _match_kw_any(self, *kws: str) -> bool:
        return any(self._match_keyword(k) for k in kws)

    def _is_type_token(self) -> bool:
        t = self._cur()
        if t.type == TokenType.TYPE_KEYWORD:
            return True
        if t.type == TokenType.KEYWORD and t.value.upper() == "STRUCTURE":
            return True
        return False

    def _is_proc_decl(self) -> bool:
        if self._match_keyword("PROC"):
            return True
        if self._is_type_token():
            nxt = self._peek()
            if nxt.type == TokenType.KEYWORD and nxt.value.upper() == "PROC":
                return True
        return False

    def parse(self, source_file: str = "") -> Program:
        program = Program(source_file=source_file)
        self.program = program
        while self._cur().type != TokenType.EOF:
            self._skip_semis()
            if self._cur().type == TokenType.EOF:
                break
            if self._cur().type == TokenType.DIRECTIVE:
                program.directives.append(self._advance().value)
                continue
            if self._match_keyword("NAME"):
                self._skip_to_semi()
                continue
            if self._match_keyword("BLOCK"):
                self._parse_block_globals(program)
                continue
            if self._match_keyword("END"):
                if self._peek().type == TokenType.KEYWORD and self._peek().value.upper() == "BLOCK":
                    self._advance()
                    self._advance()
                    if self._cur().type == TokenType.SEMI:
                        self._advance()
                else:
                    self._advance()
                    if self._cur().type == TokenType.SEMI:
                        self._advance()
                continue
            if self._is_proc_decl():
                proc = self._parse_procedure(is_main=not program.procedures)
                program.procedures.append(proc)
                continue
            if self._is_type_token():
                decls = self._parse_var_decls()
                program.globals_.extend(decls)
                continue
            if self._match_keyword("LITERAL"):
                self._parse_literal_decl()
                continue
            if self._match_keyword("DEFINE"):
                self._skip_to_semi_or_endblock()
                continue
            if self._match_keyword("STRUCT") or self._match_keyword("STRUCTURE"):
                self._parse_struct_def(program.globals_)
                continue
            self._skip_to_semi()
        self._process_directives(program)
        return program

    def _process_directives(self, program: Program):
        import re
        combined = "\n".join(program.directives)
        for m in re.finditer(
            r'SOURCE\s+([^\s,(]+)\s*(?:\(([^)]*)\))?',
            combined, re.IGNORECASE
        ):
            path = m.group(1).strip()
            names_raw = m.group(2) or ""
            names = [n.strip().lstrip("?") for n in names_raw.split(",") if n.strip()]
            is_system = path.upper().startswith("$SYSTEM.") or path.upper().startswith("$RTL")
            si = SourceImport(path=path, names=names, is_system=is_system)
            program.source_imports.append(si)

    def _skip_semis(self):
        while self._cur().type == TokenType.SEMI:
            self._advance()

    def _skip_to_semi(self):
        while self._cur().type not in (TokenType.SEMI, TokenType.EOF):
            self._advance()
        if self._cur().type == TokenType.SEMI:
            self._advance()

    def _skip_to_semi_or_endblock(self):
        while self._cur().type not in (TokenType.SEMI, TokenType.EOF):
            if self._match_keyword("END"):
                break
            self._advance()
        if self._cur().type == TokenType.SEMI:
            self._advance()

    def _parse_struct_def(self, target_list: list):
        loc = SourceLocation(self._cur().line, self._cur().col)
        self._advance()

        is_indirect = False
        if self._cur().type == TokenType.DOT:
            is_indirect = True
            self._advance()

        name = ""
        if self._cur().type in (TokenType.IDENT, TokenType.KEYWORD):
            name = self._advance().value

        array_bounds = None
        is_template = False
        has_paren_content = False
        if self._cur().type == TokenType.LPAREN:
            self._advance()
            paren_content = ""
            while self._cur().type not in (TokenType.RPAREN, TokenType.EOF):
                paren_content += self._cur().value
                self._advance()
            has_paren_content = True
            if paren_content.strip() == "*":
                is_template = True
            if self._cur().type == TokenType.RPAREN:
                self._advance()
        if self._cur().type == TokenType.LBRACK:
            self._advance()
            lo_str = ""
            while self._cur().type not in (TokenType.COLON, TokenType.RBRACK, TokenType.EOF):
                lo_str += self._advance().value
            try:
                lo = int(lo_str.replace("%", "0o"))
            except ValueError:
                lo = 0
            hi = lo
            if self._cur().type == TokenType.COLON:
                self._advance()
                hi_str = ""
                while self._cur().type not in (TokenType.RBRACK, TokenType.EOF):
                    hi_str += self._advance().value
                try:
                    hi = int(hi_str.replace("%", "0o"))
                except ValueError:
                    hi = lo
            if self._cur().type == TokenType.RBRACK:
                self._advance()
            array_bounds = ArrayBounds(lo, hi)

        if self._cur().type == TokenType.SEMI:
            self._advance()

        struct_fields: list[VarDecl] | None = None

        if (not has_paren_content or is_template) and self._match_keyword("BEGIN"):
            self._advance()
            struct_fields = []
            depth = 1
            while depth > 0 and self._cur().type != TokenType.EOF:
                self._skip_semis()
                if self._match_keyword("BEGIN"):
                    self._advance()
                    depth += 1
                    continue
                if self._match_keyword("END"):
                    self._advance()
                    depth -= 1
                    continue
                if self._match_keyword("STRUCT") or self._match_keyword("STRUCTURE"):
                    self._parse_struct_def(struct_fields)
                    continue
                if self._is_type_token():
                    struct_fields.extend(self._parse_var_decls())
                    continue
                self._skip_to_semi()
            if self._cur().type == TokenType.SEMI:
                self._advance()

        if not name:
            return

        decl = VarDecl(
            name=name, tal_type=TalType.STRUCT,
            loc=loc, is_indirect=is_indirect,
            array_bounds=array_bounds,
            struct_fields=struct_fields,
            is_template=is_template,
        )
        target_list.append(decl)

    def _parse_literal_decl(self):
        self._advance()

        while True:
            self._skip_semis()
            name = ""
            if self._cur().type in (TokenType.IDENT, TokenType.KEYWORD):
                name = self._advance().value

            if self._cur().type == TokenType.EQ:
                self._advance()

            value = None
            if self._cur().type == TokenType.NUMBER:
                raw = self._cur().value.rstrip("fFrReElL")
                try:
                    value = int(raw.replace("%", "0o"))
                except ValueError:
                    value = None
                self._advance()
            elif self._cur().type == TokenType.MINUS:
                self._advance()
                if self._cur().type == TokenType.NUMBER:
                    raw = self._cur().value.rstrip("fFrReElL")
                    try:
                        value = -int(raw.replace("%", "0o"))
                    except ValueError:
                        value = None
                    self._advance()
                else:
                    self._skip_to_semi()
                    return
            else:
                self._skip_to_semi()
                return

            if name and value is not None:
                self.program.literals[name.upper()] = value

            if self._cur().type == TokenType.COMMA:
                self._advance()
                continue
            break

        if self._cur().type == TokenType.SEMI:
            self._advance()

    def _parse_block_globals(self, program: Program):
        self._advance()
        if self._cur().type in (TokenType.IDENT, TokenType.KEYWORD):
            self._advance()
        if self._cur().type == TokenType.SEMI:
            self._advance()

        while self._cur().type != TokenType.EOF:
            self._skip_semis()
            if self._cur().type == TokenType.EOF:
                break
            if self._match_keyword("END"):
                nxt = self._peek()
                if nxt.type == TokenType.KEYWORD and nxt.value.upper() == "BLOCK":
                    self._advance()
                    self._advance()
                    if self._cur().type == TokenType.SEMI:
                        self._advance()
                    break
                else:
                    break
            if self._cur().type == TokenType.DIRECTIVE:
                dval = self._cur().value.upper()
                if "LARGESTACK" in dval:
                    pass
                program.directives.append(self._advance().value)
                continue
            if self._match_keyword("NAME"):
                self._skip_to_semi()
                continue
            if self._match_keyword("LITERAL"):
                self._parse_literal_decl()
                continue
            if self._match_keyword("DEFINE"):
                self._skip_to_semi_or_endblock()
                continue
            if self._match_keyword("STRUCT") or self._match_keyword("STRUCTURE"):
                self._parse_struct_def(program.globals_)
                continue
            if self._is_type_token():
                decls = self._parse_var_decls()
                program.globals_.extend(decls)
                continue
            self._skip_to_semi()

    def _parse_procedure(self, is_main: bool = False) -> Procedure:
        loc = SourceLocation(self._cur().line, self._cur().col)
        return_type = None

        if self._is_type_token() and not self._match_keyword("PROC"):
            return_type = self._advance().value

        if self._match_keyword("PROC"):
            self._advance()

        name = ""
        if self._cur().type == TokenType.IDENT:
            name = self._advance().value
        elif self._cur().type == TokenType.KEYWORD:
            name = self._advance().value

        params: list[ParamDecl] = []
        if self._cur().type == TokenType.LPAREN:
            self._advance()
            params = self._parse_param_list()
            if self._cur().type == TokenType.RPAREN:
                self._advance()

        is_variable = False
        has_largestack = False

        if self._cur().type == TokenType.SEMI:
            self._advance()

        if self._match_keyword("EXTERNAL") or self._match_keyword("EXTERN"):
            self._advance()
            if self._cur().type == TokenType.SEMI:
                self._advance()
            return Procedure(
                name=name, loc=loc, params=params,
                is_main=is_main, is_extern=True,
            )

        locals_: list[VarDecl] = []
        body: list[Statement] = []
        subprocs: list[Procedure] = []

        while self._cur().type != TokenType.EOF:
            self._skip_semis()
            if self._cur().type == TokenType.EOF:
                break
            if self._match_keyword("BEGIN"):
                self._advance()
                continue
            if self._match_keyword("END"):
                self._advance()
                if self._cur().type == TokenType.SEMI:
                    self._advance()
                break
            if self._cur().type == TokenType.DIRECTIVE:
                dval = self._cur().value.upper()
                if "LARGESTACK" in dval:
                    has_largestack = True
                self._advance()
                continue
            if self._match_keyword("SUBPROC"):
                sub = self._parse_subprocedure()
                subprocs.append(sub)
                continue
            if self._match_keyword("STRUCT") or self._match_keyword("STRUCTURE"):
                self._parse_struct_def(locals_)
                continue
            if self._is_type_token():
                locals_.extend(self._parse_var_decls())
                continue
            if self._match_keyword("LITERAL"):
                self._parse_literal_decl()
                continue
            if self._match_keyword("DEFINE"):
                self._skip_to_semi()
                continue
            if self._match_keyword("FORWARD"):
                self._advance()
                if self._cur().type == TokenType.SEMI:
                    self._advance()
                return Procedure(
                    name=name, loc=loc, params=params,
                    locals_=locals_,
                    is_forward=True,
                )
            stmt = self._parse_statement()
            if stmt:
                body.append(stmt)

        proc = Procedure(
            name=name, loc=loc, params=params, locals_=locals_,
            body=body, subprocs=subprocs,
            is_main=is_main, is_variable=is_variable,
            has_largestack=has_largestack,
        )
        proc.calls_self = self._check_recursion(proc)
        return proc

    def _parse_subprocedure(self) -> Procedure:
        loc = SourceLocation(self._cur().line, self._cur().col)
        self._advance()

        name = ""
        if self._cur().type == TokenType.IDENT:
            name = self._advance().value

        params: list[ParamDecl] = []
        if self._cur().type == TokenType.LPAREN:
            self._advance()
            params = self._parse_param_list()
            if self._cur().type == TokenType.RPAREN:
                self._advance()

        if self._cur().type == TokenType.SEMI:
            self._advance()

        locals_: list[VarDecl] = []
        body: list[Statement] = []
        subprocs: list[Procedure] = []

        while self._cur().type != TokenType.EOF:
            self._skip_semis()
            if self._cur().type == TokenType.EOF:
                break
            if self._match_keyword("END"):
                self._advance()
                if self._cur().type == TokenType.SEMI:
                    self._advance()
                break
            if self._cur().type == TokenType.DIRECTIVE:
                self._advance()
                continue
            if self._match_keyword("SUBPROC"):
                sub = self._parse_subprocedure()
                subprocs.append(sub)
                continue
            if self._match_keyword("STRUCT") or self._match_keyword("STRUCTURE"):
                self._parse_struct_def(locals_)
                continue
            if self._is_type_token():
                locals_.extend(self._parse_var_decls())
                continue
            if self._match_keyword("LITERAL"):
                self._parse_literal_decl()
                continue
            if self._match_keyword("DEFINE"):
                self._skip_to_semi()
                continue
            stmt = self._parse_statement()
            if stmt:
                body.append(stmt)

        proc = Procedure(name=name, loc=loc, params=params, locals_=locals_,
                         body=body, subprocs=subprocs)
        proc.calls_self = self._check_recursion(proc)
        return proc

    def _parse_param_list(self) -> list[ParamDecl]:
        params: list[ParamDecl] = []
        while self._cur().type not in (TokenType.RPAREN, TokenType.EOF):
            if self._is_type_token():
                ptype = self._parse_type_keyword()
                is_ext = False
                if self._match_keyword("EXT"):
                    is_ext = True
                    self._advance()
                is_ref = False
                if self._cur().type == TokenType.DOT:
                    is_ref = True
                    self._advance()
                pname = ""
                if self._cur().type == TokenType.IDENT:
                    pname = self._advance().value
                elif self._cur().type == TokenType.KEYWORD:
                    pname = self._advance().value
                bounds = None
                if self._cur().type == TokenType.LBRACK:
                    self._advance()
                    lo_s, hi_s = "", ""
                    while self._cur().type not in (TokenType.COLON, TokenType.RBRACK, TokenType.EOF):
                        lo_s += self._advance().value
                    if self._cur().type == TokenType.COLON:
                        self._advance()
                    while self._cur().type not in (TokenType.RBRACK, TokenType.EOF):
                        hi_s += self._advance().value
                    if self._cur().type == TokenType.RBRACK:
                        self._advance()
                    try:
                        bounds = ArrayBounds(int(lo_s.replace("%", "0o")), int(hi_s.replace("%", "0o")))
                    except ValueError:
                        bounds = None
                params.append(ParamDecl(
                    name=pname, tal_type=ptype,
                    is_reference=is_ref, is_extended=is_ext,
                    fpoint=ptype_fpoint(ptype), width=ptype_width(ptype),
                ))
            elif self._cur().type == TokenType.DOT:
                self._advance()
                pname = ""
                if self._cur().type == TokenType.IDENT:
                    pname = self._advance().value
                params.append(ParamDecl(
                    name=pname, tal_type=TalType.INT,
                    is_reference=True,
                ))
            elif self._cur().type in (TokenType.IDENT, TokenType.KEYWORD):
                pname = self._advance().value
                params.append(ParamDecl(name=pname, tal_type=TalType.INT))
            else:
                self._advance()
            if self._cur().type == TokenType.COMMA:
                self._advance()
            elif self._cur().type == TokenType.SEMI:
                self._advance()
        return params

    def _parse_type_keyword(self) -> TalType:
        t = self._cur()
        upper = t.value.upper()
        self._advance()
        if upper.startswith("INT("):
            return TalType.INT32
        if upper == "INT":
            return TalType.INT
        if upper == "STRING":
            return TalType.STRING
        if upper == "REAL":
            return TalType.REAL
        if upper.startswith("FIXED"):
            return TalType.FIXED
        if upper.startswith("UNSIGNED"):
            return TalType.UNSIGNED
        if upper == "EXT":
            return TalType.INT
        if upper in ("STRUCT", "STRUCTURE"):
            return TalType.STRUCT
        return TalType.INT

    def _parse_var_decls(self) -> list[VarDecl]:
        decls: list[VarDecl] = []
        tal_type = self._parse_type_keyword()
        fpoint = ptype_fpoint(tal_type)
        width = ptype_width(tal_type)

        while True:
            loc = SourceLocation(self._cur().line, self._cur().col)
            has_init = False
            is_ext = False
            if self._match_keyword("EXT"):
                is_ext = True
                self._advance()

            is_indirect = False
            if self._cur().type == TokenType.DOT:
                is_indirect = True
                self._advance()

            name = ""
            if self._cur().type == TokenType.IDENT:
                name = self._advance().value
            elif self._cur().type == TokenType.KEYWORD:
                name = self._advance().value

            array_bounds = None
            if self._cur().type == TokenType.LBRACK:
                self._advance()
                lo_str = ""
                while self._cur().type not in (TokenType.COLON, TokenType.RBRACK, TokenType.EOF):
                    lo_str += self._advance().value
                try:
                    lo = int(lo_str.replace("%", "0o"))
                except ValueError:
                    lo = 0
                hi = lo
                if self._cur().type == TokenType.COLON:
                    self._advance()
                    hi_str = ""
                    while self._cur().type not in (TokenType.RBRACK, TokenType.EOF):
                        hi_str += self._advance().value
                    try:
                        hi = int(hi_str.replace("%", "0o"))
                    except ValueError:
                        hi = lo
                if self._cur().type == TokenType.RBRACK:
                    self._advance()
                array_bounds = ArrayBounds(lo, hi)

            is_readonly = False
            is_equivalence = False
            equivalence_target = None

            if self._cur().type == TokenType.EQ:
                self._advance()
                if self._cur().type == TokenType.STRING_LIT and self._cur().value.upper() == "P":
                    is_readonly = True
                    self._advance()
                elif self._cur().type == TokenType.STRING_LIT:
                    self._advance()
                elif self._cur().type in (TokenType.IDENT, TokenType.KEYWORD):
                    is_equivalence = True
                    equivalence_target = self._advance().value
                elif self._cur().type == TokenType.MINUS:
                    self._advance()
                    if self._cur().type == TokenType.IDENT:
                        equivalence_target = self._advance().value
            elif self._match_keyword("STORE"):
                self._advance()

            if self._cur().type == TokenType.ASSIGN:
                self._advance()
                has_init = True
                self._skip_initializer()

            decls.append(VarDecl(
                name=name, tal_type=tal_type,
                loc=loc, is_indirect=is_indirect, is_extended=is_ext,
                array_bounds=array_bounds, is_readonly=is_readonly,
                is_equivalence=is_equivalence,
                equivalence_target=equivalence_target,
                fpoint=fpoint, width=width,
                has_initializer=has_init,
            ))

            if self._cur().type == TokenType.COMMA:
                self._advance()
                if self._cur().type == TokenType.DOT:
                    continue
                continue
            break

        if self._cur().type == TokenType.SEMI:
            self._advance()
        return decls

    def _skip_initializer(self):
        depth = 0
        while self._cur().type not in (TokenType.SEMI, TokenType.EOF):
            if self._cur().type == TokenType.LBRACK:
                depth += 1
            elif self._cur().type == TokenType.RBRACK:
                depth -= 1
                if depth < 0:
                    break
            elif self._cur().type == TokenType.COMMA and depth == 0:
                break
            self._advance()

    def _parse_statement(self) -> Statement | None:
        t = self._cur()
        if t.type == TokenType.EOF or self._match_keyword("END"):
            return None

        if self._match_keyword("IF"):
            return self._parse_if()
        if self._match_keyword("WHILE"):
            return self._parse_while()
        if self._match_keyword("FOR"):
            return self._parse_for()
        if self._match_keyword("SCAN") or self._match_keyword("RSCAN"):
            return self._parse_scan()
        if self._match_keyword("RETURN"):
            return self._parse_return()
        if self._match_keyword("GOTO"):
            self._advance()
            label = ""
            if self._cur().type == TokenType.IDENT:
                label = self._advance().value
            if self._cur().type == TokenType.SEMI:
                self._advance()
            return GotoStmt(label=label, loc=SourceLocation(t.line, t.col))
        if self._match_keyword("CALL"):
            self._advance()
            name = ""
            if self._cur().type == TokenType.IDENT:
                name = self._advance().value
            args: list[Expr] = []
            if self._cur().type == TokenType.LPAREN:
                self._advance()
                args = self._parse_expr_list()
                if self._cur().type == TokenType.RPAREN:
                    self._advance()
            if self._cur().type == TokenType.SEMI:
                self._advance()
            return CallStmt(
                expr=CallExpr(name=name, args=args, loc=SourceLocation(t.line, t.col)),
                loc=SourceLocation(t.line, t.col),
            )

        expr = self._try_parse_expr()
        if expr is None:
            self._skip_to_semi()
            return None

        if self._cur().type in (TokenType.ASSIGN, TokenType.MOVE_LR, TokenType.MOVE_RL):
            self._advance()
            source = self._try_parse_expr()
            if source is None:
                source = LiteralExpr(0)
            if self._cur().type == TokenType.SEMI:
                self._advance()
            return AssignStmt(target=expr, source=source, loc=SourceLocation(t.line, t.col))

        if isinstance(expr, CallExpr):
            if self._cur().type == TokenType.SEMI:
                self._advance()
            return CallStmt(expr=expr, loc=SourceLocation(t.line, t.col))

        if self._cur().type == TokenType.SEMI:
            self._advance()

        return OtherStmt(raw=t.value, loc=SourceLocation(t.line, t.col))

    def _parse_if(self) -> IfStmt:
        loc = SourceLocation(self._cur().line, self._cur().col)
        self._advance()
        cond = self._try_parse_expr()
        if self._match_keyword("THEN"):
            self._advance()
        then_body = self._parse_simple_stmt_list()
        else_body: list[Statement] = []
        if self._match_keyword("ELSE"):
            self._advance()
            else_body = self._parse_simple_stmt_list()
        return IfStmt(condition=cond or LiteralExpr(0), then_body=then_body,
                      else_body=else_body, loc=loc)

    def _parse_while(self) -> WhileStmt:
        loc = SourceLocation(self._cur().line, self._cur().col)
        self._advance()
        cond = self._try_parse_expr()
        if self._match_keyword("DO"):
            self._advance()
        body = self._parse_simple_stmt_list()
        return WhileStmt(condition=cond or LiteralExpr(0), body=body, loc=loc)

    def _parse_for(self) -> ForStmt:
        loc = SourceLocation(self._cur().line, self._cur().col)
        self._advance()
        var = ""
        if self._cur().type == TokenType.IDENT:
            var = self._advance().value
        if self._cur().type == TokenType.ASSIGN:
            self._advance()
        from_expr = self._try_parse_expr() or LiteralExpr(0)
        if self._match_keyword("TO"):
            self._advance()
        to_expr = self._try_parse_expr() or LiteralExpr(0)
        step = None
        if self._match_keyword("STEP"):
            self._advance()
            step = self._try_parse_expr()
        if self._match_keyword("DO"):
            self._advance()
        body = self._parse_simple_stmt_list()
        return ForStmt(var=var, from_expr=from_expr, to_expr=to_expr, step=step,
                       body=body, loc=loc)

    def _parse_scan(self) -> ScanStmt:
        loc = SourceLocation(self._cur().line, self._cur().col)
        direction = self._advance().value.upper()
        array = self._try_parse_expr()
        while_expr = None
        if self._match_keyword("WHILE") or self._match_keyword("UNTIL"):
            self._advance()
            while_expr = self._try_parse_expr()
        next_addr = None
        if self._cur().type == TokenType.ARROW:
            self._advance()
            next_addr = self._try_parse_expr()
        if self._cur().type == TokenType.SEMI:
            self._advance()
        return ScanStmt(direction=direction, array=array or LiteralExpr(0),
                        while_expr=while_expr or LiteralExpr(0),
                        next_addr=next_addr, loc=loc)

    def _parse_return(self) -> ReturnStmt:
        loc = SourceLocation(self._cur().line, self._cur().col)
        self._advance()
        value = None
        if not self._match_keyword("END") and self._cur().type not in (TokenType.SEMI, TokenType.EOF):
            value = self._try_parse_expr()
        if self._cur().type == TokenType.SEMI:
            self._advance()
        return ReturnStmt(value=value, loc=loc)

    def _parse_simple_stmt_list(self) -> list[Statement]:
        stmts: list[Statement] = []
        if self._match_keyword("BEGIN"):
            self._advance()
            while not self._match_keyword("END") and self._cur().type != TokenType.EOF:
                self._skip_semis()
                if self._match_keyword("END"):
                    break
                stmt = self._parse_statement()
                if stmt:
                    stmts.append(stmt)
            if self._match_keyword("END"):
                self._advance()
                if self._cur().type == TokenType.SEMI:
                    self._advance()
        else:
            stmt = self._parse_statement()
            if stmt:
                stmts.append(stmt)
        return stmts

    def _try_parse_expr(self) -> Expr | None:
        return self._parse_or_expr()

    def _parse_or_expr(self) -> Expr | None:
        left = self._parse_and_expr()
        if left is None:
            return None
        while self._match_keyword("OR") or self._match_keyword("LOR"):
            op = self._advance().value
            right = self._parse_and_expr()
            if right is None:
                break
            left = BinOpExpr(op=op, left=left, right=right)
        return left

    def _parse_and_expr(self) -> Expr | None:
        left = self._parse_not_expr()
        if left is None:
            return None
        while self._match_keyword("AND") or self._match_keyword("LAND"):
            op = self._advance().value
            right = self._parse_not_expr()
            if right is None:
                break
            left = BinOpExpr(op=op, left=left, right=right)
        return left

    def _parse_not_expr(self) -> Expr | None:
        if self._match_keyword("NOT"):
            self._advance()
            inner = self._parse_comparison()
            if inner is None:
                return None
            return BinOpExpr(op="NOT", left=inner, right=LiteralExpr(0))
        return self._parse_comparison()

    def _parse_comparison(self) -> Expr | None:
        left = self._parse_additive()
        if left is None:
            return None
        while self._cur().type in (TokenType.EQ, TokenType.NEQ, TokenType.LT,
                                    TokenType.GT, TokenType.LE, TokenType.GE):
            op = self._advance().value
            right = self._parse_additive()
            if right is None:
                break
            left = BinOpExpr(op=op, left=left, right=right, loc=SourceLocation(self._cur().line))
        return left

    def _parse_additive(self) -> Expr | None:
        left = self._parse_multiplicative()
        if left is None:
            return None
        while self._cur().type in (TokenType.PLUS, TokenType.MINUS, TokenType.USUB, TokenType.UADD):
            op = self._advance().value
            right = self._parse_multiplicative()
            if right is None:
                break
            left = BinOpExpr(op=op, left=left, right=right)
        return left

    def _parse_multiplicative(self) -> Expr | None:
        left = self._parse_unary()
        if left is None:
            return None
        while self._cur().type in (TokenType.STAR, TokenType.SLASH):
            op = self._advance().value
            right = self._parse_unary()
            if right is None:
                break
            left = BinOpExpr(op=op, left=left, right=right)
        return left

    def _parse_unary(self) -> Expr | None:
        if self._cur().type == TokenType.MINUS:
            self._advance()
            inner = self._parse_primary()
            if inner is None:
                return None
            return BinOpExpr(op="-", left=LiteralExpr(0), right=inner)
        return self._parse_primary()

    def _parse_primary(self) -> Expr | None:
        t = self._cur()
        if t.type == TokenType.EOF:
            return None

        if t.type == TokenType.AT:
            self._advance()
            inner = self._parse_primary()
            if inner is None:
                return AddressOfExpr(inner=VarExpr(""), loc=SourceLocation(t.line, t.col))
            return AddressOfExpr(inner=inner, loc=SourceLocation(t.line, t.col))

        if t.type == TokenType.DOT:
            self._advance()
            inner = self._parse_primary()
            if inner is None:
                return DerefExpr(inner=VarExpr(""), loc=SourceLocation(t.line, t.col))
            return DerefExpr(inner=inner, loc=SourceLocation(t.line, t.col))

        if t.type == TokenType.DOLLAR_FUNC:
            name = self._advance().value
            args: list[Expr] = []
            if self._cur().type == TokenType.LPAREN:
                self._advance()
                args = self._parse_expr_list()
                if self._cur().type == TokenType.RPAREN:
                    self._advance()
            return DollarFuncExpr(name=name, args=args, loc=SourceLocation(t.line, t.col))

        if t.type == TokenType.NUMBER:
            self._advance()
            raw = t.value.rstrip("fFrReElL")
            try:
                val = int(raw.replace("%", "0o"))
            except ValueError:
                val = 0
            return LiteralExpr(value=val, loc=SourceLocation(t.line, t.col))

        if t.type in (TokenType.STRING_LIT, TokenType.CHAR_LIT):
            self._advance()
            return LiteralExpr(value=t.value, loc=SourceLocation(t.line, t.col))

        if t.type == TokenType.LPAREN:
            self._advance()
            inner = self._try_parse_expr()
            if self._cur().type == TokenType.RPAREN:
                self._advance()
            return inner

        if t.type in (TokenType.IDENT, TokenType.KEYWORD):
            name = self._advance().value
            if self._cur().type == TokenType.LPAREN:
                self._advance()
                call_args = self._parse_expr_list()
                if self._cur().type == TokenType.RPAREN:
                    self._advance()
                return CallExpr(name=name, args=call_args, loc=SourceLocation(t.line, t.col))
            expr: Expr = VarExpr(name=name, loc=SourceLocation(t.line, t.col))
            if self._cur().type == TokenType.DOT:
                self._advance()
                if self._cur().type in (TokenType.IDENT, TokenType.KEYWORD):
                    field_name = self._advance().value
                    expr = FieldExpr(obj=expr, field_name=field_name, loc=SourceLocation(t.line, t.col))
            if self._cur().type == TokenType.LBRACK:
                self._advance()
                idx = self._try_parse_expr()
                if self._cur().type == TokenType.RBRACK:
                    self._advance()
                if idx:
                    expr = IndexExpr(array=expr, index=idx, loc=SourceLocation(t.line, t.col))
            return expr

        return None

    def _parse_expr_list(self) -> list[Expr]:
        exprs: list[Expr] = []
        while self._cur().type not in (TokenType.RPAREN, TokenType.EOF):
            e = self._try_parse_expr()
            if e:
                exprs.append(e)
            if self._cur().type == TokenType.COMMA:
                self._advance()
            elif self._cur().type not in (TokenType.RPAREN, TokenType.EOF):
                break
            elif not e:
                break
        return exprs

    def _check_recursion(self, proc: Procedure) -> bool:
        name_upper = proc.name.upper()
        for stmt in proc.body:
            if self._stmt_calls(stmt, name_upper):
                return True
        return False

    def _stmt_calls(self, stmt: Statement, name: str) -> bool:
        if isinstance(stmt, CallStmt):
            if stmt.expr.name.upper() == name:
                return True
        if isinstance(stmt, AssignStmt):
            if self._expr_calls(stmt.source, name):
                return True
        if isinstance(stmt, IfStmt):
            for s in stmt.then_body + stmt.else_body:
                if self._stmt_calls(s, name):
                    return True
        if isinstance(stmt, WhileStmt):
            for s in stmt.body:
                if self._stmt_calls(s, name):
                    return True
        if isinstance(stmt, ForStmt):
            for s in stmt.body:
                if self._stmt_calls(s, name):
                    return True
        return False

    def _expr_calls(self, expr: Expr, name: str) -> bool:
        if isinstance(expr, CallExpr):
            if expr.name.upper() == name:
                return True
            for a in expr.args:
                if self._expr_calls(a, name):
                    return True
        if isinstance(expr, BinOpExpr):
            return self._expr_calls(expr.left, name) or self._expr_calls(expr.right, name)
        return False


def ptype_fpoint(t: TalType) -> int:
    return 0

def ptype_width(t: TalType) -> int:
    return 0
