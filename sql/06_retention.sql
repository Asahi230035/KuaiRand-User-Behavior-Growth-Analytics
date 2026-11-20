-- Exact-day return among eligible first-observed-activity cohorts.

CREATE OR REPLACE TABLE result_return_overall AS
SELECT *
FROM mart_return_overall
ORDER BY offset_day;

CREATE OR REPLACE TABLE result_cohort_retention AS
SELECT *
FROM mart_cohort_retention
ORDER BY cohort_date, offset_day;

CREATE OR REPLACE TABLE result_return_any_seven_day AS
SELECT * FROM mart_cohort_any_seven_day;

CREATE OR REPLACE TABLE result_return_left_truncation_sensitivity AS
SELECT *
FROM mart_return_left_truncation_sensitivity
ORDER BY offset_day;

CREATE OR REPLACE TABLE result_return_by_exposure_quartile AS
WITH ranked AS (
    SELECT
        *,
        NTILE(4) OVER (
            ORDER BY event_count, user_id, activity_date
        ) AS event_count_quartile
    FROM mart_return_model
)
SELECT
    event_count_quartile,
    COUNT(*)::BIGINT AS user_day_count,
    MIN(event_count)::BIGINT AS minimum_event_count,
    MAX(event_count)::BIGINT AS maximum_event_count,
    AVG(event_count)::DOUBLE AS mean_event_count,
    AVG(returned_d7)::DOUBLE AS return_rate_d7,
    AVG(
        CASE
            WHEN GREATEST(
                like_count, comment_count, share_count, follow_count
            ) > 0 THEN 1
            ELSE 0
        END
    )::DOUBLE AS any_explicit_share,
    AVG(long_view_rate)::DOUBLE AS mean_long_view_rate,
    AVG(like_rate)::DOUBLE AS mean_like_rate
FROM ranked
GROUP BY event_count_quartile
ORDER BY event_count_quartile;

COPY result_return_overall
TO '{{ results_dir }}/return_overall.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY result_cohort_retention
TO '{{ results_dir }}/cohort_retention.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY result_return_any_seven_day
TO '{{ results_dir }}/return_any_seven_day.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY result_return_left_truncation_sensitivity
TO '{{ results_dir }}/return_left_truncation_sensitivity.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY result_return_by_exposure_quartile
TO '{{ results_dir }}/return_by_exposure_quartile.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);
