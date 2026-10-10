"""Aggregate-only guard: nothing published may identify an origin."""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable
from pathlib import Path

FORBIDDEN_COLUMNS = {"url", "page", "root_page", "origin", "host", "hostname", "ip", "ip_addr", "ip_addr_alt"}
# A hostname needs an alphabetic top-level label; "1.13.35.2" has none. Column `network`
# is exempt because AS names legitimately contain domains ("Amazon.com, Inc.").
HOSTNAME_RE = re.compile(r"(?i)\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b")
# Version strings look exactly like IPv4 literals, so the IP check skips column `version`.
IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
# An IPv6 literal: the full eight groups, or any form compressed with "::". Checked in
# every column; neither a version string nor a timestamp matches.
_H = r"[0-9a-f]{1,4}"
IPV6_RE = re.compile(
    rf"(?i)(?<![0-9a-f:.])(?:(?:{_H}:){{7}}{_H}|(?:{_H}:){{1,7}}:(?:{_H}(?::{_H}){{0,5}})?|::{_H}(?::{_H}){{0,6}})(?![0-9a-f:])"
)
HOSTNAME_EXEMPT = {"network"}
IPV4_EXEMPT = {"version"}
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
URL_RE = re.compile(r"https?://")


def _check_row(where: str, row: dict) -> list[str]:
    out: list[str] = []
    for col, val in row.items():
        if val is None:
            continue
        val = str(val)
        if col not in HOSTNAME_EXEMPT and HOSTNAME_RE.search(val):
            out.append(f"{where}: hostname-like value in column {col!r}: {val!r}")
        if col not in IPV4_EXEMPT and IPV4_RE.search(val):
            out.append(f"{where}: IP-like value in column {col!r}: {val!r}")
        if IPV6_RE.search(val):
            out.append(f"{where}: IPv6-like value in column {col!r}: {val!r}")
    return out


def _scan_csv(path: Path) -> list[str]:
    out: list[str] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return out
        bad_cols = FORBIDDEN_COLUMNS.intersection(c.lower() for c in reader.fieldnames)
        if bad_cols:
            out.append(f"{path}: forbidden column(s) {sorted(bad_cols)}")
        for i, row in enumerate(reader, start=2):
            out.extend(_check_row(f"{path}:{i}", row))
    return out


def _scan_svg(path: Path) -> list[str]:
    # Origins always appear as URLs; labels legitimately carry versions and AS names.
    text = path.read_text(encoding="utf-8").replace(SVG_NAMESPACE, "")
    if URL_RE.search(text):
        return [f"{path}: URL in SVG text"]
    return []


def _forbidden_keys(node: object) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for k, v in node.items():
            if k.lower() in FORBIDDEN_COLUMNS:
                found.add(k)
            found |= _forbidden_keys(v)
    elif isinstance(node, list):
        for v in node:
            found |= _forbidden_keys(v)
    return found


def _scan_json(path: Path) -> list[str]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    out: list[str] = []
    bad = _forbidden_keys(doc)
    if bad:
        out.append(f"{path}: forbidden key(s) {sorted(bad)}")
    tables = doc.get("tables") if isinstance(doc, dict) else None
    if isinstance(tables, dict):
        for name, rows in tables.items():
            if not isinstance(rows, list):
                continue
            for i, row in enumerate(rows):
                if isinstance(row, dict):
                    out.extend(_check_row(f"{path}:{name}[{i}]", row))
    return out


def scan(paths: Iterable[Path]) -> list[str]:
    violations: list[str] = []
    for p in paths:
        if p.suffix == ".csv":
            violations.extend(_scan_csv(p))
        elif p.suffix == ".svg":
            violations.extend(_scan_svg(p))
        elif p.suffix == ".json":
            violations.extend(_scan_json(p))
    return violations
