-- Full-scale source inventory and quality checks. All raw files are read-only.

CREATE OR REPLACE VIEW raw_standard AS
SELECT *
FROM read_csv(
    '{{ raw_dir }}/log_standard_*.csv',
    header = true,
    union_by_name = true,
    filename = true,
    columns = {
        'user_id': 'BIGINT',
        'video_id': 'BIGINT',
        'date': 'BIGINT',
        'hourmin': 'BIGINT',
        'time_ms': 'BIGINT',
        'is_click': 'BIGINT',
        'is_like': 'BIGINT',
        'is_follow': 'BIGINT',
        'is_comment': 'BIGINT',
        'is_forward': 'BIGINT',
        'is_hate': 'BIGINT',
        'long_view': 'BIGINT',
        'play_time_ms': 'BIGINT',
        'duration_ms': 'BIGINT',
        'profile_stay_time': 'BIGINT',
        'comment_stay_time': 'BIGINT',
        'is_profile_enter': 'BIGINT',
        'is_rand': 'BIGINT',
        'tab': 'BIGINT'
    }
);

CREATE OR REPLACE VIEW raw_random AS
SELECT *
FROM read_csv(
    '{{ raw_dir }}/log_random*.csv',
    header = true,
    union_by_name = true,
    filename = true,
    columns = {
        'user_id': 'BIGINT',
        'video_id': 'BIGINT',
        'date': 'BIGINT',
        'hourmin': 'BIGINT',
        'time_ms': 'BIGINT',
        'is_click': 'BIGINT',
        'is_like': 'BIGINT',
        'is_follow': 'BIGINT',
        'is_comment': 'BIGINT',
        'is_forward': 'BIGINT',
        'is_hate': 'BIGINT',
        'long_view': 'BIGINT',
        'play_time_ms': 'BIGINT',
        'duration_ms': 'BIGINT',
        'profile_stay_time': 'BIGINT',
        'comment_stay_time': 'BIGINT',
        'is_profile_enter': 'BIGINT',
        'is_rand': 'BIGINT',
        'tab': 'BIGINT'
    }
);

CREATE OR REPLACE VIEW raw_users AS
SELECT *
FROM read_csv(
    '{{ raw_dir }}/user_features_27k.csv',
    header = true,
    union_by_name = true,
    filename = true,
    columns = {
        'user_id': 'BIGINT',
        'user_active_degree': 'VARCHAR',
        'is_lowactive_period': 'BIGINT',
        'is_live_streamer': 'BIGINT',
        'is_video_author': 'BIGINT',
        'follow_user_num': 'BIGINT',
        'follow_user_num_range': 'VARCHAR',
        'fans_user_num': 'BIGINT',
        'fans_user_num_range': 'VARCHAR',
        'friend_user_num': 'BIGINT',
        'friend_user_num_range': 'VARCHAR',
        'register_days': 'BIGINT',
        'register_days_range': 'VARCHAR',
        'onehot_feat0': 'DOUBLE',
        'onehot_feat1': 'DOUBLE',
        'onehot_feat2': 'DOUBLE',
        'onehot_feat3': 'DOUBLE',
        'onehot_feat4': 'DOUBLE',
        'onehot_feat5': 'DOUBLE',
        'onehot_feat6': 'DOUBLE',
        'onehot_feat7': 'DOUBLE',
        'onehot_feat8': 'DOUBLE',
        'onehot_feat9': 'DOUBLE',
        'onehot_feat10': 'DOUBLE',
        'onehot_feat11': 'DOUBLE',
        'onehot_feat12': 'DOUBLE',
        'onehot_feat13': 'DOUBLE',
        'onehot_feat14': 'DOUBLE',
        'onehot_feat15': 'DOUBLE',
        'onehot_feat16': 'DOUBLE',
        'onehot_feat17': 'DOUBLE'
    }
);

