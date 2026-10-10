"""Raw query CSVs → the public, origin-free tables and census.json."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from census.buckets import (
    BUCKETS,
    RANK_ORDER,
    bucket_for,
    canonical_version,
    header_engine,
    rank_label,
    server_family,
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _share(num: int, den: int) -> str:
    return f"{(num / den) if den else 0.0:.6f}"


def _is_true(v: str) -> bool:
    return v.strip().lower() == "true"


def build_series(q1: list[dict], q0: list[dict]) -> list[dict]:
    totals: dict[str, int] = defaultdict(int)
    for r in q0:
        totals[r["date"]] += int(r["origins"])
    counts: dict[tuple[str, str], int] = defaultdict(int)
    dates: set[str] = set()
    for r in q1:
        dates.add(r["date"])
        counts[(r["date"], bucket_for(r["info"]))] += int(r["origins"])
    rows = []
    for d in sorted(dates):
        for b in BUCKETS:
            n = counts.get((d, b), 0)
            rows.append(
                {
                    "date": d,
                    "bucket": b,
                    "origins": str(n),
                    "all_origins": str(totals.get(d, 0)),
                    "share": _share(n, totals.get(d, 0)),
                }
            )
    return rows


def build_disagreements(q1: list[dict]) -> list[dict]:
    dis: dict[str, int] = defaultdict(int)
    tot: dict[str, int] = defaultdict(int)
    for r in q1:
        dis[r["date"]] += int(r["disagreements"])
        tot[r["date"]] += int(r["origins"])
    return [{"date": d, "disagreements": str(dis[d]), "origins": str(tot[d])} for d in sorted(tot)]


def build_distribution(q1: list[dict], crawl_date: str) -> list[dict]:
    counts: dict[str, int] = defaultdict(int)
    for r in q1:
        if r["date"] != crawl_date:
            continue
        counts[canonical_version(r["info"])] += int(r["origins"])
    rows = [
        {"version": v, "bucket": bucket_for(v if v != "(hidden)" else ""), "origins": str(n)}
        for v, n in counts.items()
    ]
    rows.sort(key=lambda r: (-int(r["origins"]), r["version"]))
    return rows


def build_ranks(q2: list[dict], q0: list[dict], crawl_date: str) -> list[dict]:
    ps: dict[str, int] = defaultdict(int)
    for r in q2:
        if _is_true(r["pagespeed"]):
            ps[rank_label(r["rank"])] += int(r["origins"])
    totals: dict[str, int] = defaultdict(int)
    for r in q0:
        if r["date"] == crawl_date:
            totals[rank_label(r["rank"])] += int(r["origins"])
    return [
        {
            "rank": label,
            "pagespeed_origins": str(ps.get(label, 0)),
            "all_origins": str(totals.get(label, 0)),
            "share": _share(ps.get(label, 0), totals.get(label, 0)),
        }
        for label in RANK_ORDER
    ]


def build_cooccurrence(q2: list[dict]) -> list[dict]:
    seg = {"pagespeed": [0, 0, 0], "all": [0, 0, 0]}  # origins, wordpress, cpanel
    for r in q2:
        n = int(r["origins"])
        targets = ["all"] + (["pagespeed"] if _is_true(r["pagespeed"]) else [])
        for t in targets:
            seg[t][0] += n
            seg[t][1] += n if _is_true(r["wordpress"]) else 0
            seg[t][2] += n if _is_true(r["cpanel"]) else 0
    rows = []
    for name in ("pagespeed", "all"):
        o, w, c = seg[name]
        rows.append(
            {
                "segment": name,
                "origins": str(o),
                "wordpress_origins": str(w),
                "cpanel_origins": str(c),
                "wordpress_share": _share(w, o),
                "cpanel_share": _share(c, o),
            }
        )
    return rows


def build_servers(q3: list[dict]) -> list[dict]:
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for r in q3:
        if r["client"] != "desktop" or not r["ps_header"]:
            continue
        counts[(header_engine(r["ps_header"]), server_family(r["server"]))] += int(r["origins"])
    rows = [{"engine": e, "server_family": f, "origins": str(n)} for (e, f), n in counts.items()]
    rows.sort(key=lambda r: (r["engine"], -int(r["origins"]), r["server_family"]))
    return rows


def build_detection(q3: list[dict]) -> list[dict]:
    both = header_only = wapp_only = 0
    for r in q3:
        if r["client"] != "desktop":
            continue
        n = int(r["origins"])
        has_header = bool(r["ps_header"])
        has_wapp = _is_true(r["wappalyzer"])
        if has_header and has_wapp:
            both += n
        elif has_header:
            header_only += n
        elif has_wapp:
            wapp_only += n
    return [
        {"signal": "both", "origins": str(both)},
        {"signal": "header_only", "origins": str(header_only)},
        {"signal": "wappalyzer_only", "origins": str(wapp_only)},
    ]


def build_headline(series: list[dict], distribution: list[dict], detection: list[dict], crawl_date: str) -> dict:
    per_date: dict[str, int] = defaultdict(int)
    for r in series:
        per_date[r["date"]] += int(r["origins"])
    dates = sorted(per_date)
    first, latest = dates[0], crawl_date
    peak = max(dates, key=lambda d: (per_date[d], d))
    by_bucket = {b: sum(int(r["origins"]) for r in distribution if r["bucket"] == b) for b in BUCKETS}
    versioned = by_bucket["google-era"] + by_bucket["incubator-era"] + by_bucket["current"]
    out_of_fixes = by_bucket["google-era"] + by_bucket["incubator-era"]
    first_total, latest_total = per_date[first], per_date[latest]
    crawled = {r["date"]: int(r["all_origins"]) for r in series}
    first_share = first_total / crawled[first] if crawled[first] else 0.0
    latest_share = latest_total / crawled[latest] if crawled[latest] else 0.0
    return {
        "crawl_date": latest,
        "first_date": first,
        "first_total": first_total,
        "peak_date": peak,
        "peak_total": per_date[peak],
        "latest_total": latest_total,
        "versioned_total": versioned,
        "hidden_total": by_bucket["hidden"],
        "google_era": by_bucket["google-era"],
        "incubator_era": by_bucket["incubator-era"],
        "current": by_bucket["current"],
        "share_out_of_fixes": round(out_of_fixes / versioned, 4) if versioned else 0.0,
        "share_google_of_versioned": round(by_bucket["google-era"] / versioned, 4) if versioned else 0.0,
        "share_incubator_of_versioned": round(by_bucket["incubator-era"] / versioned, 4) if versioned else 0.0,
        "change_first_to_latest_pct": (
            round((latest_total - first_total) / first_total * 100, 1) if first_total else 0.0
        ),
        "first_share": round(first_share, 6),
        "latest_share": round(latest_share, 6),
        "share_change_pct": (
            round((latest_share - first_share) / first_share * 100, 1) if first_share else 0.0
        ),
        "detection": {r["signal"]: int(r["origins"]) for r in detection},
    }


def write_outputs(date: str, out_dir: Path, tables: dict[str, list[dict]], headline: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        with (out_dir / f"{name}.csv").open("w", newline="", encoding="utf-8") as fh:
            if not rows:
                fh.write("")
                continue
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    # networks_top10.csv is written by `census networks`; keep it in census.json on a re-aggregate.
    extra = out_dir / "networks_top10.csv"
    if "networks_top10" not in tables and extra.exists():
        tables = {**tables, "networks_top10": read_csv(extra)}
    doc = {"crawl_date": date, "headline": headline, "tables": tables}
    (out_dir / "census.json").write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(date: str, work: Path, out_dir: Path) -> dict:
    q0 = read_csv(work / "q0.csv")
    q1 = read_csv(work / "q1.csv")
    q2 = read_csv(work / "q2.csv")
    q3 = read_csv(work / "q3.csv")
    for name, rows in (("q0", q0), ("q1", q1)):
        if not any(r["date"] == date for r in rows):
            raise ValueError(
                f"crawl {date} is absent from {work / (name + '.csv')}; "
                f"re-run `census run --date {date}` before aggregating"
            )
    tables = {
        "series": build_series(q1, q0),
        "disagreements": build_disagreements(q1),
        "distribution": build_distribution(q1, date),
        "ranks": build_ranks(q2, q0, date),
        "cooccurrence": build_cooccurrence(q2),
        "servers": build_servers(q3),
        "detection": build_detection(q3),
    }
    headline = build_headline(tables["series"], tables["distribution"], tables["detection"], date)
    write_outputs(date, out_dir, tables, headline)
    return headline
