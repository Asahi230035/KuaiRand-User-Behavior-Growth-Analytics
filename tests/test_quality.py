from __future__ import annotations

from pathlib import Path

import pytest

from kuairand_analysis.config import AnalysisConfig
from kuairand_analysis.db import render_sql, sql_literal


def test_sql_helpers_render_and_escape() -> None:
    assert sql_literal("a'b") == "'a''b'"
    assert render_sql("SELECT {{ value }}", {"value": 7}) == "SELECT 7"
    with pytest.raises(ValueError, match="Unresolved"):
        render_sql("SELECT {{ missing }}", {})


def test_config_rejects_incomplete_ten_file_source(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    for index in range(9):
        (raw_dir / f"file_{index}.csv").write_text("x\n1\n", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
project:
  name: test
  timezone: Asia/Shanghai
paths:
  raw_dir: {raw_dir}
  processed_dir: {tmp_path / "processed"}
  marts_dir: {tmp_path / "marts"}
  results_dir: {tmp_path / "results"}
  figures_dir: {tmp_path / "figures"}
duckdb:
  database: ":memory:"
  memory_limit: 1GB
  threads: 2
  temp_directory: {tmp_path / "tmp"}
  min_free_gb: 0
analysis:
  cohort_offsets: [1, 3, 7]
  modeling:
    outcome_offset: 7
    train_fraction: 0.8
    min_eligible_dates: 2
  content:
    min_tag_exposures: 0
""",
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="Expected exactly ten"):
        AnalysisConfig.from_yaml(config_path)

def test_validation_guard_rejects_null_status() -> None:
    import duckdb

    validation_sql = (
        Path(__file__).resolve().parents[1] / "sql" / "08_validation.sql"
    ).read_text(encoding="utf-8")
    assert "WHERE passed IS DISTINCT FROM TRUE" in validation_sql

    with duckdb.connect(":memory:") as connection:
        failures = connection.execute(
            "SELECT COUNT(*) FROM (VALUES (TRUE), (FALSE), (NULL)) AS checks(passed) "
            "WHERE passed IS DISTINCT FROM TRUE"
        ).fetchone()[0]
    assert failures == 2