CREATE OR REPLACE VIEW raw_video_basic AS
SELECT *
FROM read_csv(
    '{{ raw_dir }}/video_features_basic_27k.csv',
    header = true,
    union_by_name = true,
    filename = true,
    columns = {
        'video_id': 'BIGINT',
        'author_id': 'BIGINT',
        'video_type': 'VARCHAR',
        'upload_dt': 'DATE',
        'upload_type': 'VARCHAR',
        'visible_status': 'DOUBLE',
        'video_duration': 'DOUBLE',
        'server_width': 'DOUBLE',
        'server_height': 'DOUBLE',
        'music_id': 'BIGINT',
        'music_type': 'DOUBLE',
        'tag': 'VARCHAR'
    }
);

CREATE OR REPLACE VIEW raw_video_statistics AS
SELECT *
FROM read_csv(
    '{{ raw_dir }}/video_features_statistic_27k_part*.csv',
    header = true,
    union_by_name = true,
    filename = true
);

CREATE OR REPLACE TABLE quality_file_inventory AS
SELECT
    'standard_logs' AS data_type,
    parse_filename(filename) AS source_file,
    COUNT(*)::BIGINT AS row_count
FROM raw_standard
GROUP BY filename
UNION ALL
SELECT
    'random_logs',
    parse_filename(filename),
    COUNT(*)::BIGINT
FROM raw_random
GROUP BY filename
UNION ALL
SELECT
    'user_features',
    parse_filename(filename),
    COUNT(*)::BIGINT
FROM raw_users
GROUP BY filename
UNION ALL
SELECT
    'video_basic',
    parse_filename(filename),
    COUNT(*)::BIGINT
FROM raw_video_basic
GROUP BY filename
UNION ALL
SELECT
    'video_statistics',
    parse_filename(filename),
    COUNT(*)::BIGINT
FROM raw_video_statistics
GROUP BY filename;

CREATE OR REPLACE TABLE quality_schema_summary AS
SELECT
    table_name,
    COUNT(*) FILTER (WHERE column_name <> 'filename')::INTEGER AS column_count
FROM duckdb_columns()
WHERE table_name IN (
    'raw_standard', 'raw_random', 'raw_users', 'raw_video_basic', 'raw_video_statistics'
)
GROUP BY table_name;

