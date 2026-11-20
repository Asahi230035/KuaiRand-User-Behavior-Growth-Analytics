-- Engagement metrics use valid standard-log events as the common denominator.

CREATE OR REPLACE TABLE result_engagement_overall AS
SELECT * FROM mart_engagement_overall;

CREATE OR REPLACE TABLE result_engagement_by_tab AS
SELECT
    *,
    CAST(event_count / NULLIF(SUM(event_count) OVER (), 0) AS DOUBLE) AS event_share
FROM mart_engagement_by_tab
ORDER BY event_count DESC;

CREATE OR REPLACE TABLE result_user_segment_engagement AS
SELECT *
FROM mart_user_segment_engagement
ORDER BY active_segment;

CREATE OR REPLACE TABLE result_random_engagement AS
SELECT
    'random'::VARCHAR AS source_type,
    COUNT(*)::BIGINT AS event_count,
    COUNT(DISTINCT user_id)::INTEGER AS active_users,
    COUNT(DISTINCT video_id)::BIGINT AS distinct_videos,
    CAST(SUM(is_click) / NULLIF(COUNT(*), 0) AS DOUBLE) AS click_rate,
    CAST(SUM(is_like) / NULLIF(COUNT(*), 0) AS DOUBLE) AS like_rate,
    CAST(SUM(is_comment) / NULLIF(COUNT(*), 0) AS DOUBLE) AS comment_rate,
    CAST(SUM(is_forward) / NULLIF(COUNT(*), 0) AS DOUBLE) AS share_rate,
    CAST(SUM(is_follow) / NULLIF(COUNT(*), 0) AS DOUBLE) AS follow_rate,
    CAST(SUM(long_view) / NULLIF(COUNT(*), 0) AS DOUBLE) AS long_view_rate,
    AVG(watch_depth_ratio) FILTER (WHERE duration_ms > 0)::DOUBLE AS mean_watch_depth,
    APPROX_QUANTILE(
        watch_depth_ratio, 0.5
    ) FILTER (WHERE duration_ms > 0)::DOUBLE AS median_watch_depth
FROM prepared_random
WHERE is_valid_event;

COPY result_engagement_overall
TO '{{ results_dir }}/engagement_overall.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY result_engagement_by_tab
TO '{{ results_dir }}/engagement_by_tab.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY result_user_segment_engagement
TO '{{ results_dir }}/user_segment_engagement.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY result_random_engagement
TO '{{ results_dir }}/random_engagement.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);
