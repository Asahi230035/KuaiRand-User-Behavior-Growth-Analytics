"""End-to-end DuckDB pipeline orchestration."""

from __future__ import annotations

import logging
from pathlib import Path
from time import perf_counter

from .config import AnalysisConfig
from .db import connect, execute_sql_file
from .statistics import fit_return_models


LOGGER = logging.getLogger(__name__)

SQL_SEQUENCE = (
    "01_quality.sql",
    "02_prepare.sql",
    "03_marts.sql",
    "04_activity.sql",
    "05_engagement.sql",
    "06_retention.sql",
    "07_content.sql",
    "08_validation.sql",
)


class AnalysisPipeline:
    """Run all SQL stages and statistical validation with deterministic overwrites."""

    def __init__(
        self,
        config: AnalysisConfig,
        run_statistics: bool = True,
        sql_dir: str | Path | None = None,
    ):
        self.config = config
        self.run_statistics = run_statistics
        self.sql_dir = (
            Path(sql_dir).resolve() if sql_dir is not None else config.project_root / "sql"
        )

    @property
    def template_variables(self) -> dict[str, str | int | Path]:
        return {
            "raw_dir": self.config.raw_dir,
            "processed_dir": self.config.processed_dir,
            "marts_dir": self.config.marts_dir,
            "results_dir": self.config.results_dir,
            "figures_dir": self.config.figures_dir,
            "min_tag_exposures": self.config.analysis.min_tag_exposures,
        }

    def run(self) -> dict[str, object]:
        started = perf_counter()
        connection = connect(self.config)
        completed: list[str] = []
        try:
            for filename in SQL_SEQUENCE:
                stage_started = perf_counter()
                LOGGER.info("Running %s", filename)
                if filename == "08_validation.sql" and self.run_statistics:
                    LOGGER.info("Fitting clustered return models")
                    fit_return_models(connection, self.config)
                execute_sql_file(
                    connection,
                    self.sql_dir / filename,
                    self.template_variables,
                )
                completed.append(filename)
                LOGGER.info(
                    "Completed %s in %.1f seconds", filename, perf_counter() - stage_started
                )

            elapsed = perf_counter() - started
            LOGGER.info("Pipeline completed in %.1f seconds", elapsed)
            return {
                "completed_stages": completed,
                "elapsed_seconds": elapsed,
                "statistics_run": self.run_statistics,
            }
        finally:
            connection.close()
