import csv
import json
from pathlib import Path

import pytest

from census import aggregate as ag

Q0 = [
    {"date": "2020-12-01", "rank": "", "origins": "100"},
    {"date": "2026-09-01", "rank": "1000", "origins": "10"},
    {"date": "2026-09-01", "rank": "50000000", "origins": "90"},
]
Q1 = [
    {"date": "2020-12-01", "info": "1.13.35.2", "rank": "", "origins": "8", "disagreements": "1"},
    {"date": "2020-12-01", "info": "on", "rank": "", "origins": "2", "disagreements": "0"},
    {"date": "2026-09-01", "info": "1.13.35.2", "rank": "1000", "origins": "1", "disagreements": "0"},
    {"date": "2026-09-01", "info": "1.13.35.2", "rank": "50000000", "origins": "3", "disagreements": "0"},
    {"date": "2026-09-01", "info": "1.14.36.1", "rank": "50000000", "origins": "2", "disagreements": "1"},
    {"date": "2026-09-01", "info": "1.15.0", "rank": "50000000", "origins": "1", "disagreements": "0"},
    {"date": "2026-09-01", "info": "", "rank": "50000000", "origins": "2", "disagreements": "0"},
    {"date": "2026-09-01", "info": "Till.Tech", "rank": "50000000", "origins": "1", "disagreements": "0"},
]
Q2 = [
    {"pagespeed": "true", "info": "1.13.35.2", "rank": "1000", "wordpress": "true", "cpanel": "false", "origins": "1"},
    {"pagespeed": "true", "info": "", "rank": "50000000", "wordpress": "false", "cpanel": "true", "origins": "3"},
    {"pagespeed": "false", "info": "", "rank": "1000", "wordpress": "true", "cpanel": "false", "origins": "9"},
    {"pagespeed": "false", "info": "", "rank": "50000000", "wordpress": "false", "cpanel": "false", "origins": "87"},
]
Q3 = [
    {"client": "desktop", "ps_header": "x-mod-pagespeed", "ps_value": "1.13.35.2-0", "server": "Apache/2.4", "wappalyzer": "true", "origins": "5"},
    {"client": "desktop", "ps_header": "x-page-speed", "ps_value": "1.13.35.2-0", "server": "nginx", "wappalyzer": "true", "origins": "2"},
    {"client": "desktop", "ps_header": "x-mod-pagespeed", "ps_value": "on", "server": "", "wappalyzer": "false", "origins": "1"},
    {"client": "desktop", "ps_header": "", "ps_value": "", "server": "Apache", "wappalyzer": "true", "origins": "1"},
    {"client": "mobile", "ps_header": "x-mod-pagespeed", "ps_value": "1.13.35.2-0", "server": "Apache", "wappalyzer": "true", "origins": "99"},
]


def test_series_zero_fills_every_bucket_and_handles_zero_denominator():
    rows = ag.build_series(Q1, Q0)
    by = {(r["date"], r["bucket"]): r for r in rows}
    assert len(rows) == 2 * 4
    assert by[("2020-12-01", "google-era")]["origins"] == "8"
    assert by[("2020-12-01", "hidden")]["origins"] == "2"
    assert by[("2020-12-01", "current")]["origins"] == "0"
    assert by[("2020-12-01", "google-era")]["all_origins"] == "100"
    assert by[("2020-12-01", "google-era")]["share"] == "0.080000"
    assert by[("2026-09-01", "google-era")]["origins"] == "4"
    assert by[("2026-09-01", "incubator-era")]["origins"] == "2"
    assert by[("2026-09-01", "hidden")]["origins"] == "3"
    missing_denominator = ag.build_series(Q1, [])
    assert all(r["share"] == "0.000000" for r in missing_denominator)


def test_disagreements_sum_per_date():
    rows = ag.build_disagreements(Q1)
    assert rows == [
        {"date": "2020-12-01", "disagreements": "1", "origins": "10"},
        {"date": "2026-09-01", "disagreements": "1", "origins": "10"},
    ]


def test_distribution_collapses_hidden_and_canonicalises():
    rows = ag.build_distribution(Q1, "2026-09-01")
    assert rows[0] == {"version": "1.13.35.2", "bucket": "google-era", "origins": "4"}
    assert {"version": "(hidden)", "bucket": "hidden", "origins": "3"} in rows
    assert {"version": "1.15.0", "bucket": "current", "origins": "1"} in rows
    assert len(rows) == 4


def test_ranks_use_rank_order_and_latest_denominators():
    rows = ag.build_ranks(Q2, Q0, "2026-09-01")
    assert [r["rank"] for r in rows][:2] == ["top 1k", "top 5k"]
    top1k = next(r for r in rows if r["rank"] == "top 1k")
    assert top1k == {"rank": "top 1k", "pagespeed_origins": "1", "all_origins": "10", "share": "0.100000"}
    top5k = next(r for r in rows if r["rank"] == "top 5k")
    assert top5k["share"] == "0.000000"


def test_cooccurrence_two_segments():
    rows = ag.build_cooccurrence(Q2)
    ps = next(r for r in rows if r["segment"] == "pagespeed")
    assert ps["origins"] == "4" and ps["wordpress_origins"] == "1" and ps["cpanel_origins"] == "3"
    assert ps["wordpress_share"] == "0.250000"
    allr = next(r for r in rows if r["segment"] == "all")
    assert allr["origins"] == "100" and allr["wordpress_origins"] == "10"


