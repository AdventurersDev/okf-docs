#!/usr/bin/env python3
"""okf-docs helper for Open Knowledge Format (OKF) v0.3 bundles.

The deterministic part of the okf-docs skill: find bundles, check them against
the OKF spec and the house rules, generate index.md files and log.md entries,
lint prose for bloat, build the re-check queue, rank files for a question,
upgrade older formats (v3 and OKF 0.2), and run the session-start and edit hooks. Standard library only, Python 3.8+.

Exit status: 0 on success; 1 when `check` finds OKF errors or a command fails;
2 on a usage error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

VERSION = "1.0.5"
AGENT_ACTOR = "okf-docs/" + VERSION
OKF_VERSION = "0.3"
OKF_VERSION_TUPLE = (0, 3)
EXT_PREFIX = "x-okfdocs-"  # OKF 0.3 section 4.1: extension keys carry the producer name
EXT_NAMES = ("scope", "specificity", "class", "visibility", "supersedes")  # the 0.9 names, unprefixed
CREDIBILITY_KEYS = ("x-okfdocs-credibility", "credibility")  # retired in 1.0.4: OKF 0.3 keeps signals in `sources`
VIA_VALUES = ("chat", "review")  # x-okfdocs-via on a human `verified` entry: how the person confirmed it
CONFIG_REL = Path(".okf") / "config.yaml"
UTC = dt.timezone.utc
RESERVED = ("index.md", "log.md")
SKIP_DIRS = {
    ".git", ".hg", ".svn", ".okf", "node_modules", ".venv", "venv", "__pycache__",
    "dist", "build", ".next", ".nuxt", "vendor", "target", ".cache", ".idea", ".vscode",
}
MODULES = ("core", "code", "brain", "publish")
KINDS = ("docs", "brain", "site", "other")

try:  # optional; used only for YAML the built-in parser can't read
    import yaml as _pyyaml  # type: ignore
except Exception:  # pragma: no cover - depends on the machine
    _pyyaml = None


# --------------------------------------------------------------------------
# YAML subset: block and flow mappings and sequences, plain, quoted and block
# scalars, comments. Enough for frontmatter and config files.
# --------------------------------------------------------------------------

class YAMLError(ValueError):
    """YAML the parser can't read."""


class _Incomplete(Exception):
    """A flow collection or quoted scalar continues on the next line."""


# YAML 1.2 core schema (OKF 0.3 section 4).
_INT_RE = re.compile(r"^[-+]?[0-9]+$")
_OCT_RE = re.compile(r"^0o[0-7]+$")
_HEX_RE = re.compile(r"^0x[0-9a-fA-F]+$")
_FLOAT_RE = re.compile(r"^[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?$")
_INF_RE = re.compile(r"^[-+]?\.(?:inf|Inf|INF)$")
_NAN_RE = re.compile(r"^\.(?:nan|NaN|NAN)$")
_ESCAPES = {
    "0": "\0", "a": "\a", "b": "\b", "t": "\t", "n": "\n", "v": "\v", "f": "\f", "r": "\r",
    "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\", "N": "\x85", "_": "\xa0",
    "L": " ", "P": " ",
}


def _resolve_plain(text):
    t = text.strip()
    if t in ("", "~", "null", "Null", "NULL"):
        return None
    if t in ("true", "True", "TRUE"):
        return True
    if t in ("false", "False", "FALSE"):
        return False
    if _INT_RE.match(t):
        return int(t)
    if _OCT_RE.match(t):
        return int(t[2:], 8)
    if _HEX_RE.match(t):
        return int(t[2:], 16)
    if _FLOAT_RE.match(t):
        return float(t)
    if _INF_RE.match(t):
        return float("-inf") if t.startswith("-") else float("inf")
    if _NAN_RE.match(t):
        return float("nan")
    return t


# How YAML 1.1 parsers (PyYAML, the OKF reference validator) read a plain scalar, for the values where
# that differs from YAML 1.2: yes/no/on/off, 1:20, 010, 1_000, 0b101, 1e3.
_Y11_NULL_RE = re.compile(r"^(?:~|null|Null|NULL|)$")
_Y11_BOOL_RE = re.compile(r"^(?:yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF)$")
_Y11_INT_RE = re.compile(r"^(?:[-+]?0b[0-1_]+|[-+]?0[0-7_]+|[-+]?(?:0|[1-9][0-9_]*)|[-+]?0x[0-9a-fA-F_]+"
                         r"|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$")
_Y11_FLOAT_RE = re.compile(r"^(?:[-+]?[0-9][0-9_]*\.[0-9_]*(?:[eE][-+][0-9]+)?|\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?"
                           r"|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$")


def _yaml11_plain(t):
    if _Y11_NULL_RE.match(t):
        return None
    if _Y11_BOOL_RE.match(t):
        return t.lower() in ("yes", "true", "on")
    if _Y11_INT_RE.match(t):
        v, sign = t.replace("_", ""), 1
        if v[0] in "+-":
            sign, v = (-1 if v[0] == "-" else 1), v[1:]
        if ":" in v:
            n = 0
            for part in v.split(":"):
                n = n * 60 + int(part)
        elif v.startswith("0b"):
            n = int(v[2:], 2)
        elif v.startswith("0x"):
            n = int(v[2:], 16)
        elif len(v) > 1 and v[0] == "0":
            n = int(v, 8)
        else:
            n = int(v)
        return sign * n
    if _Y11_FLOAT_RE.match(t):
        v = t.replace("_", "")
        if ":" in v:
            return ("sexagesimal", v)
        if v.lstrip("+-").lower() == ".inf":
            return float("-inf") if v.startswith("-") else float("inf")
        return float("nan") if v.lower() == ".nan" else float(v)
    return t


def yaml11_differs(text):
    """True when a YAML 1.1 parser reads this plain scalar differently than YAML 1.2 does."""
    t = text.strip()
    a, b = _resolve_plain(t), _yaml11_plain(t)
    if isinstance(a, float) and isinstance(b, float) and a != a and b != b:
        return False  # both NaN
    return type(a) is not type(b) or a != b


def _yaml11_warning(line, text):
    t = text.strip()
    return ("line %d: unquoted `%s` reads as %r in YAML 1.2 but as %r in YAML 1.1 tools such as PyYAML; "
            "quote it (OKF 0.3 section 4)" % (line, t, _resolve_plain(t), _yaml11_plain(t)))


YAML11_NOTE = "in YAML 1.1 tools"


def _unescape(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            if n in _ESCAPES:
                out.append(_ESCAPES[n])
                i += 2
                continue
            width = {"x": 2, "u": 4, "U": 8}.get(n)
            if width:
                try:
                    out.append(chr(int(s[i + 2:i + 2 + width], 16)))
                    i += 2 + width
                    continue
                except ValueError:
                    pass
            out.append(n)
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _find_close(s, quote):
    """Index of the closing quote in s (s starts after the opening quote), or -1."""
    i = 0
    while i < len(s):
        c = s[i]
        if quote == '"' and c == "\\":
            i += 2
            continue
        if c == quote:
            if quote == "'" and i + 1 < len(s) and s[i + 1] == "'":
                i += 2
                continue
            return i
        i += 1
    return -1


def _is_dash(content):
    return content == "-" or content.startswith("- ") or content.startswith("-\t")


def _map_sep(content):
    """Index of the ':' that ends a block mapping key on this line, or -1."""
    if not content or content[0] in "[{#|>":
        return -1
    if content[0] in "\"'":
        end = _find_close(content[1:], content[0])
        if end < 0:
            return -1
        k = end + 2
        while k < len(content) and content[k] in " \t":
            k += 1
        if k < len(content) and content[k] == ":" and (k + 1 == len(content) or content[k + 1] in " \t"):
            return k
        return -1
    j = 0
    while True:
        j = content.find(":", j)
        if j < 0:
            return -1
        if j + 1 == len(content) or content[j + 1] in " \t":
            if re.search(r"[ \t]#", content[:j]):
                return -1
            return j
        j += 1


def _strip_comment(s):
    if s.startswith("#"):
        return ""
    m = re.search(r"[ \t]#", s)
    return s[:m.start()] if m else s


def _fold(lines):
    out, prev = "", None
    for line in lines:
        if line == "":
            out += "\n"
            prev = "blank"
        elif line[:1] in (" ", "\t"):
            if prev == "text":
                out += "\n"
            out += line + "\n"
            prev = "more"
        else:
            if prev == "text":
                out += " "
            out += line
            prev = "text"
    return out


class _Flow:
    def __init__(self, s):
        self.s = s
        self.i = 0
        self.colon = False  # a plain scalar held ':', which libyaml < 0.2.2 and PyYAML < 5.1 reject here
        self.yaml11 = []  # plain scalars that YAML 1.1 parsers read differently

    def peek(self):
        while self.i < len(self.s) and self.s[self.i] in " \t":
            self.i += 1
        if self.i >= len(self.s):
            raise _Incomplete()
        return self.s[self.i]

    def value(self, key=False):
        c = self.peek()
        if c == "[":
            return self.seq()
        if c == "{":
            return self.map()
        if c in "\"'":
            end = _find_close(self.s[self.i + 1:], c)
            if end < 0:
                raise _Incomplete()
            raw = self.s[self.i + 1:self.i + 1 + end]
            self.i += end + 2
            return _unescape(raw) if c == '"' else raw.replace("''", "'")
        start = self.i
        while self.i < len(self.s):
            ch = self.s[self.i]
            if ch in ",]}":
                break
            if key and ch == ":" and (self.i + 1 >= len(self.s) or self.s[self.i + 1] in " \t,]}"):
                break
            self.i += 1
        if self.i >= len(self.s):
            raise _Incomplete()
        text = self.s[start:self.i]
        if ":" in text:
            self.colon = True
        if yaml11_differs(text):
            self.yaml11.append(text)
        return _resolve_plain(text)

    def seq(self):
        self.i += 1
        out = []
        while True:
            c = self.peek()
            if c == "]":
                self.i += 1
                return out
            if c == ",":
                self.i += 1
                continue
            out.append(self.value())
            if self.peek() not in ",]":
                raise YAMLError("expected ',' or ']' in a flow list")

    def map(self):
        self.i += 1
        out = {}
        while True:
            c = self.peek()
            if c == "}":
                self.i += 1
                return out
            if c == ",":
                self.i += 1
                continue
            key = self.value(key=True)
            val = None
            if self.peek() == ":":
                self.i += 1
                if self.peek() not in ",}":
                    val = self.value()
            out["" if key is None else str(key)] = val
            if self.peek() not in ",}":
                raise YAMLError("expected ',' or '}' in a flow mapping")


class _Parser:
    def __init__(self, text, line_offset=0):
        self.lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.n = len(self.lines)
        self.offset = line_offset
        self.warnings = []

    def err(self, i, msg):
        return YAMLError("line %d: %s" % (i + 1 + self.offset, msg))

    def indent(self, i):
        line = self.lines[i]
        rest = line.lstrip(" ")
        if rest[:1] == "\t" and rest.strip():
            raise self.err(i, "tab used for indentation")
        return len(line) - len(rest)

    def next_significant(self, i):
        while i < self.n:
            s = self.lines[i].strip()
            if s and not s.startswith("#"):
                return i
            i += 1
        return i

    def parse(self):
        i = self.next_significant(0)
        if i >= self.n:
            return None
        value, i = self.node(i, self.indent(i))
        i = self.next_significant(i)
        if i < self.n:
            raise self.err(i, "unexpected content")
        return value

    def node(self, i, ind):
        content = self.lines[i][ind:]
        if _is_dash(content):
            return self.sequence(i, ind)
        if _map_sep(content) >= 0:
            return self.mapping(i, ind)
        return self.value(i, content, ind)

    def mapping(self, i, ind):
        result = {}
        while True:
            i = self.next_significant(i)
            if i >= self.n:
                break
            cur = self.indent(i)
            if cur < ind:
                break
            if cur > ind:
                raise self.err(i, "unexpected indentation")
            content = self.lines[i][ind:]
            if _is_dash(content):
                break
            sep = _map_sep(content)
            if sep < 0:
                raise self.err(i, "expected 'key: value'")
            key = content[:sep].strip()
            if key[:1] == '"':
                key = _unescape(key[1:-1])
            elif key[:1] == "'":
                key = key[1:-1].replace("''", "'")
            if key in result:
                self.warnings.append("line %d: duplicate key '%s'" % (i + 1 + self.offset, key))
            result[key], i = self.after_key(i, ind, content[sep + 1:])
        return result, i

    def after_key(self, i, ind, rest):
        s = rest.strip()
        if not s or s.startswith("#"):
            j = self.next_significant(i + 1)
            if j < self.n:
                nind = self.indent(j)
                if nind > ind:
                    return self.node(j, nind)
                if nind == ind and _is_dash(self.lines[j][ind:]):
                    return self.sequence(j, ind)
            return None, i + 1
        return self.value(i, rest, ind + 1)

    def sequence(self, i, ind):
        result = []
        while True:
            i = self.next_significant(i)
            if i >= self.n:
                break
            cur = self.indent(i)
            if cur < ind:
                break
            if cur > ind:
                raise self.err(i, "unexpected indentation")
            content = self.lines[i][ind:]
            if not _is_dash(content):
                break
            after = content[1:]
            body = after.lstrip(" \t")
            if not body or body.startswith("#"):
                j = self.next_significant(i + 1)
                if j < self.n and self.indent(j) > ind:
                    item, i = self.node(j, self.indent(j))
                else:
                    item, i = None, i + 1
                result.append(item)
                continue
            col = ind + 1 + (len(after) - len(body))
            if _is_dash(body) or _map_sep(body) >= 0:
                self.lines[i] = " " * col + body
                item, i = self.node(i, col)
            else:
                item, i = self.value(i, body, ind + 1)
            result.append(item)
        return result, i

    def value(self, i, text, cont_min):
        s = text.strip()
        if s[:1] in ("&", "*", "!"):
            raise self.err(i, "anchors, aliases and tags are not supported")
        if s[:1] in ("|", ">"):
            return self.block_scalar(i, s, cont_min)
        if s[:1] in ("[", "{"):
            return self.flow(i, s)
        if s[:1] in ('"', "'"):
            return self.quoted(i, s)
        return self.plain(i, s, cont_min)

    def plain(self, i, text, cont_min):
        first = _strip_comment(text).strip()
        parts = [first]
        j = i + 1
        while j < self.n:
            s = self.lines[j].strip()
            if not s:
                k = j
                while k < self.n and not self.lines[k].strip():
                    k += 1
                if k < self.n and not self.lines[k].strip().startswith("#") and self.indent(k) >= cont_min:
                    parts.append("\n" * (k - j))
                    j = k
                    continue
                break
            if s.startswith("#") or self.indent(j) < cont_min:
                break
            parts.append(_strip_comment(s).strip())
            j += 1
        if len(parts) == 1:
            if ": " in first or first.endswith(":"):
                self.warnings.append(
                    "line %d: unquoted value contains ': '; quote it so strict YAML parsers accept it"
                    % (i + 1 + self.offset))
            if yaml11_differs(first):
                self.warnings.append(_yaml11_warning(i + 1 + self.offset, first))
            return _resolve_plain(first), j
        out, newlines = parts[0], 0
        for p in parts[1:]:
            if p.startswith("\n"):
                newlines += len(p)
                continue
            out += ("\n" * newlines + p) if newlines else (" " + p)
            newlines = 0
        return out, j

    def quoted(self, i, s):
        q, buf, pieces, j = s[0], s[1:], [], i
        while True:
            end = _find_close(buf, q)
            if end >= 0:
                pieces.append(buf[:end])
                tail = buf[end + 1:].strip()
                if tail and not tail.startswith("#"):
                    raise self.err(j, "unexpected text after a quoted value")
                break
            pieces.append(buf.rstrip())
            j += 1
            if j >= self.n:
                raise self.err(i, "unterminated quoted value")
            buf = self.lines[j].strip()
        text = pieces[0]
        for piece in pieces[1:]:
            if piece == "":
                text += "\n"
            elif text.endswith("\n"):
                text += piece
            else:
                text += " " + piece
        return (_unescape(text) if q == '"' else text.replace("''", "'")), j + 1

    def flow(self, i, s):
        buf, j = s, i
        while True:
            parser = _Flow(buf)
            try:
                value = parser.value()
            except _Incomplete:
                j += 1
                if j >= self.n:
                    raise self.err(i, "unterminated [ or {")
                buf += " " + _strip_comment(self.lines[j].strip())
                continue
            except YAMLError as exc:
                raise self.err(j, str(exc))
            tail = buf[parser.i:].strip()
            if tail and not tail.startswith("#"):
                raise self.err(j, "unexpected text after a flow value")
            if parser.colon:
                self.warnings.append(
                    "line %d: unquoted value with ':' inside [ ] or { } breaks some YAML parsers; "
                    "quote it or use block style" % (i + 1 + self.offset))
            for text in parser.yaml11:
                self.warnings.append(_yaml11_warning(i + 1 + self.offset, text))
            return value, j + 1

    def block_scalar(self, i, header, cont_min):
        style, chomp, explicit = header[0], "clip", None
        for ch in header[1:]:
            if ch == "-":
                chomp = "strip"
            elif ch == "+":
                chomp = "keep"
            elif ch.isdigit() and ch != "0":
                explicit = int(ch)
            elif ch in " \t#":
                break
            else:
                raise self.err(i, "bad block scalar header")
        block_ind = (cont_min - 1 + explicit) if explicit else None
        lines, j = [], i + 1
        while j < self.n:
            line = self.lines[j]
            if not line.strip():
                lines.append("")
                j += 1
                continue
            ind = len(line) - len(line.lstrip(" "))
            if block_ind is None:
                if ind < cont_min:
                    break
                block_ind = ind
            if ind < block_ind:
                break
            lines.append(line[block_ind:])
            j += 1
        trailing = 0
        while lines and lines[-1] == "":
            lines.pop()
            trailing += 1
        if not lines:
            return ("\n" * trailing if chomp == "keep" else ""), j
        text = "\n".join(lines) if style == "|" else _fold(lines)
        if chomp == "clip":
            text += "\n"
        elif chomp == "keep":
            text += "\n" * (trailing + 1)
        return text, j


def _pyyaml_load(text):
    class _Loader(_pyyaml.SafeLoader):  # type: ignore[name-defined]
        pass
    _Loader.yaml_implicit_resolvers = {
        k: [r for r in v if r[0] != "tag:yaml.org,2002:timestamp"]
        for k, v in _pyyaml.SafeLoader.yaml_implicit_resolvers.items()
    }
    return _pyyaml.load(text, Loader=_Loader)


def yaml_load(text, line_offset=0):
    """Parse YAML text. Returns (value, warnings). Raises YAMLError."""
    parser = _Parser(text, line_offset)
    try:
        return parser.parse(), parser.warnings
    except YAMLError:
        if _pyyaml is None:
            raise
        try:
            return _pyyaml_load(text), []
        except Exception as exc:  # noqa: BLE001 - any PyYAML failure means invalid YAML
            raise YAMLError((str(exc).splitlines() or ["invalid YAML"])[0])


_YAML11_RE = re.compile(
    r"^(?:y|n|yes|no|on|off|[-+]?\.(?:inf|nan)|[-+]?0[xo][0-9a-f_]+|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+(?:\.[0-9_]*)?"
    r"|[-+]?(?:[0-9][0-9_]*(?:\.[0-9_]*)?|\.[0-9_]+)(?:e[-+]?[0-9]+)?)$", re.I)


def _needs_quotes(s):
    """True when a string must be quoted to read back as the same string in YAML 1.1 and 1.2 parsers."""
    if s == "" or s != s.strip() or "\n" in s or "\t" in s:
        return True
    if s[0] in "-?:,[]{}#&*!|>'\"%@`":
        return True
    if ": " in s or " #" in s or s.endswith(":"):
        return True
    return _resolve_plain(s) != s or bool(_YAML11_RE.match(s))


def _dump_scalar(v):
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v)
    return json.dumps(s, ensure_ascii=False) if _needs_quotes(s) else s


def _flow_scalar(v):
    """A scalar inside [ ]. Quoted when it holds a character that older parsers misread there:
    libyaml before 0.2.2 and PyYAML before 5.1 reject any ':' in a plain scalar inside [ ] or { }."""
    s = _dump_scalar(v)
    if not s.startswith('"') and any(c in s for c in ",[]{}:#"):
        return json.dumps(str(v), ensure_ascii=False)
    return s


def _key(k):
    k = str(k)
    return json.dumps(k, ensure_ascii=False) if _needs_quotes(k) else k


def _flow_list(value):
    """`[a, b]` for a list of plain scalars; None when an item is a mapping, a list or multi-line text."""
    parts = []
    for v in value:
        if isinstance(v, (dict, list)) or (isinstance(v, str) and "\n" in v):
            return None
        parts.append(_flow_scalar(v))
    return "[" + ", ".join(parts) + "]"


def yaml_dump(data, indent=0):
    """Serialize a mapping as YAML lines in the house style: mappings always in block style,
    lists of scalars as `[a, b]`, everything else in block style."""
    lines = []
    for key, value in data.items():
        lines.extend(_dump_entry(" " * indent + _key(key) + ":", value, indent))
    return lines


def _literal_ok(s):
    return not s.startswith((" ", "\n")) and not s.endswith("\n\n") and "\r" not in s


def _dump_entry(prefix, value, indent):
    if value is None:
        return [prefix]
    if isinstance(value, dict):
        if not value:
            return [prefix + " {}"]
        return [prefix] + yaml_dump(value, indent + 2)
    if isinstance(value, list):
        if not value:
            return [prefix + " []"]
        flow = _flow_list(value)
        if flow is not None and len(prefix) + len(flow) < 100:
            return [prefix + " " + flow]
        out = [prefix]
        for item in value:
            out.extend(_dump_item(item, indent + 2))
        return out
    if isinstance(value, str) and "\n" in value and _literal_ok(value):
        out = [prefix + (" |" if value.endswith("\n") else " |-")]
        for line in value.rstrip("\n").split("\n"):
            out.append((" " * (indent + 2) + line) if line else "")
        return out
    return [prefix + " " + _dump_scalar(value)]


def _dump_item(item, indent):
    pad = " " * indent
    if isinstance(item, (dict, list)) and not item:
        return [pad + "- " + ("{}" if isinstance(item, dict) else "[]")]
    if isinstance(item, dict):
        sub = yaml_dump(item, indent + 2)
    elif isinstance(item, list):
        flow = _flow_list(item)
        if flow is not None:
            return [pad + "- " + flow]
        sub = []
        for x in item:
            sub.extend(_dump_item(x, indent + 2))
    else:
        return [pad + "- " + _dump_scalar(item)]
    sub[0] = pad + "- " + sub[0][indent + 2:]
    return sub


# --------------------------------------------------------------------------
# Time and durations
# --------------------------------------------------------------------------

