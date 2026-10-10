"""Origin IP -> network, with an offline routing snapshot.

Public output is the ten largest networks by SHARE only. The full per-network table,
with counts and the version split, is written only when the caller names a path for it,
and is not for publication.
"""

from __future__ import annotations

import csv
import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pyasn

from census.buckets import BUCKETS, bucket_for

_TS = "%Y-%m-%dT%H:%M:%SZ"

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_snapshot(work: Path) -> tuple[Path, Path, dict]:
    """Download the latest RouteViews RIB, convert it, fetch AS names. Idempotent per work dir."""
    work.mkdir(parents=True, exist_ok=True)
    dat = work / "ipasn.dat"
    names = work / "asnames.json"
    sidecar = work / "rib-fetched-at.txt"
    if not dat.exists():
        subprocess.run(["pyasn_util_download.py", "--latestv46"], cwd=work, check=True)
        ribs = sorted(work.glob("rib.*.bz2"))
        if not ribs:
            raise RuntimeError("pyasn_util_download.py produced no rib.*.bz2")
        subprocess.run(
            ["pyasn_util_convert.py", "--single", ribs[-1].name, dat.name], cwd=work, check=True
        )
        sidecar.write_text(datetime.now(UTC).strftime(_TS) + "\n")
    if not names.exists():
        subprocess.run(["pyasn_util_asnames.py", "-o", names.name], cwd=work, check=True)
    return dat, names, snapshot_record(work)


def use_snapshot(snapshot_dir: Path) -> tuple[Path, Path, dict]:
    """Use an existing snapshot (ipasn.dat + asnames.json) as it is. Downloads nothing."""
    dat = snapshot_dir / "ipasn.dat"
    names = snapshot_dir / "asnames.json"
    missing = [p.name for p in (dat, names) if not p.exists()]
    if missing:
        raise FileNotFoundError(f"{snapshot_dir} lacks {', '.join(missing)}")
    return dat, names, snapshot_record(snapshot_dir)


def snapshot_record(directory: Path) -> dict:
    dat = directory / "ipasn.dat"
    names = directory / "asnames.json"
    sidecar = directory / "rib-fetched-at.txt"
    ribs = sorted(directory.glob("rib.*.bz2"))
    if sidecar.exists():
        fetched_at = sidecar.read_text().strip()
    else:  # snapshot from before the sidecar existed: the .dat mtime is the best evidence
        fetched_at = datetime.fromtimestamp(dat.stat().st_mtime, UTC).strftime(_TS)
    return {
        "rib_file": ribs[-1].name if ribs else None,
        "ipasn_sha256": _sha256(dat),
        "asnames_sha256": _sha256(names),
        "fetched_at": fetched_at,
        "attribution_method": "httparchive-payload-ip",
    }


def choose_ip(row: dict) -> str | None:
    for key in ("ip_addr", "ip_addr_alt"):
        v = (row.get(key) or "").strip().strip("[]")  # archive stores IPv6 as [addr]
        if v:
            return v
    return None


def map_rows(rows: list[dict], ipasn_dat: Path, asnames_json: Path) -> tuple[list[dict], dict]:
    db = pyasn.pyasn(str(ipasn_dat), as_names_file=str(asnames_json))
    mapped: list[dict] = []
    with_ip = 0
    for r in rows:
        ip = choose_ip(r)
        if ip is None:
            continue
        with_ip += 1
        try:
            as_number, _prefix = db.lookup(ip)
        except ValueError:
            as_number = None
        if as_number is None:
            continue
        mapped.append(
            {
                "asn": str(as_number),
                "network": db.get_as_name(as_number) or f"AS{as_number}",
                "bucket": bucket_for(r.get("ps_value")),
            }
        )
    return mapped, {"rows": len(rows), "with_ip": with_ip, "mapped": len(mapped)}


def aggregate_networks(mapped: list[dict]) -> list[dict]:
    per: dict[str, dict] = {}
    for r in mapped:
        entry = per.setdefault(r["asn"], {"network": r["network"], "origins": 0, **{b: 0 for b in BUCKETS}})
        entry["origins"] += 1
        entry[r["bucket"]] += 1
    total = sum(e["origins"] for e in per.values())
    rows = []
    for as_number, e in per.items():
        rows.append(
            {
                "asn": as_number,
                "network": e["network"],
                "origins": str(e["origins"]),
                "google_era": str(e["google-era"]),
                "incubator_era": str(e["incubator-era"]),
                "current": str(e["current"]),
                "hidden": str(e["hidden"]),
                "share": f"{(e['origins'] / total) if total else 0.0:.6f}",
            }
        )
    rows.sort(key=lambda r: (-int(r["origins"]), r["asn"]))
    return rows


def write_public_top10(agg: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["asn", "network", "share_pct"])
        for r in agg[:10]:
            w.writerow([r["asn"], r["network"], f"{float(r['share']) * 100:.1f}"])


def write_internal(agg: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["asn", "network", "origins", "google_era", "incubator_era", "current", "hidden", "share"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(agg)
