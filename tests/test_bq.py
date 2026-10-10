from pathlib import Path

import pytest

from census import bq


class _Field:
    def __init__(self, name):
        self.name = name


class _Row:
    def __init__(self, values):
        self._values = values

    def values(self):
        return self._values


class _Rows:
    def __init__(self, names, rows, billed):
        self.schema = [_Field(n) for n in names]
        self._rows = rows
        self.total_bytes_billed = billed

    def __iter__(self):
        return iter(_Row(r) for r in self._rows)


class _Job:
    def __init__(self, dry_bytes=None, rows=None, billed=0):
        self.total_bytes_processed = dry_bytes
        self._rows = rows
        self.total_bytes_billed = billed

    def result(self):
        return self._rows


class _Client:
    def __init__(self):
        self.calls = []

    def query(self, sql, job_config=None):
        self.calls.append((sql, job_config))
        if job_config.dry_run:
            return _Job(dry_bytes=123_456_789)
        rows = _Rows(["date", "origins"], [("2026-09-01", 3), ("2026-08-01", None)], billed=100)
        return _Job(rows=rows, billed=100)


@pytest.fixture
def fake_client(monkeypatch):
    c = _Client()
    monkeypatch.setattr(bq, "client", lambda: c)
    return c


def test_load_sql_reads_every_declared_query():
    assert set(bq.QUERIES) == {"q0", "q1", "q2", "q3", "q4"}
    for name in bq.QUERIES.values():
        sql = bq.load_sql(name)
        assert "httparchive.crawl" in sql
        assert "@crawl_date" in sql


def test_query_params_are_dates():
    params = bq.query_params("2026-09-01", "2020-12-01")
    by_name = {p.name: p for p in params}
    assert by_name["crawl_date"].type_ == "DATE"
    assert by_name["crawl_date"].value == "2026-09-01"
    assert by_name["start_date"].value == "2020-12-01"


def test_dry_run_returns_bytes_and_never_executes(fake_client):
    n = bq.dry_run("SELECT 1", [])
    assert n == 123_456_789
    cfg = fake_client.calls[0][1]
    assert cfg.dry_run is True
    assert cfg.use_query_cache is False


def test_cap_for_is_one_and_a_half_times_plus_floor():
    assert bq.cap_for(1_000_000_000) == 1_510_000_000
    assert bq.cap_for(0) == 10_000_000


def test_run_to_csv_writes_header_rows_and_blank_for_null(fake_client, tmp_path: Path):
    out = tmp_path / "q0.csv"
    rows, billed = bq.run_to_csv("SELECT 1", [], out, maximum_bytes_billed=999)
    assert rows == 2 and billed == 100
    assert out.read_text().splitlines() == ["date,origins", "2026-09-01,3", "2026-08-01,"]
    cfg = fake_client.calls[0][1]
    assert cfg.maximum_bytes_billed == 999
    assert cfg.dry_run is False


def test_run_to_csv_refuses_without_cap(fake_client, tmp_path: Path):
    with pytest.raises(ValueError):
        bq.run_to_csv("SELECT 1", [], tmp_path / "x.csv", maximum_bytes_billed=0)


def test_run_to_csv_replaces_the_target_only_after_a_complete_write(fake_client, tmp_path: Path, monkeypatch):
    out = tmp_path / "q0.csv"
    out.write_text("previous,complete\n")

    class _Broken(_Rows):
        def __iter__(self):
            yield _Row(("2026-09-01", 3))
            raise RuntimeError("connection lost")

    broken = _Broken(["date", "origins"], [], billed=1)
    monkeypatch.setattr(fake_client, "query", lambda sql, job_config=None: _Job(rows=broken, billed=1))
    with pytest.raises(RuntimeError):
        bq.run_to_csv("SELECT 1", [], out, maximum_bytes_billed=999)
    assert out.read_text() == "previous,complete\n"
    assert [p.name for p in tmp_path.iterdir()] == ["q0.csv"]


def test_run_to_csv_leaves_no_temp_file_behind(fake_client, tmp_path: Path):
    bq.run_to_csv("SELECT 1", [], tmp_path / "q0.csv", maximum_bytes_billed=999)
    assert [p.name for p in tmp_path.iterdir()] == ["q0.csv"]


@pytest.mark.parametrize("env,expected", [("my-project", "my-project"), ("", None), (None, None)])
def test_client_takes_the_project_from_the_environment(monkeypatch, env, expected):
    seen = {}

    def fake_client_cls(project=None):
        seen["project"] = project
        return object()

    monkeypatch.setattr(bq.bigquery, "Client", fake_client_cls)
    if env is None:
        monkeypatch.delenv("CENSUS_BQ_PROJECT", raising=False)
    else:
        monkeypatch.setenv("CENSUS_BQ_PROJECT", env)
    bq.client()
    assert seen["project"] == expected


def test_bq_module_names_no_project():
    assert not hasattr(bq, "PROJECT")


def test_bq_module_never_imports_the_storage_api():
    import census.bq as module

    assert "bigquery_storage" not in Path(module.__file__).read_text()
