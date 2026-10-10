import json
from pathlib import Path

import pytest

from census import bq, cli


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def fake_bq(monkeypatch):
    calls = {"dry": [], "run": []}

    def fake_dry(sql, params):
        calls["dry"].append(sql)
        return 1_000_000_000

    def fake_run(sql, params, out_path: Path, maximum_bytes_billed: int):
        calls["run"].append((out_path.name, maximum_bytes_billed))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("a,b\n1,2\n")
        return 1, 900_000_000

    monkeypatch.setattr(bq, "dry_run", fake_dry)
    monkeypatch.setattr(bq, "run_to_csv", fake_run)
    return calls


def test_dry_run_prints_every_step_and_spends_nothing(repo, fake_bq, capsys):
    rc = cli.main(["dry-run", "--date", "2026-09-01"])
    assert rc == 0
    out = capsys.readouterr().out
    for step in ("q0", "q1", "q2", "q3", "q4"):
        assert step in out
    assert "total" in out.lower()
    assert len(fake_bq["dry"]) == 5
    assert fake_bq["run"] == []


def test_run_refuses_without_execute(repo, fake_bq, capsys):
    rc = cli.main(["run", "--date", "2026-09-01", "--step", "q0"])
    assert rc == 2
    assert "--execute" in capsys.readouterr().err
    assert fake_bq["run"] == []


def test_run_executes_with_cap_and_records_billing(repo, fake_bq):
    rc = cli.main(["run", "--date", "2026-09-01", "--step", "q0", "--execute"])
    assert rc == 0
    assert fake_bq["run"] == [("q0.csv", bq.cap_for(1_000_000_000))]
    assert (repo / "work" / "2026-09-01" / "q0.csv").exists()
    billing = json.loads((repo / "data" / "2026-09-01" / "billing.json").read_text())
    assert billing[0]["step"] == "q0"
    assert billing[0]["dry_bytes"] == 1_000_000_000
    assert billing[0]["cap_bytes"] == bq.cap_for(1_000_000_000)
    assert billing[0]["billed_bytes"] == 900_000_000
    assert billing[0]["rows"] == 1
    assert billing[0]["ran_at"].endswith("Z")


def test_run_all_excludes_q4_by_default(repo, fake_bq):
    rc = cli.main(["run", "--date", "2026-09-01", "--step", "all", "--execute"])
    assert rc == 0
    assert [name for name, _ in fake_bq["run"]] == ["q0.csv", "q1.csv", "q2.csv", "q3.csv"]


@pytest.fixture
def networks_repo(repo, fake_bq, monkeypatch):
    """A work dir with q4.csv and a snapshot; any download or query fails the test."""
    fix = Path(__file__).parent / "fixtures"
    work = repo / "work" / "2026-09-01"
    work.mkdir(parents=True)
    (work / "q4.csv").write_text(
        "root_page,ps_value,ip_addr,ip_addr_alt\n"
        "https://a.example/,1.13.35.2-0,1.0.0.7,\n"
        "https://b.example/,1.15.0+r19,1.0.0.9,\n"
    )
    snap = repo / "pinned"
    snap.mkdir()
    (snap / "ipasn.dat").write_bytes((fix / "ipasn_mini.dat").read_bytes())
    (snap / "asnames.json").write_bytes((fix / "asnames_mini.json").read_bytes())
    (snap / "rib-fetched-at.txt").write_text("2026-10-01T00:00:00Z\n")

    def boom(*a, **k):
        raise AssertionError("must not download")

    monkeypatch.setattr(cli.asn, "ensure_snapshot", boom)
    monkeypatch.setattr(cli.asn.subprocess, "run", boom)
    monkeypatch.setenv("HOME", str(repo / "home"))
    return repo, snap


