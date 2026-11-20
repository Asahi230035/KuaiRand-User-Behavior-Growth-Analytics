# Repository development and analysis rules

## Purpose

Build a reproducible KuaiRand-27K user behavior and growth analysis using DuckDB, SQL, Parquet, Python and rigorous statistics. Main research dimensions: activity, engagement, observed return, and content performance. This is a data-analysis repository, not an AI chatbot or web application.

## Source of truth

- Real input data and verified executable queries are the only sources for numeric research findings.
- Raw CSV data is read-only and never committed. Ignore `data/raw/`, `data/processed/`, `data/marts/`, DuckDB storage, local caches, and intermediate outputs.
- Separate standard recommendation logs from randomized exposure logs in every baseline metric; keep provenance. Do not equate observed sample behavior with population-wide platform behavior.
- Preserve event grain. Repeated user–video pairs are not necessarily duplicates. Validate missingness, type parsing, event dates, invalid values and table joins before cleaning.
- Treat aggregate video statistics cautiously: validate their aggregation period before using them, and never leak future information into historical prediction.

## Metrics and interpretation

- Use one documented metric definition per business quantity; give the numerator, denominator, filters, grain and observation window.
- Define D1/D7 as **observed exact-day return** among eligible cohorts. First observed activity is not registration; omit cohorts without a full future observation window.
- Define engagement and video ratios precisely; do not silently truncate watch-depth values above 1 or treat invalid denominators as zero.
- Statistical findings require appropriate samples, uncertainty, diagnostics and limitations. Observational associations are not causal effects.
- Register every material assumption in `docs/methodology.md` with executable evidence, its evidence status and the interpretations the data can support.

## Architecture

- DuckDB/SQL owns full-scale ingestion, profiling, cleaning, Parquet output, marts and metric queries.
- `src/kuairand_analysis` contains reusable Python logic: configuration, DuckDB orchestration, pipeline, statistics, reporting and visualization.
- `scripts/` contains thin CLI entry points. No all-data pandas loads, no duplicated SQL/Python definitions and no unnecessary framework.
- Paths, DuckDB memory/thread limits and temporary directories must be configurable, not machine-specific.
- Programs must be rerunnable and fail with useful diagnostics; test metric logic, window boundaries, config and pipeline behavior.

## Repository hygiene

- The release repository retains only working source, executable SQL, dependency/config files, targeted tests, three focused docs (`data_dictionary`, `metric_dictionary`, `methodology`), `data/README.md`, `README.md`, license and one `reports/final_report.md` plus its referenced figures.
- Do not commit investigation notebooks, phase reports, collaboration logs, planning files, draft figures, local CSV/Parquet/DuckDB, temp artifacts, debug screenshots or duplicate summaries.
- Never add empty scaffold files, invented results, unrun commands, misleading validation claims or unfinished document placeholders.
- The project README explains the problem, verified findings, real run commands and report location; the final report contains the substantial results, evidence and limitations. No duplicate narrative across files.
- Report operational progress in the conversation or task output rather than creating tracked work logs.

## Publishing gate

Before describing the repository as complete: run meaningful tests, verify full-data outputs and key reconciliation queries, check links/figures, and audit `git ls-files` for ignored/private/redundant content. Preserve scientifically important limitations even while removing temporary drafts and placeholders.