def test_servers_and_detection_are_desktop_only():
    servers = ag.build_servers(Q3)
    assert {"engine": "apache-module", "server_family": "apache", "origins": "5"} in servers
    assert {"engine": "nginx-module", "server_family": "nginx", "origins": "2"} in servers
    assert {"engine": "apache-module", "server_family": "hidden", "origins": "1"} in servers
    assert sum(int(r["origins"]) for r in servers) == 8
    det = ag.build_detection(Q3)
    assert det == [
        {"signal": "both", "origins": "7"},
        {"signal": "header_only", "origins": "1"},
        {"signal": "wappalyzer_only", "origins": "1"},
    ]


def test_headline_numbers():
    series = ag.build_series(Q1, Q0)
    dist = ag.build_distribution(Q1, "2026-09-01")
    det = ag.build_detection(Q3)
    h = ag.build_headline(series, dist, det, "2026-09-01")
    assert h["latest_total"] == 10
    assert h["versioned_total"] == 7
    assert h["hidden_total"] == 3
    assert h["google_era"] == 4 and h["incubator_era"] == 2 and h["current"] == 1
    assert h["share_out_of_fixes"] == round(6 / 7, 4)
    assert h["share_google_of_versioned"] == round(4 / 7, 4)
    assert h["first_date"] == "2020-12-01" and h["first_total"] == 10
    assert h["peak_total"] == 10
    assert h["change_first_to_latest_pct"] == 0.0
    assert h["first_share"] == 0.1 and h["latest_share"] == 0.1
    assert h["share_change_pct"] == 0.0
    assert h["detection"] == {"both": 7, "header_only": 1, "wappalyzer_only": 1}


def test_write_outputs_is_deterministic(tmp_path: Path):
    tables = {"series": ag.build_series(Q1, Q0)}
    headline = {"latest_total": 10}
    ag.write_outputs("2026-09-01", tmp_path / "a", tables, headline)
    ag.write_outputs("2026-09-01", tmp_path / "b", tables, headline)
    assert (tmp_path / "a" / "series.csv").read_bytes() == (tmp_path / "b" / "series.csv").read_bytes()
    doc = json.loads((tmp_path / "a" / "census.json").read_text())
    assert doc["headline"]["latest_total"] == 10
    assert doc["tables"]["series"][0]["date"] == "2020-12-01"
    assert (tmp_path / "a" / "census.json").read_text().endswith("}\n")


def test_write_outputs_keeps_an_existing_networks_table(tmp_path):
    import json

    (tmp_path / "networks_top10.csv").write_text("rank,network,share\n1,X,0.5\n")
    ag.write_outputs("2026-09-01", tmp_path, {"servers": [{"a": "1"}]}, {})
    doc = json.loads((tmp_path / "census.json").read_text())
    assert doc["tables"]["networks_top10"] == [{"rank": "1", "network": "X", "share": "0.5"}]


def test_headline_share_follows_the_crawl_size():
    q0 = [
        {"date": "2020-12-01", "rank": "", "origins": "3000"},
        {"date": "2026-09-01", "rank": "1000", "origins": "40000"},
    ]
    series = ag.build_series(Q1, q0)
    h = ag.build_headline(series, ag.build_distribution(Q1, "2026-09-01"), ag.build_detection(Q3), "2026-09-01")
    assert h["first_share"] == round(10 / 3000, 6) == 0.003333
    assert h["latest_share"] == 0.00025
    assert h["share_change_pct"] == -92.5


def test_distribution_puts_trunk_builds_in_the_incubator_era_and_other_majors_in_hidden():
    q1 = [
        {"date": "2026-09-01", "info": "1.15.0.0-8917", "rank": "", "origins": "2", "disagreements": "0"},
        {"date": "2026-09-01", "info": "1.15.0.0-8811", "rank": "", "origins": "1", "disagreements": "0"},
        {"date": "2026-09-01", "info": "1.15.0+r19", "rank": "", "origins": "4", "disagreements": "0"},
        {"date": "2026-09-01", "info": "2.0.0.1", "rank": "", "origins": "5", "disagreements": "0"},
        {"date": "2026-09-01", "info": "on", "rank": "", "origins": "1", "disagreements": "0"},
    ]
    assert ag.build_distribution(q1, "2026-09-01") == [
        {"version": "(hidden)", "bucket": "hidden", "origins": "6"},
        {"version": "1.15.0", "bucket": "current", "origins": "4"},
        {"version": "1.15.0.0", "bucket": "incubator-era", "origins": "3"},
    ]


def _write_work(work: Path, q0=Q0, q1=Q1) -> None:
    work.mkdir(parents=True, exist_ok=True)
    for name, rows in (("q0", q0), ("q1", q1), ("q2", Q2), ("q3", Q3)):
        with (work / f"{name}.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)


def test_run_writes_outputs_for_a_crawl_that_is_present(tmp_path: Path):
    _write_work(tmp_path / "work")
    h = ag.run("2026-09-01", tmp_path / "work", tmp_path / "out")
    assert h["latest_total"] == 10
    assert (tmp_path / "out" / "census.json").exists()


@pytest.mark.parametrize("missing", ["q0", "q1"])
def test_run_fails_when_the_crawl_is_absent_from_a_query_result(tmp_path: Path, missing):
    q0 = [r for r in Q0 if missing != "q0" or r["date"] != "2026-09-01"]
    q1 = [r for r in Q1 if missing != "q1" or r["date"] != "2026-09-01"]
    _write_work(tmp_path / "work", q0=q0, q1=q1)
    with pytest.raises(ValueError, match=rf"crawl 2026-09-01 is absent from .*{missing}\.csv"):
        ag.run("2026-09-01", tmp_path / "work", tmp_path / "out")
    assert not (tmp_path / "out").exists()
