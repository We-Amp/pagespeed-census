"""SHA256SUMS over the published files of one crawl, so a re-run can be checked against them."""

from __future__ import annotations

import hashlib
from pathlib import Path

EXCLUDE = {"billing.json", "rib-snapshot.json", "SHA256SUMS"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _published(date: str, repo_root: Path) -> list[Path]:
    data = repo_root / "data" / date
    files = [p for p in data.iterdir() if p.is_file() and p.name not in EXCLUDE]
    files += list((repo_root / "charts" / date).glob("*.svg"))
    return sorted(files)


def write(date: str, repo_root: Path) -> Path:
    out = repo_root / "data" / date / "SHA256SUMS"
    lines = [
        f"{_sha256(p)}  {p.relative_to(repo_root).as_posix()}"
        for p in _published(date, repo_root)
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def verify(path: Path, repo_root: Path) -> list[str]:
    bad = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        if not (repo_root / rel).exists() or _sha256(repo_root / rel) != digest:
            bad.append(rel)
    return bad
