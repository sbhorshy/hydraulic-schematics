"""Narrow SysML v2 syntax parser (syntax layer only, no catalog/topology/layout).

Public API::

    parse(text: str) -> Model

Consumes the repository's narrow grammar completely and returns an AST of
dataclasses with 1-based source lines:

    package NAME { ... }
    part def NAME { ... }  |  part def NAME ;
    part NAME : TYPE ;         (typed instance part)
    part NAME { ... }          (system instance part)
    port NAME ;
    connect ENDPOINT to ENDPOINT ;   ENDPOINT = NAME ( '.' NAME )*

NAME is a plain identifier or a single-quoted long name; quoted names may
contain '//' and '/*' without being comments. The keywords package, part,
def, port, connect and to are recognized only as bare identifiers — a
quoted spelling such as 'def' or 'to' is always a plain name and is legal
in any name position. // and block comments are collected into
Model.comments with text and 1-based line numbers.

Any unknown syntax, dangling token, connect with more than two endpoints,
unterminated string/comment/brace, or duplicate member in the same scope
raises SysmlParseError carrying the 1-based line. Same names in different
scopes are legal; scope membership is preserved exactly (part-def internals
never leak into a system part).
"""

from __future__ import annotations

from collections import namedtuple
from dataclasses import dataclass, field
from typing import Dict, List, Optional

Token = namedtuple("Token", "kind value line quoted")


class SysmlParseError(Exception):
    """Parse error with the offending 1-based source line."""

    def __init__(self, message: str, line: int):
        super().__init__("line {}: {}".format(line, message))
        self.line = line


@dataclass
class Comment:
    line: int      # 1-based line where the comment starts
    text: str      # comment body without the // or /* */ markers
    kind: str      # "line" or "block"
    end_line: int  # 1-based last line the comment touches


@dataclass
class Endpoint:
    segments: List[str]  # dotted path, e.g. ['TANK-001', 'suction_out']
    line: int


@dataclass
class Connect:
    source: Endpoint
    target: Endpoint
    line: int


@dataclass
class Port:
    name: str
    line: int


@dataclass
class Part:
    name: str
    line: int
    kind: str                      # "def" | "instance" | "system"
    type_ref: Optional[List[str]]  # dotted type name for "instance", else None
    ports: List[Port] = field(default_factory=list)
    parts: List["Part"] = field(default_factory=list)
    connects: List[Connect] = field(default_factory=list)


@dataclass
class Package:
    name: str
    line: int
    packages: List["Package"] = field(default_factory=list)
    parts: List[Part] = field(default_factory=list)  # defs and instance/system parts


@dataclass
class Model:
    packages: List[Package] = field(default_factory=list)
    parts: List[Part] = field(default_factory=list)  # top-level parts, if any
    comments: List[Comment] = field(default_factory=list)


# --------------------------------------------------------------------------
# Lexer
# --------------------------------------------------------------------------

_PUNCT = "{}:;."


def _tokenize(text):
    # returns (tokens, comments); tokens are (kind, value, line), kind in
    # {"NAME", "{", "}", ":", ";", ".", "EOF"}
    if text.startswith("\ufeff"):
        text = text[1:]
    tokens: List = []
    comments: List[Comment] = []
    i, n, line = 0, len(text), 1
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if c in " \t\r\f\v":
            i += 1
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            if j == -1:
                j = n
            comments.append(Comment(line, text[i + 2:j].strip(), "line", line))
            i = j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j == -1:
                raise SysmlParseError("unterminated block comment", line)
            body = text[i + 2:j]
            end_line = line + body.count("\n")
            comments.append(Comment(line, body, "block", end_line))
            line = end_line
            i = j + 2
            continue
        if c == "'":
            j = i + 1
            while j < n and text[j] != "'" and text[j] != "\n":
                j += 1
            if j >= n or text[j] == "\n":
                raise SysmlParseError("unterminated quoted name", line)
            tokens.append(Token("NAME", text[i + 1:j], line, True))
            i = j + 1
            continue
        if c.isalpha() or c == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            tokens.append(Token("NAME", text[i:j], line, False))
            i = j
            continue
        if c in _PUNCT:
            tokens.append(Token(c, c, line, False))
            i += 1
            continue
        raise SysmlParseError("unexpected character {!r}".format(c), line)
    tokens.append(Token("EOF", "", line, False))
    return tokens, comments


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