CREATE OR REPLACE TABLE quality_event_summary AS
WITH standard AS (
    SELECT
        'standard' AS source_type,
        COUNT(*) AS row_count,
        COUNT(*) FILTER (WHERE user_id IS NULL) AS null_user_id,
        COUNT(*) FILTER (WHERE video_id IS NULL) AS null_video_id,
        COUNT(*) FILTER (WHERE date IS NULL) AS null_event_date,
        COUNT(*) FILTER (WHERE time_ms IS NULL OR time_ms <= 0) AS invalid_timestamp,
        COUNT(*) FILTER (
            WHERE TRY_STRPTIME(CAST(date AS VARCHAR), '%Y%m%d') IS NULL
        ) AS invalid_date_format,
        COUNT(*) FILTER (
            WHERE TRY_STRPTIME(CAST(date AS VARCHAR), '%Y%m%d')::DATE
                <> CAST(epoch_ms(time_ms) + INTERVAL 8 HOUR AS DATE)
        ) AS date_timestamp_mismatch,
        COUNT(*) FILTER (
            WHERE COALESCE(is_click NOT IN (0, 1), TRUE)
               OR COALESCE(is_like NOT IN (0, 1), TRUE)
               OR COALESCE(is_follow NOT IN (0, 1), TRUE)
               OR COALESCE(is_comment NOT IN (0, 1), TRUE)
               OR COALESCE(is_forward NOT IN (0, 1), TRUE)
               OR COALESCE(is_hate NOT IN (0, 1), TRUE)
               OR COALESCE(long_view NOT IN (0, 1), TRUE)
               OR COALESCE(is_profile_enter NOT IN (0, 1), TRUE)
               OR COALESCE(is_rand NOT IN (0, 1), TRUE)
        ) AS invalid_binary_rows,
        COUNT(*) FILTER (WHERE COALESCE(play_time_ms < 0, TRUE)) AS invalid_play_time,
        COUNT(*) FILTER (WHERE COALESCE(duration_ms < 0, TRUE)) AS negative_duration,
        COUNT(*) FILTER (WHERE duration_ms = 0) AS zero_duration,
        COUNT(*) FILTER (
            WHERE play_time_ms > duration_ms AND duration_ms > 0
        ) AS play_time_above_duration,
        COUNT(*) FILTER (
            WHERE COALESCE(profile_stay_time < 0, TRUE)
               OR COALESCE(comment_stay_time < 0, TRUE)
        ) AS negative_stay_time,
        COUNT(*) FILTER (WHERE tab NOT BETWEEN 0 AND 14) AS tab_outside_documented_range,
        COUNT(*) FILTER (
            WHERE hourmin NOT BETWEEN 0 AND 2359 OR hourmin % 100 NOT BETWEEN 0 AND 59
        ) AS invalid_hourmin,
        COUNT(*) FILTER (WHERE is_rand = 1) AS random_flag_rows,
        COUNT(*) FILTER (
            WHERE user_id IS NOT NULL
              AND video_id IS NOT NULL
              AND TRY_STRPTIME(CAST(date AS VARCHAR), '%Y%m%d') IS NOT NULL
              AND time_ms > 0
              AND tab BETWEEN 0 AND 14
              AND hourmin BETWEEN 0 AND 2359
              AND hourmin % 100 BETWEEN 0 AND 59
              AND COALESCE(is_click NOT IN (0, 1), TRUE) = FALSE
              AND COALESCE(is_like NOT IN (0, 1), TRUE) = FALSE
              AND COALESCE(is_follow NOT IN (0, 1), TRUE) = FALSE
              AND COALESCE(is_comment NOT IN (0, 1), TRUE) = FALSE
              AND COALESCE(is_forward NOT IN (0, 1), TRUE) = FALSE
              AND COALESCE(is_hate NOT IN (0, 1), TRUE) = FALSE
              AND COALESCE(long_view NOT IN (0, 1), TRUE) = FALSE
              AND COALESCE(is_profile_enter NOT IN (0, 1), TRUE) = FALSE
              AND COALESCE(is_rand NOT IN (0, 1), TRUE) = FALSE
              AND is_rand = 0
              AND COALESCE(play_time_ms < 0, TRUE) = FALSE
              AND COALESCE(duration_ms < 0, TRUE) = FALSE
              AND COALESCE(profile_stay_time < 0, TRUE) = FALSE
              AND COALESCE(comment_stay_time < 0, TRUE) = FALSE
        ) AS valid_event_rows
    FROM raw_standard
),
random AS (
    SELECT
        'random' AS source_type,
        COUNT(*) AS row_count,
        COUNT(*) FILTER (WHERE user_id IS NULL) AS null_user_id,
        COUNT(*) FILTER (WHERE video_id IS NULL) AS null_video_id,
        COUNT(*) FILTER (WHERE date IS NULL) AS null_event_date,
        COUNT(*) FILTER (WHERE time_ms IS NULL OR time_ms <= 0) AS invalid_timestamp,
        COUNT(*) FILTER (
            WHERE TRY_STRPTIME(CAST(date AS VARCHAR), '%Y%m%d') IS NULL
        ) AS invalid_date_format,
        COUNT(*) FILTER (
            WHERE TRY_STRPTIME(CAST(date AS VARCHAR), '%Y%m%d')::DATE
                <> CAST(epoch_ms(time_ms) + INTERVAL 8 HOUR AS DATE)
        ) AS date_timestamp_mismatch,
        COUNT(*) FILTER (
            WHERE COALESCE(is_click NOT IN (0, 1), TRUE)
               OR COALESCE(is_like NOT IN (0, 1), TRUE)
               OR COALESCE(is_follow NOT IN (0, 1), TRUE)
               OR COALESCE(is_comment NOT IN (0, 1), TRUE)
               OR COALESCE(is_forward NOT IN (0, 1), TRUE)
               OR COALESCE(is_hate NOT IN (0, 1), TRUE)
               OR COALESCE(long_view NOT IN (0, 1), TRUE)
               OR COALESCE(is_profile_enter NOT IN (0, 1), TRUE)
               OR COALESCE(is_rand NOT IN (0, 1), TRUE)
        ) AS invalid_binary_rows,
        COUNT(*) FILTER (WHERE COALESCE(play_time_ms < 0, TRUE)) AS invalid_play_time,
        COUNT(*) FILTER (WHERE COALESCE(duration_ms < 0, TRUE)) AS negative_duration,
        COUNT(*) FILTER (WHERE duration_ms = 0) AS zero_duration,
        COUNT(*) FILTER (
            WHERE play_time_ms > duration_ms AND duration_ms > 0
        ) AS play_time_above_duration,
        COUNT(*) FILTER (
            WHERE COALESCE(profile_stay_time < 0, TRUE)
               OR COALESCE(comment_stay_time < 0, TRUE)
        ) AS negative_stay_time,
        COUNT(*) FILTER (WHERE tab NOT BETWEEN 0 AND 14) AS tab_outside_documented_range,
        COUNT(*) FILTER (
            WHERE hourmin NOT BETWEEN 0 AND 2359 OR hourmin % 100 NOT BETWEEN 0 AND 59
        ) AS invalid_hourmin,
        COUNT(*) FILTER (WHERE is_rand = 1) AS random_flag_rows,
        COUNT(*) FILTER (
            WHERE user_id IS NOT NULL
              AND video_id IS NOT NULL
              AND TRY_STRPTIME(CAST(date AS VARCHAR), '%Y%m%d') IS NOT NULL
              AND time_ms > 0
              AND tab BETWEEN 0 AND 14
              AND hourmin BETWEEN 0 AND 2359
              AND hourmin % 100 BETWEEN 0 AND 59
              AND COALESCE(is_click NOT IN (0, 1), TRUE) = FALSE
              AND COALESCE(is_like NOT IN (0, 1), TRUE) = FALSE
              AND COALESCE(is_follow NOT IN (0, 1), TRUE) = FALSE
              AND COALESCE(is_comment NOT IN (0, 1), TRUE) = FALSE
              AND COALESCE(is_forward NOT IN (0, 1), TRUE) = FALSE
              AND COALESCE(is_hate NOT IN (0, 1), TRUE) = FALSE
              AND COALESCE(long_view NOT IN (0, 1), TRUE) = FALSE
              AND COALESCE(is_profile_enter NOT IN (0, 1), TRUE) = FALSE
              AND COALESCE(is_rand NOT IN (0, 1), TRUE) = FALSE
              AND is_rand = 1
              AND COALESCE(play_time_ms < 0, TRUE) = FALSE
              AND COALESCE(duration_ms < 0, TRUE) = FALSE
              AND COALESCE(profile_stay_time < 0, TRUE) = FALSE
              AND COALESCE(comment_stay_time < 0, TRUE) = FALSE
        ) AS valid_event_rows
    FROM raw_random
)
SELECT * FROM standard
UNION ALL
SELECT * FROM random;

