"""Thin BigQuery wrapper: dry runs, byte caps, REST row iteration to CSV.

Result sets are megabytes, and the Storage Read API bills per TiB read, so this
module never constructs a storage client: rows are paged over the REST API.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

from google.cloud import bigquery

PROJECT_ENV = "CENSUS_BQ_PROJECT"
SQL_DIR = Path(__file__).resolve().parents[2] / "sql"

QUERIES: dict[str, str] = {
    "q0": "q0_totals.sql",
    "q1": "q1_series.sql",
    "q2": "q2_latest_pages.sql",
    "q3": "q3_latest_headers.sql",
    "q4": "q4_latest_ips.sql",
}

CAP_FACTOR = 1.5
CAP_FLOOR = 10_000_000  # BigQuery's 10 MB minimum billing unit


def client() -> bigquery.Client:
    """Bill queries to $CENSUS_BQ_PROJECT, or to the application-default project when unset."""
    return bigquery.Client(project=os.environ.get(PROJECT_ENV) or None)


def load_sql(name: str) -> str:
    return (SQL_DIR / name).read_text(encoding="utf-8")


def query_params(crawl_date: str, start_date: str) -> list[bigquery.ScalarQueryParameter]:
    return [
        bigquery.ScalarQueryParameter("crawl_date", "DATE", crawl_date),
        bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
    ]


def dry_run(sql: str, params: list[bigquery.ScalarQueryParameter]) -> int:
    cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False, query_parameters=params)
    job = client().query(sql, job_config=cfg)
    return int(job.total_bytes_processed or 0)


def cap_for(dry_bytes: int) -> int:
    return int(dry_bytes * CAP_FACTOR) + CAP_FLOOR


def run_to_csv(
    sql: str,
    params: list[bigquery.ScalarQueryParameter],
    out_path: Path,
    maximum_bytes_billed: int,
) -> tuple[int, int]:
    if maximum_bytes_billed <= 0:
        raise ValueError("refusing to run a query without a positive maximum_bytes_billed")
    cfg = bigquery.QueryJobConfig(
        dry_run=False,
        use_query_cache=True,
        maximum_bytes_billed=maximum_bytes_billed,
        query_parameters=params,
    )
    job = client().query(sql, job_config=cfg)
    rows = job.result()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Write beside the target and rename, so an interrupted download never leaves a
    # truncated CSV where a complete one is expected.
    tmp_path = out_path.with_name(out_path.name + ".tmp")
    n = 0
    try:
        with tmp_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow([f.name for f in rows.schema])
            for row in rows:
                writer.writerow(["" if v is None else v for v in row.values()])
                n += 1
        os.replace(tmp_path, out_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    billed = getattr(rows, "total_bytes_billed", None)
    if billed is None:
        billed = getattr(job, "total_bytes_billed", 0)
    return n, int(billed or 0)
