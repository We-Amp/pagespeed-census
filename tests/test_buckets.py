# tests/test_buckets.py
import pytest

from census.buckets import (
    BUCKETS,
    RANK_ORDER,
    bucket_for,
    canonical_version,
    header_engine,
    parse_version,
    rank_label,
    server_family,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1.13.35.2", (1, 13, 35, 2)),
        ("1.13.35.2-0", (1, 13, 35, 2)),
        ("1.14.36.1", (1, 14, 36, 1)),
        ("1.15.0", (1, 15, 0)),
        ("1.15.0+r19", (1, 15, 0)),
        ("1.16.0", (1, 16, 0)),
        ("1.15.0.0-8917", (1, 15, 0, 0)),
        ("1.15.0.0-8811", (1, 15, 0, 0)),
        ("2.0.0.1", (2, 0, 0, 1)),
        ("60.09.02", (60, 9, 2)),
        ("2.1.0-22", (2, 1, 0)),
        ("v1.9.32.14", (1, 9, 32, 14)),
        (" 1.4.26.5 ", (1, 4, 26, 5)),
        ("", None),
        (None, None),
        ("on", None),
        ("1", None),
        ("yes", None),
        ("Enabled", None),
        ("off", None),
        ("X", None),
        ("Till.Tech", None),
        ("PageSpeed", None),
    ],
)
def test_parse_version(value, expected):
    assert parse_version(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1.13.35.2", "google-era"),
        ("1.13.35.2-0", "google-era"),
        ("1.4.26.5", "google-era"),
        ("0.10.22.4", "google-era"),
        ("0.9.18.7", "google-era"),
        ("1.9.32.14", "google-era"),
        ("1.13.35.3", "google-era"),
        ("1.14.36.1", "incubator-era"),
        ("1.14.33.1", "incubator-era"),
        ("1.15.0", "current"),
        ("1.15.0+r19", "current"),
        ("1.16.0", "current"),
        ("1.17.0", "current"),
        ("1.15.0.0-8917", "incubator-era"),
        ("1.15.0.0-8811", "incubator-era"),
        ("1.15.0.0", "incubator-era"),
        ("1.16.0.0-1", "incubator-era"),
        ("1.14.0", "incubator-era"),
        ("2.0.1", "hidden"),
        ("2.0.0.1", "hidden"),
        ("60.09.02", "hidden"),
        ("2.1.0-22", "hidden"),
        ("", "hidden"),
        (None, "hidden"),
        ("on", "hidden"),
        ("1", "hidden"),
    ],
)
def test_bucket_for(value, expected):
    assert bucket_for(value) == expected


def test_bucket_display_order():
    assert BUCKETS == ("google-era", "incubator-era", "current", "hidden")


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1.13.35.2-0", "1.13.35.2"),
        ("1.15.0+r19", "1.15.0"),
        ("1.15.0", "1.15.0"),
        ("1.16.0", "1.16.0"),
        ("1.15.0.0-8917", "1.15.0.0"),
        ("1.15.0.0-8811", "1.15.0.0"),
        ("2.0.0.1", "(hidden)"),
        ("60.09.02", "(hidden)"),
        ("2.1.0-22", "(hidden)"),
        ("v1.9.32.14", "1.9.32.14"),
        ("0.10.22.4", "0.10.22.4"),
        ("on", "(hidden)"),
        ("", "(hidden)"),
        (None, "(hidden)"),
    ],
)
def test_canonical_version(value, expected):
    assert canonical_version(value) == expected


@pytest.mark.parametrize(
    "rank,label",
    [
        (1000, "top 1k"),
        (5000, "top 5k"),
        (10000, "top 10k"),
        (50000, "top 50k"),
        (100000, "top 100k"),
        (500000, "top 500k"),
        (1000000, "top 1M"),
        (5000000, "top 5M"),
        (10000000, "top 10M"),
        (50000000, "top 50M"),
        (None, "unranked"),
        ("", "unranked"),
        ("1000", "top 1k"),
    ],
)
def test_rank_label(rank, label):
    assert rank_label(rank) == label


def test_rank_order_covers_every_label():
    assert RANK_ORDER == (
        "top 1k", "top 5k", "top 10k", "top 50k", "top 100k", "top 500k",
        "top 1M", "top 5M", "top 10M", "top 50M", "unranked",
    )


def test_rank_label_rejects_unknown_value():
    with pytest.raises(ValueError):
        rank_label(1234)


@pytest.mark.parametrize(
    "value,family",
    [
        ("Apache", "apache"),
        ("Apache/2.4.58 (Ubuntu)", "apache"),
        ("nginx", "nginx"),
        ("nginx/1.24.0", "nginx"),
        ("openresty/1.25.3.1", "nginx"),
        ("Tengine", "nginx"),
        ("LiteSpeed", "litespeed"),
        ("Microsoft-IIS/10.0", "iis"),
        ("cloudflare", "cloudflare"),
        ("Caddy", "other"),
        ("", "hidden"),
        (None, "hidden"),
    ],
)
def test_server_family(value, family):
    assert server_family(value) == family


@pytest.mark.parametrize(
    "name,engine",
    [
        ("x-mod-pagespeed", "apache-module"),
        ("X-Mod-Pagespeed", "apache-module"),
        ("x-page-speed", "nginx-module"),
        ("X-Page-Speed", "nginx-module"),
        (None, "unknown"),
        ("", "unknown"),
    ],
)
def test_header_engine(name, engine):
    assert header_engine(name) == engine


@pytest.mark.parametrize(
    "value",
    ["1.13.35.2-0", "1.14.36.1", "1.15.0+r19", "1.15.0.0-8917", "1.16.0", "2.0.0.1", "on", ""],
)
def test_canonical_form_keeps_its_bucket(value):
    canon = canonical_version(value)
    assert bucket_for("" if canon == "(hidden)" else canon) == bucket_for(value)
