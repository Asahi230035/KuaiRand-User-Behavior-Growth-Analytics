-- Reconciliation and source-isolation checks. Any failed check aborts the build.

-- Date-convention sensitivity:
-- compare the published date/hour fields with dates derived from time_ms in UTC+8.
CREATE OR REPLACE TABLE date_convention_alt_user_day AS
SELECT
    user_id,
    CAST(event_ts_local AS DATE) AS activity_date,
    COUNT(*)::BIGINT AS event_count
FROM prepared_standard
WHERE is_valid_event
GROUP BY user_id, CAST(event_ts_local AS DATE);

CREATE OR REPLACE TABLE date_convention_alt_window AS
SELECT MIN(activity_date) AS start_date, MAX(activity_date) AS end_date
FROM date_convention_alt_user_day;

CREATE OR REPLACE TABLE date_convention_alt_first_seen AS
SELECT user_id, MIN(activity_date) AS first_seen_date
FROM date_convention_alt_user_day
GROUP BY user_id;

CREATE OR REPLACE TABLE date_convention_alt_cohort_return AS
WITH offsets AS (
    SELECT UNNEST([1, 7])::INTEGER AS offset_day
),
user_offsets AS (
    SELECT
        f.user_id,
        f.first_seen_date,
        o.offset_day,
        CAST(f.first_seen_date + o.offset_day AS DATE) AS target_date,
        w.start_date,
        w.end_date
    FROM date_convention_alt_first_seen f
    CROSS JOIN offsets o
    CROSS JOIN date_convention_alt_window w
)
SELECT
    u.user_id,
    u.first_seen_date,
    u.offset_day,
    (u.target_date <= u.end_date) AS eligible,
    (d.user_id IS NOT NULL) AS returned_exactly,
    u.first_seen_date > u.start_date AS after_first_cohort
FROM user_offsets u
LEFT JOIN date_convention_alt_user_day d
    ON d.user_id = u.user_id
   AND d.activity_date = u.target_date;

CREATE OR REPLACE TABLE date_convention_alt_summary AS
SELECT
    offset_day,
    COUNT(*) FILTER (WHERE eligible)::BIGINT AS eligible_users,
    COUNT(*) FILTER (
        WHERE eligible AND returned_exactly
    )::BIGINT AS returned_users,
    CAST(
        COUNT(*) FILTER (WHERE eligible AND returned_exactly)
        / NULLIF(COUNT(*) FILTER (WHERE eligible), 0)
        AS DOUBLE
    ) AS return_rate,
    COUNT(*) FILTER (
        WHERE eligible AND after_first_cohort
    )::BIGINT AS eligible_users_excluding_first_cohort,
    COUNT(*) FILTER (
        WHERE eligible AND after_first_cohort AND returned_exactly
    )::BIGINT AS returned_users_excluding_first_cohort,
    CAST(
        COUNT(*) FILTER (
            WHERE eligible AND after_first_cohort AND returned_exactly
        )
        / NULLIF(
            COUNT(*) FILTER (WHERE eligible AND after_first_cohort),
            0
        )
        AS DOUBLE
    ) AS return_rate_excluding_first_cohort
FROM date_convention_alt_cohort_return
GROUP BY offset_day;

CREATE OR REPLACE TABLE result_date_convention_sensitivity AS
WITH source_dates AS (
    SELECT
        o.offset_day,
        o.eligible_users,
        o.returned_users,
        o.return_rate,
        s.eligible_users_excluding_first_cohort,
        s.returned_users_excluding_first_cohort,
        s.return_rate_excluding_first_cohort
    FROM mart_return_overall o
    JOIN mart_return_left_truncation_sensitivity s USING (offset_day)
    WHERE o.offset_day IN (1, 7)
)
SELECT
    'source_date'::VARCHAR AS convention,
    *
FROM source_dates
UNION ALL
SELECT
    'timestamp_utc8'::VARCHAR AS convention,
    *
FROM date_convention_alt_summary
ORDER BY convention, offset_day;

