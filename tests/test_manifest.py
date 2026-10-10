from pathlib import Path

from census import manifest


def _seed(root: Path) -> None:
    (root / "data" / "2026-09-01").mkdir(parents=True)
    (root / "charts" / "2026-09-01").mkdir(parents=True)
    (root / "data" / "2026-09-01" / "series.csv").write_text("a\n")
    (root / "data" / "2026-09-01" / "census.json").write_text("{}\n")
    (root / "data" / "2026-09-01" / "billing.json").write_text("[]\n")
    (root / "charts" / "2026-09-01" / "series.svg").write_text("<svg/>\n")


def test_manifest_covers_published_files_and_excludes_run_records(tmp_path: Path):
    _seed(tmp_path)
    p = manifest.write("2026-09-01", tmp_path)
    text = p.read_text()
    assert "data/2026-09-01/series.csv" in text
    assert "data/2026-09-01/census.json" in text
    assert "charts/2026-09-01/series.svg" in text
    assert "billing.json" not in text and "SHA256SUMS" not in text
    assert manifest.verify(p, tmp_path) == []


def test_verify_reports_a_changed_file(tmp_path: Path):
    _seed(tmp_path)
    p = manifest.write("2026-09-01", tmp_path)
    (tmp_path / "data" / "2026-09-01" / "series.csv").write_text("b\n")
    assert manifest.verify(p, tmp_path) == ["data/2026-09-01/series.csv"]


def test_verify_tolerates_blank_lines_and_reports_a_missing_file(tmp_path: Path):
    _seed(tmp_path)
    p = manifest.write("2026-09-01", tmp_path)
    p.write_text("\n" + p.read_text() + "\n\n")
    assert manifest.verify(p, tmp_path) == []
    (tmp_path / "charts" / "2026-09-01" / "series.svg").unlink()
    assert manifest.verify(p, tmp_path) == ["charts/2026-09-01/series.svg"]
