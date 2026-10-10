from pathlib import Path

from census import guard


def _write(p: Path, text: str) -> Path:
    p.write_text(text)
    return p


def test_version_strings_do_not_trip_the_ip_check(tmp_path):
    f = _write(tmp_path / "distribution.csv", "version,bucket,origins\n1.13.35.2,google-era,9741\n1.14.36.1,incubator-era,2831\n")
    assert guard.scan([f]) == []


def test_real_ip_in_any_other_column_fails(tmp_path):
    f = _write(tmp_path / "servers.csv", "engine,server_family,origins\napache-module,1.13.35.2,5\n")
    assert any("IP" in v for v in guard.scan([f]))


def test_forbidden_column_names_fail(tmp_path):
    for col in ("url", "page", "root_page", "origin", "host", "hostname", "ip", "ip_addr"):
        f = _write(tmp_path / f"{col}.csv", f"{col},origins\nx,1\n")
        assert guard.scan([f]), col


def test_network_column_may_contain_a_domain_but_others_may_not(tmp_path):
    ok = _write(tmp_path / "networks_top10.csv", "asn,network,share\n16509,\"Amazon.com, Inc.\",12.3\n")
    assert guard.scan([ok]) == []
    bad = _write(tmp_path / "servers.csv", "engine,server_family,origins\napache-module,example.com,5\n")
    assert any("hostname" in v for v in guard.scan([bad]))


def test_json_and_svg_are_scanned_too(tmp_path):
    j = _write(tmp_path / "census.json", '{"tables": {"x": [{"root_page": "https://example.com/"}]}}')
    s = _write(tmp_path / "series.svg", "<svg><title>https://example.com/</title></svg>")
    assert guard.scan([j]) and guard.scan([s])


def test_clean_json_passes(tmp_path):
    j = _write(tmp_path / "census.json", '{"headline": {"latest_total": 28733, "crawl_date": "2026-09-01"}}')
    assert guard.scan([j]) == []


def test_svg_namespace_version_labels_and_network_names_pass(tmp_path):
    s = _write(
        tmp_path / "chart.svg",
        '<svg xmlns="http://www.w3.org/2000/svg"><text>1.13.35.2</text><text>Amazon.com, Inc.</text></svg>',
    )
    assert guard.scan([s]) == []


def test_json_network_column_exempt_but_other_columns_are_not(tmp_path):
    ok = _write(
        tmp_path / "ok.json",
        '{"tables": {"networks_top10": [{"asn": "16509", "network": "Amazon.com, Inc.", "share_pct": "12.3"}]}}',
    )
    assert guard.scan([ok]) == []
    bad = _write(
        tmp_path / "bad.json",
        '{"tables": {"servers": [{"engine": "x", "server_family": "example.com", "origins": "1"}]}}',
    )
    assert any("hostname" in v for v in guard.scan([bad]))


def test_ipv6_literal_fails_in_any_column_including_version_and_network(tmp_path):
    for i, addr in enumerate(
        ["2606:4700::1111", "2001:db8:0:0:0:0:0:1", "::1", "[2a01:4f8::2]", "fe80::"]
    ):
        v = _write(tmp_path / f"v{i}.csv", f"version,bucket,origins\n{addr},hidden,1\n")
        assert any("IPv6" in x for x in guard.scan([v])), addr
        n = _write(tmp_path / f"n{i}.csv", f"asn,network,share_pct\n1,{addr},1.0\n")
        assert any("IPv6" in x for x in guard.scan([n])), addr
    j = _write(tmp_path / "t.json", '{"tables": {"x": [{"network": "2606:4700::1111"}]}}')
    assert any("IPv6" in x for x in guard.scan([j]))


def test_dates_times_and_versions_are_not_ipv6(tmp_path):
    f = _write(
        tmp_path / "ok.csv",
        "date,version,note,share\n2026-09-01,1.13.35.2,2026-10-10T08:49:27Z,0.002450\n",
    )
    assert guard.scan([f]) == []
