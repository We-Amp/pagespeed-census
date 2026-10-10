"""Dry-runs every SQL file against BigQuery. Spends nothing. Opt in with CENSUS_BQ=1."""

import os

import pytest

from census import bq

pytestmark = pytest.mark.bq
needs_bq = pytest.mark.skipif(os.environ.get("CENSUS_BQ") != "1", reason="set CENSUS_BQ=1")

# Upper bounds from the 2026-10-10 dry runs for crawl 2026-09-01 / start 2020-12-01, x1.25 headroom.
EXPECTED_MAX_BYTES = {
    "q0": int(0.204e12),
    "q1": int(1.20e12),
    "q2": int(0.04e12),
    "q3": int(0.62e12),
    "q4": int(0.50e12),
}


@needs_bq
@pytest.mark.parametrize("step", sorted(bq.QUERIES))
def test_dry_run_within_budget(step):
    params = bq.query_params("2026-09-01", "2020-12-01")
    n = bq.dry_run(bq.load_sql(bq.QUERIES[step]), params)
    print(f"{step}: {n / 1e9:.1f} GB")
    assert 0 < n <= EXPECTED_MAX_BYTES[step], f"{step}: {n / 1e9:.1f} GB"