_TS_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[Tt ](\d{2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?\s*(Z|z|[+-]\d{2}(?::?\d{2})?)?$")
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
DATE_ONLY = "date without time and offset"
NO_OFFSET = "no UTC offset"


def parse_ts(value):
    """Parse an OKF timestamp. Returns (aware datetime or None, problem or None)."""
    if value is None or value == "":
        return None, "missing"
    if isinstance(value, dt.datetime):
        return (value.replace(tzinfo=UTC), NO_OFFSET) if value.tzinfo is None else (value, None)
    if isinstance(value, dt.date):
        return dt.datetime(value.year, value.month, value.day, tzinfo=UTC), DATE_ONLY
    s = str(value).strip()
    m = _TS_RE.match(s)
    if m:
        y, mo, d, h, mi, sec, frac, off = m.groups()
        try:
            base = dt.datetime(int(y), int(mo), int(d), int(h), int(mi), int(sec or 0),
                               int((frac or "0")[:6].ljust(6, "0")))
        except ValueError:
            return None, "not a valid date"
        if not off:
            return base.astimezone(), NO_OFFSET
        if off in "Zz":
            return base.replace(tzinfo=UTC), None
        digits = off[1:].replace(":", "")
        delta = dt.timedelta(hours=int(digits[:2]), minutes=int(digits[2:4] or 0))
        return base.replace(tzinfo=dt.timezone(delta if off[0] == "+" else -delta)), None
    m = _DATE_RE.match(s)
    if m:
        try:
            return dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=UTC), DATE_ONLY
        except ValueError:
            return None, "not a valid date"
    return None, "not an ISO 8601 datetime"


def now():
    return dt.datetime.now().astimezone().replace(microsecond=0)


_DUR_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(d|days?|w|weeks?|mo|months?|m|y|years?)$")


def parse_duration(value):
    """A duration such as 90d, 6w, 12mo or 2y, in days. math.inf for never; None if unreadable."""
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in ("never", "none", "off", "inf", "infinite", "false"):
        return math.inf
    m = _DUR_RE.match(s)
    if not m:
        return None
    unit = m.group(2)
    days = 30.44 if unit.startswith("mo") or unit == "m" else {"d": 1, "w": 7, "y": 365.25}[unit[0]]
    return float(m.group(1)) * days


def fmt_date(d):
    return d.astimezone().strftime("%Y-%m-%d") if d else "?"


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def norm(p):
    return os.path.normcase(os.path.normpath(str(p)))


def write_lf(path, text):
    """Write UTF-8 text with LF line endings on every OS (Windows would otherwise write CRLF)."""
    with open(str(path), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def relpath(p, base):
    try:
        return os.path.relpath(str(p), str(base)).replace(os.sep, "/")
    except ValueError:  # different drive on Windows
        return str(p)


def is_within(p, root):
    a, b = norm(p), norm(root)
    return a == b or a.startswith(b.rstrip(os.sep) + os.sep)


def home_path(p):
    """A path under the home folder as ~/…, with / on every OS, so messages read the same on Windows."""
    try:
        return "~/" + Path(p).relative_to(Path.home()).as_posix()
    except ValueError:
        return Path(p).as_posix()


def humanize(name):
    acronyms = {"api": "API", "apis": "APIs", "faq": "FAQ", "ui": "UI", "ux": "UX", "sdk": "SDK",
                "cli": "CLI", "adr": "ADR", "okf": "OKF", "id": "ID", "url": "URL"}
    words = re.split(r"[-_ ]+", name)
    out = [acronyms.get(w.lower(), w) for w in words if w]
    if out and out[0] == out[0].lower():
        out[0] = out[0][:1].upper() + out[0][1:]
    return " ".join(out) or name


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s or "unknown"


def run_git(args, cwd, timeout=20):
    try:
        res = subprocess.run(["git", "-c", "core.quotePath=false"] + list(args), cwd=str(cwd),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    return res.stdout.decode("utf-8", "replace")


def git_toplevel(path):
    out = run_git(["rev-parse", "--show-toplevel"], path)
    return Path(out.strip()).resolve() if out and out.strip() else None


def git_config(key, cwd):
    out = run_git(["config", "--get", key], cwd)
    return out.strip() if out and out.strip() else None


_GITHUB_REMOTE_RE = re.compile(r"github\.com[:/]+([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")


def github_remotes(root):
    """owner/repo for each GitHub remote of the repository at root, origin first; [] when git can't run."""
    out = run_git(["remote", "-v"], root)
    found = []
    for line in (out or "").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        m = _GITHUB_REMOTE_RE.search(parts[1])
        if m:
            found.append((parts[0] != "origin", "%s/%s" % (m.group(1), m.group(2))))
    seen = []
    for _, repo in sorted(found, key=lambda x: x[0]):
        if repo not in seen:
            seen.append(repo)
    return seen


def dot_git(path):
    """The nearest .git at or above path. Tells a repository where git can't run apart from no repository."""
    p = Path(path).resolve()
    for d in [p] + list(p.parents):
        if (d / ".git").exists():
            return d / ".git"
    return None


def mtime(p):
    try:
        return dt.datetime.fromtimestamp(p.stat().st_mtime, tz=UTC)
    except OSError:
        return None


_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_DRIVE_RE = re.compile(r"^[a-zA-Z]:[\\/]")


def is_url(target):
    return bool(_SCHEME_RE.match(target)) and not _DRIVE_RE.match(target)


def is_descriptor(resource):
    """A sources entry that names a scope or origin rather than a file ("pasted in conversation")."""
    r = resource.strip()
    if is_url(r):
        return False
    return ("/" not in r and "." not in r) or (" " in r and "/" not in r)


def is_compared_ts(key):
    """True for the timestamps that consumers compare with each other: generated.at and verified[n].at
    (a key as iter_timestamps yields it)."""
    return key == "generated.at" or (key.startswith("verified[") and key.endswith(".at"))


def blank(value):
    """OKF 0.3 section 11.2: null, an empty string and an empty list mean the key is absent."""
    return value is None or (isinstance(value, (str, list)) and len(value) == 0)


def as_list(value):
    """One item stands for a list with one item; a blank value is an empty list."""
    if blank(value):
        return []
    return value if isinstance(value, list) else [value]


def version_tuple(value):
    """(0, 3) for "0.3"; None when the value isn't dotted integers."""
    try:
        return tuple(int(part) for part in str(value).strip().split("."))
    except ValueError:
        return None


def ext_key(name):
    return EXT_PREFIX + name


# --------------------------------------------------------------------------
# Project, bundles, documents
# --------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "modules": [],
    "bundles": [],
    "related": {},
    "links": "relative",
    "hooks": {"session": True, "max_findings": 5},  # edits, capture: see hook_on()
    "decay": {
        "default": "12mo", "observation": "3mo", "runbook": "6mo", "decision": "never",
        "asset": "never", "release": "never", "update": "never",
    },
    "retention": {"raw_files": "24mo"},
    "brain": {"actions": "report", "names": "team", "tickets": {"system": "none", "target": ""}},
}
BRAIN_CHOICES = {"actions": ("report", "track", "off"), "names": ("team", "roles", "all")}
# brain.tickets.system: the ticket system meeting actions sync to, through the connector the user has in their
# agent. Any short name works (linear, jira, github, asana, clickup, monday, ...); none switches sync off.
_TICKET_SYSTEM_RE = re.compile(r"^[a-z0-9][a-z0-9 ._-]{0,39}$")
TICKETS_OFF = ("none", "off", "no", "false")
GITHUB_SYSTEMS = ("github", "github issues", "github-issues", "gh")  # the gh CLI fallback applies to these


HOOK_SWITCHES = ("session", "edits", "capture", "enabled")


def as_flag(value):
    """True or False for a YAML on/off value (true/yes/on/1, false/no/off/0), None for anything else."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "yes", "on", "1"):
            return True
        if v in ("false", "no", "off", "0"):
            return False
    return None


def hook_on(config, name):
    """Whether a hook is on. session defaults to on, edits and capture to off; `enabled` is the old name for edits.
    A value that isn't an on/off value means the default (validate_config reports it)."""
    hooks = config.get("hooks")
    default = name == "session"
    if not isinstance(hooks, dict):
        return default
    if name == "edits" and "edits" not in hooks:
        name = "enabled"
    flag = as_flag(hooks.get(name))
    return default if flag is None else flag


def _merge(base, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = dict(base[k])
            base[k].update(v)
        else:
            base[k] = v
    return base


def split_frontmatter(text):
    """Return (frontmatter text or None, body, first body line number, problem or None)."""
    if text.startswith("﻿"):
        text = text[1:]
    lines = text.split("\n")
    if not lines or lines[0].rstrip("\r").rstrip() != "---":
        return None, text, 1, None
    for idx in range(1, len(lines)):
        if lines[idx].rstrip("\r").rstrip() in ("---", "..."):
            fm = "\n".join(line.rstrip("\r") for line in lines[1:idx])
            return fm, "\n".join(lines[idx + 1:]), idx + 2, None
    return None, text, 1, ("fm-unterminated", "frontmatter has no closing ---")


class Project:
    def __init__(self, root, config_path, config, config_error=None):
        self.root = root
        self.config_path = config_path
        self.config = config
        self.config_error = config_error
        self.config_issues = []
        self.bundles = []
        self._git_root = None
        self._git_checked = False

    @staticmethod
    def locate(start):
        """Walk up from start. Returns (config path or None, repo root or None).

        Stops at the first folder holding .okf/config.yaml or .git, at the home folder, or at the
        filesystem root. Runs no subprocess, so the edit hook stays cheap."""
        cur = Path(start).resolve()
        while not cur.exists() and cur.parent != cur:
            cur = cur.parent
        if cur.is_file():
            cur = cur.parent
        home = Path.home().resolve()
        while True:
            if (cur / CONFIG_REL).is_file():
                return cur / CONFIG_REL, None
            if (cur / ".git").exists():
                return None, cur
            if cur == home or cur.parent == cur:
                return None, None
            cur = cur.parent

    @classmethod
    def find(cls, start):
        config, repo = cls.locate(start)
        if config is not None:
            return cls.load(config.parent.parent, config)
        if repo is None:
            repo = Path(start).resolve()
            while not repo.is_dir() and repo.parent != repo:
                repo = repo.parent
        return cls.load(repo, None)

    @classmethod
    def load(cls, root, config_path):
        config = json.loads(json.dumps(DEFAULT_CONFIG))
        error = None
        if config_path:
            try:
                data, _ = yaml_load(config_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    _merge(config, data)
                elif data is not None:
                    error = "config is not a mapping"
            except (OSError, UnicodeDecodeError, YAMLError) as exc:
                error = str(exc)
        project = cls(root, config_path, config, error)
        project.validate_config()
        project.discover()
        return project

    def validate_config(self):
        """Check the `brain:` and `hooks:` values. A bad one is listed in config_issues and the default is used."""
        hooks = self.config.get("hooks")
        if isinstance(hooks, dict):
            for key in HOOK_SWITCHES:
                if key in hooks and not blank(hooks[key]) and as_flag(hooks[key]) is None:
                    self.config_issues.append("`hooks.%s` is %r; use true or false. Using %s"
                                              % (key, hooks[key], "true" if key == "session" else "false"))
        brain = self.config.get("brain")
        defaults = DEFAULT_CONFIG["brain"]
        if not isinstance(brain, dict):
            if not blank(brain):
                self.config_issues.append("`brain` must be a mapping with `actions` and `names`; using the defaults")
            brain = {}
        out = {}
        for key, allowed in BRAIN_CHOICES.items():
            v = brain.get(key)
            if blank(v):
                out[key] = defaults[key]
            elif isinstance(v, str) and v.strip().lower() in allowed:
                out[key] = v.strip().lower()
            else:
                out[key] = defaults[key]
                self.config_issues.append("`brain.%s` is %r; use one of: %s. Using %s"
                                          % (key, v, ", ".join(allowed), defaults[key]))
        out["tickets"] = self._tickets_config(brain.get("tickets"), out["actions"])
        self.config["brain"] = out

    def _tickets_config(self, raw, actions):
        """{"system", "target"} from `brain.tickets`; system "none" when sync is off or the value is bad."""
        off = dict(DEFAULT_CONFIG["brain"]["tickets"])
        if blank(raw) or raw is False:
            return off
        if not isinstance(raw, dict):
            self.config_issues.append("`brain.tickets` must be a mapping with `system` and `target`; ticket sync is off")
            return off
        system, target = raw.get("system"), raw.get("target")
        if blank(system) or system is False:
            return off
        name = str(system).strip().lower() if isinstance(system, str) else None
        if name in TICKETS_OFF:
            return off
        if not name or not _TICKET_SYSTEM_RE.match(name):
            self.config_issues.append("`brain.tickets.system` is %r; use the ticket system's name (linear, jira, "
                                      "github, asana, ...) or none. Ticket sync is off" % (system,))
            return off
        if not blank(target) and not isinstance(target, (str, int)):
            self.config_issues.append("`brain.tickets.target` is %r; use the team, project, board or repository "
                                      "as text. Ticket sync is off" % (target,))
            return off
        if actions == "off":
            self.config_issues.append("`brain.tickets.system` is %s but `brain.actions` is off, so no actions are "
                                      "extracted to sync" % name)
        return {"system": name, "target": "" if blank(target) else str(target).strip()}

    @property
    def brain_actions(self):
        return self.config["brain"]["actions"]

    @property
    def brain_names(self):
        return self.config["brain"]["names"]

    @property
    def brain_tickets(self):
        """{"system", "target"} when meeting actions sync to a ticket system, else None."""
        t = self.config["brain"]["tickets"]
        return t if t["system"] != "none" and self.brain_actions != "off" else None

    @property
    def git_root(self):
        if not self._git_checked:
            self._git_root = git_toplevel(self.root)
            self._git_checked = True
        return self._git_root

    @property
    def modules(self):
        mods = self.config.get("modules") or []
        if isinstance(mods, str):
            mods = [m.strip() for m in mods.split(",")]
        return ["core"] + [str(m).lower() for m in mods if str(m).lower() in MODULES and str(m).lower() != "core"]

    def discover(self):
        entries = self.config.get("bundles") or []
        if isinstance(entries, list) and entries:
            for entry in entries:
                if isinstance(entry, str):
                    entry = {"path": entry}
                if not isinstance(entry, dict) or not entry.get("path"):
                    continue
                path = (self.root / str(entry["path"])).resolve()
                self.bundles.append(Bundle(self, path, str(entry.get("kind") or guess_kind(path)), entry))
        else:
            for path in find_bundles(self.root):
                self.bundles.append(Bundle(self, path, guess_kind(path), {}))

    def bundle_for(self, path):
        best = None
        for b in self.bundles:
            if is_within(path, b.root) and (best is None or len(str(b.root)) > len(str(best.root))):
                best = b
        return best

    def related_entries(self):
        rel = self.config.get("related") or {}
        out = []
        if isinstance(rel, dict):
            for name, entry in rel.items():
                if isinstance(entry, str):
                    entry = {"url": entry}
                if isinstance(entry, dict):
                    out.append((str(name), entry))
        return out

    def map_url(self, url):
        """Map a URL into a related bundle with a local checkout to a local path, else None."""
        for _, entry in self.related_entries():
            base, local = entry.get("url"), entry.get("path")
            if base and local and url.startswith(str(base)):
                root = (self.root / str(local)).resolve()
                if root.is_dir():
                    tail = urllib.parse.unquote(url[len(str(base)):].split("#")[0].split("?")[0])
                    return Path(os.path.normpath(str(root / tail.lstrip("/"))))
        return None


def find_bundles(root, max_depth=4):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)
        depth = len(d.relative_to(root).parts)
        dirnames[:] = sorted(n for n in dirnames if not n.startswith(".") and n not in SKIP_DIRS)
        if depth > max_depth:
            dirnames[:] = []
            continue
        if "index.md" in filenames:
            try:
                fm, _, _, _ = split_frontmatter((d / "index.md").read_text(encoding="utf-8"))
                data = yaml_load(fm)[0] if fm else None
            except (OSError, UnicodeDecodeError, YAMLError):
                data = None
            if isinstance(data, dict) and "okf_version" in data:
                found.append(d.resolve())
                dirnames[:] = []
                continue
        if d != root and d.name in ("docs", "brain") and depth <= 2 and _looks_okf(d):
            found.append(d.resolve())
            dirnames[:] = []
    return found


def _looks_okf(d):
    seen = 0
    for p in sorted(d.rglob("*.md"))[:30]:
        if p.name in RESERVED or any(part.startswith(".") for part in p.relative_to(d).parts):
            continue
        try:
            fm, _, _, _ = split_frontmatter(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if fm and re.search(r"^type\s*:", fm, re.M):
            seen += 1
            if seen >= 2:
                return True
    return False


def guess_kind(path):
    name = path.name.lower()
    if "brain" in name:
        return "brain"
    if name in ("help", "developers", "changelog", "site", "public-docs"):
        return "site"
    if name in ("docs", "doc") or ((path / "decisions").is_dir() and any(
            (path / n).is_dir() for n in ("product", "system", "operations"))):
        return "docs"
    return "other"


ASSET_TYPES = {"meeting", "transcript", "email", "note", "research", "document", "recording"}
BRAIN_REFERENCE_TYPES = {"external", "report", "article"}


class Bundle:
    def __init__(self, project, root, kind, entry):
        self.project = project
        self.root = root
        self.kind = kind if kind in KINDS else "other"
        self.entry = entry
        self.preset = entry.get("preset")
        self.scope = entry.get("scope")
        self._docs = None
        self._version = False  # not read yet
        self._fallback = None

    @property
    def exists(self):
        return self.root.is_dir()

    @property
    def okf_version(self):
        """The okf_version the root index.md declares, or None."""
        if self._version is False:
            self._version = None
            try:
                fm, _, _, _ = split_frontmatter((self.root / "index.md").read_text(encoding="utf-8"))
                data = yaml_load(fm)[0] if fm else None
                if isinstance(data, dict) and not blank(data.get("okf_version")):
                    self._version = str(data["okf_version"]).strip()
            except (OSError, UnicodeDecodeError, YAMLError):
                pass
        return self._version

    @property
    def is_older(self):
        """True when the bundle declares an OKF version before 0.3, or none."""
        v = version_tuple(self.okf_version) if self.okf_version is not None else None
        return v is None or v < OKF_VERSION_TUPLE

    @property
    def root_fallback(self):
        """OKF 0.3 section 6.2: a bundle that declares 0.2 or earlier, or no version, may resolve a bare
        path field from the bundle root when it doesn't resolve from the file."""
        v = version_tuple(self.okf_version) if self.okf_version is not None else None
        return v is None or v <= (0, 2)

    @property
    def rel(self):
        return relpath(self.root, self.project.root) + "/"

    @staticmethod
    def skips(d, name):
        """True for a subfolder of d that bundles never hold docs in."""
        return name.startswith(".") or name in SKIP_DIRS or (name == "files" and d.name == "assets")

    def walk(self):
        for dirpath, dirnames, filenames in os.walk(self.root):
            d = Path(dirpath)
            dirnames[:] = sorted(n for n in dirnames if not self.skips(d, n))
            yield d, dirnames, sorted(filenames)

    def emptied_dirs(self):
        """Folders below the root that hold index.md or log.md but nothing else, as after deleting their files.
        A README.md, a note without `type` or an asset still counts as something."""
        used = {norm(p) for p in self.dirs_with_docs()}
        for d, _, files in self.walk():
            if any(f not in RESERVED and not f.startswith(".") for f in files):
                p = d
                while is_within(p, self.root) and norm(p) not in used:
                    used.add(norm(p))
                    p = p.parent
        out = []
        for d, _, files in self.walk():
            if norm(d) != norm(self.root) and norm(d) not in used and any(f in RESERVED for f in files):
                out.append(d)
        return out

    def plain_index_dirs(self):
        """Folders below the root with an index.md whose only docs are non-concepts: the index isn't built
        (nothing to list), but a subfolder index.md still may not have frontmatter."""
        listed = {norm(p) for p in self.dirs_with_docs()}
        out = {}
        for doc in self.docs:
            d = doc.path.parent
            if norm(d) not in listed and (d / "index.md").is_file():
                out.setdefault(norm(d), d)
        return sorted(out.values(), key=lambda p: (len(p.parts), str(p)))

    @property
    def docs(self):
        if self._docs is None:
            self._docs = []
            if self.exists:
                for d, _, files in self.walk():
                    for name in files:  # dot-files are not part of the bundle (OKF 0.3 section 3.2)
                        if name.endswith(".md") and name not in RESERVED and not name.startswith("."):
                            self._docs.append(Doc.load(self, d / name))
        return self._docs

    def fallback_paths(self):
        """[(doc, field, value)] for bare path fields that resolve only from the bundle root (0.2 bundles)."""
        if self._fallback is None:
            self._fallback = []
            if self.root_fallback:
                for doc in self.docs:
                    if doc.fm is None:
                        continue
                    for label, value in doc.path_fields():
                        if doc.resolve_field(value)[1] == "fallback":
                            self._fallback.append((doc, label, value))
        return self._fallback

    @property
    def indexable(self):
        """Docs that index.md lists: not the files OKF 0.3 section 3.2 says are no concepts."""
        return [d for d in self.docs if not d.nonconcept]

    def dirs_with_docs(self):
        dirs = {norm(self.root): self.root}
        for doc in self.indexable:
            p = doc.path.parent
            while is_within(p, self.root):
                dirs.setdefault(norm(p), p)
                if norm(p) == norm(self.root):
                    break
                p = p.parent
        return sorted(dirs.values(), key=lambda p: (len(p.parts), str(p)))


EXEMPT_NAMES = {"readme.md", "agents.md", "contributing.md", "skill.md", "claude.md"}


class Doc:
    def __init__(self, bundle, path):
        self.bundle = bundle
        self.path = path
        self.text = ""
        self.fm = None
        self.body = ""
        self.body_line = 1
        self.error = None
        self.warnings = []
        self.dup_keys = []

    @classmethod
    def load(cls, bundle, path):
        doc = cls(bundle, path)
        try:
            doc.text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            doc.error = ("read-error", "can't read the file: %s" % exc)
            return doc
        fm_text, body, body_line, problem = split_frontmatter(doc.text)
        doc.body, doc.body_line = body, body_line
        if problem:
            doc.error = problem
            return doc
        if fm_text is None:  # no frontmatter: not a concept (OKF 0.3 section 3.2); check_doc says so
            return doc
        try:
            data, warnings = yaml_load(fm_text, line_offset=1)
        except YAMLError as exc:
            doc.error = ("fm-invalid", "frontmatter isn't valid YAML: %s" % exc)
            return doc
        doc.dup_keys = [w for w in warnings if "duplicate key" in w]
        doc.warnings = [w for w in warnings if "duplicate key" not in w]
        if data is None:
            data = {}
        if not isinstance(data, dict):
            doc.error = ("fm-not-mapping", "frontmatter must be a YAML mapping")
            return doc
        doc.fm = data
        return doc

    # identity -------------------------------------------------------------
    @property
    def rel(self):
        return relpath(self.path, self.bundle.root)

    @property
    def prel(self):
        return relpath(self.path, self.bundle.project.root)

    def get(self, key, default=None):
        """A frontmatter value; a blank one (null, "", []) counts as absent (OKF 0.3 section 11.2)."""
        value = (self.fm or {}).get(key, default)
        return default if blank(value) else value

    def ext(self, name, default=None):
        """An okf-docs extension key: x-okfdocs-<name> first, the 0.9 name as a fallback."""
        value = self.get(EXT_PREFIX + name)
        return value if value is not None else self.get(name, default)

    @property
    def type(self):
        t = self.get("type")
        return str(t).strip() if isinstance(t, (str, int, float)) and not isinstance(t, bool) else ""

    @property
    def exempt(self):
        """README.md, AGENTS.md and the like: never reported as non-concepts."""
        return self.path.name.lower() in EXEMPT_NAMES

    @property
    def nonconcept(self):
        """No frontmatter, or no non-empty `type`: consumers skip the file (OKF 0.3 section 3.2)."""
        return self.error is None and (self.fm is None or not self.type)

    @property
    def title(self):
        t = self.get("title")
        return str(t).strip() if t is not None else humanize(self.path.stem)

    @property
    def description(self):
        d = self.get("description")
        return " ".join(str(d).split()) if d is not None else ""

    @property
    def status(self):
        s = self.get("status")
        return str(s).strip().lower() if s is not None else "stable"

    @property
    def current(self):
        """OKF 0.3 section 5.4: draft and stable are current, deprecated isn't, and an unknown value isn't."""
        return self.status in ("draft", "stable")

    @property
    def visibility(self):
        v = self.ext("visibility")
        return str(v).strip().lower() if v is not None else "internal"

    @property
    def klass(self):
        c = self.ext("class")
        if c is not None:
            return str(c).strip().lower()
        t = self.type.lower()
        if t in ("decision", "observation"):
            return t
        if self.bundle.kind == "brain":
            if t in ASSET_TYPES:
                return "asset"
            if t in BRAIN_REFERENCE_TYPES:
                return "reference"
        return "canonical"

    @property
    def scope(self):
        s = self.ext("scope")
        return str(s).strip() if s is not None else str(self.bundle.scope or "")

    @property
    def tags(self):
        """A list of tags. A scalar is one tag; it is never split at commas (OKF 0.3 section 4.1)."""
        return [str(t).strip() for t in as_list(self.get("tags")) if not isinstance(t, (dict, list)) and str(t).strip()]

    # trust and time ---------------------------------------------------------
    def verified_entries(self):
        return [e for e in as_list(self.get("verified")) if isinstance(e, dict)]

    def valid_events(self):
        """Verified entries with both `by` and `at`; consumers ignore the others."""
        return [e for e in self.verified_entries() if not blank(e.get("by")) and not blank(e.get("at"))]

    def last_verified(self):
        times = [parse_ts(e.get("at"))[0] for e in self.valid_events()]
        times = [t for t in times if t]
        return max(times) if times else None

    def generated_at(self):
        g = self.get("generated")
        if isinstance(g, dict):
            return parse_ts(g.get("at"))[0]
        return parse_ts(self.get("timestamp"))[0] if self.get("timestamp") else None

    def current_events(self):
        """OKF 0.3 section 5.3: an event is current when its `at` is equal to or later than generated.at,
        or when `generated` is absent or has no usable `at`. Older events are history."""
        events = self.valid_events()
        gen = self.generated_at()
        if gen is None:
            return events
        current = []
        for e in events:
            when = parse_ts(e.get("at"))[0]
            if when is not None and when >= gen:
                current.append(e)
        return current

    def verification_outdated(self):
        """Events exist, but each one is older than generated.at."""
        return bool(self.valid_events()) and not self.current_events()

    def trust_note(self):
        return "verified before the last change" if self.verification_outdated() else ""

    def last_check(self):
        """The latest current verified `at`; else generated.at. Decay counts from here."""
        times = [parse_ts(e.get("at"))[0] for e in self.current_events()]
        times = [t for t in times if t]
        if times:
            return max(times)
        return self.generated_at()

    def trust(self):
        """The OKF 0.3 tier (section 5.3): human-reviewed > machine-confirmed > unverified, from current events only."""
        events = self.current_events()
        if any(str(e.get("by", "")).startswith("human:") for e in events):
            return "human-reviewed"
        return "machine-confirmed" if events else "unverified"

    def sourced(self):
        """True when `sources` names at least one resource. Inside a tier, sourced files rank first: OKF records
        where content came from as source signals, not as a credibility label (section 5.1)."""
        return bool(self.source_entries())

    def stated_by(self):
        """The `human:` authors of the sources: the people who stated what the file says."""
        return sorted({str(e["author"]) for e in self.source_entries()
                       if isinstance(e.get("author"), str) and e["author"].startswith("human:")})

    def legacy_trust(self):
        """The tier under the 0.2 rule, where any verified event counted."""
        events = self.valid_events()
        if any(str(e.get("by", "")).startswith("human:") for e in events):
            return "human-reviewed"
        return "machine-confirmed" if events else "unverified"

    def reviewed(self):
        return bool(self.current_events())

    def stale_after(self):
        """The stale_after time, or None when it is absent or can't be used (see stale_after_bad)."""
        v = self.get("stale_after")
        if v is None:
            return None
        when, problem = parse_ts(v)
        return None if problem == NO_OFFSET else when

    def stale_after_bad(self):
        """OKF 0.3 section 5.5: a value that doesn't parse counts as stale, never fresh."""
        v = self.get("stale_after")
        if v is None:
            return False
        when, problem = parse_ts(v)
        return when is None or problem == NO_OFFSET

    def is_stale(self, at):
        if self.klass == "tracker":
            return False
        sa = self.stale_after()
        return self.stale_after_bad() or bool(sa and at >= sa)

    # links and sources ----------------------------------------------------
    def resolve(self, target):
        """Local path for a link or resource, or None for anchors, descriptors and unmapped URLs."""
        t = str(target).strip().strip("<>")
        if not t or t.startswith("#"):
            return None
        if is_url(t):
            return self.bundle.project.map_url(t)
        t = urllib.parse.unquote(t.split("#", 1)[0].split("?", 1)[0])
        if not t:
            return None
        base = self.bundle.root / t.lstrip("/") if t.startswith("/") else self.path.parent / t
        return Path(os.path.normpath(str(base)))

    def resolve_field(self, target):
        """(path, kind) for a path field (OKF 0.3 section 6). kind is "found", "fallback" (a bare path that
        resolves only from the bundle root, which a 0.2 bundle may do), "missing" or "none"."""
        path = self.resolve(target)
        if path is None:
            return None, "none"
        if path.exists():
            return path, "found"
        t = str(target).strip().strip("<>")
        if self.bundle.root_fallback and not is_url(t) and not t.startswith("/"):
            clean = urllib.parse.unquote(t.split("#", 1)[0].split("?", 1)[0])
            alt = Path(os.path.normpath(str(self.bundle.root / clean)))
            if alt.exists() and is_within(alt, self.bundle.root):
                return alt, "fallback"
        return path, "missing"

    def source_entries(self):
        src = self.get("sources")
        if isinstance(src, dict):
            src = [src]
        if not isinstance(src, list):
            return []
        out = []
        for e in src:
            if isinstance(e, str):
                out.append({"resource": e, "_bare": True})
            elif isinstance(e, dict) and not blank(e.get("resource")):
                out.append(e)
        return out

    def local_sources(self):
        """(entry, path) for sources that name local files. Descriptors such as
        'pasted in conversation, 2026-11-12' are skipped unless a file by that name exists."""
        out = []
        for e in self.source_entries():
            r = str(e["resource"])
            p, kind = self.resolve_field(r)
            if p is None or (is_descriptor(r) and kind != "found"):
                continue
            out.append((e, p))
        return out

    def path_fields(self):
        """(label, value) for every frontmatter field that holds a path (OKF 0.3 section 6)."""
        out = []
        for key in ("resource", "computation"):
            if isinstance(self.get(key), str):
                out.append((key, self.get(key)))
        for i, e in enumerate(self.source_entries()):
            if isinstance(e.get("resource"), str) and not e.get("_bare"):
                out.append(("sources[%d].resource" % i, e["resource"]))
        for label, value in (("superseded_by", self.get("superseded_by")), ("supersedes", self.ext("supersedes"))):
            for item in as_list(value):
                if isinstance(item, str):
                    out.append((label, item))
        for key in ("executor", "attester"):
            v = self.get(key)
            if isinstance(v, dict) and isinstance(v.get("resource"), str):
                out.append((key + ".resource", v["resource"]))
        return [(label, v) for label, v in out if not is_url(v) and not re.search(r"\s", v.strip())]


def alt_source_path(doc, resource):
    """For a v3-style source path, the path it most likely meant, or None."""
    r = str(resource).strip().lstrip("/")
    roots = [doc.bundle.project.root, doc.bundle.root]
    if doc.bundle.project.git_root:
        roots.append(doc.bundle.project.git_root)
    for root in roots:
        cand = Path(os.path.normpath(str(root / r)))
        if cand.exists():
            return cand
    return None


def rel_from(doc_path, target):
    return relpath(target, doc_path.parent)


# --------------------------------------------------------------------------
# Markdown scanning
# --------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")


def fence_step(fence, line):
    """Track fenced code blocks as CommonMark does. `fence` is the open fence's marker ("```", "~~~~", ...)
    or None. Returns (the fence now open or None, whether this line is a fence line or inside a block).
    Only a bare marker of the same character, at least as long as the opener, closes a block."""
    m = _FENCE_RE.match(line)
    if fence is not None:
        if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not m.group(2).strip():
            return None, True
        return fence, True
    if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
        return m.group(1), True
    return None, False
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_LINK_RE = re.compile(r"!?\[(?:[^\]\[]|\[[^\]]*\])*\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'(][^)]*)?\)")
_REFDEF_RE = re.compile(r"^\s{0,3}\[(?!\^)[^\]]+\]:\s*<?(\S+?)>?(?:\s+.*)?$")
_FOOTREF_RE = re.compile(r"\[\^([^\]\s]+)\](?!:)")
_FOOTDEF_RE = re.compile(r"^\s{0,3}\[\^([^\]\s]+)\]:")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def prose_lines(text):
    """Yield (line number, line) outside fenced code and HTML comments, with inline code removed."""
    in_comment, fence = False, None
    for n, line in enumerate(text.split("\n"), 1):
        fence, in_code = fence_step(fence, line)
        if in_code:
            continue
        if in_comment:
            if "-->" in line:
                in_comment = False
                line = line.split("-->", 1)[1]
            else:
                continue
        while "<!--" in line:
            head, tail = line.split("<!--", 1)
            if "-->" in tail:
                line = head + tail.split("-->", 1)[1]
            else:
                line = head
                in_comment = True
        yield n, _INLINE_CODE_RE.sub("", line)


def body_links(doc):
    out = []
    for n, line in prose_lines(doc.body):
        for m in _LINK_RE.finditer(line):
            out.append((m.group(1), doc.body_line + n - 1))
        m = _REFDEF_RE.match(line)
        if m:
            out.append((m.group(1), doc.body_line + n - 1))
    return out


def footnotes(doc):
    refs, defs = [], set()
    for n, line in prose_lines(doc.body):
        m = _FOOTDEF_RE.match(line)
        if m:
            defs.add(m.group(1))
            continue
        for m in _FOOTREF_RE.finditer(line):
            refs.append((m.group(1), doc.body_line + n - 1))
    return refs, defs


# --------------------------------------------------------------------------
# Findings and checks
# --------------------------------------------------------------------------

LEVEL_NAMES = {"okf": "OKF", "house": "House", "content": "Content"}
LEVEL_ORDER = {"okf": 0, "house": 1, "content": 2}
SEV_ORDER = {"error": 0, "warn": 1, "info": 2}
VALID_STATUS = ("draft", "stable", "deprecated")
ENUMS = {  # short names; the keys carry the x-okfdocs- prefix, and the 0.9 names still read as a fallback
    "specificity": ("general", "specific", "exact"),
    "visibility": ("internal", "public"),
    "class": ("canonical", "decision", "observation", "asset", "reference", "tracker"),
}
ACTOR_RE = re.compile(r"^(?:[^\s/:]+/\S+|[A-Za-z][A-Za-z0-9+.-]*:\S+)$")  # <producer>/<version> or <scheme>:<id>
NAME_RE = re.compile(r"^[a-z0-9]+(?:[-.][a-z0-9]+)*\.md$")
DATED_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")
DECISION_RE = re.compile(r"^(\d{3,})-")
LEGACY_KEYS = {
    "links": "v3 key; links belong in the body (okf.py upgrade moves them to a Related list)",
    "timestamp": "OKF v0.1 key; use a `generated` mapping with `by` and `at`",
}
AGGREGATED = ("unverified", "draft", "verification-outdated")
ROOT_KEYS = ("okf_version", "title", "description", "license")  # OKF 0.3 section 8.1, besides x- keys
V3_ROOT_KEYS = ("type", "class", "scope", "specificity", "credibility", "x-okfdocs-credibility", "generated",
                "verified", "sources", "links")
SPDX_RE = re.compile(r"^[A-Za-z0-9.+-]+(?: (?:AND|OR|WITH) [A-Za-z0-9.+-]+)*$")


_HISTORY_RE = re.compile(r"^##\s+History\s*#*\s*$", re.I)
_HISTORY_LINE_RE = re.compile(r"^\s*[-*]\s+(\d{4}-\d{2}-\d{2})\b")


def history_span(lines):
    """(heading index, end index) of the `## History` section in a list of body lines, or None. The section
    runs to the next heading of level one or two, outside fenced code."""
    fence, start = None, None
    for i, line in enumerate(lines):
        fence, in_code = fence_step(fence, line)
        if in_code:
            continue
        if start is None:
            if _HISTORY_RE.match(line):
                start = i
        elif re.match(r"^#{1,2}\s", line):
            return start, i
    return (start, len(lines)) if start is not None else None


def without_history(body):
    """The body without its `## History` section: what a history line may change without changing meaning."""
    lines = body.split("\n")
    span = history_span(lines)
    if span:
        lines = lines[:span[0]] + lines[span[1]:]
    return lines


def meaning_text(fm, body):
    """What generated.at stands for, compared with whitespace collapsed: title, description and the body
    outside `## History`. A history line or a whitespace change leaves it equal."""
    fm = fm if isinstance(fm, dict) else {}
    parts = [str(fm.get("title") or ""), str(fm.get("description") or "")] + without_history(body)
    return " ".join(" ".join(parts).split())


def add_history_line(body, line, day):
    """Insert `line` into the `## History` section of `body`, newest first; add the section at the end when
    there is none. Returns the new body."""
    lines = body.split("\n")
    span = history_span(lines)
    if span is None:
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines + ["", "## History", "", line, ""])
    start, end = span
    at = None
    for i in range(start + 1, end):
        m = _HISTORY_LINE_RE.match(lines[i])
        if m and m.group(1) <= day:
            at = i
            break
    if at is None:  # after the last history line, or right under the heading
        items = [i for i in range(start + 1, end) if _HISTORY_LINE_RE.match(lines[i])]
        if items:
            at = items[-1] + 1
        else:
            at = start + 1
            if at < len(lines) and not lines[at].strip():
                at += 1
            else:
                lines.insert(at, "")
                at += 1
            if at >= len(lines) or lines[at].strip():
                lines.insert(at, "")
    lines.insert(at, line)
    return "\n".join(lines)


class Finding:
    __slots__ = ("level", "severity", "code", "path", "message", "line", "fixable")

    def __init__(self, level, severity, code, path, message, line=None, fixable=None):
        self.level, self.severity, self.code = level, severity, code
        self.path, self.message, self.line, self.fixable = path, message, line, fixable

    def to_dict(self):
        d = {"level": self.level, "severity": self.severity, "code": self.code, "path": self.path,
             "message": self.message}
        if self.line:
            d["line"] = self.line
        if self.fixable:
            d["fix"] = self.fixable
        return d

    def sort_key(self):
        return (LEVEL_ORDER[self.level], SEV_ORDER[self.severity], self.path, self.line or 0)


class Ctx:
    """Shared state for one run: the project, the clock, decay settings, all docs by path."""

    def __init__(self, project, at=None):
        self.project = project
        self.now = at or now()
        self._docs = None
        decay = project.config.get("decay") or {}
        self.decay = {}
        if isinstance(decay, dict):
            for k, v in decay.items():
                days = parse_duration(v)
                if days is not None:
                    self.decay[str(k).lower()] = days
        self.link_style = str(project.config.get("links") or "relative").lower()
        self._changed = None

    @property
    def changed_since_head(self):
        """Paths (normalized) that differ from git HEAD; empty outside git or without a commit."""
        if self._changed is None:
            self._changed = set()
            top = self.project.git_root
            out = run_git(["diff", "--name-only", "HEAD", "--"], top) if top else None
            for line in (out or "").splitlines():
                if line.strip():
                    self._changed.add(norm(top / line.strip()))
        return self._changed

    def head_doc(self, doc):
        """(frontmatter dict or None, body) of the file as git HEAD has it; None when HEAD doesn't have it."""
        top = self.project.git_root
        if top is None:
            return None
        text = run_git(["show", "HEAD:" + relpath(doc.path, top)], top)
        if text is None:
            return None
        fm_text, body, _, problem = split_frontmatter(text)
        if problem or fm_text is None:
            return None, body
        try:
            data, _ = yaml_load(fm_text)
        except YAMLError:
            data = None
        return (data if isinstance(data, dict) else None), body

    @property
    def docs_by_path(self):
        if self._docs is None:
            self._docs = {norm(d.path): d for b in self.project.bundles for d in b.docs}
        return self._docs

    def half_life(self, doc):
        for key in (doc.type.lower(), doc.klass):
            if key in self.decay:
                return self.decay[key]
        return self.decay.get("default", 365.25)

    def decay_weight(self, doc, at=None):
        if doc.klass == "tracker":
            return 1.0, None
        last = doc.last_check()
        half = self.half_life(doc)
        if not last or not math.isfinite(half) or half <= 0:
            return 1.0, None
        age = max(0.0, ((at or self.now) - last).total_seconds() / 86400)
        return 0.5 ** (age / half), age


def iter_timestamps(fm):
    gen = fm.get("generated")
    if isinstance(gen, dict) and "at" in gen:
        yield "generated.at", gen.get("at")
    for i, e in enumerate(as_list(fm.get("verified"))):
        if isinstance(e, dict) and "at" in e:
            yield "verified[%d].at" % i, e.get("at")
    if "stale_after" in fm:
        yield "stale_after", fm.get("stale_after")
    for i, e in enumerate(as_list(fm.get("sources"))):
        if isinstance(e, dict):
            if "last_modified" in e:
                yield "sources[%d].last_modified" % i, e.get("last_modified")
            uw = e.get("usage_window")
            if isinstance(uw, dict):
                for k in ("from", "to"):
                    if k in uw:
                        yield "sources[%d].usage_window.%s" % (i, k), uw.get(k)
    uw = fm.get("usage_window")
    if isinstance(uw, dict):
        for k in ("from", "to"):
            if k in uw:
                yield "usage_window." + k, uw.get(k)


def computation_fences(body):
    """Fenced code blocks under a `Computation` heading (OKF 0.3 section 10.3). The section runs to the
    next heading of the same or a higher level."""
    level, count, fence = None, 0, None
    for line in body.split("\n"):
        opened = fence is None
        fence, in_code = fence_step(fence, line)
        if in_code:
            if opened and fence is not None and level is not None:
                count += 1
            continue
        m = _HEADING_RE.match(line)
        if m:
            depth = len(m.group(1))
            if level is not None and depth <= level:
                break
            if level is None and m.group(2).strip().lower() == "computation":
                level = depth
    return count


def _check_attested(doc, add):
    """An Attested Computation (OKF 0.3 section 10). okf-docs reads these and never edits their code."""
    fm = doc.fm
    if blank(fm.get("runtime")):
        add("okf", "warn", "attested-runtime", "an Attested Computation needs `runtime`")
    fences = computation_fences(doc.body)
    if doc.get("computation") is not None:
        if fences:
            add("okf", "warn", "attested-computation",
                "with a `computation` path, don't also put a fenced block under a Computation heading")
    elif fences == 0:
        add("okf", "warn", "attested-computation",
            "no computation: set `computation` to a file, or put one fenced block under a Computation heading")
    elif fences > 1:
        add("okf", "warn", "attested-computation",
            "put exactly one fenced block under the Computation heading; consumers use the first of %d" % fences)
    for i, entry in enumerate(as_list(fm.get("parameters"))):
        if not isinstance(entry, dict) or blank(entry.get("name")) or blank(entry.get("type")):
            add("okf", "warn", "attested-parameters", "parameters[%d] needs `name` and `type`" % i)
    for key in ("executor", "attester"):
        value = fm.get(key)
        if value is None:
            continue
        if not isinstance(value, dict) or blank(value.get("resource")):
            add("okf", "warn", "attested-executor", "`%s` is a mapping with a `resource` path" % key)
        elif key == "executor" and not isinstance(value.get("receipt"), list):
            add("okf", "warn", "attested-executor", "`executor.receipt` lists the fields that a run returns")
    if blank(fm.get("attester")):
        add("okf", "info", "attested-no-attester",
            "not attestable: without an `attester`, consumers can't show its values as attested")


# --------------------------------------------------------------------------
# Tracker files: actions.md and questions.md in a brain
# --------------------------------------------------------------------------

TRACKER_TYPES = {"action-list": "actions", "question-list": "questions"}
TRACKER_TABLES = {  # kind -> (closed section name, Open header, closed header)
    "actions": ("Done", ("Owner", "Action", "Due", "From", "Added"),
                ("Owner", "Action", "Due", "From", "Added", "Done")),
    "questions": ("Answered", ("Area", "Question", "Why it matters", "Asked"),
                  ("Area", "Question", "Answer in", "Answered")),
}
TICKET_COLUMN = "Ticket"  # optional in the actions tables, right after Action; used with brain.tickets


def _with_ticket(header):
    return header[:2] + (TICKET_COLUMN,) + header[2:]


def tracker_headers(kind, which):
    """The headers a tracker table may have: the plain one, and for actions also one with a Ticket column."""
    closed_name, open_header, closed_header = TRACKER_TABLES[kind]
    header = open_header if which == "open" else closed_header
    return (header, _with_ticket(header)) if kind == "actions" else (header,)
TRACKER_PRUNE_DAYS = 90
_ISO_DAY_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_H2_RE = re.compile(r"^##\s+(.*?)\s*#*\s*$")


def tracker_kind(doc):
    """'actions' or 'questions' for a tracker file, else None."""
    if doc.klass != "tracker":
        return None
    return TRACKER_TYPES.get(doc.type.lower())


def _table_cells(line):
    inner = line.strip().replace("\\|", "\x00")
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [c.replace("\x00", "|").strip() for c in inner.split("|")]


def _iso_day(value):
    m = _ISO_DAY_RE.match(str(value).strip())
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parse_tracker(doc):
    """Read the tables of a tracker file. Returns {"kind", "open", "closed", "open_ok", "closed_ok"}.

    "open" and "closed" are lists of (line number, {header: cell}); a section with no table gives None."""
    kind = tracker_kind(doc)
    closed_name, open_header, closed_header = TRACKER_TABLES[kind]
    sections = {}
    name, fence = None, None
    for i, raw in enumerate(doc.body.split("\n")):
        fence, in_code = fence_step(fence, raw)
        if in_code:  # nothing inside a fenced block is a heading or a row
            continue
        m = _H2_RE.match(raw)
        if m:
            name = m.group(1).strip().lower()
            continue
        if name is not None and raw.lstrip().startswith("|"):
            sections.setdefault(name, []).append((doc.body_line + i, raw))
    out = {"kind": kind, "open": None, "closed": None, "open_ok": False, "closed_ok": False, "ticket_column": False}
    for key, section in (("open", "open"), ("closed", closed_name.lower())):
        lines = sections.get(section)
        if not lines:
            continue
        header = tuple(_table_cells(lines[0][1]))
        found = [h for h in tracker_headers(kind, key) if tuple(c.lower() for c in h) == tuple(c.lower() for c in header)]
        out[key + "_ok"] = bool(found)
        if found:
            header = found[0]  # rows are keyed by the canonical names, whatever the case in the file
            if key == "open":
                out["ticket_column"] = TICKET_COLUMN in header
        rows = []
        for no, raw in lines[1:]:
            cells = _table_cells(raw)
            if all(re.match(r"^:?-{1,}:?$", c) for c in cells if c) and any(cells):
                continue  # the |---|---| row
            if not any(cells):
                continue
            rows.append((no, dict(zip(header, cells + [""] * (len(header) - len(cells))))))
        out[key] = rows
    return out


def tracker_overdue(rows, today):
    """The Open action rows whose Due date is before today. `-` or no date means none was set."""
    out = []
    for no, row in rows or []:
        due = _iso_day(row.get("Due", ""))
        if due is not None and due < today:
            out.append((no, row, due))
    return out


def unsynced_actions(info):
    """Open action rows with no ticket link and no `-`: not yet synced to the ticket system."""
    if not info["open_ok"]:
        return []
    return [(no, row) for no, row in info["open"] or [] if not row.get(TICKET_COLUMN, "").strip()]


def check_tracker(doc, ctx, add):
    info = parse_tracker(doc)
    kind = info["kind"]
    closed_name, open_header, _ = TRACKER_TABLES[kind]
    tickets = ctx.project.brain_tickets if kind == "actions" else None
    expected = _with_ticket(open_header) if tickets else open_header
    today = ctx.now.date()
    if info["open"] is None:
        add("house", "warn", "tracker-format", "no `## Open` table; the tracker needs one with the columns: %s"
            % " | ".join(expected))
    elif not info["open_ok"]:
        add("house", "warn", "tracker-format", "the Open table header must be: %s" % " | ".join(expected))
    elif tickets and not info["ticket_column"]:
        add("house", "info", "tracker-format", "brain.tickets is on: add a Ticket column after Action in the Open "
            "and Done tables, so ticket links are kept with each action")
    if kind == "actions" and info["open_ok"]:
        for no, row, due in tracker_overdue(info["open"], today):
            add("content", "info", "action-overdue", "%s: %s was due %s" % (
                row.get("Owner") or "no owner", row.get("Action") or "(no action)", due.isoformat()), no)
        if tickets and info["ticket_column"]:
            for no, row in unsynced_actions(info):
                add("content", "info", "action-unsynced", "%s: %s has no ticket in %s yet; sync it, or put - "
                    "when it needs none" % (row.get("Owner") or "no owner", row.get("Action") or "(no action)",
                                            tickets["system"]), no)
    if info["closed"] and info["closed_ok"]:
        col = closed_name
        old = [r for _, r in info["closed"]
               if _iso_day(r.get(col, "")) is not None and (today - _iso_day(r.get(col, ""))).days > TRACKER_PRUNE_DAYS]
        if old:
            add("house", "info", "tracker-prune", "%d %s %s older than %d days; propose removing %s"
                % (len(old), closed_name.lower(), "row" if len(old) == 1 else "rows", TRACKER_PRUNE_DAYS,
                   "it" if len(old) == 1 else "them"))


def tracker_counts(bundle, ctx):
    """For the tracker files at a bundle root: {"actions_open", "overdue", "questions_open"}, only the ones present."""
    out = {}
    for doc in bundle.docs:
        if doc.fm is None or doc.rel not in ("actions.md", "questions.md") or tracker_kind(doc) is None:
            continue
        info = parse_tracker(doc)
        rows = info["open"] or []
        if info["kind"] == "actions":
            out["actions_open"] = len(rows)
            out["overdue"] = len(tracker_overdue(rows, ctx.now.date())) if info["open_ok"] else 0
            if bundle.project.brain_tickets and info["open_ok"]:
                out["unsynced"] = len(unsynced_actions(info)) if info["ticket_column"] else len(rows)
        else:
            out["questions_open"] = len(rows)
    return out


def check_doc(doc, ctx):
    out = []
    p = doc.prel

    def add(level, severity, code, message, line=None, fixable=None):
        out.append(Finding(level, severity, code, p, message, line, fixable))

    if doc.error:
        code, msg = doc.error
        add("okf", "error", code, msg)
        return out
    if doc.fm is None:
        if not doc.exempt:
            add("okf", "warn", "not-a-concept", "not a concept: no frontmatter; consumers skip it")
        return out
    fm = doc.fm
    tracker = doc.klass == "tracker"  # no sources or verification; see the tracker section above
    for w in doc.warnings:
        add("okf", "warn", "yaml-quote" if YAML11_NOTE in w else "yaml-strict", w)
    for w in doc.dup_keys:
        add("okf", "error", "duplicate-key", "frontmatter repeats a key (%s); keys must be unique" % w)
    if not doc.type:
        if not doc.exempt:
            add("okf", "warn", "not-a-concept", "not a concept: no `type`; consumers skip it")
        return out

    for key in ("type", "title", "description", "status"):
        v = fm.get(key)
        if not blank(v) and not isinstance(v, str):
            add("okf", "warn", "yaml-quote", "quote `%s`: it parses as %s, not a string"
                % (key, type(v).__name__ if not isinstance(v, (dict, list)) else "a collection"))
    if not doc.get("title"):
        add("house", "warn", "title-missing", "add a `title`")
    desc = doc.get("description")
    if not desc:
        add("house", "warn", "description-missing", "add a one-sentence `description`; index.md uses it")
    elif len(str(desc)) > 220 or len(re.findall(r"[.!?](?:\s|$)", str(desc).strip())) > 1:
        add("house", "info", "description-long", "`description` should be one sentence")
    for key in ("title", "description"):
        if isinstance(fm.get(key), str) and _TEMPLATE_RE.search(fm[key]):
            add("house", "warn", "template-text", "`%s` still holds template text in < >; fill it in" % key)

    tags = doc.get("tags")
    if tags is not None and not isinstance(tags, list):
        add("house", "warn", "tags-format",
            "`tags` is a list; a scalar is read as one tag and never split at commas", fixable="upgrade")

    for key, value in iter_timestamps(fm):
        when, problem = parse_ts(value)
        if not problem or problem == "missing" or key == "stale_after":
            continue
        if problem == DATE_ONLY:  # valid OKF: the start of that day in UTC. generated.at and verified.at compare.
            if is_compared_ts(key):
                add("house", "warn", "timestamp-date-only",
                    "%s is the date %s; write a date-time, such as %s, because consumers compare it with the "
                    "other timestamps" % (key, value, ctx.now.isoformat()), fixable="upgrade")
            continue
        add("okf", "warn", "timestamp-format",
            "%s is %r: %s. Use ISO 8601 with an offset, such as %s" % (key, value, problem, ctx.now.isoformat()),
            fixable="upgrade" if problem == NO_OFFSET else None)
    if doc.stale_after_bad():
        add("okf", "warn", "stale-after-format",
            "stale_after %r doesn't parse, so the file counts as stale; write ISO 8601 with an offset, or a date"
            % fm.get("stale_after"), fixable="upgrade" if parse_ts(fm.get("stale_after"))[1] == NO_OFFSET else None)

    gen = doc.get("generated")
    if gen is not None:
        if not isinstance(gen, dict):
            add("okf", "warn", "generated-format", "`generated` must be a mapping with `by` and `at`")
        elif blank(gen.get("by")):
            add("okf", "warn", "generated-by-missing", "`generated.by` is required (an actor)")
        elif not ACTOR_RE.match(str(gen.get("by"))):
            add("okf", "warn", "actor-format",
                "generated.by %r isn't an actor: use human:<id>, <tool>/<version> or <scheme>:<id>" % gen.get("by"),
                fixable="upgrade" if _upgrade_actor(gen.get("by")) else None)
    for e in as_list(doc.get("verified")):
        if not isinstance(e, dict) or blank(e.get("by")) or blank(e.get("at")):
            add("okf", "warn", "verified-format", "each `verified` entry needs `by` and `at`")
        elif not ACTOR_RE.match(str(e.get("by"))):
            add("okf", "warn", "actor-format",
                "verified.by %r isn't an actor: people are human:<id>" % e.get("by"),
                fixable="upgrade" if _upgrade_actor(e.get("by")) else None)
        elif not blank(e.get(EXT_PREFIX + "via")) and str(e[EXT_PREFIX + "via"]).strip().lower() not in VIA_VALUES:
            add("house", "warn", "via-value", "verified.%svia is %r; use one of: %s"
                % (EXT_PREFIX, e[EXT_PREFIX + "via"], ", ".join(VIA_VALUES)))

    st = doc.get("status")
    if st is not None and str(st).strip().lower() not in VALID_STATUS:
        add("okf", "warn", "status-value",
            "`status` is %r; use draft, stable or deprecated (consumers treat any other value as not current)" % st)

    src = doc.get("sources")
    ids = set()
    shared_window = doc.get("usage_window")
    if shared_window is not None:
        _check_window(shared_window, "usage_window", add)
    if src is not None:
        if not isinstance(src, (list, dict)):
            add("okf", "warn", "sources-format", "`sources` must be a list of entries with `resource`")
        else:
            for i, e in enumerate(as_list(src)):
                label = "sources[%d]" % i
                if isinstance(e, str):
                    add("okf", "warn", "sources-format",
                        "source %r is a bare string; write `- resource: <path>`" % e, fixable="upgrade")
                elif not isinstance(e, dict) or blank(e.get("resource")):
                    add("okf", "warn", "source-no-resource", "%s needs a `resource`; consumers ignore the entry" % label)
                else:
                    if not blank(e.get("id")):
                        if str(e["id"]) in ids:
                            add("okf", "warn", "source-id-duplicate", "%s.id %r isn't unique in this file"
                                % (label, str(e["id"])))
                        ids.add(str(e["id"]))
                    if not blank(e.get("author")) and not (isinstance(e["author"], str) and ACTOR_RE.match(e["author"])):
                        add("okf", "warn", "actor-format",
                            "%s.author %r isn't an actor: use human:<id>, team:<id> or <tool>/<version>"
                            % (label, e["author"]))
                    if not blank(e.get("usage_window")):
                        _check_window(e["usage_window"], label + ".usage_window", add)
                    if not blank(e.get("usage_count")) and shared_window is None and blank(e.get("usage_window")):
                        add("okf", "warn", "usage-window-missing",
                            "%s.usage_count needs a `usage_window` that gives its period" % label)
        for e in ([] if tracker else doc.source_entries()):
            r = str(e["resource"])
            path, kind = doc.resolve_field(r)
            if kind in ("found", "fallback", "none") or (is_descriptor(r) and kind != "found"):
                continue
            alt = alt_source_path(doc, r)
            if alt is not None:
                add("house", "warn", "source-path",
                    "source %r resolves only from the repo or bundle root; write it relative to this file: %s"
                    % (r, rel_from(doc.path, alt)), fixable="upgrade")
            else:
                add("content", "warn", "source-missing", "cited source %r doesn't exist" % r)
    for label, value in doc.path_fields():
        if doc.resolve_field(value)[1] == "fallback":
            add("okf", "warn", "path-root-fallback",
                "%s %r resolves only from the bundle root, which a bundle that declares 0.2 or no version may do; "
                "write it as /%s (okf.py upgrade fixes it)" % (label, value, value.lstrip("/")), fixable="upgrade")
    refs, defs = footnotes(doc)
    seen_labels = set()
    for label, line in refs + [(d, None) for d in sorted(defs)]:
        if label not in ids and label not in seen_labels:
            seen_labels.add(label)
            add("okf", "warn", "footnote-no-source",
                "footnote [^%s] has no `sources` entry with that id, so the claim isn't attributed" % label, line)

    for key, allowed in ENUMS.items():
        v = doc.ext(key)
        if v is not None and str(v).strip().lower() not in allowed:
            add("house", "warn", "enum-value", "`%s` is %r; use one of: %s" % (ext_key(key), v, ", ".join(allowed)))
    cred = doc.ext("credibility")
    if cred is not None and str(cred).strip().lower() == "verified":
        add("house", "warn", "credibility-verified",
            "`credibility: verified` is the v3 value; a human `verified` entry records review now "
            "(okf.py upgrade removes it where one exists)", fixable="upgrade")
    elif any(k in fm for k in CREDIBILITY_KEYS):
        add("house", "warn", "credibility-retired",
            "`%s` is retired: OKF 0.3 records where content came from in `sources` (a person who stated it is "
            "`author: \"human:<id>\"`), not as a label; okf.py upgrade removes it"
            % next(k for k in CREDIBILITY_KEYS if k in fm), fixable="upgrade")
    for name in EXT_NAMES:
        if name in fm:
            if ext_key(name) in fm:
                add("house", "warn", "legacy-key-name",
                    "`%s` and `%s` are both set; the new one wins: remove `%s`" % (name, ext_key(name), name),
                    fixable="upgrade")
            else:
                add("house", "warn", "legacy-key-name",
                    "`%s` is the 0.9 name; write `%s`" % (name, ext_key(name)), fixable="upgrade")
    for key, why in LEGACY_KEYS.items():
        if key in fm:
            add("house", "warn", "legacy-key", "`%s`: %s" % (key, why), fixable="upgrade" if key != "timestamp" else None)

    name = doc.path.name
    if not NAME_RE.match(name):
        add("house", "warn", "naming", "file name should be kebab-case, like `data-export.md`")
    klass = doc.klass
    if klass in ("observation", "asset") and not DATED_RE.match(name):
        add("house", "warn", "dated-name", "%s files start with their date: YYYY-MM-DD-slug.md" % klass)
    if klass == "decision" and doc.path.parent.name == "decisions" and not DECISION_RE.match(name):
        add("house", "warn", "decision-number", "decisions are named NNN-short-title.md")

    for target, line in body_links(doc):
        path = doc.resolve(target)
        if path is not None and not path.exists():
            add("content", "warn", "link-broken", "link target %s doesn't exist" % target, line)
        elif path is not None and not is_url(target):
            rooted = target.startswith("/")
            if (ctx.link_style == "rooted") != rooted and is_within(path, doc.bundle.root):
                add("house", "info", "link-style",
                    "link %s is %s; config says links: %s" % (target, "rooted" if rooted else "relative",
                                                            ctx.link_style), line)

    status = doc.status
    sa = doc.stale_after()
    if doc.is_stale(ctx.now):
        when = fmt_date(sa) if sa else "unparsable"
        if klass == "observation":
            add("content", "warn", "delete-candidate",
                "observation past its stale_after (%s): delete it, or re-check and extend" % when)
        else:
            add("content", "warn", "stale", "past its stale_after (%s): re-check it" % when)
    superseded = doc.get("superseded_by")
    if superseded is not None:
        if status != "deprecated":
            add("okf", "warn", "superseded-not-deprecated",
                "`superseded_by` is set, but it has a meaning only with `status: deprecated`: mark it deprecated, "
                "or delete the file and repoint links")
        if klass == "observation":
            add("content", "warn", "delete-candidate", "promoted observation (superseded_by is set): delete it; "
                                                       "the canonical file carries its sources")
    elif status == "deprecated" and klass != "decision":
        add("house", "info", "deprecated-no-replacement", "deprecated without `superseded_by`; name the replacement")
    if klass == "observation" and status != "deprecated" and superseded is None and not doc.is_stale(ctx.now):
        n = len(distinct_sources(doc))
        if n >= 2:
            add("content", "info", "promotion-candidate",
                "supported by %d sources; propose promoting it (lifecycle.md, Promotion)" % n)
    if status == "draft":
        add("content", "info", "draft", "draft: needs review")
    elif doc.current and klass != "asset" and not tracker:
        if doc.verification_outdated():
            add("content", "info", "verification-outdated",
                "verified before the last change on %s; re-check it" % fmt_date(doc.generated_at()))
        elif not doc.reviewed():
            add("content", "info", "unverified", "never verified")
        else:
            _check_bumped(doc, ctx, add)

    # Team updates are internal pages, and a voice file is guidance for writers, not a page.
    if doc.bundle.kind == "site" and doc.type.lower() not in ("update", "voice"):
        if doc.visibility != "public":
            add("house", "warn", "page-visibility",
                "site pages need `x-okfdocs-visibility: public`; only team updates (`type: update`) "
                "and the voice file (`type: voice`) stay internal")
        for e, path in doc.local_sources():
            src_doc = ctx.docs_by_path.get(norm(path))
            if src_doc is not None and src_doc.fm is not None and src_doc.visibility != "public":
                add("content", "warn", "public-source-internal",
                    "cites %s, which isn't `x-okfdocs-visibility: public`" % src_doc.prel)
    if doc.type.lower() == "attested computation":
        _check_attested(doc, add)
    if tracker_kind(doc):
        check_tracker(doc, ctx, add)
    return out


def _check_bumped(doc, ctx, add):
    """generated-not-bumped: the text changed since git HEAD, a verification still counts, and generated.at
    didn't move. A history line or a whitespace change doesn't count; a verification added since HEAD covers
    the new text."""
    if norm(doc.path) not in ctx.changed_since_head:
        return
    head = ctx.head_doc(doc)
    if head is None:
        return
    old_fm, old_body = head
    old_gen = None
    if isinstance(old_fm, dict) and isinstance(old_fm.get("generated"), dict):
        old_gen = parse_ts(old_fm["generated"].get("at"))[0]
    if doc.generated_at() != old_gen:
        return
    old_events = set()
    for e in as_list((old_fm or {}).get("verified")):
        if isinstance(e, dict):
            old_events.add((str(e.get("by")), parse_ts(e.get("at"))[0]))
    current = doc.current_events()
    if any((str(e.get("by")), parse_ts(e.get("at"))[0]) not in old_events for e in current):
        return
    if meaning_text(old_fm, old_body) == meaning_text(doc.fm, doc.body):
        return
    by = sorted({str(e.get("by")) for e in current})
    add("content", "warn", "generated-not-bumped",
        "the text changed since the last commit, but generated.at didn't move, so the verification by %s still "
        "counts for the new text: bump generated.at, or leave it if the edit was trivial (typo, format, link "
        "repair)" % ", ".join(by))


def _check_window(value, label, add):
    if not isinstance(value, dict) or blank(value.get("from")) or blank(value.get("to")):
        add("okf", "warn", "usage-window-format", "%s is a { from, to } mapping of timestamps" % label)


LOG_DATE_RE = re.compile(r"^##\s+(\S.*?)\s*$")


def distinct_sources(doc):
    """The distinct resources a file cites: local files by path, anything else by its text."""
    seen = set()
    for e in doc.source_entries():
        r = str(e["resource"]).strip()
        p, _ = doc.resolve_field(r)
        seen.add(norm(p) if p is not None and not is_url(r) else r.lower())
    return seen


def check_log(path, project):
    out = []
    p = relpath(path, project.root)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [Finding("okf", "error", "read-error", p, "can't read: %s" % exc)]
    fm, body, body_line, _ = split_frontmatter(text)
    if fm is not None:
        out.append(Finding("okf", "error", "log-frontmatter", p, "log.md has no frontmatter (OKF 0.3 section 9)",
                           fixable="fix"))
    prev = None
    for n, line in enumerate(body.split("\n"), body_line):
        m = LOG_DATE_RE.match(line)
        if not m:
            continue
        label = m.group(1)
        if not _DATE_RE.match(label):
            out.append(Finding("okf", "error", "log-format", p, "date heading %r isn't YYYY-MM-DD" % label, n))
            continue
        if prev and label > prev:
            out.append(Finding("okf", "warn", "log-order", p, "dates must run newest first (%s after %s)"
                               % (label, prev), n))
        prev = label
    return out


_LIST_LINE_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)]|\||>|#)")


def index_is_page(idx):
    """True when an index.md holds a page instead of a listing, as v3 product folders did
    (products/<name>/index.md). Indexes are rebuilt from the folder, so such a file is never rewritten."""
    try:
        text = idx.read_text(encoding="utf-8") if idx.is_file() else ""
    except (OSError, UnicodeDecodeError):
        return False
    _, body, _, _ = split_frontmatter(text)
    prose = [l for _, l in prose_lines(body or "") if l.strip() and not _LIST_LINE_RE.match(l)]
    return len(prose) >= 3


def page_indexes(bundle):
    """Every index.md in the bundle that holds a page, including folders with no other files."""
    out = []
    for dirpath, dirnames, filenames in os.walk(str(bundle.root)):
        dirnames[:] = sorted(n for n in dirnames if not n.startswith("."))
        if "index.md" in filenames and index_is_page(Path(dirpath) / "index.md"):
            out.append(Path(dirpath) / "index.md")
    return out


def page_index_hint(idx):
    d = idx.parent
    return ("index.md holds a page (v3 layout). OKF 0.3 section 3.1 never reads an index.md as a concept, and "
            "indexes leave it alone: move it to %s/%s.md, repoint links to it, then rebuild the index"
            % (d.name, d.name))


def bundle_overlaps(bundle):
    """Each bundle needs its own folder: a brain, a site or the docs never share a folder or sit inside another
    bundle, or their files, indexes and logs mix. Reported once, on the later or inner bundle."""
    out = []
    bundles = bundle.project.bundles
    for i, other in enumerate(bundles):
        if other is bundle:
            continue
        if norm(other.root) == norm(bundle.root):
            if i < bundles.index(bundle):
                out.append(Finding("house", "warn", "bundle-overlap", bundle.rel,
                                   "same folder as the %s bundle; give each bundle its own folder"
                                   % other.kind))
        elif is_within(bundle.root, other.root):
            out.append(Finding("house", "warn", "bundle-overlap", bundle.rel,
                               "inside the %s bundle %s; move it to its own folder, such as next to it"
                               % (other.kind, other.rel)))
    return out


def _check_root_index(bundle, p, fm_text):
    """The root index.md may carry okf_version, title, description, license and x- keys (OKF 0.3 section 8.1)."""
    out = []
    fix = "upgrade" if bundle.fallback_paths() else "fix"  # a 0.2 bundle with bare root paths needs upgrade first
    if fm_text is None:
        return [Finding("okf", "warn", "okf-version", p,
                        'declare okf_version: "%s" in the root index.md' % OKF_VERSION, fixable=fix)]
    try:
        data, warnings = yaml_load(fm_text, line_offset=1)
    except YAMLError as exc:
        return [Finding("okf", "error", "fm-invalid", p, "frontmatter isn't valid YAML: %s" % exc)]
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return [Finding("okf", "error", "fm-not-mapping", p, "frontmatter must be a YAML mapping")]
    for w in warnings:
        if "duplicate key" in w:
            out.append(Finding("okf", "error", "duplicate-key", p, "frontmatter repeats a key (%s); keys must be unique" % w))
        elif YAML11_NOTE in w:
            out.append(Finding("okf", "warn", "yaml-quote", p, w))
    version = data.get("okf_version")
    if blank(version):
        out.append(Finding("okf", "warn", "okf-version", p,
                           'okf_version is missing; set it to "%s"' % OKF_VERSION, fixable=fix))
    else:
        if not isinstance(version, str):
            out.append(Finding("okf", "warn", "yaml-quote", p,
                               'quote okf_version: write "%s" as a string' % OKF_VERSION, fixable=fix))
        vt = version_tuple(version)
        if vt is None or vt < OKF_VERSION_TUPLE:
            out.append(Finding("okf", "warn", "okf-version", p,
                               'okf_version is "%s": this bundle uses the older format; set "%s"%s'
                               % (version, OKF_VERSION, "" if fix == "fix" else " with okf.py upgrade"),
                               fixable=fix))
    for key in ("title", "description"):
        if not blank(data.get(key)) and not isinstance(data.get(key), str):
            out.append(Finding("okf", "warn", "yaml-quote", p, "quote `%s`: it parses as %s, not a string"
                               % (key, type(data[key]).__name__)))
    if blank(data.get("title")) or blank(data.get("description")):
        out.append(Finding("house", "info", "root-index-meta", p,
                           "add `title` and a one-sentence `description` (the scope of the bundle and when to "
                           "use it) to the root index.md"))
    lic = data.get("license")
    if isinstance(lic, str) and not SPDX_RE.match(lic.strip()) and not (bundle.root / lic.strip().lstrip("/")).exists():
        out.append(Finding("okf", "warn", "license-format", p,
                           "license %r is neither an SPDX expression nor a file in the bundle" % lic))
    stray = [k for k in data if str(k) in V3_ROOT_KEYS or str(k) in EXT_NAMES or str(k) in CREDIBILITY_KEYS]
    if stray:
        out.append(Finding("house", "warn", "index-frontmatter", p,
                           "root index.md holds concept keys (%s) that OKF 0.3 doesn't define there; "
                           "okf.py upgrade drops them" % ", ".join(map(str, stray)), fixable="upgrade"))
    return out


def index_page_finding(bundle, idx):
    # Below the root, an index.md with frontmatter breaks OKF 0.3 conformance (section 8).
    below_root = norm(idx.parent) != norm(bundle.root)
    return Finding("okf" if below_root else "house", "error" if below_root else "warn", "index-page",
                   relpath(idx, bundle.project.root), page_index_hint(idx))


def check_bundle(bundle, ctx, dirs=None):
    out = []
    project = bundle.project
    if not bundle.exists:
        return [Finding("house", "warn", "bundle-missing", bundle.rel, "bundle folder doesn't exist")]
    if dirs is None:
        out.extend(bundle_overlaps(bundle))
        for idx in page_indexes(bundle):
            out.append(index_page_finding(bundle, idx))
    for d in bundle.plain_index_dirs() if dirs is None else []:  # nothing to list: only the frontmatter rule
        idx = d / "index.md"
        if not index_is_page(idx) and _index_frontmatter(idx) is not None:
            out.append(Finding("okf", "error", "index-frontmatter", relpath(idx, project.root),
                               "only the bundle-root index.md may have frontmatter (OKF 0.3 section 8)",
                               fixable="fix"))
    for d in (dirs if dirs is not None else bundle.dirs_with_docs()):
        idx = d / "index.md"
        p = relpath(idx, project.root)
        if index_is_page(idx):
            if dirs is not None:
                out.append(index_page_finding(bundle, idx))
            continue
        if not idx.exists():
            out.append(Finding("house", "warn", "index-missing", p, "no index.md", fixable="fix"))
            continue
        try:
            current = idx.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm_text, _, _, _ = split_frontmatter(current)
        if norm(d) != norm(bundle.root):
            if fm_text is not None:
                out.append(Finding("okf", "error", "index-frontmatter", p,
                                   "only the bundle-root index.md may have frontmatter (OKF 0.3 section 8)",
                                   fixable="fix"))
        else:
            out.extend(_check_root_index(bundle, p, fm_text))
        expected, summary = build_index(bundle, d, ctx)
        if split_frontmatter(expected)[1].strip() != split_frontmatter(current)[1].strip():
            details = []
            if summary["added"]:
                details.append("missing: " + ", ".join(summary["added"][:5]))
            if summary["removed"]:
                details.append("lists what was deleted: " + ", ".join(summary["removed"][:5]))
            if summary["updated"]:
                details.append("%d entries out of date" % summary["updated"])
            out.append(Finding("house", "warn", "index-stale", p,
                               "index.md is out of date" + (" (" + "; ".join(details) + ")" if details else ""),
                               fixable="fix"))
        for title in summary["undescribed"]:
            out.append(Finding("house", "info", "folder-description", p,
                               "folder entry %r has no description; add one line after ' - '" % title))
    if dirs is None:
        if not (bundle.root / "log.md").exists():
            out.append(Finding("house", "warn", "log-missing", bundle.rel + "log.md", "no log.md", fixable="fix"))
        for d, _, files in bundle.walk():
            if "log.md" in files:
                out.extend(check_log(d / "log.md", project))
        for d in bundle.emptied_dirs():
            out.append(Finding("content", "warn", "delete-candidate", relpath(d, project.root) + "/",
                               "no docs left, only index.md or log.md: delete the folder and log the deletion "
                               "in the bundle's log.md"))
        out.extend(_check_bundle_docs(bundle, ctx))
    return out


def _check_bundle_docs(bundle, ctx):
    out = []
    docs = [d for d in bundle.docs if d.fm is not None and not d.nonconcept and d.klass != "tracker"]
    titles = {}
    for doc in docs:
        key = doc.title.strip().lower()
        if key in titles:
            out.append(Finding("content", "warn", "duplicate-title", doc.prel,
                               "same title as %s: one subject, one file" % titles[key].prel))
        else:
            titles[key] = doc
    numbers = {}
    for doc in docs:
        m = DECISION_RE.match(doc.path.name)
        if doc.klass == "decision" and m:
            key = (norm(doc.path.parent), int(m.group(1)))
            if key in numbers:
                out.append(Finding("house", "warn", "decision-number", doc.prel,
                                   "decision number %s is also used by %s" % (m.group(1), numbers[key].prel)))
            numbers[key] = doc
    for doc in docs:
        for key, back in (("superseded_by", "supersedes"), ("supersedes", "superseded_by")):
            raw = doc.get(key) if key == "superseded_by" else doc.ext("supersedes")
            for target in as_list(raw):
                path = doc.resolve_field(str(target))[0]
                if path is None:
                    continue
                other = ctx.docs_by_path.get(norm(path))
                if other is None:
                    if not path.exists():
                        out.append(Finding("house", "warn", "supersede-missing", doc.prel,
                                           "%s points to %s, which doesn't exist"
                                       % (key if key == "superseded_by" else ext_key(key), target)))
                    continue
                if doc.klass != "decision" or other.klass != "decision":
                    continue  # only decisions link both ways; a replaced file just names its replacement
                back_raw = other.get(back) if back == "superseded_by" else other.ext("supersedes")
                backs = as_list(back_raw)
                if not any(other.resolve_field(str(b))[0] is not None
                           and norm(other.resolve_field(str(b))[0]) == norm(doc.path) for b in backs):
                    out.append(Finding("house", "warn", "supersede-mutual", doc.prel,
                                       "%s is %s, but %s has no matching %s"
                                       % (key if key == "superseded_by" else ext_key(key), target, other.prel,
                                          back if back == "superseded_by" else ext_key(back))))
    if bundle.kind == "brain":
        for doc in bundle.docs:
            parts = doc.rel.split("/")
            if parts[0] in ("decisions", "observations", "assets") and len(parts) > 2:
                out.append(Finding("house", "warn", "brain-flat", doc.prel,
                                   "%s/ stays flat (no subfolders except assets/files/)" % parts[0]))
            elif len(parts) > 3:
                out.append(Finding("house", "warn", "brain-depth", doc.prel,
                                   "deeper than category → entity → file"))
        files_dir = bundle.root / "assets" / "files"
        keep = parse_duration((bundle.project.config.get("retention") or {}).get("raw_files"))
        if files_dir.is_dir() and keep and math.isfinite(keep):
            for raw in sorted(files_dir.rglob("*")):
                if not raw.is_file():
                    continue
                # age from the YYYY-MM-DD name prefix, since checkouts reset file times
                t = parse_ts(raw.name[:10])[0] if _DATE_RE.match(raw.name[:10]) else None
                t = t or mtime(raw)
                if t and (ctx.now - t).days > keep:
                    out.append(Finding("content", "info", "delete-candidate", relpath(raw, bundle.project.root),
                                       "raw file older than retention.raw_files: delete it, keep its metadata"))
    return out


# --------------------------------------------------------------------------
# index.md
# --------------------------------------------------------------------------

ENTRY_RE = re.compile(r"^(\s*)[*+-]\s+\[([^\]]+)\]\(\s*<?([^)\s>]+)>?\s*\)\s*(?:(?:-|–|—|:)\s*(.*?))?\s*$")
TYPE_LABELS = {
    "concept": "Concepts", "design": "Designs", "api": "APIs", "schema": "Schemas",
    "convention": "Conventions", "security": "Security", "runbook": "Runbooks", "decision": "Decisions",
    "observation": "Observations", "tutorial": "Tutorials", "how-to": "How-to guides",
    "reference": "Reference", "explanation": "Explanation", "troubleshooting": "Troubleshooting",
    "faq": "FAQ", "release": "Releases", "update": "Updates", "page": "Pages",
}
SECTIONS_HEADING = "Sections"


CLASS_LABELS = {"decision": "Decisions", "observation": "Observations", "asset": "Assets",
                "reference": "References"}
GROUP_ORDER = list(TYPE_LABELS.values()) + list(CLASS_LABELS.values())


def _group_label(doc, dirpath):
    if doc.klass in CLASS_LABELS:
        return CLASS_LABELS[doc.klass]
    if doc.bundle.kind == "brain":
        return humanize(dirpath.name) if norm(dirpath) != norm(doc.bundle.root) else "Knowledge"
    t = doc.type.lower()
    if t in TYPE_LABELS:
        return TYPE_LABELS[t]
    label = humanize(t) if t else "Documents"
    return label if label.endswith("s") else (label[:-1] + "ies" if label.endswith("y") else label + "s")


def _sort_key(name, title):
    if DATED_RE.match(name):
        return (0, "".join(chr(0x10FFFF - ord(c)) for c in name))  # newest date first
    if DECISION_RE.match(name):
        return (1, name)
    return (2, title.lower())


def _parse_index(body):
    sections = [{"heading": None, "items": []}]
    fence = None
    for line in body.split("\n"):
        fence, in_code = fence_step(fence, line)
        if not in_code:
            m = _HEADING_RE.match(line)
            if m:
                sections.append({"heading": line.rstrip(), "title": m.group(2).strip(), "items": []})
                continue
            m = ENTRY_RE.match(line)
            if m:
                sections[-1]["items"].append(["entry", {"indent": m.group(1), "title": m.group(2),
                                                        "url": m.group(3), "desc": (m.group(4) or "").strip()}])
                continue
        sections[-1]["items"].append(["text", line])
    return sections


def _entry_line(e):
    line = "%s* [%s](%s)" % (e.get("indent", ""), e["title"], e["url"])
    return line + (" - " + e["desc"] if e.get("desc") else "")


def _end_of_list(items):
    """Position for a new entry at the end of a section: before its trailing blank lines, so the list stays one list."""
    pos = len(items)
    while pos and items[pos - 1][0] == "text" and not items[pos - 1][1].strip():
        pos -= 1
    return pos


_TOP_KEY_RE = re.compile(r"""^(?:"([^"]+)"|'([^']+)'|([^\s#:'"-][^:#]*?))\s*:(?:\s|$)""")


def _fm_blocks(fm_text):
    """[(top-level key or None, [lines])] for a frontmatter block; indented lines, comments and blank lines
    belong to the key above them."""
    blocks = []
    for line in fm_text.split("\n"):
        m = _TOP_KEY_RE.match(line)
        if m:
            blocks.append((next(g for g in m.groups() if g).strip(), [line]))
        elif blocks:
            blocks[-1][1].append(line)
        else:
            blocks.append((None, [line]))
    return blocks


def root_frontmatter(existing, bump=True, upgrade=False):
    """The frontmatter text for a root index.md and the notes on what changed. It keeps the existing
    frontmatter exactly (OKF 0.3 section 8.1), except it sets okf_version to the current version when it is
    missing or older (bump), and, for upgrade, drops the v3 concept keys the root index doesn't define.
    Without bump, a root index that has no frontmatter gets none (None), so the bundle declares no version."""
    notes = []
    fm_text = split_frontmatter(existing)[0] if existing else None
    if fm_text is None:
        return ('okf_version: "%s"' % OKF_VERSION if bump else None), notes
    try:
        data = yaml_load(fm_text)[0]
    except YAMLError:
        return fm_text, notes
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return fm_text, notes
    blocks = _fm_blocks(fm_text) if fm_text.strip() else []
    version = data.get("okf_version")
    vt = version_tuple(version) if not blank(version) else None
    if bump and (blank(version) or not isinstance(version, str) or vt is None or vt < OKF_VERSION_TUPLE):
        line = 'okf_version: "%s"' % OKF_VERSION
        for i, (key, lines) in enumerate(blocks):
            if key == "okf_version":
                blocks[i] = (key, [line])
                break
        else:
            blocks.insert(0, ("okf_version", [line]))
        if blank(version) or vt is None or vt < OKF_VERSION_TUPLE:
            notes.append("okf_version: %s -> \"%s\"" % (version if not blank(version) else "missing", OKF_VERSION))
    if upgrade:
        kept = []
        for key, lines in blocks:
            if key in V3_ROOT_KEYS or key in EXT_NAMES or key in CREDIBILITY_KEYS:
                notes.append("dropped root index key `%s` (OKF 0.3 doesn't define it there)" % key)
            else:
                kept.append((key, lines))
        blocks = kept
    return "\n".join(line for _, lines in blocks for line in lines).rstrip("\n"), notes


def _index_frontmatter(idx):
    """The frontmatter text of an index.md, or None when it has none or can't be read."""
    try:
        return split_frontmatter(idx.read_text(encoding="utf-8"))[0]
    except (OSError, UnicodeDecodeError):
        return None


def strip_index_frontmatter(idx, write=True):
    """Drop the frontmatter block from a subfolder index.md and keep the rest. True when there was one."""
    try:
        fm, body, _, _ = split_frontmatter(idx.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return False
    if fm is None:
        return False
    if write:
        write_lf(idx, body.lstrip("\n"))
    return True


def build_index(bundle, dirpath, ctx, upgrade=False, bump=True):
    """Expected index.md text for dirpath, merged with the existing file. Returns (text, summary).
    The root index keeps its frontmatter; see root_frontmatter. With upgrade, bump=False keeps the version."""
    is_root = norm(dirpath) == norm(bundle.root)
    files = sorted((d for d in bundle.indexable if norm(d.path.parent) == norm(dirpath)), key=lambda d: d.path.name)
    file_keys = {norm(d.path): d for d in files}
    subdirs = {}
    for doc in bundle.indexable:
        if is_within(doc.path, dirpath) and norm(doc.path.parent) != norm(dirpath):
            child = Path(os.path.normpath(str(dirpath / doc.path.relative_to(dirpath).parts[0])))
            subdirs[norm(child)] = child
    idx = dirpath / "index.md"
    existing = ""
    if idx.exists():
        try:
            existing = idx.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            existing = ""
    _, body, _, _ = split_frontmatter(existing) if existing else (None, "", 1, None)
    sections = _parse_index(body) if existing else [{"heading": None, "items": []}]
    summary = {"added": [], "removed": [], "updated": 0, "undescribed": [], "root_notes": []}
    listed = set()
    rooted = ctx.link_style == "rooted"

    def url_for(path, is_dir):
        if rooted:
            u = "/" + relpath(path, bundle.root)
        else:
            u = relpath(path, dirpath)
        return u + "/" if is_dir else u

    for sec in sections:
        kept = []
        for item in sec["items"]:
            if item[0] != "entry":
                kept.append(item)
                continue
            e = item[1]
            url = e["url"]
            if is_url(url):
                kept.append(item)
                continue
            clean = urllib.parse.unquote(url.split("#", 1)[0])
            target = Path(os.path.normpath(str(bundle.root / clean.lstrip("/") if clean.startswith("/")
                                               else dirpath / clean)))
            if target.name == "index.md":
                target = target.parent
            key = norm(target)
            if key in file_keys and key not in listed:
                doc = file_keys[key]
                new = e if doc.fm is None else dict(e, title=doc.title.replace("]", ")"),
                                                    desc=doc.description or e["desc"])
                if new["title"] != e["title"] or new["desc"] != e["desc"]:
                    summary["updated"] += 1
                kept.append(["entry", new])
                listed.add(key)
            elif key in subdirs and key not in listed:
                kept.append(item)
                listed.add(key)
                if not e["desc"]:
                    summary["undescribed"].append(e["title"])
            elif key in listed:
                summary["removed"].append(url + " (listed twice)")
            elif not target.exists() or key in (norm(dirpath),):
                summary["removed"].append(url)
            elif (target.is_dir() and is_within(target, bundle.root) and norm(target) != norm(bundle.root)
                  and not Bundle.skips(target.parent, target.name)
                  and norm(target) in {norm(p) for p in bundle.emptied_dirs()}):
                summary["removed"].append(url + " (no docs left)")  # emptied by deletions
            else:
                kept.append(item)
        sec["items"] = kept

    def section_for(label, first=False):
        for sec in sections:
            if sec["heading"] and sec.get("title", "").lower() == label.lower():
                return sec
        sec = {"heading": "# " + label, "title": label, "items": []}
        if first:
            pos = 1 if sections and sections[0]["heading"] is None else 0
            sections.insert(pos, sec)
        else:
            sections.append(sec)
        return sec

    new_dirs = [p for k, p in subdirs.items() if k not in listed]
    if new_dirs:
        sec = section_for(SECTIONS_HEADING, first=True)
        for p in sorted(new_dirs, key=lambda p: p.name):
            title = humanize(p.name)
            sec["items"].insert(_end_of_list(sec["items"]), ["entry", {"title": title, "url": url_for(p, True), "desc": ""}])
            summary["added"].append(p.name + "/")
            summary["undescribed"].append(title)
    new_files = [d for k, d in file_keys.items() if k not in listed]
    groups = {}
    for doc in new_files:
        groups.setdefault(_group_label(doc, dirpath), []).append(doc)
    for label in sorted(groups, key=lambda s: (GROUP_ORDER.index(s) if s in GROUP_ORDER else len(GROUP_ORDER), s)):
        sec = section_for(label)
        for doc in sorted(groups[label], key=lambda d: _sort_key(d.path.name, d.title)):
            item = ["entry", {"title": doc.title.replace("]", ")"), "url": url_for(doc.path, False),
                              "desc": doc.description}]
            pos = _end_of_list(sec["items"])
            if DATED_RE.match(doc.path.name):  # keep dated lists newest first
                for k, (kind, val) in enumerate(sec["items"]):
                    name = val["url"].rstrip("/").rsplit("/", 1)[-1] if kind == "entry" else ""
                    if DATED_RE.match(name) and name < doc.path.name:
                        pos = k
                        break
            sec["items"].insert(pos, item)
            summary["added"].append(doc.path.name)

    lines = []
    if is_root:
        # a 0.2 bundle with bare root-relative paths keeps its version until upgrade rewrites them
        fm_text, summary["root_notes"] = root_frontmatter(existing, bump=bump if upgrade else not bundle.fallback_paths(),
                                                          upgrade=upgrade)
        if fm_text is not None:
            lines += ["---", fm_text, "---", ""]
    for sec in sections:
        items = sec["items"]
        while items and items[0][0] == "text" and not items[0][1].strip():
            items.pop(0)
        while items and items[-1][0] == "text" and not items[-1][1].strip():
            items.pop()
        has_entries = any(i[0] == "entry" for i in items)
        has_text = any(i[0] == "text" and i[1].strip() for i in items)
        if sec["heading"] is not None and not has_entries and not has_text:
            continue
        if sec["heading"] is None and not items:
            continue
        if sec["heading"] is not None:
            lines += [sec["heading"], ""]
        prev_blank = False
        for kind, val in items:
            line = _entry_line(val) if kind == "entry" else val.rstrip()
            if not line.strip():
                if prev_blank:
                    continue
                prev_blank = True
            else:
                prev_blank = False
            lines.append(line)
        lines.append("")
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines) + "\n", summary


def fix_bundle(bundle, ctx):
    """Mechanical repairs: indexes, root okf_version, log.md frontmatter, missing log.md. Returns changed paths."""
    changed = []
    if not bundle.exists:
        return changed
    for d in bundle.dirs_with_docs():
        idx = d / "index.md"
        if index_is_page(idx):
            continue
        text, _ = build_index(bundle, d, ctx)
        old = idx.read_text(encoding="utf-8") if idx.exists() else None
        if old is None or old.strip() != text.strip():
            write_lf(idx, text)
            changed.append(relpath(idx, bundle.project.root))
    for d in bundle.plain_index_dirs():
        if not index_is_page(d / "index.md") and strip_index_frontmatter(d / "index.md"):
            changed.append(relpath(d / "index.md", bundle.project.root))
    for d, _, files in bundle.walk():  # log.md has no frontmatter (OKF 0.3 section 9)
        if "log.md" in files and strip_log_frontmatter(d / "log.md"):
            changed.append(relpath(d / "log.md", bundle.project.root))
    log = bundle.root / "log.md"
    if not log.exists():
        write_lf(log, "# Directory Update Log\n")
        changed.append(relpath(log, bundle.project.root))
    return changed


def strip_log_frontmatter(path, write=True):
    """Drop the frontmatter block from a log.md. Returns True when there was one."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    fm, body, _, _ = split_frontmatter(text)
    if fm is None:
        return False
    if write:
        write_lf(path, body.lstrip("\n").rstrip("\n") + "\n")
    return True


# --------------------------------------------------------------------------
# log.md
# --------------------------------------------------------------------------

def add_log_entry(folder, kind, message, today=None):
    """Add `* **Kind**: message` under today's `## YYYY-MM-DD` heading in folder/log.md, newest first."""
    path = folder / "log.md"
    today = today or dt.date.today().isoformat()
    label = kind.strip().strip("*").strip()
    entry = "* **%s**: %s" % (label[:1].upper() + label[1:], " ".join(message.split()))
    text = path.read_text(encoding="utf-8") if path.exists() else "# Directory Update Log\n"
    lines = text.rstrip("\n").split("\n")
    first = next((i for i, line in enumerate(lines) if LOG_DATE_RE.match(line)), None)
    if first is not None and LOG_DATE_RE.match(lines[first]).group(1) == today:
        p = first + 1
        while p < len(lines) and not lines[p].strip():
            p += 1
        lines[first + 1:p] = ["", entry]
    else:
        at = first if first is not None else len(lines)
        lines[at:at] = ["## " + today, "", entry, ""]
    out = []
    for line in lines:
        if not line.strip():
            if out and out[-1].strip():
                out.append("")
            continue
        if line.startswith("#") and out and out[-1].strip():
            out.append("")
        out.append(line)
    write_lf(path, "\n".join(out).strip("\n") + "\n")
    return path


def last_log_date_of(path, kind):
    """The newest `## date` heading in a log.md that has a `**kind**` entry under it, or None."""
    best = None
    try:
        day = None
        for line in path.read_text(encoding="utf-8").split("\n"):
            m = LOG_DATE_RE.match(line)
            if m:
                day = m.group(1) if _DATE_RE.match(m.group(1)) else None
            elif day and "**%s**" % kind in line and (best is None or day > best):
                best = day
    except (OSError, UnicodeDecodeError):
        pass
    return best


def asset_date(doc):
    """YYYY-MM-DD of an asset: generated.at, else the date in its file name, else None."""
    gen = doc.generated_at()
    if gen:
        return gen.date().isoformat()
    m = DATED_RE.match(doc.path.name)
    return doc.path.name[:10] if m else None


def assets_since_review(bundle):
    """(count, date of the last Review log entry or None) for the assets added after that date."""
    last = last_log_date_of(bundle.root / "log.md", "Review")
    n = 0
    for doc in bundle.docs:
        if doc.fm is None or doc.nonconcept or doc.klass != "asset":
            continue
        d = asset_date(doc)
        if d and (last is None or d > last):
            n += 1
    return n, last


def last_log_date(path):
    try:
        for line in path.read_text(encoding="utf-8").split("\n"):
            m = LOG_DATE_RE.match(line)
            if m and _DATE_RE.match(m.group(1)):
                return m.group(1)
    except (OSError, UnicodeDecodeError):
        pass
    return None


def last_sync_ref(project):
    """The commit named in the newest **Sync** log entry of a docs bundle, if git knows it."""
    if not project.git_root:
        return None
    for b in project.bundles:
        log = b.root / "log.md"
        if b.kind != "docs" or not log.exists():
            continue
        for line in log.read_text(encoding="utf-8", errors="replace").split("\n"):
            if "**Sync**" in line:
                for sha in re.findall(r"\b[0-9a-f]{7,40}\b", line):
                    if run_git(["rev-parse", "--verify", "--quiet", sha + "^{commit}"], project.git_root):
                        return sha
    return None


# --------------------------------------------------------------------------
# Lint
# --------------------------------------------------------------------------

LINT_RULES = [
    ("filler", r"\bit(?:'s|’s| is) (?:important|worth|crucial|essential|key) to (?:note|mention|remember|"
               r"understand|highlight)(?: that)?", "cut it; start with the fact"),
    ("filler", r"\bit should be noted(?: that)?", "cut it"),
    ("filler", r"\bplease note(?: that)?", "cut it"),
    ("filler", r"\bin this (?:document|guide|section|article|page|post|tutorial)\b", "cut it; say the thing"),
    ("filler", r"\bthis (?:document|page|guide|section|article) (?:describes|explains|covers|outlines|provides)",
     "cut it; state the content"),
    ("filler", r"\blet(?:'|’)?s (?:dive|take a (?:closer )?look|explore|get started|begin)\b", "cut it"),
    ("filler", r"\b(?:dive|delve|deep[- ]dive) (?:deep )?into\b", "cut it"),
    ("filler", r"\bin today(?:'|’)?s (?:fast-paced|digital|modern|ever-changing)", "cut it"),
    ("filler", r"\bwhen it comes to\b", "use 'for', or cut it"),
    ("filler", r"\bat the end of the day\b", "cut it"),
    ("filler", r"\bin order to\b", "use 'to'"),
    ("filler", r"\bas (?:mentioned|noted|discussed|stated|described) (?:above|earlier|previously|before)\b",
     "cut it, or link the section"),
    ("filler", r"\b(?:needless to say|first and foremost|without further ado)\b", "cut it"),
    ("filler", r"\b(?:in conclusion|to summari[sz]e|in summary|all in all)\b", "cut the recap"),
    ("filler", r"\bthe (?:fact|reality) (?:is|of the matter is) that\b", "cut it"),
    ("hedge", r"\b(?:might|may|could|can) potentially\b", "state it, or state the condition"),
    ("hedge", r"\b(?:arguably|seemingly|somewhat|more or less|to some extent|generally speaking|"
              r"for the most part)\b", "state it, or state the condition"),
    ("hedge", r"\bit (?:seems|appears) (?:that|like)\b", "state it, or say who observed it"),
    ("intensifier", r"\b(?:basically|essentially|literally|actually|really|very|truly|extremely|incredibly|"
                    r"absolutely)\b", "cut it"),
    ("hype", r"\b(?:seamless(?:ly)?|robust|powerful|cutting[- ]edge|state[- ]of[- ]the[- ]art|revolutionary|"
             r"game[- ]chang(?:ing|er)|best[- ]in[- ]class|world[- ]class|next[- ]gen(?:eration)?|"
             r"(?:blazing(?:ly)?|lightning)[- ]fast|effortless(?:ly)?|unparalleled|groundbreaking|transformative|"
             r"innovative|holistic|synerg(?:y|ies|istic)|comprehensive)\b", "say what it does, with a number"),
    ("hype", r"\b(?:leverag(?:e|es|ed|ing)|empower(?:s|ed|ing)?|supercharg(?:e|es|ed|ing)|unleash(?:es|ed|ing)?|"
             r"streamlin(?:e|es|ed|ing)|revolutioniz(?:e|es|ed|ing))\b", "use a plain verb: use, enable, speed up"),
    ("hype", r"\b(?:a testament to|in the realm of|tapestry|to the next level|look no further|rest assured|"
             r"say goodbye to)\b", "cut it"),
    ("chat", r"(?:\bgreat question\b|\bi hope this helps\b|\bfeel free to\b|\bdon(?:'|’)?t hesitate to\b|"
             r"\bhappy to help\b|\blet me know if\b|\bcertainly!|\babsolutely!)", "cut it"),
    ("construction", r"\bit(?:'|’)?s not (?:just |only |merely )?[^.;:\n]{1,40}?[,;—–] *it(?:'|’)?s\b",
     "say what it is"),
]
_LINT = [(cat, re.compile(rx, re.I), advice) for cat, rx, advice in LINT_RULES]
_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\U0001F000-\U0001F2FF☀-➿⭐⬆⤴⤵]")
_RECAP_RE = re.compile(r"^(?:summary|conclusions?|wrap[- ]?up|final thoughts|key takeaways|in summary|recap)$", re.I)
_PLACEHOLDER_RE = re.compile(r"^(?:tbd|todo|tba|coming soon|n/?a|\.\.\.|…|-)\.?$", re.I)
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’-]*")
_URL_RE = re.compile(r"https?://\S+")
_LINK_TEXT_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
# unordered only: numbered steps with a bold step name are a sound pattern
_BOLD_BULLET_RE = re.compile(r"^[-*+]\s+(?:\*\*|__)[^*_\n]+(?:\*\*|__)")
_QUOTED_RE = re.compile(r"\"[^\"\n]*\"|“[^”\n]*”")  # quoted words are someone else's: not linted
_LIST_MARK_RE = re.compile(r"^(?:[-*+]|\d+\.)\s+")
_HTML_TAGS = ("a|abbr|b|br|code|del|details|div|em|i|iframe|img|ins|kbd|mark|p|picture|pre|q|s|small|source|span|"
              "strong|sub|summary|sup|table|tbody|td|th|thead|tr|u|video")
