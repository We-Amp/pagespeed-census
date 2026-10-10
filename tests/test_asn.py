from pathlib import Path

from census import asn

FIX = Path(__file__).parent / "fixtures"
Q4 = [
    {"root_page": "https://a.example/", "ps_value": "1.13.35.2-0", "ip_addr": "1.0.0.7", "ip_addr_alt": ""},
    {"root_page": "https://b.example/", "ps_value": "1.13.35.2-0", "ip_addr": "", "ip_addr_alt": "1.0.0.9"},
    {"root_page": "https://c.example/", "ps_value": "on", "ip_addr": "8.8.8.8", "ip_addr_alt": ""},
    {"root_page": "https://d.example/", "ps_value": "1.15.0+r19", "ip_addr": "203.0.113.5", "ip_addr_alt": ""},
    {"root_page": "https://e.example/", "ps_value": "1.14.36.1", "ip_addr": "", "ip_addr_alt": ""},
    {"root_page": "https://f.example/", "ps_value": "1.13.35.2-0", "ip_addr": "192.0.2.1", "ip_addr_alt": ""},
]


def test_choose_ip_prefers_primary_then_alt_then_none():
    assert asn.choose_ip(Q4[0]) == "1.0.0.7"
    assert asn.choose_ip(Q4[1]) == "1.0.0.9"
    assert asn.choose_ip(Q4[4]) is None


def test_map_rows_drops_origin_and_reports_coverage():
    mapped, cov = asn.map_rows(Q4, FIX / "ipasn_mini.dat", FIX / "asnames_mini.json")
    assert cov == {"rows": 6, "with_ip": 5, "mapped": 4}
    assert all(set(r) == {"asn", "network", "bucket"} for r in mapped)
    assert {"asn": "13335", "network": "CLOUDFLARENET", "bucket": "google-era"} in mapped
    assert {"asn": "64500", "network": "Amazon.com, Inc.", "bucket": "current"} in mapped


def test_aggregate_and_public_top10_has_shares_only(tmp_path):
    mapped, _ = asn.map_rows(Q4, FIX / "ipasn_mini.dat", FIX / "asnames_mini.json")
    agg = asn.aggregate_networks(mapped)
    assert agg[0]["asn"] == "13335" and agg[0]["origins"] == "2" and agg[0]["google_era"] == "2"
    assert agg[0]["share"] == "0.500000"
    pub = tmp_path / "networks_top10.csv"
    asn.write_public_top10(agg, pub)
    text = pub.read_text()
    assert text.splitlines()[0] == "asn,network,share_pct"
    assert "50.0" in text and "origins" not in text and "google_era" not in text
    internal = tmp_path / "full" / "networks_full.csv"
    asn.write_internal(agg, internal)
    assert "origins,google_era,incubator_era,current,hidden,share" in internal.read_text().splitlines()[0]


def test_module_has_no_default_location_for_the_full_table():
    assert not hasattr(asn, "INTERNAL_DIR")


def test_choose_ip_strips_ipv6_brackets():
    assert asn.choose_ip({"ip_addr": "[2606:4700::1111]", "ip_addr_alt": ""}) == "2606:4700::1111"


def _work(tmp_path):
    import shutil

    shutil.copy(FIX / "ipasn_mini.dat", tmp_path / "ipasn.dat")
    shutil.copy(FIX / "asnames_mini.json", tmp_path / "asnames.json")
    return tmp_path


def _no_subprocess(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("no download may happen")

    monkeypatch.setattr(asn.subprocess, "run", boom)


def test_ensure_snapshot_reads_fetched_at_from_sidecar(tmp_path, monkeypatch):
    work = _work(tmp_path)
    (work / "rib-fetched-at.txt").write_text("2026-10-01T00:00:00Z\n")
    _no_subprocess(monkeypatch)
    _, _, rec = asn.ensure_snapshot(work)
    assert rec["fetched_at"] == "2026-10-01T00:00:00Z"
    assert rec["attribution_method"] == "httparchive-payload-ip"


def test_ensure_snapshot_falls_back_to_dat_mtime(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    work = _work(tmp_path)
    _no_subprocess(monkeypatch)
    _, _, rec = asn.ensure_snapshot(work)
    expected = datetime.fromtimestamp((work / "ipasn.dat").stat().st_mtime, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert rec["fetched_at"] == expected


def test_use_snapshot_reads_a_pinned_directory_and_downloads_nothing(tmp_path, monkeypatch):
    pinned = _work(tmp_path)
    (pinned / "rib-fetched-at.txt").write_text("2026-10-01T00:00:00Z\n")
    _no_subprocess(monkeypatch)
    dat, names, rec = asn.use_snapshot(pinned)
    assert dat == pinned / "ipasn.dat" and names == pinned / "asnames.json"
    assert rec["fetched_at"] == "2026-10-01T00:00:00Z"
    assert rec["ipasn_sha256"] == asn._sha256(dat)


def test_use_snapshot_fails_when_a_file_is_missing(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError, match="asnames.json"):
        (tmp_path / "ipasn.dat").write_text("x")
        asn.use_snapshot(tmp_path)
