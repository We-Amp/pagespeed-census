"""`census` command line: dry-run, run (capped), aggregate, networks, charts, guard, manifest, verify."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from census import aggregate, asn, bq, charts, guard, manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_START = "2020-12-01"
PRICE_PER_TIB_USD = 6.25
TIB = 1024**4


def work_dir(date: str) -> Path:
    return REPO_ROOT / "work" / date


def data_dir(date: str) -> Path:
    return REPO_ROOT / "data" / date


def _steps(step: str) -> list[str]:
    if step == "all":
        return ["q0", "q1", "q2", "q3"]  # q4 is per-origin and run deliberately via `networks`
    return [step]


def cmd_dry_run(args: argparse.Namespace) -> int:
    params = bq.query_params(args.date, args.start)
    total = 0
    print(f"{'step':<5} {'GB':>10} {'cap GB':>10}  file")
    for step, filename in bq.QUERIES.items():
        n = bq.dry_run(bq.load_sql(filename), params)
        total += n
        print(f"{step:<5} {n / 1e9:>10.1f} {bq.cap_for(n) / 1e9:>10.1f}  {filename}")
    usd = total / TIB * PRICE_PER_TIB_USD
    print(f"total {total / 1e9:>10.1f} GB  ≈ ${usd:.2f} at ${PRICE_PER_TIB_USD}/TiB before the 1 TiB free tier")
    return 0


def _append_billing(date: str, record: dict) -> None:
    path = data_dir(date) / "billing.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    records = json.loads(path.read_text()) if path.exists() else []
    records.append(record)
    path.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n")


def cmd_run(args: argparse.Namespace) -> int:
    if not args.execute:
        print("refusing to spend: re-run with --execute after reading the dry-run numbers", file=sys.stderr)
        return 2
    params = bq.query_params(args.date, args.start)
    for step in _steps(args.step):
        sql = bq.load_sql(bq.QUERIES[step])
        dry = bq.dry_run(sql, params)
        cap = bq.cap_for(dry)
        out = work_dir(args.date) / f"{step}.csv"
        rows, billed = bq.run_to_csv(sql, params, out, maximum_bytes_billed=cap)
        _append_billing(
            args.date,
            {
                "step": step,
                "dry_bytes": dry,
                "cap_bytes": cap,
                "billed_bytes": billed,
                "rows": rows,
                "ran_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
        print(f"{step}: {rows} rows, {billed / 1e9:.1f} GB billed (cap {cap / 1e9:.1f} GB) -> {out}")
    return 0


def cmd_aggregate(args: argparse.Namespace) -> int:
    headline = aggregate.run(args.date, work_dir(args.date), data_dir(args.date))
    print(json.dumps(headline, indent=2, sort_keys=True))
    return 0


def cmd_guard(args: argparse.Namespace) -> int:
    data = REPO_ROOT / "data"
    paths = (
        list(data.rglob("*.csv"))
        + list(data.rglob("*.json"))
        + list((REPO_ROOT / "charts").rglob("*.svg"))
    )
    violations = guard.scan(paths)
    for v in violations:
        print(v, file=sys.stderr)
    print(f"guard: {len(paths)} files scanned, {len(violations)} violation(s)")
    return 1 if violations else 0


def cmd_networks(args: argparse.Namespace) -> int:
    if not args.execute:
        print("refusing to spend: re-run with --execute (q4 scans ~0.4 TB)", file=sys.stderr)
        return 2
    work = work_dir(args.date)
    q4_csv = work / "q4.csv"
    if q4_csv.exists():
        print(f"q4: using {q4_csv}; no query run")
    else:
        params = bq.query_params(args.date, args.start)
        sql = bq.load_sql(bq.QUERIES["q4"])
        dry = bq.dry_run(sql, params)
        cap = bq.cap_for(dry)
        rows, billed = bq.run_to_csv(sql, params, q4_csv, maximum_bytes_billed=cap)
        _append_billing(
            args.date,
            {
                "step": "q4",
                "dry_bytes": dry,
                "cap_bytes": cap,
                "billed_bytes": billed,
                "rows": rows,
                "ran_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
    if args.snapshot_dir:
        dat, names, record = asn.use_snapshot(Path(args.snapshot_dir).expanduser())
        print(f"routing snapshot: using {dat.parent}; nothing downloaded")
    else:
        dat, names, record = asn.ensure_snapshot(work)
    mapped, coverage = asn.map_rows(aggregate.read_csv(q4_csv), dat, names)
    record["coverage"] = coverage
    snap = data_dir(args.date) / "rib-snapshot.json"
    if record["rib_file"] is None and snap.exists():
        # A pinned snapshot ships without the raw RIB file; keep its recorded name
        # when the hashes show it is the same snapshot.
        previous = json.loads(snap.read_text())
        if all(previous.get(k) == record[k] for k in ("ipasn_sha256", "asnames_sha256")):
            record["rib_file"] = previous.get("rib_file")
    if coverage["rows"] and coverage["with_ip"] / coverage["rows"] < 0.9:
        print(
            f"STOP: fewer than 90% of rows carry an IP ({coverage['with_ip']}/{coverage['rows']}); "
            "attribution stopped",
            file=sys.stderr,
        )
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        return 3
    agg = asn.aggregate_networks(mapped)
    asn.write_public_top10(agg, data_dir(args.date) / "networks_top10.csv")
    census_json = data_dir(args.date) / "census.json"
    if census_json.exists():  # census.json is the single source for the post
        doc = json.loads(census_json.read_text())
        doc["tables"]["networks_top10"] = aggregate.read_csv(data_dir(args.date) / "networks_top10.csv")
        census_json.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    if args.internal_out:
        asn.write_internal(agg, Path(args.internal_out).expanduser())
    snap.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


def cmd_charts(args: argparse.Namespace) -> int:
    census = json.loads((data_dir(args.date) / "census.json").read_text())
    for p in charts.render_all(census, REPO_ROOT / "charts" / args.date):
        print(p)
    return 0


def cmd_manifest(args: argparse.Namespace) -> int:
    print(manifest.write(args.date, REPO_ROOT))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    sums = data_dir(args.date) / "SHA256SUMS"
    if not sums.exists():
        print(f"verify: {sums} not found", file=sys.stderr)
        return 1
    bad = manifest.verify(sums, REPO_ROOT)
    for rel in bad:
        print(f"MISMATCH {rel}", file=sys.stderr)
    checked = sum(1 for line in sums.read_text(encoding="utf-8").splitlines() if line.strip())
    print(f"verify: {checked} files checked, {len(bad)} mismatch(es)")
    return 1 if bad else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="census")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--date", required=True, help="crawl date, YYYY-MM-01")
        sp.add_argument("--start", default=DEFAULT_START, help="first crawl of the series")

    sp = sub.add_parser("dry-run", help="print bytes per query; spends nothing")
    common(sp)
    sp.set_defaults(func=cmd_dry_run)

    sp = sub.add_parser("run", help="run q0–q3 (or one step) under byte caps")
    common(sp)
    sp.add_argument("--step", default="all", choices=["all", "q0", "q1", "q2", "q3", "q4"])
    sp.add_argument("--execute", action="store_true")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("aggregate", help="raw work/<date> CSVs -> data/<date> tables + census.json")
    common(sp)
    sp.set_defaults(func=cmd_aggregate)

    sp = sub.add_parser("networks", help="q4 + routing snapshot -> the public top-10 network shares")
    common(sp)
    sp.add_argument("--execute", action="store_true")
    sp.add_argument(
        "--snapshot-dir",
        metavar="PATH",
        help="use PATH/ipasn.dat and PATH/asnames.json (a pinned routing snapshot); download nothing",
    )
    sp.add_argument(
        "--internal-out",
        metavar="PATH",
        help="also write the full per-network table to PATH (not for publication)",
    )
    sp.set_defaults(func=cmd_networks)

    sp = sub.add_parser("charts", help="data/<date>/census.json -> charts/<date>/*.svg")
    common(sp)
    sp.set_defaults(func=cmd_charts)

    sp = sub.add_parser("manifest", help="write data/<date>/SHA256SUMS over the published files")
    common(sp)
    sp.set_defaults(func=cmd_manifest)

    sp = sub.add_parser("verify", help="check the published files against data/<date>/SHA256SUMS")
    common(sp)
    sp.set_defaults(func=cmd_verify)

    sp = sub.add_parser("guard", help="scan published files for origins, hostnames, IPs")
    sp.set_defaults(func=cmd_guard)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