# Template text such as <what it does, in one sentence>: words with a space between < and >, not an HTML tag
_TEMPLATE_RE = re.compile(r"<(?!(?:%s)\b)[A-Za-z][\w,.'’()/-]*\s[\w ,.'’()/-]*>" % _HTML_TAGS)


def lint_text(text):
    """Return {"words", "hits": [{line, category, text, advice}], "per100"} for markdown text."""
    fm, body, body_line, _ = split_frontmatter(text)
    offset = body_line - 1 if fm is not None else 0
    source = body if fm is not None else text
    hits, words, bold, long_lines = [], 0, 0, []
    headings = []
    content_since = {}
    run = [None, 0]  # first line and length of the current run of bold-label bullets

    def end_run():
        if run[1] >= 5:
            hits.append({"line": run[0], "category": "structure", "text": "%d bold-label bullets" % run[1],
                         "advice": "use a table, or plain sentences"})
        run[0], run[1] = None, 0

    for n, raw in prose_lines(source):
        line_no = n + offset
        line = _URL_RE.sub("", _LINK_TEXT_RE.sub(r"\1", raw))
        stripped = line.strip()
        if _BOLD_BULLET_RE.match(stripped):
            run[0] = run[0] or line_no
            run[1] += 1
        elif stripped:
            end_run()
        if re.match(r"^\|?\s*:?-{3,}", stripped):
            continue
        m = _HEADING_RE.match(stripped)
        if m:
            headings.append((line_no, len(m.group(1)), m.group(2)))
            if _EMOJI_RE.search(m.group(2)):
                hits.append({"line": line_no, "category": "structure", "text": m.group(2),
                             "advice": "drop the emoji from the heading"})
        elif stripped and headings:
            content_since.setdefault(headings[-1][0], []).append(stripped)
        w = _WORD_RE.findall(line)
        words += len(w)
        bold += len(re.findall(r"\*\*[^*\n]+\*\*|__[^_\n]+__", line))
        unquoted = _QUOTED_RE.sub('""', line)
        for cat, rx, advice in _LINT:
            for hit in rx.finditer(unquoted):
                hits.append({"line": line_no, "category": cat, "text": hit.group(0), "advice": advice})
        for hit in _TEMPLATE_RE.finditer(line):
            hits.append({"line": line_no, "category": "structure", "text": hit.group(0),
                         "advice": "template text left in: fill it in or cut it"})
        if not m:
            for sentence in re.split(r"(?<=[.!?])\s+", stripped):
                if len(_WORD_RE.findall(sentence)) > 35:
                    long_lines.append(line_no)
            if re.search(r"\w!(?:\s|$)", line):
                hits.append({"line": line_no, "category": "structure", "text": "!",
                             "advice": "drop the exclamation mark"})
    end_run()
    for i, (line_no, level, title) in enumerate(headings):
        body_lines = content_since.get(line_no, [])
        nxt = headings[i + 1] if i + 1 < len(headings) else None
        if not body_lines and (nxt is None or nxt[1] <= level):
            hits.append({"line": line_no, "category": "structure", "text": title,
                         "advice": "empty section: fill it or remove the heading"})
        elif body_lines and all(_PLACEHOLDER_RE.match(_LIST_MARK_RE.sub("", b).strip("*_ ")) for b in body_lines):
            hits.append({"line": line_no, "category": "structure", "text": title,
                         "advice": "placeholder section: fill it or remove it"})
    if headings and len(headings) > 1 and headings[-1][1] >= 2 and _RECAP_RE.match(headings[-1][2].strip()):
        hits.append({"line": headings[-1][0], "category": "structure", "text": headings[-1][2],
                     "advice": "recap at the end: delete it, or move one summary line to the top"})
    if bold >= 4 and words and bold * 100.0 / words > 3:
        hits.append({"line": None, "category": "structure", "text": "%d bold spans" % bold,
                     "advice": "bold only what a skimmer must not miss"})
    for line_no in long_lines[:5]:
        hits.append({"line": line_no, "category": "long-sentence", "text": "> 35 words",
                     "advice": "split it"})
    counted = [h for h in hits if h["category"] != "long-sentence"]
    hits.sort(key=lambda h: (h["line"] or 0))
    return {"words": words, "hits": hits, "per100": round(len(counted) * 100.0 / words, 1) if words else 0.0}