def _all_files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def test_networks_writes_no_full_table_without_the_flag(networks_repo, fake_bq):
    repo, snap = networks_repo
    before = _all_files(repo)
    rc = cli.main(["networks", "--date", "2026-09-01", "--execute", "--snapshot-dir", str(snap)])
    assert rc == 0
    assert _all_files(repo) - before == {
        "data/2026-09-01/networks_top10.csv",
        "data/2026-09-01/rib-snapshot.json",
    }
    assert fake_bq["run"] == [] and fake_bq["dry"] == []
    rec = json.loads((repo / "data" / "2026-09-01" / "rib-snapshot.json").read_text())
    assert rec["fetched_at"] == "2026-10-01T00:00:00Z"
    assert rec["coverage"] == {"rows": 2, "with_ip": 2, "mapped": 2}


def test_networks_keeps_the_recorded_rib_name_for_the_same_pinned_snapshot(networks_repo):
    repo, snap = networks_repo
    args = ["networks", "--date", "2026-09-01", "--execute", "--snapshot-dir", str(snap)]
    assert cli.main(args) == 0
    path = repo / "data" / "2026-09-01" / "rib-snapshot.json"
    rec = json.loads(path.read_text())
    assert rec["rib_file"] is None
    path.write_text(json.dumps({**rec, "rib_file": "rib.20261001.0000.bz2"}))
    assert cli.main(args) == 0
    assert json.loads(path.read_text())["rib_file"] == "rib.20261001.0000.bz2"
    path.write_text(json.dumps({**rec, "rib_file": "rib.other.bz2", "ipasn_sha256": "0" * 64}))
    assert cli.main(args) == 0
    assert json.loads(path.read_text())["rib_file"] is None


def test_networks_writes_the_full_table_only_where_asked(networks_repo, fake_bq):
    repo, snap = networks_repo
    full = repo / "elsewhere" / "full.csv"
    rc = cli.main(["networks", "--date", "2026-09-01", "--execute", "--snapshot-dir", str(snap),
                   "--internal-out", str(full)])
    assert rc == 0
    lines = full.read_text().splitlines()
    assert lines[0] == "asn,network,origins,google_era,incubator_era,current,hidden,share"
    assert lines[1].startswith("13335,CLOUDFLARENET,2,1,0,1,0,")
    assert fake_bq["run"] == [] and fake_bq["dry"] == []


def test_networks_stops_when_too_few_rows_carry_an_ip(networks_repo, capsys):
    repo, snap = networks_repo
    (repo / "work" / "2026-09-01" / "q4.csv").write_text(
        "root_page,ps_value,ip_addr,ip_addr_alt\nhttps://a.example/,on,,\nhttps://b.example/,on,1.0.0.7,\n"
    )
    rc = cli.main(["networks", "--date", "2026-09-01", "--execute", "--snapshot-dir", str(snap)])
    assert rc == 3
    err = capsys.readouterr().err
    assert "fewer than 90% of rows carry an IP" in err and "attribution stopped" in err
    assert not (repo / "data" / "2026-09-01" / "networks_top10.csv").exists()


def test_verify_passes_then_lists_a_changed_file(repo, capsys):
    d = repo / "data" / "2026-09-01"
    d.mkdir(parents=True)
    (d / "series.csv").write_text("a\n")
    assert cli.main(["manifest", "--date", "2026-09-01"]) == 0
    assert cli.main(["verify", "--date", "2026-09-01"]) == 0
    assert "1 files checked, 0 mismatch(es)" in capsys.readouterr().out
    (d / "series.csv").write_text("b\n")
    assert cli.main(["verify", "--date", "2026-09-01"]) == 1
    assert "MISMATCH data/2026-09-01/series.csv" in capsys.readouterr().err


def test_verify_fails_without_a_manifest(repo, capsys):
    assert cli.main(["verify", "--date", "2026-09-01"]) == 1
    assert "not found" in capsys.readouterr().err


def test_unknown_subcommand_exits_2():
    with pytest.raises(SystemExit) as e:
        cli.main(["frobnicate"])
    assert e.value.code == 2


def test_networks_without_execute_exits_2_and_runs_nothing(repo, fake_bq):
    rc = cli.main(["networks", "--date", "2026-09-01"])
    assert rc == 2
    assert fake_bq["run"] == [] and fake_bq["dry"] == []