CREATE OR REPLACE TABLE quality_dimension_summary AS
SELECT
    'users' AS table_name,
    COUNT(*) AS row_count,
    COUNT(DISTINCT user_id) AS distinct_primary_key,
    COUNT(*) FILTER (WHERE user_id IS NULL) AS null_primary_key,
    COUNT(*) FILTER (WHERE user_active_degree IS NULL) AS null_active_degree,
    COUNT(*) FILTER (WHERE register_days IS NULL) AS null_register_days,
    COUNT(*) FILTER (
        WHERE onehot_feat0 IS NULL OR onehot_feat1 IS NULL OR onehot_feat2 IS NULL
           OR onehot_feat3 IS NULL OR onehot_feat4 IS NULL OR onehot_feat5 IS NULL
           OR onehot_feat6 IS NULL OR onehot_feat7 IS NULL OR onehot_feat8 IS NULL
           OR onehot_feat9 IS NULL OR onehot_feat10 IS NULL OR onehot_feat11 IS NULL
           OR onehot_feat12 IS NULL OR onehot_feat13 IS NULL OR onehot_feat14 IS NULL
           OR onehot_feat15 IS NULL OR onehot_feat16 IS NULL OR onehot_feat17 IS NULL
    ) AS rows_with_any_onehot_missing