# --------------------------------------------------------------------------
# Change times and the re-check queue
# --------------------------------------------------------------------------

def change_times(project, paths):
    """{path: (time, commit or None)} for files: last commit, or mtime when uncommitted or outside git."""
    paths = {norm(p): p for p in paths if p.is_file()}
    result = {}
    root = project.git_root
    if root and paths:
        rels = {}
        for key, p in paths.items():
            r = relpath(p, root)
            if not r.startswith(".."):
                rels[r] = key
        names = sorted(rels)
        for i in range(0, len(names), 300):
            chunk = names[i:i + 300]
            out = run_git(["log", "--format=%x00%H %cI", "--name-only", "--no-renames", "--"] + chunk, root, 60)
            if out is None:
                continue
            commit, when = None, None
            for line in out.split("\n"):
                if line.startswith("\x00"):
                    parts = line[1:].split(" ", 1)
                    commit = parts[0]
                    when = parse_ts(parts[1])[0] if len(parts) > 1 else None
                    continue
                line = line.strip()
                if not line or line not in rels:
                    continue
                key = rels[line]
                entry = result.setdefault(key, {"time": when, "commit": commit, "commits": set()})
                entry["commits"].add(commit)
        status = run_git(["status", "--porcelain", "-z", "--untracked-files=all", "--"] + names[:2000], root)
        if status:
            fields = status.split("\x00")
            i = 0
            while i < len(fields):
                f = fields[i]
                i += 1
                if len(f) < 4:
                    continue
                code, name = f[:2], f[3:]
                if "R" in code or "C" in code:
                    i += 1  # skip the original path
                key = rels.get(name)
                if key:
                    entry = result.setdefault(key, {"time": None, "commit": None, "commits": set()})
                    entry["time"], entry["commit"] = mtime(paths[key]), None
    for key, p in paths.items():
        if key not in result:
            result[key] = {"time": mtime(p), "commit": None, "commits": set()}
    return result