CREATE OR REPLACE TABLE validation_results AS
WITH prepared_counts AS (
    SELECT 'standard_logs' AS data_type, COUNT(*)::BIGINT AS row_count
    FROM prepared_standard
    UNION ALL
    SELECT 'random_logs', COUNT(*)
    FROM prepared_random
    UNION ALL
    SELECT 'user_features', COUNT(*)
    FROM prepared_users
    UNION ALL
    SELECT 'video_basic', COUNT(*)
    FROM prepared_video_basic
    UNION ALL
    SELECT 'video_statistics', COUNT(*)
    FROM prepared_video_statistics
),
raw_counts AS (
    SELECT data_type, SUM(row_count)::BIGINT AS row_count
    FROM quality_file_inventory
    GROUP BY data_type
),
checks AS (
    SELECT
        'ten_source_files_present' AS check_name,
        (SELECT COUNT(*) = 10 FROM quality_file_inventory) AS passed,
        (SELECT COUNT(*) FROM quality_file_inventory)::VARCHAR AS observed,
        '10' AS expected
    UNION ALL
    SELECT
        'date_convention_sensitivity_complete',
        (
            SELECT COUNT(*) = 4
            AND COUNT(DISTINCT convention) = 2
            AND COUNT(DISTINCT offset_day) = 2
            FROM result_date_convention_sensitivity
        ),
        (
            SELECT COUNT(*)::VARCHAR
            FROM result_date_convention_sensitivity
        ),
        '4'
    UNION ALL
    SELECT
        'schema_standard_19_columns',
        (SELECT column_count = 19 FROM quality_schema_summary WHERE table_name = 'raw_standard'),
        (SELECT CAST(column_count AS VARCHAR) FROM quality_schema_summary WHERE table_name = 'raw_standard'),
        '19'
    UNION ALL
    SELECT
        'schema_random_19_columns',
        (SELECT column_count = 19 FROM quality_schema_summary WHERE table_name = 'raw_random'),
        (SELECT CAST(column_count AS VARCHAR) FROM quality_schema_summary WHERE table_name = 'raw_random'),
        '19'
    UNION ALL
    SELECT
        'schema_users_31_columns',
        (SELECT column_count = 31 FROM quality_schema_summary WHERE table_name = 'raw_users'),
        (SELECT CAST(column_count AS VARCHAR) FROM quality_schema_summary WHERE table_name = 'raw_users'),
        '31'
    UNION ALL
    SELECT
        'schema_video_basic_12_columns',
        (SELECT column_count = 12 FROM quality_schema_summary WHERE table_name = 'raw_video_basic'),
        (SELECT CAST(column_count AS VARCHAR) FROM quality_schema_summary WHERE table_name = 'raw_video_basic'),
        '12'
    UNION ALL
    SELECT
        'schema_video_statistics_52_columns',
        (SELECT column_count = 52 FROM quality_schema_summary WHERE table_name = 'raw_video_statistics'),
        (SELECT CAST(column_count AS VARCHAR) FROM quality_schema_summary WHERE table_name = 'raw_video_statistics'),
        '52'
    UNION ALL
    SELECT
        'prepared_row_count_matches_raw_' || r.data_type,
        p.row_count = r.row_count,
        p.row_count::VARCHAR,
        r.row_count::VARCHAR
    FROM prepared_counts p
    JOIN raw_counts r USING (data_type)
    UNION ALL
    SELECT
        'standard_source_isolation',
        COUNT(*) FILTER (WHERE source_type <> 'standard' OR is_rand <> 0) = 0,
        COUNT(*) FILTER (WHERE source_type <> 'standard' OR is_rand <> 0)::VARCHAR,
        '0'
    FROM prepared_standard
    UNION ALL
    SELECT
        'random_source_isolation',
        COUNT(*) FILTER (WHERE source_type <> 'random' OR is_rand <> 1) = 0,
        COUNT(*) FILTER (WHERE source_type <> 'random' OR is_rand <> 1)::VARCHAR,
        '0'
    FROM prepared_random
    UNION ALL
    SELECT
        'valid_events_reconcile_to_user_day',
        (
            SELECT COUNT(*) FROM prepared_standard WHERE is_valid_event
        ) = (
            SELECT SUM(event_count) FROM mart_user_day
        ),
        (SELECT SUM(event_count) FROM mart_user_day)::VARCHAR,
        (SELECT COUNT(*) FROM prepared_standard WHERE is_valid_event)::VARCHAR
    UNION ALL
    SELECT
        'quality_valid_standard_matches_prepared',
        (
            SELECT valid_event_rows
            FROM quality_event_summary
            WHERE source_type = 'standard'
        ) = (
            SELECT COUNT(*) FROM prepared_standard WHERE is_valid_event
        ),
        (SELECT COUNT(*) FROM prepared_standard WHERE is_valid_event)::VARCHAR,
        (
            SELECT valid_event_rows::VARCHAR
            FROM quality_event_summary
            WHERE source_type = 'standard'
        )
    UNION ALL
    SELECT
        'quality_valid_random_matches_prepared',
        (
            SELECT valid_event_rows
            FROM quality_event_summary
            WHERE source_type = 'random'
        ) = (
            SELECT COUNT(*) FROM prepared_random WHERE is_valid_event
        ),
        (SELECT COUNT(*) FROM prepared_random WHERE is_valid_event)::VARCHAR,
        (
            SELECT valid_event_rows::VARCHAR
            FROM quality_event_summary
            WHERE source_type = 'random'
        )
    UNION ALL
    SELECT
        'user_day_reconciles_to_user_summary',
        (SELECT COUNT(*) FROM mart_user_day) = (SELECT SUM(active_days) FROM mart_user_summary),
        (SELECT SUM(active_days) FROM mart_user_summary)::VARCHAR,
        (SELECT COUNT(*) FROM mart_user_day)::VARCHAR
    UNION ALL
    SELECT
        'user_features_user_id_unique',
        (SELECT row_count = distinct_primary_key FROM quality_dimension_summary WHERE table_name = 'users'),
        (SELECT distinct_primary_key::VARCHAR FROM quality_dimension_summary WHERE table_name = 'users'),
        (SELECT row_count::VARCHAR FROM quality_dimension_summary WHERE table_name = 'users')
    UNION ALL
    SELECT
        'video_basic_video_id_unique',
        (SELECT row_count = distinct_primary_key FROM quality_dimension_summary WHERE table_name = 'video_basic'),
        (SELECT distinct_primary_key::VARCHAR FROM quality_dimension_summary WHERE table_name = 'video_basic'),
        (SELECT row_count::VARCHAR FROM quality_dimension_summary WHERE table_name = 'video_basic')
    UNION ALL
    SELECT
        'video_statistics_video_id_unique',
        (SELECT COUNT(*) = COUNT(DISTINCT video_id) FROM prepared_video_statistics),
        (SELECT COUNT(DISTINCT video_id)::VARCHAR FROM prepared_video_statistics),
        (SELECT COUNT(*)::VARCHAR FROM prepared_video_statistics)
    UNION ALL
    SELECT
        'cohort_return_counts_valid',
        COUNT(*) FILTER (WHERE returned_exactly AND NOT eligible) = 0,
        COUNT(*) FILTER (WHERE returned_exactly AND NOT eligible)::VARCHAR,
        '0'
    FROM mart_cohort_return
    UNION ALL
    SELECT
        'cohort_return_numerator_bounded',
        COUNT(*) FILTER (
            WHERE returned_users > eligible_users
        ) = 0,
        COUNT(*) FILTER (WHERE returned_users > eligible_users)::VARCHAR,
        '0'
    FROM mart_return_overall
    UNION ALL
    SELECT
        'return_model_has_no_missing_outcomes',
        COUNT(*) FILTER (
            WHERE returned_d1 IS NULL OR returned_d7 IS NULL OR returned_any_7d IS NULL
        ) = 0,
        COUNT(*) FILTER (
            WHERE returned_d1 IS NULL OR returned_d7 IS NULL OR returned_any_7d IS NULL
        )::VARCHAR,
        '0'
    FROM mart_return_model
    UNION ALL
    SELECT
        'return_exposure_quartiles_complete',
        (
            SELECT COUNT(*) = 4
            AND SUM(user_day_count) = (SELECT COUNT(*) FROM mart_return_model)
            FROM result_return_by_exposure_quartile
        ),
        (SELECT COUNT(*)::VARCHAR FROM result_return_by_exposure_quartile),
        '4'
)
SELECT
    check_name,
    passed,
    observed,
    expected,
    CASE WHEN passed THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks;

COPY validation_results
TO '{{ results_dir }}/validation_results.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY result_date_convention_sensitivity
TO '{{ results_dir }}/date_convention_sensitivity.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

SELECT CASE
    WHEN (SELECT COUNT(*) FROM validation_results WHERE NOT passed) > 0
    THEN error('One or more full-data validation checks failed; see validation_results.')
    ELSE NULL
END;
