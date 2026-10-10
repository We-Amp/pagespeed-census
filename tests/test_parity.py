"""census.json must equal the CSVs it is derived from, for every published crawl."""

import json
from pathlib import Path

import pytest

from census.aggregate import read_csv

ROOT = Path(__file__).resolve().parents[1]
DATES = sorted(p.name for p in (ROOT / "data").glob("20*-*-01") if (p / "census.json").exists())


@pytest.mark.parametrize("date", DATES)
def test_json_tables_match_csvs(date):
    doc = json.loads((ROOT / "data" / date / "census.json").read_text())
    for name, rows in doc["tables"].items():
        csv_rows = read_csv(ROOT / "data" / date / f"{name}.csv")
        assert rows == csv_rows, name


@pytest.mark.parametrize("date", DATES)
def test_headline_is_consistent_with_distribution(date):
    doc = json.loads((ROOT / "data" / date / "census.json").read_text())
    h = doc["headline"]
    dist = doc["tables"]["distribution"]
    assert h["latest_total"] == sum(int(r["origins"]) for r in dist)
    assert h["hidden_total"] == sum(int(r["origins"]) for r in dist if r["bucket"] == "hidden")
    assert h["versioned_total"] == h["google_era"] + h["incubator_era"] + h["current"]
