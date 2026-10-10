import xml.etree.ElementTree as ET
from pathlib import Path

from census import charts, guard

SERIES = []
for i, d in enumerate(["2020-12-01", "2021-01-01", "2021-02-01"]):
    for b, n in (("google-era", 100 - i), ("incubator-era", 10 + i), ("current", 0), ("hidden", 40)):
        SERIES.append({"date": d, "bucket": b, "origins": str(n), "all_origins": "1000", "share": "0.1"})

BARS = [
    {"version": "1.13.35.2", "bucket": "google-era", "origins": "9741"},
    {"version": "(hidden)", "bucket": "hidden", "origins": "6227"},
    {"version": "1.14.36.1", "bucket": "incubator-era", "origins": "2831"},
]

NS = {"s": "http://www.w3.org/2000/svg"}


def _root(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def test_series_has_four_panels_a_legend_and_hover_targets():
    root = _root(charts.series_svg(SERIES))
    assert root.attrib["class"] == "census" and root.attrib["role"] == "img"
    assert len(root.findall(".//s:path[@class='census-line']", NS)) == 4
    legend = root.find(".//s:g[@class='census-legend']", NS)
    assert legend is not None and len(legend.findall("s:text", NS)) == 4
    points = root.findall(".//s:circle[@class='census-point']", NS)
    assert len(points) == 12 and all(float(c.attrib["r"]) >= 6 for c in points)
    assert all(c.find("s:title", NS) is not None for c in points)
    assert root.find("s:title", NS) is not None and root.find("s:desc", NS) is not None


def test_bars_have_rounded_ends_titles_and_no_value_text():
    svg = charts.bars_svg(BARS, label_key="version", value_key="origins", title="Versions",
                          desc="Origins per version", color_key="bucket")
    root = _root(svg)
    bars = root.findall(".//s:path[@class='census-bar']", NS)
    assert len(bars) == 3
    assert all(b.find("s:title", NS) is not None for b in bars)
    assert all(" a4 4 0 0 1 " in b.attrib["d"] for b in bars)
    texts = [t.text for t in root.findall(".//s:text", NS)]
    assert "9,741" not in texts
    assert "1.13.35.2" in texts
    assert root.findall(".//s:text[@class='census-era']", NS)


def test_output_is_deterministic_and_origin_free(tmp_path: Path):
    a = charts.series_svg(SERIES)
    assert a == charts.series_svg(SERIES)
    p = tmp_path / "series.svg"
    p.write_text(a)
    assert guard.scan([p]) == []


def test_render_all_writes_four_files(tmp_path: Path):
    census = {
        "crawl_date": "2026-09-01",
        "headline": {},
        "tables": {
            "series": SERIES,
            "distribution": BARS,
            "ranks": [{"rank": "top 1k", "pagespeed_origins": "1", "all_origins": "598", "share": "0.001672"}],
            "networks_top10": [{"asn": "16509", "network": "Amazon.com, Inc.", "share_pct": "12.3"}],
        },
    }
    paths = charts.render_all(census, tmp_path)
    assert sorted(p.name for p in paths) == ["distribution.svg", "networks.svg", "ranks.svg", "series.svg"]
    for p in paths:
        ET.fromstring(p.read_text())


def test_style_uses_site_tokens_and_dark_class():
    assert "var(--color-interactive" in charts.STYLE
    assert ".dark svg.census" in charts.STYLE
    assert "prefers-color-scheme" not in charts.STYLE


def test_nice_ceiling_handles_shares():
    assert charts._nice_ceiling(0.0017) == 0.002
    assert charts._nice_ceiling(0.145) == 0.2
    assert charts._nice_ceiling(16421) == 20000
    assert charts._nice_ceiling(0) == 1.0


def test_render_all_ids_are_unique_across_fragments(tmp_path: Path):
    census = {
        "tables": {
            "series": SERIES,
            "distribution": BARS,
            "ranks": [{"rank": "top 1k", "share": "0.001672"}],
            "networks_top10": [{"asn": "16509", "network": "Amazon.com, Inc.", "share_pct": "12.3"}],
        },
    }
    ids: list[str] = []
    for p in charts.render_all(census, tmp_path):
        root = ET.fromstring(p.read_text())
        own = [e.attrib["id"] for e in root.iter() if "id" in e.attrib]
        refs = root.attrib["aria-labelledby"].split()
        assert len(refs) == 2 and all(r in own for r in refs)
        ids += own
    assert len(ids) == len(set(ids))


def test_ranks_chart_labels_exclusive_bands(tmp_path: Path):
    census = {
        "tables": {
            "series": SERIES,
            "distribution": BARS,
            "ranks": [
                {"rank": "top 1k", "share": "0.001"},
                {"rank": "top 5k", "share": "0.002"},
            ],
            "networks_top10": [{"asn": "1", "network": "X", "share_pct": "1"}],
        },
    }
    charts.render_all(census, tmp_path)
    text = (tmp_path / "ranks.svg").read_text()
    assert "1k–5k" in text and "top 5k" not in text


def test_ranks_chart_omits_empty_rows(tmp_path: Path):
    census = {
        "tables": {
            "series": SERIES,
            "distribution": BARS,
            "ranks": [
                {"rank": "top 1k", "all_origins": "598", "share": "0.001"},
                {"rank": "unranked", "all_origins": "0", "share": "0"},
            ],
            "networks_top10": [{"asn": "1", "network": "X", "share_pct": "1"}],
        },
    }
    charts.render_all(census, tmp_path)
    text = (tmp_path / "ranks.svg").read_text()
    assert "unranked" not in text and "top 1k" in text


def _bar_rows(values):
    return [{"k": f"row{i}", "v": str(v)} for i, v in enumerate(values)]


def test_zero_value_draws_no_bar_but_keeps_its_label():
    svg = charts.bars_svg(_bar_rows([100, 0]), label_key="k", value_key="v", title="t", desc="d")
    root = _root(svg)
    assert len(root.findall(".//s:path[@class='census-bar']", NS)) == 1
    assert [t.text for t in root.findall(".//s:text[@class='census-label']", NS)] == ["row0", "row1"]


def test_narrow_bars_stay_right_of_the_axis():
    import re

    svg = charts.bars_svg(_bar_rows([100000, 700, 300, 1]), label_key="k", value_key="v",
                          title="t", desc="d")
    left = 250
    for bar in _root(svg).findall(".//s:path[@class='census-bar']", NS):
        d = bar.attrib["d"]
        h = float(re.search(r"H([\d.]+) a", d).group(1))
        rad = float(re.search(r" a([\d.]+) ", d).group(1))
        assert h >= left, d
        assert 0 < rad <= 4 and "v-" not in d, d