def stale_queue(project, ctx, docs=None):
    docs = [d for d in (docs if docs is not None else ctx.docs_by_path.values())
            if d.fm is not None and not d.nonconcept and d.klass != "tracker"]
    sources = {}
    for doc in docs:
        sources[norm(doc.path)] = [(e, p) for e, p in doc.local_sources() if p.is_file()]
    all_paths = [p for lst in sources.values() for _, p in lst] + [d.path for d in docs]
    times = change_times(project, all_paths)
    tolerance = dt.timedelta(minutes=2)
    queue = []
    for doc in docs:
        reasons, hard = [], False
        last = doc.last_check()
        sa = doc.stale_after()
        stale = doc.is_stale(ctx.now)
        if stale:
            reasons.append("past stale_after (%s)" % fmt_date(sa) if sa
                           else "stale_after isn't a valid timestamp, so it counts as stale")
            hard = True
        doc_info = times.get(norm(doc.path)) or {}
        doc_commits = doc_info.get("commits", set())
        floor = last
        if last and doc_info.get("time") and doc_info.get("commit") is None:
            floor = max(last, doc_info["time"])  # doc edited but not committed, or no git: the edit counts
        for e, p in sources[norm(doc.path)]:
            info = times.get(norm(p))
            if not info or not info["time"] or not floor:
                continue
            if info["time"] > floor + tolerance and not (info["commit"] and info["commit"] in doc_commits):
                reasons.append("source changed %s: %s" % (fmt_date(info["time"]), relpath(p, project.root)))
                hard = True
        weight, age = ctx.decay_weight(doc)
        if not hard and weight < 0.5 and age is not None:
            reasons.append("past half-life: last checked %s (%d days ago; half-life %d days)"
                           % (fmt_date(doc.last_check()), age, ctx.half_life(doc)))
        if last is None and not reasons:
            reasons.append("no generated.at or verified.at")
        if reasons:
            queue.append({"path": doc.prel, "title": doc.title, "hard": hard, "weight": round(weight, 2),
                          "trust": doc.trust(), "trust_note": doc.trust_note(), "status": doc.status,
                          "class": doc.klass, "reasons": reasons,
                          "delete_candidate": doc.klass == "observation" and stale})
    queue.sort(key=lambda q: (not q["hard"], q["weight"], q["path"]))
    return queue


