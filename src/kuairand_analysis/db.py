"""DuckDB connection and SQL execution helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import duckdb
import pandas as pd

from .config import AnalysisConfig


def sql_literal(value: str | Path) -> str:
    """Return a safe DuckDB string literal for a filesystem path or text value."""

    return "'" + str(value).replace("'", "''") + "'"


def connect(config: AnalysisConfig) -> duckdb.DuckDBPyConnection:
    """Create and configure a DuckDB connection."""

    connection = duckdb.connect(config.duckdb.database)
    connection.execute(f"SET threads = {int(config.duckdb.threads)}")
    connection.execute(
        f"SET memory_limit = {sql_literal(config.duckdb.memory_limit)}"
    )
    connection.execute(
        f"SET temp_directory = {sql_literal(config.duckdb.temp_directory)}"
    )
    connection.execute("SET preserve_insertion_order = false")
    connection.execute("SET enable_progress_bar = false")
    return connection


def render_sql(template: str, variables: Mapping[str, str | Path]) -> str:
    """Replace simple ``{{ name }}`` placeholders without a template dependency."""

    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{{ {key} }}}}", str(value))
    unresolved = [
        token.strip()
        for token in rendered.split("{{")[1:]
        if "}}" in token
        for token in token.split("}}", maxsplit=1)
    ]
    if unresolved:
        raise ValueError(f"Unresolved SQL template placeholders: {unresolved}")
    return rendered


def execute_sql_file(
    connection: duckdb.DuckDBPyConnection,
    path: Path,
    variables: Mapping[str, str | Path],
) -> None:
    """Execute a repository SQL file as one script."""

    template = path.read_text(encoding="utf-8")
    sql = render_sql(template, variables)
    try:
        connection.execute(sql)
    except Exception as exc:
        raise RuntimeError(f"SQL execution failed in {path.name}: {exc}") from exc


def query_df(
    connection: duckdb.DuckDBPyConnection,
    sql: str,
    parameters: list[Any] | tuple[Any, ...] | None = None,
) -> pd.DataFrame:
    """Run a bounded analytical query and return a pandas frame."""

    return connection.execute(sql, parameters or []).fetchdf()


def copy_table_to_parquet(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    destination: Path,
) -> None:
    """Write a small mart or result table to a compressed Parquet file."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    statement = (
        f"COPY (SELECT * FROM {table_name}) TO {sql_literal(destination)} "
        "(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE)"
    )
    connection.execute(statement)