FROM raw_users
UNION ALL
SELECT
    'video_basic',
    COUNT(*),
    COUNT(DISTINCT video_id),
    COUNT(*) FILTER (WHERE video_id IS NULL),
    COUNT(*) FILTER (WHERE video_type IS NULL),
    COUNT(*) FILTER (
        WHERE video_duration IS NULL OR server_width IS NULL OR server_height IS NULL
           OR music_id IS NULL OR music_type IS NULL OR tag IS NULL
    ),
    NULL
FROM raw_video_basic;

CREATE OR REPLACE TABLE quality_duplicate_key_summary AS
WITH standard_keys AS (
    SELECT user_id, video_id, time_ms, COUNT(*) AS occurrences
    FROM raw_standard
    GROUP BY user_id, video_id, time_ms
    HAVING COUNT(*) > 1
),
random_keys AS (
    SELECT user_id, video_id, time_ms, COUNT(*) AS occurrences
    FROM raw_random
    GROUP BY user_id, video_id, time_ms
    HAVING COUNT(*) > 1
)
SELECT
    'standard' AS source_type,
    COUNT(*) AS duplicate_key_groups,
    COALESCE(SUM(occurrences), 0)::BIGINT AS rows_in_duplicate_key_groups
FROM standard_keys
UNION ALL
SELECT
    'random',
    COUNT(*),
    COALESCE(SUM(occurrences), 0)::BIGINT
FROM random_keys;

CREATE OR REPLACE TABLE quality_join_coverage AS
WITH standard_users AS (
    SELECT DISTINCT user_id FROM raw_standard WHERE user_id IS NOT NULL
),
random_users AS (
    SELECT DISTINCT user_id FROM raw_random WHERE user_id IS NOT NULL
),
standard_videos AS (
    SELECT DISTINCT video_id FROM raw_standard WHERE video_id IS NOT NULL
),
random_videos AS (
    SELECT DISTINCT video_id FROM raw_random WHERE video_id IS NOT NULL
),
video_stat_ids AS (
    SELECT DISTINCT video_id
    FROM raw_video_statistics
    WHERE video_id IS NOT NULL
)
SELECT
    'standard_users_to_user_features' AS coverage,
    COUNT(*) AS denominator_distinct_ids,
    COUNT(u.user_id) AS matched_distinct_ids
FROM standard_users s
LEFT JOIN raw_users u USING (user_id)
UNION ALL
SELECT
    'random_users_to_user_features',
    COUNT(*),
    COUNT(u.user_id)
FROM random_users r
LEFT JOIN raw_users u USING (user_id)
UNION ALL
SELECT
    'standard_videos_to_video_basic',
    COUNT(*),
    COUNT(b.video_id)
FROM standard_videos s
LEFT JOIN raw_video_basic b USING (video_id)
UNION ALL
SELECT
    'random_videos_to_video_basic',
    COUNT(*),
    COUNT(b.video_id)
FROM random_videos r
LEFT JOIN raw_video_basic b USING (video_id)
UNION ALL
SELECT
    'standard_videos_to_video_statistics',
    COUNT(*),
    COUNT(s.video_id)
FROM standard_videos v
LEFT JOIN video_stat_ids s USING (video_id)
UNION ALL
SELECT
    'random_videos_to_video_statistics',
    COUNT(*),
    COUNT(s.video_id)
FROM random_videos v
LEFT JOIN video_stat_ids s USING (video_id);

CREATE OR REPLACE TABLE quality_video_statistics_grain AS
SELECT
    parse_filename(filename) AS source_file,
    COUNT(*) AS row_count,
    COUNT(DISTINCT video_id) AS distinct_video_id,
    MIN(counts) AS minimum_counts,
    MAX(counts) AS maximum_counts
FROM raw_video_statistics
GROUP BY filename;

COPY quality_file_inventory
TO '{{ results_dir }}/quality_file_inventory.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY quality_event_summary
TO '{{ results_dir }}/quality_event_summary.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY quality_join_coverage
TO '{{ results_dir }}/quality_join_coverage.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY quality_duplicate_key_summary
TO '{{ results_dir }}/quality_duplicate_key_summary.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);