UNCOVERED_SKIP = re.compile(
    r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|bun\.lockb?|Cargo\.lock|poetry\.lock|uv\.lock|"
    r"Gemfile\.lock|composer\.lock|go\.sum|AGENTS\.md|CLAUDE\.md|\.gitignore|\.okf/.*)$"
    r"|(^|/)(tests?|__tests__|spec|fixtures)/|\.(test|spec)\.[a-z0-9]+$"
    r"|\.(png|jpe?g|gif|svg|ico|webp|pdf|lock|map|min\.js)$", re.I)


def changes_since(project, ctx, ref):
    root = project.git_root
    if not root:
        why = "git didn't run here" if dot_git(project.root) else "not a git repository"
        return {"error": "can't compare with %s: %s" % (ref, why)}
    if not run_git(["rev-parse", "--verify", "--quiet", ref + "^{commit}"], root):
        return {"error": "unknown git ref: %s" % ref}
    out = run_git(["diff", "--name-only", "-z", ref], root) or ""
    names = [n for n in out.split("\x00") if n]
    untracked = run_git(["ls-files", "--others", "--exclude-standard", "-z"], root) or ""
    names += [n for n in untracked.split("\x00") if n]
    changed = {norm(root / n): n for n in names}
    cited = {}
    for doc in ctx.docs_by_path.values():
        if doc.fm is None:
            continue
        for _, p in doc.local_sources():
            if norm(p) in changed:
                cited.setdefault(norm(p), []).append(doc.prel)
    bundle_roots = [b.root for b in project.bundles]
    affected = {}
    for key, docs in cited.items():
        for d in docs:
            affected.setdefault(d, []).append(changed[key])
    uncovered = []
    for key, name in sorted(changed.items(), key=lambda kv: kv[1]):
        if key in cited or UNCOVERED_SKIP.search(name):
            continue
        if any(is_within(root / name, b) for b in bundle_roots):
            continue
        uncovered.append(name)
    commits = run_git(["rev-list", "--count", ref + "..HEAD"], root)
    return {"ref": ref, "commits": int(commits.strip()) if commits and commits.strip().isdigit() else None,
            "changed": len(changed), "affected": [{"path": k, "sources": v} for k, v in sorted(affected.items())],
            "uncovered": uncovered}


# --------------------------------------------------------------------------
# find
# --------------------------------------------------------------------------

STOPWORDS = set("""a an and are as at be by can do does for from has have how i in is it its of on or our
that the this to was we what when where which who why will with you your about into than then there these
they those""".split())