def _is_kw(tok, word):
    """True only for a *bare* (unquoted) identifier token equal to *word*;
    a quoted long name like 'part' or 'to' is always a plain name."""
    return tok[0] == "NAME" and not tok.quoted and tok[1] == word


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos]

    def advance(self):
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, kind, what):
        tok = self.advance()
        if tok[0] != kind:
            shown = "end of input" if tok[0] == "EOF" else repr(tok[1])
            raise SysmlParseError("expected {}, found {}".format(what, shown), tok[2])
        return tok

    def name_token(self, where):
        tok = self.advance()
        if tok[0] != "NAME":
            shown = "end of input" if tok[0] == "EOF" else repr(tok[1])
            raise SysmlParseError("expected name in {}, found {}".format(where, shown), tok[2])
        return tok

    def keyword(self, word):
        """Consume a bare identifier token equal to *word*, or raise."""
        tok = self.advance()
        if not _is_kw(tok, word):
            shown = "end of input" if tok[0] == "EOF" else repr(tok[1])
            raise SysmlParseError("expected {!r}, found {}".format(word, shown), tok[2])
        return tok

    def dotted_name(self, where):
        segments = [self.name_token(where).value]
        while self.peek()[0] == ".":
            self.advance()
            segments.append(self.name_token(where).value)
        return segments

    def _declare(self, seen: Dict[str, str], name: str, kind: str, line: int):
        if name in seen:
            raise SysmlParseError(
                "duplicate member {!r} in the same scope (already declared as {})".format(
                    name, seen[name]),
                line)
        seen[name] = kind

    # -- top level ---------------------------------------------------------

    def parse_model(self) -> Model:
        model = Model()
        seen: Dict[str, str] = {}
        while True:
            tok = self.peek()
            if tok[0] == "EOF":
                return model
            if _is_kw(tok, "package"):
                package = self.parse_package()
                self._declare(seen, package.name, "package", package.line)
                model.packages.append(package)
            elif _is_kw(tok, "part"):
                part = self.parse_part()
                self._declare(seen, part.name, "part", part.line)
                model.parts.append(part)
            else:
                shown = "end of input" if tok[0] == "EOF" else repr(tok[1])
                raise SysmlParseError(
                    "unexpected token {}; expected 'package' or 'part'".format(shown), tok[2])

    # -- package -----------------------------------------------------------

    def parse_package(self) -> Package:
        kw = self.keyword("package")
        name_tok = self.name_token("package name")
        self.expect("{", "'{' after package name")
        package = Package(name=name_tok.value, line=kw[2])
        seen: Dict[str, str] = {}
        while True:
            tok = self.peek()
            if tok[0] == "}":
                self.advance()
                return package
            if tok[0] == "EOF":
                raise SysmlParseError("unterminated package body, expected '}'", tok[2])
            if _is_kw(tok, "package"):
                child = self.parse_package()
                self._declare(seen, child.name, "package", child.line)
                package.packages.append(child)
            elif _is_kw(tok, "part"):
                part = self.parse_part()
                self._declare(seen, part.name, "part", part.line)
                package.parts.append(part)
            else:
                shown = "end of input" if tok[0] == "EOF" else repr(tok[1])
                raise SysmlParseError(
                    "unexpected token {} in package body; expected 'package' or 'part'".format(shown),
                    tok[2])

    # -- part --------------------------------------------------------------

    def parse_part(self) -> Part:
        kw = self.keyword("part")
        is_def = False
        tok = self.peek()
        if _is_kw(tok, "def"):
            self.advance()
            is_def = True
        name_tok = self.name_token("part name")
        part = Part(name=name_tok.value, line=kw[2],
                    kind="def" if is_def else "system", type_ref=None)
        tok = self.peek()
        if is_def:
            if tok[0] == "{":
                self.parse_part_body(part)
            elif tok[0] == ";":
                self.advance()
            else:
                shown = "end of input" if tok[0] == "EOF" else repr(tok[1])
                raise SysmlParseError(
                    "expected '{{' or ';' after part def name, found {}".format(shown), tok[2])
            return part
        if tok[0] == ":":
            self.advance()
            part.kind = "instance"
            part.type_ref = self.dotted_name("part type reference")
            self.expect(";", "';' after typed part")
            return part
        if tok[0] == "{":
            self.parse_part_body(part)
            return part
        shown = "end of input" if tok[0] == "EOF" else repr(tok[1])
        raise SysmlParseError(
            "expected ':', '{{' or ';' after part name, found {}".format(shown), tok[2])

    def parse_part_body(self, part: Part):
        self.expect("{", "'{'")
        seen: Dict[str, str] = {}
        while True:
            tok = self.peek()
            if tok[0] == "}":
                self.advance()
                return
            if tok[0] == "EOF":
                raise SysmlParseError(
                    "unterminated body of part {!r}, expected '}}'".format(part.name), tok[2])
            if _is_kw(tok, "port"):
                self.advance()
                name_tok = self.name_token("port name")
                self.expect(";", "';' after port name")
                self._declare(seen, name_tok.value, "port", name_tok.line)
                part.ports.append(Port(name_tok.value, name_tok.line))
            elif _is_kw(tok, "part"):
                child = self.parse_part()
                self._declare(seen, child.name, "part", child.line)
                part.parts.append(child)
            elif _is_kw(tok, "connect"):
                part.connects.append(self.parse_connect())
            else:
                shown = "end of input" if tok[0] == "EOF" else repr(tok[1])
                raise SysmlParseError(
                    "unexpected token {} in part body; expected 'port', 'part' or 'connect'".format(shown),
                    tok[2])

    # -- connect -----------------------------------------------------------

    def parse_connect(self) -> Connect:
        kw = self.keyword("connect")
        source = self.parse_endpoint()
        self.keyword("to")
        target = self.parse_endpoint()
        tok = self.peek()
        if _is_kw(tok, "to"):
            raise SysmlParseError(
                "connect supports exactly two endpoints (binary only); "
                "extra 'to' clause at this line", tok[2])
        self.expect(";", "';' after connect")
        return Connect(source=source, target=target, line=kw[2])

    def parse_endpoint(self) -> Endpoint:
        first = self.name_token("connect endpoint")
        segments = [first.value]
        while self.peek()[0] == ".":
            self.advance()
            segments.append(self.name_token("name after '.' in endpoint").value)
        return Endpoint(segments=segments, line=first.line)


def parse(text: str) -> Model:
    """Parse *text* (narrow SysML grammar, see module docstring) into a Model.

    Raises SysmlParseError with a 1-based line for any malformed input.
    """
    tokens, comments = _tokenize(text)
    parser = _Parser(tokens)
    model = parser.parse_model()
    model.comments = comments
    return model
