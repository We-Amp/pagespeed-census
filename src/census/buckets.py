"""Version parsing and the classification rules of the census.

A version is the leading run of three or four dot-separated numbers in the header value.

- google-era    : 1.13.x and earlier, including the 0.x releases (the last Google
                  release is 1.13.35.2)
- incubator-era : 1.14.x releases, and unreleased trunk builds that report
                  1.15.0.0-<revision> (four numeric components, 1.15.0.0 or later)
- current       : major 1, exactly three numeric components, 1.15.0 or later
                  (a suffix is allowed: 1.15.0+r19)
- hidden        : header present but no module version: no parseable version, or a
                  version with a major of 2 or more, which no release of the module
                  has carried (never counted as unpatched)
"""

from __future__ import annotations

import re

VERSION_RE = re.compile(r"^\s*v?(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?")

INCUBATOR_MINOR = (1, 14)
CURRENT_FIRST = (1, 15, 0)
MODULE_MAJOR = 1

BUCKETS: tuple[str, ...] = ("google-era", "incubator-era", "current", "hidden")

_RANK_LABELS: dict[int, str] = {
    1_000: "top 1k",
    5_000: "top 5k",
    10_000: "top 10k",
    50_000: "top 50k",
    100_000: "top 100k",
    500_000: "top 500k",
    1_000_000: "top 1M",
    5_000_000: "top 5M",
    10_000_000: "top 10M",
    50_000_000: "top 50M",
}
RANK_ORDER: tuple[str, ...] = tuple(_RANK_LABELS[k] for k in sorted(_RANK_LABELS)) + ("unranked",)

_SERVER_FAMILIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("apache", re.compile(r"apache", re.IGNORECASE)),
    ("nginx", re.compile(r"nginx|openresty|tengine", re.IGNORECASE)),
    ("litespeed", re.compile(r"litespeed", re.IGNORECASE)),
    ("iis", re.compile(r"microsoft-iis", re.IGNORECASE)),
    ("cloudflare", re.compile(r"cloudflare", re.IGNORECASE)),
)


def parse_version(value: str | None) -> tuple[int, ...] | None:
    """Return the numeric components as written, three or four of them, or None.

    The length of the tuple says whether a fourth component was present:
    "1.15.0+r19" -> (1, 15, 0), "1.15.0.0-8917" -> (1, 15, 0, 0).
    """
    if not value:
        return None
    m = VERSION_RE.match(value)
    if not m:
        return None
    return tuple(int(part) for part in m.groups() if part is not None)


def bucket_for(value: str | None) -> str:
    v = parse_version(value)
    if v is None or v[0] > MODULE_MAJOR:
        return "hidden"
    if v >= CURRENT_FIRST:
        # Releases of the current line carry three components. Four components at
        # 1.15.0.0 or later are unreleased builds of the old incubator trunk.
        return "current" if len(v) == 3 else "incubator-era"
    if v[:2] == INCUBATOR_MINOR:
        return "incubator-era"
    return "google-era"


def canonical_version(value: str | None) -> str:
    """The version as written, without any suffix; "(hidden)" for the hidden bucket."""
    if bucket_for(value) == "hidden":
        return "(hidden)"
    return ".".join(str(part) for part in parse_version(value))


def rank_label(rank: int | str | None) -> str:
    if rank is None or rank == "":
        return "unranked"
    r = int(rank)
    try:
        return _RANK_LABELS[r]
    except KeyError as exc:
        raise ValueError(f"unknown HTTP Archive rank value: {rank!r}") from exc


def server_family(value: str | None) -> str:
    if not value:
        return "hidden"
    for family, pattern in _SERVER_FAMILIES:
        if pattern.search(value):
            return family
    return "other"


def header_engine(name: str | None) -> str:
    if not name:
        return "unknown"
    lowered = name.lower()
    if lowered == "x-mod-pagespeed":
        return "apache-module"
    if lowered == "x-page-speed":
        return "nginx-module"
    return "unknown"