def _stem(w):
    for suffix in ("ing", "ed", "es", "s"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[:-len(suffix)]
    return w


def _tokens(text):
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", str(text).lower()) if w not in STOPWORDS and len(w) > 1}


def rank(project, ctx, query, include_all=False, body=True):
    q = _tokens(query)
    results = []
    if not q:
        return results
    for doc in ctx.docs_by_path.values():
        if doc.fm is None or doc.nonconcept:
            continue
        fields = [
            (4.0, _tokens(doc.title)), (3.0, _tokens(doc.description)),
            (3.0, _tokens(" ".join(doc.tags))),
            (2.0, _tokens(doc.scope)), (2.0, _tokens(doc.rel.replace("/", " ").replace("-", " "))),
        ]
        heads = " ".join(m.group(2) for _, l in prose_lines(doc.body) for m in [_HEADING_RE.match(l)] if m)
        fields.append((1.5, _tokens(heads)))
        if body:
            fields.append((0.5, _tokens(doc.body)))
        score = sum(w for tok in q for w, field in fields if tok in field)
        if score <= 0:
            continue
        flags = []
        if doc.status == "deprecated":
            if not include_all:
                score *= 0.3
            flags.append("deprecated")
        elif not doc.current and doc.status != "draft":  # an unknown status isn't current (OKF 0.3 section 5.4)
            if not include_all:
                score *= 0.3
            flags.append("not-current")
        if doc.status == "draft":
            score *= 0.8
            flags.append("draft")
        trust = doc.trust()
        score *= {"human-reviewed": 1.15, "machine-confirmed": 1.05}.get(trust, 1.0)
        if not doc.sourced() and doc.klass not in ("asset", "tracker"):
            score *= 0.9  # nothing says where it came from
        weight, _ = ctx.decay_weight(doc)
        score *= 0.5 + 0.5 * weight
        if doc.is_stale(ctx.now):
            score *= 0.8
            flags.append("stale")
        results.append({"path": doc.prel, "score": round(score, 2), "title": doc.title, "type": doc.type,
                        "description": doc.description, "trust": trust, "trust_note": doc.trust_note(),
                        "sourced": doc.sourced(), "stated_by": doc.stated_by(),
                        "last_check": fmt_date(doc.last_check()) if doc.last_check() else None,
                        "specificity": doc.ext("specificity"), "flags": flags})
    results.sort(key=lambda r: (-r["score"], r["path"]))
    return results


# --------------------------------------------------------------------------
# upgrade (v3 → v0.2 house format)
# --------------------------------------------------------------------------

AGENT_RE = re.compile(r"(?:^|[^a-z])(?:agent|ai|claude|assistant|bot|llm|gpt|model|okf[-_ ]?docs|"
                      r"(?:okf[-_ ]?)?company[-_ ]?brain)(?:$|[^a-z])", re.I)


def _upgrade_actor(value):
    """The OKF actor for a v3 `by` value; None when it already is one or can't be mapped."""
    s = str(value).strip()
    if not s or ACTOR_RE.match(s):
        return None
    if AGENT_RE.search(s):
        return "okf-docs/3"
    if re.fullmatch(r"[A-Za-z0-9._' -]+", s):
        return "human:" + slug(s)
    return None


def _upgrade_ts(container, key, label, changes):
    """A timestamp without an offset gets one. A date becomes a date-time only where consumers compare it
    (is_compared_ts: generated.at, verified.at); elsewhere a date is valid OKF and stays."""
    if not isinstance(container, dict) or container.get(key) in (None, ""):
        return
    when, problem = parse_ts(container[key])
    if problem == DATE_ONLY and when and is_compared_ts(label):
        container[key] = when.strftime("%Y-%m-%dT00:00:00Z")
        changes.append("%s: date → %s" % (label, container[key]))
    elif problem == NO_OFFSET and when:
        container[key] = when.isoformat()
        changes.append("%s: added local offset → %s" % (label, container[key]))


def _rename_ext_keys(fm, changes):
    """x-okfdocs-<name> for the 0.9 names, in the same position with the same value."""
    out = {}
    for key, value in fm.items():
        if key in EXT_NAMES:
            new = ext_key(key)
            if new in fm:
                changes.append("removed `%s` (`%s` is set and wins)" % (key, new))
            else:
                out[new] = value
                changes.append("renamed `%s` → `%s`" % (key, new))
        else:
            out[key] = value
    return out


def _fix_fallback(doc, value, ctx):
    """A bare path that resolves only from the bundle root, as a rooted or file-relative path; None otherwise."""
    if not isinstance(value, str):
        return None
    path, kind = doc.resolve_field(value)
    if kind != "fallback":
        return None
    new = "/" + relpath(path, doc.bundle.root) if ctx.link_style == "rooted" else rel_from(doc.path, path)
    return new.replace(" ", "%20")


def trust_drop(doc):
    """(old tier, new tier, why) when the 0.3 rule (only events at or after generated.at count) lowers the
    trust tier the 0.2 rule gave; None otherwise."""
    old, new = doc.legacy_trust(), doc.trust()
    order = {"human-reviewed": 2, "machine-confirmed": 1, "unverified": 0}
    if old in ("human-reviewed", "machine-confirmed") and order.get(new, 0) < order[old]:
        current = {id(e) for e in doc.current_events()}  # the events that stopped counting
        gone = [e for e in doc.valid_events() if id(e) not in current
                and (old != "human-reviewed" or str(e.get("by", "")).startswith("human:"))]
        times = [t for t in (parse_ts(e.get("at"))[0] for e in gone) if t]
        return old, new, "verified %s is older than generated.at %s" % (fmt_date(max(times) if times else None),
                                                                          fmt_date(doc.generated_at()))
    return None


def upgrade_doc(doc, ctx):
    """Return (new text, list of changes, list of problems). new text is None when nothing changes."""
    return _upgrade_doc(doc, ctx)[:3]


def _upgrade_doc(doc, ctx):
    """upgrade_doc, plus a fourth item: the (label, value) path fields that still resolve only from the
    bundle root after the rewrite."""
    if doc.fm is None:
        return None, [], [], []
    fm = json.loads(json.dumps(doc.fm, default=str))
    changes, problems = [], []
    fixed = set()  # (label, old value) of the path-root-fallback fields rewritten
    body = doc.body
    if any(name in fm for name in EXT_NAMES):
        fm = _rename_ext_keys(fm, changes)
    gen = fm.get("generated")
    if isinstance(gen, dict):
        _upgrade_ts(gen, "at", "generated.at", changes)
        if gen.get("by") not in (None, ""):
            new = _upgrade_actor(gen["by"])
            if new:
                changes.append("generated.by: %s → %s" % (gen["by"], new))
                gen["by"] = new
            elif not ACTOR_RE.match(str(gen["by"])):
                problems.append("generated.by %r: set an actor by hand" % gen["by"])
    if "timestamp" in fm and "generated" not in fm:
        problems.append("`timestamp` is OKF v0.1: replace it by hand with a `generated` mapping with `by` and `at`")
    ver = fm.get("verified")
    if isinstance(ver, dict):
        ver = fm["verified"] = [ver]
        changes.append("verified: mapping → list")
    for i, e in enumerate(ver if isinstance(ver, list) else []):
        if not isinstance(e, dict):
            continue
        _upgrade_ts(e, "at", "verified[%d].at" % i, changes)
        if e.get("by") not in (None, ""):
            new = _upgrade_actor(e["by"])
            if new:
                changes.append("verified.by: %s → %s" % (e["by"], new))
                e["by"] = new
    _upgrade_ts(fm, "stale_after", "stale_after", changes)
    src = fm.get("sources")
    if isinstance(src, str):
        src = [src]
        fm["sources"] = src
    if isinstance(src, dict):
        src = fm["sources"] = [src]
    if isinstance(src, list):
        new_src = []
        for e in src:
            entry = {"resource": e} if isinstance(e, str) else e
            old = str(entry.get("resource")) if isinstance(entry, dict) and entry.get("resource") else None
            rooted_fix = False
            if old and not is_url(old):
                path, kind = doc.resolve_field(old)
                if kind == "fallback":  # also a name like LICENSE, which reads as a descriptor
                    new = _fix_fallback(doc, old, ctx)
                    if new:
                        entry = dict(entry, resource=new)
                        changes.append("sources.resource %s → %s (path-root-fallback)" % (old, new))
                        fixed.add(("sources", old))
                        rooted_fix = True
                elif is_descriptor(old):
                    pass
                elif path is None or kind == "missing":
                    alt = alt_source_path(doc, old)
                    if alt is not None:
                        entry = dict(entry, resource=rel_from(doc.path, alt))
                    else:
                        problems.append("source %r not found" % old)
            if isinstance(e, str) or (old and entry.get("resource") != old and not rooted_fix):
                changes.append("source %s → resource: %s" % (old, entry.get("resource")))
            if isinstance(entry, dict):
                _upgrade_ts(entry, "last_modified", "sources.last_modified", changes)
            new_src.append(entry)
        fm["sources"] = new_src
    human = any(isinstance(e, dict) and str(e.get("by", "")).startswith("human:")
                for e in (fm.get("verified") if isinstance(fm.get("verified"), list) else []))
    for ck in CREDIBILITY_KEYS:
        if ck not in fm:
            continue
        cred = str(fm.get(ck) or "").strip().lower()
        if cred == "verified" and not human:
            problems.append("credibility: verified, but no human `verified` entry says who confirmed it: "
                            "ask, then add the entry, or remove the key")
            continue
        fm.pop(ck)
        if cred == "verified":
            changes.append("removed credibility: verified (the human `verified` entry records it)")
        else:
            changes.append("removed `%s: %s` (retired: `sources` records where content came from)" % (ck, cred))
            if cred == "reported" and not any(isinstance(e, dict) and str(e.get("author", "")).startswith("human:")
                                              for e in as_list(fm.get("sources"))):
                changes.append("it said a person stated this: if you know who, add a `sources` entry with "
                               "`author: \"human:<id>\"`")
    links = fm.pop("links", None)
    if links is not None:
        related = []
        for target in (links if isinstance(links, list) else [links]):
            t = str(target)
            if is_url(t):
                related.append((t, t))
                continue
            path = doc.resolve(t)
            if path is None or not path.exists():
                path = alt_source_path(doc, t) or path
            other = ctx.docs_by_path.get(norm(path)) if path is not None else None
            title = other.title if other is not None else humanize(Path(t).stem)
            url = rel_from(doc.path, path) if path is not None and path.exists() else t
            related.append((title, url))
        body = append_related(body, related)
        changes.append("moved %d frontmatter links to a Related list" % len(related))
    tags = fm.get("tags")
    if isinstance(tags, str) and tags.strip():
        if "," in tags:
            fm["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
            changes.append("tags: split %r at the commas into %d tags (a scalar is one tag; check the result)"
                           % (tags, len(fm["tags"])))
        else:
            fm["tags"] = [tags.strip()]
            changes.append("tags: scalar → list")
    for key in ("supersedes", "superseded_by"):
        full = ext_key(key) if key == "supersedes" else key
        if full in fm and fm[full] in (None, ""):
            fm.pop(full)
            changes.append("removed empty %s" % full)
    sk = ext_key("supersedes")
    for container, key, label in ([(fm, k, k) for k in ("resource", "computation", "superseded_by", sk)]
                                  + [(fm.get(k), "resource", k + ".resource") for k in ("executor", "attester")]):
        if not isinstance(container, dict) or key not in container:
            continue
        # a path field, or a list of them; the label is the one Doc.path_fields reports
        field = "supersedes" if key == sk else label
        value = container[key]
        items = value if isinstance(value, list) else [value]
        new_items = []
        for item in items:
            new = _fix_fallback(doc, item, ctx)
            if new:
                fixed.add((field, item))
                changes.append("%s: %s → %s (path-root-fallback)" % (label, item, new))
            new_items.append(new or item)
        if new_items != items:
            container[key] = new_items if isinstance(value, list) else new_items[0]
    left = [(label, v) for label, v in doc.path_fields()
            if (label if not label.startswith("sources[") else "sources", v) not in fixed
            and doc.resolve_field(v)[1] == "fallback"]
    for label, v in left:
        problems.append("%s %r still resolves only from the bundle root: write it by hand as /%s"
                        % (label, v, v.lstrip("/")))
    if not changes:
        return None, [], problems, left
    text = "---\n" + "\n".join(yaml_dump(fm)) + "\n---\n" + body
    return text, changes, problems, left


def append_related(body, links):
    present = {m.group(1) for m in _LINK_RE.finditer(body)}
    new = [(title, url) for title, url in links if url not in present]
    if not new:
        return body
    lines = body.rstrip("\n").split("\n")
    bullets = ["- [%s](%s)" % (title, url) for title, url in new]
    idx = None
    for i, line in enumerate(lines):
        if re.match(r"^#{2,3}\s+related\s*$", line.strip(), re.I):
            idx = i
    if idx is None:
        lines += ["", "## Related", ""] + bullets
    else:
        j = idx + 1
        while j < len(lines) and not lines[j].startswith("#"):
            j += 1
        while j > idx + 1 and not lines[j - 1].strip():
            j -= 1
        lines[j:j] = bullets
    return "\n".join(lines) + "\n"


def is_v3(doc):
    """The format of the old standalone skills (v3)."""
    if doc.fm is None:
        return False
    if "links" in doc.fm:
        return True
    if str(doc.ext("credibility") or "").strip().lower() == "verified":
        return True
    if any(isinstance(e, str) for e in as_list(doc.get("sources"))):
        return True
    for _, value in iter_timestamps(doc.fm):
        if parse_ts(value)[1] == NO_OFFSET:
            return True
    gen = doc.get("generated")
    if isinstance(gen, dict) and gen.get("by") not in (None, "") and _upgrade_actor(gen["by"]):
        return True
    return any(e.get("by") not in (None, "") and _upgrade_actor(e["by"]) for e in doc.verified_entries())


def is_older(doc):
    """The OKF 0.2 format that plugin versions before 1.0 wrote: 0.9 key names, date-only generated and
    verified times, a scalar `tags`, or bare paths that resolve only from the bundle root. Also the
    credibility label that versions before 1.0.4 wrote."""
    if doc.fm is None or doc.nonconcept:
        return False
    if any(name in doc.fm for name in EXT_NAMES + CREDIBILITY_KEYS):
        return True
    for key, value in iter_timestamps(doc.fm):
        if parse_ts(value)[1] == DATE_ONLY and is_compared_ts(key):
            return True
    if isinstance(doc.get("tags"), str):
        return True
    return any(doc.resolve_field(v)[1] == "fallback" for _, v in doc.path_fields()) if doc.bundle.root_fallback else False


# --------------------------------------------------------------------------
# Actors and the context report
# --------------------------------------------------------------------------

ACTOR_UNSET = ("not set (ask the person for their id; they can save it with "
               "git config --global okf.actor <id>)")


def suggested_actor(project):
    """A suggestion for the person's id when none is set: their git user.name as a slug, or None. Only a
    suggestion: the agent asks the person to confirm it before writing or saving it (lifecycle.md)."""
    name = git_config("user.name", project.root)
    s = slug(name) if name else "unknown"
    return None if s == "unknown" else "human:" + s


def actor_unset(sug):
    """The text for a missing human id, with the suggestion from suggested_actor() when there is one."""
    if not sug:
        return ACTOR_UNSET
    return ("not set; suggestion %s (from git user.name): confirm it with the person, then save it with "
            "git config --global okf.actor %s" % (sug, sug[len("human:"):]))


def human_actor(project):
    """(human:<id>, source) from OKF_ACTOR or `git config okf.actor`; (None, "not set") when neither is set.
    Never taken from the machine without the person's say: git user.name is only a suggestion (actor_unset)."""
    cwd = project.root
    env = (os.environ.get("OKF_ACTOR") or "").strip()
    v, source = (env, "OKF_ACTOR") if env else ((git_config("okf.actor", cwd) or "").strip(), "git okf.actor")
    if v:
        return (v if v.startswith("human:") else "human:" + slug(v)), source
    return None, "not set"


LEGACY_RULE_RE = re.compile(r"no `?status`? field|credibility:\s*`?verified|verified\s*\|\s*reported", re.I)


def legacy_project_rules(project):
    """Project copies of the v3 skills, and instruction files that restate the v3 format."""
    skills, rules, seen = [], [], set()
    for root in dict.fromkeys(p for p in (project.root, project.git_root) if p):
        sk = root / ".claude" / "skills"
        for name in ("okf-docs", "okf-company-brain"):
            for p in (sk / (name + ".md"), sk / name / "SKILL.md"):
                if p.is_file() and norm(p) not in seen:
                    seen.add(norm(p))
                    skills.append(p)
        for name in ("CLAUDE.md", "AGENTS.md", ".claude/CLAUDE.md"):
            p = root / name
            try:
                text = p.read_text(encoding="utf-8") if p.is_file() else ""
            except (OSError, UnicodeDecodeError):
                text = ""
            if text and LEGACY_RULE_RE.search(text) and norm(p) not in seen:
                seen.add(norm(p))
                rules.append(p)
    return skills, rules


def legacy_skills():
    found = []
    base = Path.home() / ".claude" / "skills"
    if not base.is_dir():
        return found
    for dirpath, dirnames, filenames in os.walk(base):
        d = Path(dirpath)
        if len(d.relative_to(base).parts) > 3:
            dirnames[:] = []
            continue
        if d.name in ("okf-docs", "okf-company-brain") and "SKILL.md" in filenames:
            found.append(d)
            dirnames[:] = []
    return found


def bundle_stats(bundle, ctx):
    findings = []
    for doc in bundle.docs:
        findings.extend(check_doc(doc, ctx))
    findings.extend(check_bundle(bundle, ctx))
    count = lambda level, sev=None: sum(1 for f in findings if f.level == level and (sev is None or f.severity == sev)
                                        and f.code not in AGGREGATED)
    return {
        "files": len(bundle.indexable),
        "drafts": sum(1 for f in findings if f.code == "draft"),
        "unverified": sum(1 for f in findings if f.code == "unverified"),
        "outdated": sum(1 for f in findings if f.code == "verification-outdated"),
        "okf_errors": count("okf", "error"),
        "okf_warnings": count("okf", "warn"),
        "house": count("house"),
        "content": count("content"),
        "v3": sum(1 for d in bundle.docs if is_v3(d)),
        "older": sum(1 for d in bundle.docs if not is_v3(d) and is_older(d)),
        "last_log": last_log_date(bundle.root / "log.md"),
    }


def context_report(project, ctx):
    rep = {"version": VERSION, "python": sys.version.split()[0], "project": str(project.root),
           "config": relpath(project.config_path, project.root) if project.config_path else None,
           "config_error": project.config_error, "modules": project.modules, "bundles": [], "related": [],
           "now": ctx.now.isoformat(), "directives": []}
    actor, actor_from = human_actor(project)
    rep["actor"] = {"human": actor, "from": actor_from, "agent": AGENT_ACTOR,
                    "suggested": None if actor else suggested_actor(project)}
    rep["config_issues"] = list(project.config_issues)
    rep["brain"] = ({"actions": project.brain_actions, "names": project.brain_names,
                     "tickets": project.brain_tickets}
                    if "brain" in project.modules else None)
    total = {"okf_errors": 0, "v3": 0, "older": 0, "review": 0}
    for b in project.bundles:
        st = bundle_stats(b, ctx) if b.exists else {"files": 0}
        trackers = tracker_counts(b, ctx) if b.exists and b.kind == "brain" else {}
        rep["bundles"].append(dict({"path": b.rel, "kind": b.kind, "preset": b.preset, "exists": b.exists,
                                    "trackers": trackers}, **st))
        total["okf_errors"] += st.get("okf_errors", 0)
        total["v3"] += st.get("v3", 0)
        total["older"] += st.get("older", 0)
        total["review"] += st.get("drafts", 0) + st.get("unverified", 0) + st.get("outdated", 0)
    for name, entry in project.related_entries():
        local = entry.get("path")
        found = bool(local) and (project.root / str(local)).is_dir()
        rep["related"].append({"name": name, "url": entry.get("url"), "path": local, "found": found})
    queue = stale_queue(project, ctx) if project.bundles else []
    rep["stale"] = sum(1 for q in queue if q["hard"])
    rep["decayed"] = sum(1 for q in queue if not q["hard"])
    git = None
    if project.git_root:
        branch = (run_git(["rev-parse", "--abbrev-ref", "HEAD"], project.git_root) or "").strip()
        status = run_git(["status", "--porcelain"], project.git_root) or ""
        git = {"branch": branch, "uncommitted": len([l for l in status.split("\n") if l.strip()])}
        ref = last_sync_ref(project)
        if ref:
            n = run_git(["rev-list", "--count", ref + "..HEAD"], project.git_root)
            git["last_sync"] = ref
            git["commits_since_sync"] = int(n.strip()) if n and n.strip().isdigit() else None
    elif dot_git(project.root):
        git = {"unavailable": True}
    rep["git"] = git
    rep["hooks"] = {k: hook_on(project.config, k) for k in ("session", "edits", "capture")}
    d = rep["directives"]
    if not project.config_path:
        found = ", ".join(b.rel for b in project.bundles) or "none"
        d.append("NO_CONFIG: no .okf/config.yaml. On a bare call suggest /okf-docs init; don't create bundles "
                 "before init. OKF bundles found: %s." % found)
    for issue in project.config_issues:
        d.append("CONFIG_VALUE: .okf/config.yaml: %s." % issue)
    if project.config_error:
        d.append("CONFIG_ERROR: .okf/config.yaml can't be read (%s). Fix it before anything else."
                 % project.config_error)
    legacy = legacy_skills()
    if legacy:
        names = []
        for p in legacy:
            if "synced" in p.parts:
                names.append("%s (synced from claude.ai: turn it off in claude.ai's skill settings; deleting the "
                             "folder doesn't stick)" % p.name)
            else:
                names.append("%s (local copy: delete %s)" % (p.name, home_path(p)))
        d.append("LEGACY_SKILLS: standalone skills this plugin replaces: %s. Suggest removing them."
                 % "; ".join(names))
    skills, rules = legacy_project_rules(project)
    if skills or rules:
        parts = []
        if skills:
            parts.append("copies of the v3 skills in this project (%s)"
                         % ", ".join(relpath(p, project.root) for p in skills))
        if rules:
            parts.append("instructions that restate the v3 format, such as no `status` field or "
                         "`credibility: verified` (%s)" % ", ".join(relpath(p, project.root) for p in rules))
        d.append("LEGACY_RULES: %s. They conflict with this plugin's format. Propose retiring the copies and "
                 "updating those lines with the upgrade; change nothing before the user approves." % "; ".join(parts))
    if git and git.get("unavailable"):
        d.append("GIT_UNAVAILABLE: this is a git repository, but git didn't run here (a sandbox can block it). "
                 "Staleness falls back to file times and sync can't read history. Deletions can still be "
                 "undone with git, so don't treat the project as having no version control. Mention this "
                 "only when the request depends on git: sync, history questions or deletions.")
    if (project.root / ".agent" / "okf").is_dir():
        d.append("LEGACY_STATE: .agent/okf/ from the v3 skills. init reads it as evidence and offers to remove it.")
    if total["v3"] or total["older"]:
        d.append("UPGRADE: %d files use an older format (%d v3, %d from okf-docs before 1.0.4); check runs "
                 "`okf.py upgrade --dry-run`." % (total["v3"] + total["older"], total["v3"], total["older"]))
    if total["okf_errors"]:
        d.append("ERRORS: %d OKF errors; suggest /okf-docs check." % total["okf_errors"])
    if "code" in project.modules and git:
        if git.get("commits_since_sync"):
            d.append("SYNC: %d commits since the last sync (%s); suggest /okf-docs sync."
                     % (git["commits_since_sync"], git["last_sync"][:7]))
        elif any("source changed" in r for q in queue for r in q["reasons"]):
            d.append("SYNC: docs cite code that changed after they were written; suggest /okf-docs sync.")
    tickets = project.brain_tickets if "brain" in project.modules else None
    if tickets:
        remotes = (github_remotes(project.git_root) if tickets["system"] in GITHUB_SYSTEMS and project.git_root
                   else [])
        if rep["brain"]:
            rep["brain"]["gh_cli"] = remotes[0] if remotes else None
        if tickets["target"]:
            where = "target " + tickets["target"]
        elif remotes:
            where = "no target set: suggest %s, this repository's GitHub remote, and ask" % remotes[0]
        else:
            where = "no target set: ask which team, project or repository the first time"
        line = ("TICKETS: meeting actions sync to %s (%s). Before creating any ticket, look for it in the brain "
                "and in %s, and get the user's OK; follow write.md, Tickets." % (tickets["system"], where,
                                                                                tickets["system"]))
        if tickets["system"] in GITHUB_SYSTEMS:
            line += (" Use the GitHub connector; without one, the gh CLI is allowed here (git repository with GitHub "
                     "remote %s), for gh issue list, view, create and comment only." % remotes[0] if remotes else
                     " Use the GitHub connector only: this project has no GitHub remote, so the gh CLI isn't allowed.")
        d.append(line)
    for b in rep["bundles"]:
        t = b.get("trackers") or {}
        if t.get("unsynced"):
            d.append("TICKETS_PENDING: %d open %s in %sactions.md %s no ticket yet; offer to sync %s."
                     % (t["unsynced"], "action" if t["unsynced"] == 1 else "actions", b["path"],
                        "has" if t["unsynced"] == 1 else "have", "it" if t["unsynced"] == 1 else "them"))
        if t.get("overdue"):
            d.append("ACTIONS: %d overdue %s in %sactions.md; mention them in the status."
                     % (t["overdue"], "action" if t["overdue"] == 1 else "actions", b["path"]))
        if t.get("questions_open"):
            d.append("QUESTIONS: %d open %s in %squestions.md; offer to go through them when the user "
                     "works on the brain." % (t["questions_open"], "question" if t["questions_open"] == 1 else "questions",
                                              b["path"]))
    for b in project.bundles:
        if b.kind == "brain" and b.exists:
            n, last = assets_since_review(b)
            if n >= 3:
                d.append("BRAIN_REVIEW: %d assets added since the last brain review (%s); offer /okf-docs check brain."
                         % (n, last or "never"))
    if total["review"] or rep["stale"] or rep["decayed"]:
        d.append("REVIEW: %d drafts, unverified or verified before the last change, %d stale, %d past half-life." % (
            total["review"], rep["stale"], rep["decayed"]))
    off = [m for m in MODULES if m not in project.modules]
    if project.config_path and off:
        d.append("MODULES_OFF: %s. Hide their commands; offer init if the user asks for one." % ", ".join(off))
    return rep


def print_context(rep):
    print("okf-docs %s · python %s" % (rep["version"], rep["python"]))
    print("PROJECT %s" % rep["project"])
    if rep["config"]:
        print("CONFIG %s · modules: %s" % (rep["config"], ", ".join(rep["modules"])))
        if rep["brain"]:
            t = rep["brain"].get("tickets")
            print("BRAIN actions=%s names=%s tickets=%s" % (
                rep["brain"]["actions"], rep["brain"]["names"],
                ("%s:%s" % (t["system"], t["target"] or "-")) if t else "none"))
    else:
        print("NO_CONFIG")
    for b in rep["bundles"]:
        if not b["exists"]:
            print("BUNDLE %s kind=%s MISSING" % (b["path"], b["kind"]))
            continue
        print("BUNDLE %s kind=%s%s files=%d drafts=%d unverified=%d okf_errors=%d okf_warnings=%d house=%d "
              "content=%d last_log=%s outdated=%d" % (
                  b["path"], b["kind"], " preset=%s" % b["preset"] if b["preset"] else "", b["files"], b["drafts"],
                  b["unverified"], b["okf_errors"], b["okf_warnings"], b["house"], b["content"],
                  b["last_log"] or "none", b.get("outdated", 0)))
        t = b.get("trackers") or {}
        if t:
            parts = []
            if "actions_open" in t:
                parts += ["actions_open=%d" % t["actions_open"], "overdue=%d" % t["overdue"]]
                if "unsynced" in t:
                    parts.append("unsynced=%d" % t["unsynced"])
            if "questions_open" in t:
                parts.append("questions_open=%d" % t["questions_open"])
            print("TRACKERS %s %s" % (b["path"], " ".join(parts)))
    for r in rep["related"]:
        print("RELATED %s url=%s path=%s%s" % (r["name"], r["url"], r["path"], " (found)" if r["found"] else ""))
    print("STALE %d · PAST_HALF_LIFE %d" % (rep["stale"], rep["decayed"]))
    g = rep["git"]
    if g and g.get("unavailable"):
        print("GIT unavailable (a .git folder exists, but git didn't run)")
    elif g:
        line = "GIT branch=%s uncommitted=%d" % (g["branch"], g["uncommitted"])
        if g.get("last_sync"):
            line += " last_sync=%s commits_since=%s" % (g["last_sync"][:7], g.get("commits_since_sync"))
        print(line)
    else:
        print("GIT none")
    print("HOOKS session=%s edits=%s capture=%s" % tuple("on" if rep["hooks"][k] else "off"
                                                        for k in ("session", "edits", "capture")))
    print("NOW %s" % rep["now"])
    if rep["actor"]["human"]:
        print("ACTOR %s (from %s) · agent %s" % (rep["actor"]["human"], rep["actor"]["from"], rep["actor"]["agent"]))
    else:
        print("ACTOR human %s · agent %s" % (actor_unset(rep["actor"].get("suggested")), rep["actor"]["agent"]))
    if rep["directives"]:
        print("DIRECTIVES")
        for line in rep["directives"]:
            print("- " + line)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def _project(args):
    return Project.find(Path(args.project or os.getcwd()))


def _select(project, paths):
    """Map CLI paths to (whole bundles, {bundle: docs}) inside the project."""
    if not paths:
        return [b for b in project.bundles], {}
    whole, partial, outside = [], {}, []
    for raw in paths:
        p = Path(raw).resolve()
        b = project.bundle_for(p)
        if b is None:
            outside.append(raw)
        elif norm(p) == norm(b.root):
            whole.append(b)
        else:
            docs = [d for d in b.docs if is_within(d.path, p)]
            partial.setdefault(b, []).extend(docs)
    if outside:
        sys.stderr.write("not inside a known bundle: %s\n" % ", ".join(outside))
    return whole, partial


def cmd_check(args):
    project = _project(args)
    ctx = Ctx(project)
    whole, partial = _select(project, args.paths)
    fixed = []
    if args.fix:
        for b in set(whole) | set(partial):
            fixed += fix_bundle(b, ctx)
        if fixed:
            project = _project(args)
            ctx = Ctx(project)
            whole, partial = _select(project, args.paths)
    findings, nfiles = [], 0
    for b in whole:
        for doc in b.docs:
            findings += check_doc(doc, ctx)
        findings += check_bundle(b, ctx)
        nfiles += len(b.docs)
    for b, docs in partial.items():
        dirs = {norm(d.path.parent): d.path.parent for d in docs}
        for doc in docs:
            findings += check_doc(doc, ctx)
        findings += check_bundle(b, ctx, dirs=list(dirs.values()))
        nfiles += len(docs)
    for issue in project.config_issues:
        findings.append(Finding("house", "warn", "config-value", CONFIG_REL.as_posix(), issue))
    findings.sort(key=Finding.sort_key)
    errors = sum(1 for f in findings if f.severity == "error")
    if args.json:
        print(json.dumps({"project": str(project.root), "files": nfiles, "fixed": fixed,
                          "findings": [f.to_dict() for f in findings],
                          "summary": _summary(findings)}, indent=1))
        return 1 if errors else 0
    if not project.bundles:
        print("No OKF bundles found under %s. Run /okf-docs init." % project.root)
        return 0
    print("okf-docs check · %d files" % nfiles)
    for path in fixed:
        print("  fixed  %s" % path)
    shown = [f for f in findings if f.code not in AGGREGATED]
    limit = args.limit
    for f in shown[:limit]:
        loc = f.path + (":%d" % f.line if f.line else "")
        print("  %-7s %-5s %s  %s: %s" % (LEVEL_NAMES[f.level], f.severity, loc, f.code, f.message))
    if len(shown) > limit:
        print("  … %d more (use --json or --limit)" % (len(shown) - limit))
    s = _summary(findings)
    queue = ", ".join("%d %s" % (n, c) for c, n in (("unverified", s["unverified"]),
                                                     ("verified before the last change", s["outdated"]),
                                                     ("draft" if s["draft"] == 1 else "drafts", s["draft"])) if n)
    if queue:
        print("  Review queue: %s (okf.py stale lists what to re-check first)" % queue)
    print("Summary: %d OKF errors, %d OKF warnings, %d house, %d content. %d fixable with --fix%s."
          % (s["okf_errors"], s["okf_warnings"], s["house"], s["content"], s["fixable_fix"],
             ", %d with upgrade" % s["fixable_upgrade"] if s["fixable_upgrade"] else ""))
    return 1 if errors else 0


def _summary(findings):
    real = [f for f in findings if f.code not in AGGREGATED]
    return {
        "okf_errors": sum(1 for f in real if f.level == "okf" and f.severity == "error"),
        "okf_warnings": sum(1 for f in real if f.level == "okf" and f.severity == "warn"),
        "house": sum(1 for f in real if f.level == "house"),
        "content": sum(1 for f in real if f.level == "content"),
        "unverified": sum(1 for f in findings if f.code == "unverified"),
        "outdated": sum(1 for f in findings if f.code == "verification-outdated"),
        "draft": sum(1 for f in findings if f.code == "draft"),
        "fixable_fix": sum(1 for f in real if f.fixable == "fix"),
        "fixable_upgrade": sum(1 for f in real if f.fixable == "upgrade"),
    }


def cmd_index(args):
    project = _project(args)
    ctx = Ctx(project)
    bundles = [project.bundle_for(Path(p).resolve()) for p in args.bundles] if args.bundles else project.bundles
    changed = []
    for b in [b for b in bundles if b is not None]:
        for d in b.dirs_with_docs():
            idx = d / "index.md"
            if index_is_page(idx):
                print("skipped %s: %s" % (relpath(idx, project.root), page_index_hint(idx)))
                continue
            text, _ = build_index(b, d, ctx)
            old = idx.read_text(encoding="utf-8") if idx.exists() else None
            if old is None or old.strip() != text.strip():
                changed.append(relpath(idx, project.root))
                if args.write:
                    write_lf(idx, text)
    verb = "updated" if args.write else "would update"
    for path in changed:
        print("%s %s" % (verb, path))
    if not changed:
        print("indexes are up to date")
    return 1 if changed and not args.write and args.check else 0


def cmd_lint(args):
    results = []
    for raw in args.paths:
        p = Path(raw)
        files = sorted(p.rglob("*.md")) if p.is_dir() else [p]
        for f in files:
            try:
                res = lint_text(f.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError) as exc:
                sys.stderr.write("can't read %s: %s\n" % (f, exc))
                continue
            res["path"] = str(f)
            results.append(res)
    if args.json:
        print(json.dumps(results, indent=1))
        return 0
    for res in results:
        counted = [h for h in res["hits"] if h["category"] != "long-sentence"]
        print("%s  %d words · %d hits (%.1f per 100 words)" % (res["path"], res["words"], len(counted),
                                                              res["per100"]))
        for h in res["hits"][:args.limit]:
            print("  %-5s %-13s %-34s %s" % (h["line"] or "", h["category"], '"%s"' % h["text"][:32], h["advice"]))
        if len(res["hits"]) > args.limit:
            print("  … %d more" % (len(res["hits"]) - args.limit))
    return 0


def cmd_stale(args):
    project = _project(args)
    ctx = Ctx(project)
    queue = stale_queue(project, ctx)
    ref = args.since or (last_sync_ref(project) if args.since is None else None)
    since = changes_since(project, ctx, ref) if ref else None
    if args.json:
        print(json.dumps({"queue": queue, "since": since}, indent=1))
        return 0
    if not queue:
        print("Re-check queue is empty.")
    else:
        print("Re-check queue (%d)" % len(queue))
        for q in queue[:args.limit]:
            tag = " → delete candidate" if q["delete_candidate"] else ""
            print("  %s  [%s, %s]%s" % (q["path"], ", ".join(x for x in (q["trust"], q["trust_note"]) if x),
                                      q["status"], tag))
            for r in q["reasons"]:
                print("      %s" % r)
        if len(queue) > args.limit:
            print("  … %d more (use --json)" % (len(queue) - args.limit))
    if since:
        if since.get("error"):
            print(since["error"])
        else:
            print("Since %s: %d files changed%s" % (since["ref"][:12], since["changed"],
                                                   ", %d commits" % since["commits"] if since["commits"] else ""))
            for a in since["affected"]:
                print("  affected  %s  (%s)" % (a["path"], ", ".join(a["sources"])))
            for u in since["uncovered"][:args.limit]:
                print("  uncovered %s" % u)
    elif args.since is None and project.git_root:
        print("No **Sync** entry in a docs log.md yet; pass --since <ref> to compare with a commit.")
    return 0


def cmd_find(args):
    project = _project(args)
    ctx = Ctx(project)
    results = rank(project, ctx, " ".join(args.words), include_all=args.all)[:args.limit]
    if args.json:
        print(json.dumps(results, indent=1))
        return 0
    if not results:
        print("No matches.")
    for r in results:
        meta = ", ".join(x for x in [r["type"], r["trust"], r["trust_note"],
                                     ("checked " + r["last_check"]) if r["last_check"] else "",
                                     r["specificity"] or ""] + r["flags"] if x)
        print("%6.1f  %s  [%s]\n        %s%s" % (r["score"], r["path"], meta, r["title"],
                                                (" — " + r["description"]) if r["description"] else ""))
    return 0


def cmd_log(args):
    project = _project(args)
    root = Path(args.bundle).resolve()
    if not root.is_dir():
        sys.stderr.write("not a folder: %s\n" % args.bundle)
        return 1
    path = add_log_entry(root, args.kind, " ".join(args.message))
    print("logged in %s" % relpath(path, project.root))
    return 0


def _cli_path(project, raw):
    """A path argument: as given (from the current folder), else from the project root."""
    p = Path(raw)
    if not p.is_absolute() and not p.exists():
        p = project.root / raw
    return p.resolve()


def cmd_history(args):
    """Add a `## History` line to an entity file for an asset (write.md, Meetings). It changes only that
    section, so generated.at and the verifications stay as they are (OKF 0.3 section 5.2)."""
    project = _project(args)
    ctx = Ctx(project)
    entity, asset = _cli_path(project, args.entity), _cli_path(project, args.asset)
    for path in (entity, asset):
        if not path.is_file():
            sys.stderr.write("no such file: %s\n" % path)
            return 1
    b = project.bundle_for(entity)
    if b is None:
        sys.stderr.write("%s isn't in a bundle\n" % relpath(entity, project.root))
        return 1
    ab = project.bundle_for(asset) or b
    doc, adoc = Doc.load(b, entity), Doc.load(ab, asset)
    if doc.error or doc.fm is None:
        sys.stderr.write("%s has no readable frontmatter\n" % doc.prel)
        return 1
    # The meeting's date: the asset's file name carries it; generated.at is when the asset was filed.
    day = args.date or (asset.name[:10] if DATED_RE.match(asset.name) and _iso_day(asset.name[:10]) else None) \
        or asset_date(adoc)
    if not day or not _iso_day(day):
        sys.stderr.write("no date for %s: pass --date YYYY-MM-DD\n" % adoc.prel)
        return 1
    if ctx.link_style == "rooted" and ab is b:
        target = "/" + relpath(asset, b.root)
    else:
        target = rel_from(entity, asset)
    target = target.replace(" ", "%20")
    lines = doc.body.split("\n")
    span = history_span(lines)
    if span:
        for i in range(span[0] + 1, span[1]):
            for m in _LINK_RE.finditer(lines[i]):
                linked = doc.resolve(m.group(1))
                if linked is not None and norm(linked) == norm(asset):
                    print("already listed in %s: %s" % (doc.prel, lines[i].strip()))
                    return 0
    line = "- %s [%s](%s)" % (day, (adoc.title or humanize(asset.stem)).replace("]", ")"), target)
    if args.note:
        line += ": " + " ".join(args.note.split())
    body = add_history_line(doc.body, line, day)
    fm_text, _, _, _ = split_frontmatter(doc.text)
    text = "---\n%s\n---\n%s" % (fm_text, body)
    if not text.endswith("\n"):
        text += "\n"
    if not args.dry_run:
        write_lf(entity, text)
    print("%s %s: %s" % ("would add to" if args.dry_run else "added to", doc.prel, line))
    return 0


def cmd_now(args):
    project = _project(args)
    actor, source = human_actor(project)
    print("at: %s" % now().isoformat())
    if actor:
        print("human: %s   (from %s)" % (actor, source))
    else:
        print("human: " + actor_unset(suggested_actor(project)))
    print("agent: %s" % AGENT_ACTOR)
    return 0


def cmd_context(args):
    project = _project(args)
    rep = context_report(project, Ctx(project))
    if args.json:
        print(json.dumps(rep, indent=1))
    else:
        print_context(rep)
    return 0


def cmd_upgrade(args):
    project = _project(args)
    ctx = Ctx(project)
    whole, partial = _select(project, args.paths)
    selected = [b for b in project.bundles if b in whole or b in partial]
    older = {id(b): b.is_older for b in selected}  # before anything is written
    docs = [d for b in whole for d in b.docs] + [d for ds in partial.values() for d in ds]
    planned = 0
    held = {}  # bundle -> path fields the rewrite left; the bundle keeps its version
    for doc in docs:
        text, changes, problems, left = _upgrade_doc(doc, ctx)
        if left:
            held[doc.bundle] = held.get(doc.bundle, 0) + len(left)
        if text is None and not problems:
            continue
        print(doc.prel)
        for c in changes:
            print("  · " + c)
        for p in problems:
            print("  ! " + p)
        if text is not None:
            planned += 1
            if not args.dry_run:
                write_lf(doc.path, text)
    index_fixes, page_idx, log_fixes = [], [], []
    for b in selected:
        page_idx.extend(page_indexes(b))
        for d in b.dirs_with_docs():
            idx = d / "index.md"
            if not idx.exists() or index_is_page(idx):
                continue
            old = idx.read_text(encoding="utf-8")
            fm, _, _, _ = split_frontmatter(old)
            if norm(d) != norm(b.root):
                if fm is None:
                    continue
                notes = ["index frontmatter removed (only the root index.md has frontmatter)"]
                text, _ = build_index(b, d, ctx)
            else:
                if b not in whole:
                    continue  # a single file or folder doesn't move the bundle to 0.3
                text, summary = build_index(b, d, ctx, upgrade=True, bump=b not in held)
                if split_frontmatter(text)[0] == fm:
                    continue
                notes = summary["root_notes"] or ["root index frontmatter normalized"]
            index_fixes.append((idx, notes))
            if not args.dry_run:
                write_lf(idx, text)
        for d in b.plain_index_dirs():
            idx = d / "index.md"
            if not index_is_page(idx) and strip_index_frontmatter(idx, write=not args.dry_run):
                index_fixes.append((idx, ["index frontmatter removed (only the root index.md has frontmatter)"]))
        if b in whole:
            for d, _, files in b.walk():
                if "log.md" in files and strip_log_frontmatter(d / "log.md", write=not args.dry_run):
                    log_fixes.append(d / "log.md")
    for idx, notes in index_fixes:
        print(relpath(idx, project.root))
        for n in notes:
            print("  · " + n)
    for log in log_fixes:
        print("%s\n  · removed the frontmatter (log.md has none in OKF 0.3)" % relpath(log, project.root))
    for b, count in held.items():
        print("%sindex.md\n  ! okf_version stays %s: %d path %s still resolve only from the bundle root; fix %s by "
              "hand, then run upgrade again" % (b.rel, b.okf_version or "undeclared", count,
                                                "field" if count == 1 else "fields", "it" if count == 1 else "them"))
    for idx in sorted(set(page_idx), key=str):
        print("%s\n  ! %s" % (relpath(idx, project.root), page_index_hint(idx)))
    drops = [(d, drop) for b in selected if older[id(b)]
             for d in (b.docs if b in whole else partial.get(b, [])) for drop in [trust_drop(d)] if drop]
    if drops:
        print("Trust drops under OKF 0.3 (only verified events at or after generated.at count):")
        for d, (was, now_, why) in drops:
            print("  %s: %s → %s (%s)" % (d.prel, was, now_, why))
    verb = "would change" if args.dry_run else "changed"
    print("%s %d files%s" % (verb, planned + len(index_fixes) + len(log_fixes),
                             "; run without --dry-run to apply" if args.dry_run and planned else ""))
    if not args.dry_run and planned:
        print("Comments in rewritten frontmatter are not kept. Run okf.py check next.")
    return 0


def citing_docs(project, path):
    """Docs whose `sources` name path. Parses only files that mention its file name."""
    out = []
    for b in project.bundles:
        if not b.exists:
            continue
        for d, _, files in b.walk():
            for name in files:
                if not name.endswith(".md") or name in RESERVED or name.startswith("."):
                    continue
                try:
                    text = (d / name).read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                if path.name not in text:
                    continue
                doc = Doc.load(b, d / name)
                if doc.fm is not None and any(norm(p) == norm(path) for _, p in doc.local_sources()):
                    out.append(doc.prel)
    return out


def cmd_hook(args):
    try:
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    ti = data.get("tool_input") if isinstance(data, dict) else None
    fp = (ti.get("file_path") or ti.get("path") or "") if isinstance(ti, dict) else ""
    if not fp or not isinstance(fp, str):
        return 0
    path = Path(fp)
    if not path.is_absolute():
        path = Path(data.get("cwd") or os.getcwd()) / path
    path = path.resolve()
    config, _ = Project.locate(path)
    if config is None:
        return 0
    project = Project.load(config.parent.parent, config)
    hooks = project.config.get("hooks") or {}
    if not hook_on(project.config, "edits"):
        return 0
    try:
        limit = max(1, int(hooks.get("max_findings", 5)))
    except (TypeError, ValueError):
        limit = 5
    messages = []
    bundle = project.bundle_for(path)
    if bundle is not None:
        if (path.suffix != ".md" or path.name in RESERVED or not path.is_file()
                or any(part.startswith(".") for part in Path(relpath(path, bundle.root)).parts)):
            return 0
        ctx = Ctx(project)
        doc = next((d for d in bundle.docs if norm(d.path) == norm(path)), None) or Doc.load(bundle, path)
        findings = [f for f in check_doc(doc, ctx) if f.severity != "info"]
        findings += [f for f in check_bundle(bundle, ctx, dirs=[path.parent]) if f.severity != "info"]
        lint = lint_text(doc.text) if doc.text else {"hits": []}
        notes = ["%s: %s" % (f.code, f.message) for f in sorted(findings, key=Finding.sort_key)]
        notes += ["bloat, line %s: \"%s\" (%s)" % (h["line"], h["text"], h["advice"])
                  for h in lint["hits"] if h["category"] != "long-sentence"]
        if notes:
            more = len(notes) - limit
            messages.append("okf-docs: %s has %d %s:\n- %s%s" % (
                relpath(path, project.root), len(notes), "issue" if len(notes) == 1 else "issues",
                "\n- ".join(notes[:limit]),
                "\n- … %d more (okf.py check)" % more if more > 0 else ""))
    else:
        citing = citing_docs(project, path)
        if citing and _hook_first_time(args.state, data.get("session_id"), path):
            messages.append("okf-docs: %s is cited by %s. If this changes what %s, update %s once, at the end "
                            "of the task." % (relpath(path, project.root), ", ".join(citing[:limit]),
                                         "it says" if len(citing) == 1 else "they say",
                                         "it" if len(citing) == 1 else "them"))
    if messages:
        text = "\n".join(messages)[:4000]
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}))
    return 0


