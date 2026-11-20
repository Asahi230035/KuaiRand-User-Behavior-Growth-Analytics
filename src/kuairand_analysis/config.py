"""Configuration loading and source-data validation."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


EXPECTED_SOURCE_FILES: dict[str, tuple[str, ...]] = {
    "random_logs": ("log_random_4_22_to_5_08_27k.csv",),
    "standard_logs": (
        "log_standard_4_08_to_4_21_27k_part1.csv",
        "log_standard_4_08_to_4_21_27k_part2.csv",
        "log_standard_4_22_to_5_08_27k_part1.csv",
        "log_standard_4_22_to_5_08_27k_part2.csv",
    ),
    "user_features": ("user_features_27k.csv",),
    "video_basic": ("video_features_basic_27k.csv",),
    "video_statistics": (
        "video_features_statistic_27k_part1.csv",
        "video_features_statistic_27k_part2.csv",
        "video_features_statistic_27k_part3.csv",
    ),
}


@dataclass(frozen=True)
class DuckDBConfig:
    """DuckDB resource settings."""

    database: str
    memory_limit: str
    threads: int
    temp_directory: Path
    min_free_gb: float


@dataclass(frozen=True)
class AnalysisSettings:
    """Analysis choices that affect samples and reporting."""

    cohort_offsets: tuple[int, ...]
    outcome_offset: int
    train_fraction: float
    min_eligible_dates: int
    min_tag_exposures: int


@dataclass(frozen=True)
class AnalysisConfig:
    """Validated, path-resolved project configuration."""

    project_root: Path
    config_path: Path
    project_name: str
    timezone: str
    raw_dir: Path
    processed_dir: Path
    marts_dir: Path
    results_dir: Path
    figures_dir: Path
    source_files: dict[str, tuple[Path, ...]]
    duckdb: DuckDBConfig
    analysis: AnalysisSettings

    @classmethod
    def from_yaml(
        cls,
        config_path: str | Path = "config.yaml",
        raw_dir_override: str | Path | None = None,
    ) -> "AnalysisConfig":
        path = Path(config_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with path.open("r", encoding="utf-8") as handle:
            data: dict[str, Any] = yaml.safe_load(handle) or {}

        root = path.parent
        paths = data.get("paths", {})
        raw_value = raw_dir_override or os.environ.get("KUAIRAND_RAW_DIR") or paths.get("raw_dir")
        if raw_value is None:
            raise ValueError("A raw data directory must be configured.")

        raw_dir = cls._resolve(root, raw_value)
        processed_dir = cls._resolve(root, paths.get("processed_dir", "data/processed"))
        marts_dir = cls._resolve(root, paths.get("marts_dir", "data/marts"))
        results_dir = cls._resolve(root, paths.get("results_dir", "data/results"))
        figures_dir = cls._resolve(root, paths.get("figures_dir", "reports/figures"))

        configured_sources = data.get("source_files")
        if configured_sources is not None and configured_sources != {
            key: list(value) for key, value in EXPECTED_SOURCE_FILES.items()
        }:
            configured_flat = {
                Path(name).name
                for values in configured_sources.values()
                for name in values
            }
            expected_flat = {
                name for values in EXPECTED_SOURCE_FILES.values() for name in values
            }
            if configured_flat != expected_flat:
                raise ValueError(
                    "source_files in config.yaml does not match the ten KuaiRand-27K files."
                )

        source_files = {
            role: tuple(raw_dir / name for name in names)
            for role, names in EXPECTED_SOURCE_FILES.items()
        }
        cls._validate_source_files(source_files, raw_dir)

        duckdb_data = data.get("duckdb", {})
        temp_directory = cls._resolve(
            root, duckdb_data.get("temp_directory", "data/tmp/duckdb")
        )
        duckdb_config = DuckDBConfig(
            database=str(duckdb_data.get("database", ":memory:")),
            memory_limit=str(duckdb_data.get("memory_limit", "10GB")),
            threads=int(duckdb_data.get("threads", 8)),
            temp_directory=temp_directory,
            min_free_gb=float(duckdb_data.get("min_free_gb", 12)),
        )
        if duckdb_config.threads < 1:
            raise ValueError("duckdb.threads must be at least 1.")
        if duckdb_config.min_free_gb < 0:
            raise ValueError("duckdb.min_free_gb cannot be negative.")

        analysis_data = data.get("analysis", {})
        modelling_data = analysis_data.get("modeling", {})
        content_data = analysis_data.get("content", {})
        offsets = tuple(int(value) for value in analysis_data.get("cohort_offsets", [1, 3, 7]))
        if not offsets or any(value < 1 for value in offsets):
            raise ValueError("analysis.cohort_offsets must contain positive day offsets.")
        if 7 not in offsets:
            raise ValueError("analysis.cohort_offsets must include the primary D7 horizon.")
        train_fraction = float(modelling_data.get("train_fraction", 0.8))
        if not 0.5 < train_fraction < 0.95:
            raise ValueError("analysis.modeling.train_fraction must be between 0.5 and 0.95.")

        analysis_settings = AnalysisSettings(
            cohort_offsets=offsets,
            outcome_offset=int(modelling_data.get("outcome_offset", 7)),
            train_fraction=train_fraction,
            min_eligible_dates=int(modelling_data.get("min_eligible_dates", 10)),
            min_tag_exposures=int(content_data.get("min_tag_exposures", 100_000)),
        )
        if analysis_settings.outcome_offset not in offsets:
            raise ValueError("The model outcome_offset must be one of cohort_offsets.")

        config = cls(
            project_root=root,
            config_path=path,
            project_name=str(data.get("project", {}).get("name", "KuaiRand analysis")),
            timezone=str(data.get("project", {}).get("timezone", "Asia/Shanghai")),
            raw_dir=raw_dir,
            processed_dir=processed_dir,
            marts_dir=marts_dir,
            results_dir=results_dir,
            figures_dir=figures_dir,
            source_files=source_files,
            duckdb=duckdb_config,
            analysis=analysis_settings,
        )
        config.prepare_output_directories()
        config.check_disk_space()
        return config

    @staticmethod
    def _resolve(root: Path, value: str | Path) -> Path:
        path = Path(value).expanduser()
        return path.resolve() if path.is_absolute() else (root / path).resolve()

    @staticmethod
    def _validate_source_files(
        source_files: dict[str, tuple[Path, ...]], raw_dir: Path
    ) -> None:
        if not raw_dir.is_dir():
            raise FileNotFoundError(f"Raw data directory not found: {raw_dir}")
        missing = [
            str(path)
            for paths in source_files.values()
            for path in paths
            if not path.is_file() or path.stat().st_size == 0
        ]
        if missing:
            formatted = "\n".join(f"  - {path}" for path in missing)
            raise FileNotFoundError(
                f"Expected exactly ten non-empty source CSV files. Missing or empty:\n{formatted}"
            )
        discovered = len(list(raw_dir.glob("*.csv")))
        expected = sum(len(paths) for paths in source_files.values())
        if discovered != expected:
            raise ValueError(
                f"Raw directory contains {discovered} CSV files; expected {expected}."
            )

    def prepare_output_directories(self) -> None:
        for directory in (
            self.processed_dir,
            self.marts_dir,
            self.results_dir,
            self.figures_dir,
            self.duckdb.temp_directory,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def check_disk_space(self) -> None:
        free_gb = shutil.disk_usage(self.project_root).free / (1024**3)
        if free_gb < self.duckdb.min_free_gb:
            raise OSError(
                f"Only {free_gb:.1f} GiB free; at least "
                f"{self.duckdb.min_free_gb:.1f} GiB is required for safe intermediate output."
            )

    @property
    def all_source_paths(self) -> tuple[Path, ...]:
        return tuple(path for paths in self.source_files.values() for path in paths)