def cmd_session_start(args):
    """SessionStart hook: in a project with OKF docs, tells the agent in a few lines that they exist and when
    to use the skill. Reads only the config, so it stays fast and prints nothing anywhere else."""
    try:
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        data = {}
    cwd = data.get("cwd") if isinstance(data, dict) else None
    config, _ = Project.locate(Path(cwd or os.getcwd()))
    if config is None:
        return 0
    project = Project.load(config.parent.parent, config)
    if not hook_on(project.config, "session"):
        return 0
    where = []
    for b in project.config.get("bundles") or []:
        if isinstance(b, dict) and b.get("path"):
            where.append("%s/ (%s)" % (str(b["path"]).strip("/"), b.get("kind") or "other"))
    related = project.config.get("related") or {}
    if isinstance(related, dict):
        for name, r in sorted(related.items()):
            if isinstance(r, dict) and (r.get("url") or r.get("path")):
                where.append("%s: %s" % (name, r.get("path") or r.get("url")))
    text = ("okf-docs: this project keeps OKF docs%s. Use the okf-docs skill to answer what was decided, "
            "and why or how something works, from those files with citations. At the end of a task that "
            "changed documented behavior, use it to update the docs once; don't write docs for fixes, "
            "refactors or tests." % (" in " + ", ".join(where[:6]) if where else ""))
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    return 0


STOP_REMINDER = ("okf-docs: before finishing, check this session for knowledge worth keeping: corrections, stated "
                 "conventions, workarounds, decisions, changed behavior. Update docs whose facts changed and propose "
                 "new ones in one line each (write.md, Capture). If there is nothing, finish without mentioning this.")


_HARNESS_TEXT = ("<task-notification", "<local-command", "<command-name", "<command-message", "<command-args",
                 "<bash-input", "<bash-stdout", "<bash-stderr", "<system-reminder", "<user-prompt-submit-hook")


def _human_text(text):
    """Text a person typed: not empty and not a harness message (task notifications, command output)."""
    t = str(text or "").lstrip()
    return bool(t) and not t.startswith(_HARNESS_TEXT)


def _session_did_work(transcript, project, cwd):
    """True when the transcript (JSONL) shows an Edit/Write/MultiEdit outside the bundles, or 4 user messages.
    Lines that don't parse are skipped."""
    users = 0
    with open(str(transcript), encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            msg = entry.get("message") if isinstance(entry, dict) else None
            if (not isinstance(msg, dict) or entry.get("isSidechain") or entry.get("isMeta")
                    or entry.get("isCompactSummary")):
                continue
            content = msg.get("content")
            if entry.get("type") == "user":
                if isinstance(content, str):
                    users += 1 if _human_text(content) else 0
                elif isinstance(content, list) and any(
                        isinstance(c, dict) and c.get("type") == "text" and _human_text(c.get("text"))
                        for c in content):
                    users += 1
            elif entry.get("type") == "assistant" and isinstance(content, list):
                for c in content:
                    ti = c.get("input") if isinstance(c, dict) and c.get("type") == "tool_use" else None
                    if not isinstance(ti, dict) or c.get("name") not in ("Edit", "Write", "MultiEdit"):
                        continue
                    fp = ti.get("file_path") or ti.get("path")
                    if isinstance(fp, str) and fp:
                        path = (Path(fp) if Path(fp).is_absolute() else Path(cwd) / fp).resolve()
                        if is_within(path, project.root.resolve()) and project.bundle_for(path) is None:
                            return True
            if users >= 4:
                return True
    return False


def cmd_stop(args):
    """Stop hook: once per session, asks the agent to check for knowledge worth keeping. Never raises."""
    try:
        return _stop(args)
    except Exception:  # a hook must not break the session
        return 0


def _stop(args):
    try:
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if not isinstance(data, dict) or data.get("stop_hook_active"):
        return 0
    session, transcript = data.get("session_id"), data.get("transcript_path")
    state = args.state or str(Path(tempfile.gettempdir()) / "okf-docs")  # as _hook_first_time does
    if not session or not transcript:
        return 0
    cwd = Path(data.get("cwd") or os.getcwd())
    config, _ = Project.locate(cwd)
    if config is None:
        return 0
    project = Project.load(config.parent.parent, config)
    if not hook_on(project.config, "capture"):
        return 0
    f = Path(state) / "stop-reminded.json"
    try:
        seen = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    except (OSError, ValueError):
        seen = []
    if not isinstance(seen, list) or str(session) in seen:
        return 0
    if not _session_did_work(transcript, project, cwd):
        return 0
    try:
        Path(state).mkdir(parents=True, exist_ok=True)
        write_lf(f, json.dumps((seen + [str(session)])[-300:]))
    except OSError:
        return 0
    print(json.dumps({"decision": "block", "reason": STOP_REMINDER}))
    return 0


def _hook_first_time(state_dir, session, path):
    """True the first time a session edits this cited file; keeps reminders to one per file per session."""
    if not session:
        return True
    base = Path(state_dir) if state_dir else Path(tempfile.gettempdir()) / "okf-docs"
    try:
        base.mkdir(parents=True, exist_ok=True)
        f = base / "hook-seen.json"
        seen = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
        key = "%s|%s" % (session, norm(path))
        if key in seen:
            return False
        seen = (seen + [key])[-300:]
        write_lf(f, json.dumps(seen))
    except (OSError, ValueError):
        return True
    return True


def build_parser():
    p = argparse.ArgumentParser(prog="okf.py", description="okf-docs helper for OKF v0.3 bundles.")
    p.add_argument("--version", action="version", version="okf-docs " + VERSION)
    p.add_argument("--project", help="project folder (default: current folder)")
    sub = p.add_subparsers(dest="command", metavar="<command>")

    s = sub.add_parser("context", help="session summary: config, bundles, findings, NOW, ACTOR, directives")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_context)

    s = sub.add_parser("check", help="check bundles or files against OKF and the house rules")
    s.add_argument("paths", nargs="*", help="bundle folders or files (default: all bundles)")
    s.add_argument("--json", action="store_true")
    s.add_argument("--fix", action="store_true", help="regenerate indexes, add missing log.md, drop log.md frontmatter, set okf_version")
    s.add_argument("--limit", type=int, default=60, help="findings to print (default 60)")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("index", help="regenerate index.md files from titles and descriptions")
    s.add_argument("bundles", nargs="*", help="bundle folders (default: all)")
    s.add_argument("--write", action="store_true", help="write the files (default: list what would change)")
    s.add_argument("--check", action="store_true", help="exit 1 if any index is out of date")
    s.set_defaults(func=cmd_index)

    s = sub.add_parser("lint", help="writing lint: filler, hedges, hype, structure; word counts")
    s.add_argument("paths", nargs="+", help="markdown files or folders")
    s.add_argument("--json", action="store_true")
    s.add_argument("--limit", type=int, default=40)
    s.set_defaults(func=cmd_lint)

    s = sub.add_parser("stale", help="re-check queue; with --since, docs affected by code changes")
    s.add_argument("--since", help="git ref to compare with (default: the last **Sync** log entry)")
    s.add_argument("--json", action="store_true")
    s.add_argument("--limit", type=int, default=40)
    s.set_defaults(func=cmd_stale)

    s = sub.add_parser("find", help="rank files for a question")
    s.add_argument("words", nargs="+")
    s.add_argument("--all", action="store_true", help="don't push deprecated files down")
    s.add_argument("--limit", type=int, default=8)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_find)

    s = sub.add_parser("log", help="add a log.md entry under today's date")
    s.add_argument("bundle", help="bundle folder (or the folder whose log.md to write)")
    s.add_argument("kind", help="Initialization, Creation, Update, Deprecation, Deletion, Decision, Sync, Publication, Review")
    s.add_argument("message", nargs="+")
    s.set_defaults(func=cmd_log)

    s = sub.add_parser("history", help="add a ## History line to an entity file for an asset, leaving generated.at")
    s.add_argument("entity", help="the entity file (customer, product, initiative)")
    s.add_argument("asset", help="the asset file the line links to")
    s.add_argument("--note", help="a few words: what the meeting or asset changed for the entity")
    s.add_argument("--date", help="YYYY-MM-DD; default: the date in the asset's file name, else its generated.at")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_history)

    s = sub.add_parser("now", help="current timestamp and actors to write")
    s.set_defaults(func=cmd_now)

    s = sub.add_parser("upgrade", help="upgrade v3 files (older okf skills) and OKF 0.2 files (okf-docs before 1.0) to the current format")
    s.add_argument("paths", nargs="*")
    s.add_argument("--dry-run", action="store_true", help="list the changes without writing")
    s.set_defaults(func=cmd_upgrade)

    s = sub.add_parser("session-start", help="SessionStart hook: reads the hook JSON on stdin")
    s.set_defaults(func=cmd_session_start)

    s = sub.add_parser("hook", help="PostToolUse hook: reads the hook JSON on stdin")
    s.add_argument("--state", default="", help="folder for hook state (CLAUDE_PLUGIN_DATA)")
    s.set_defaults(func=cmd_hook)

    s = sub.add_parser("stop", help="Stop hook: reads the hook JSON on stdin")
    s.add_argument("--state", default="", help="folder for hook state (CLAUDE_PLUGIN_DATA)")
    s.set_defaults(func=cmd_stop)

    for s in sub.choices.values():  # --project also works after the command name
        s.add_argument("--project", default=argparse.SUPPRESS, help="project folder (default: current folder)")
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:  # Windows consoles and pipes default to a legacy code page that can't print every title
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except BrokenPipeError:  # pragma: no cover - output piped to head
        return 0


if __name__ == "__main__":
    sys.exit(main())
