-- Content analysis uses basic attributes joined to standard-log video summaries.

CREATE OR REPLACE TABLE mart_content_video_base AS
SELECT
    p.*,
    b.video_type,
    b.upload_date,
    b.upload_type,
    b.video_duration_ms,
    b.tag
FROM mart_video_performance p
LEFT JOIN prepared_video_basic b
    ON b.video_id = p.video_id
   AND b.is_valid_video;

CREATE OR REPLACE TABLE mart_content_type_metrics AS
SELECT
    COALESCE(video_type, 'MISSING_OR_UNMATCHED') AS video_type,
    COUNT(*)::BIGINT AS video_count,
    SUM(event_count)::BIGINT AS event_count,
    CAST(SUM(click_count) / NULLIF(SUM(event_count), 0) AS DOUBLE) AS exposure_weighted_click_rate,
    CAST(SUM(like_count) / NULLIF(SUM(event_count), 0) AS DOUBLE) AS exposure_weighted_like_rate,
    CAST(SUM(comment_count) / NULLIF(SUM(event_count), 0) AS DOUBLE) AS exposure_weighted_comment_rate,
    CAST(SUM(share_count) / NULLIF(SUM(event_count), 0) AS DOUBLE) AS exposure_weighted_share_rate,
    CAST(SUM(long_view_count) / NULLIF(SUM(event_count), 0) AS DOUBLE) AS exposure_weighted_long_view_rate,
    AVG(mean_watch_depth) FILTER (WHERE mean_watch_depth IS NOT NULL)::DOUBLE AS video_weighted_mean_watch_depth,
    AVG(long_view_rate)::DOUBLE AS video_weighted_mean_long_view_rate
FROM mart_content_video_base
GROUP BY COALESCE(video_type, 'MISSING_OR_UNMATCHED');

CREATE OR REPLACE TABLE mart_content_duration_metrics AS
SELECT
    CASE
        WHEN video_duration_ms IS NULL OR video_duration_ms <= 0 THEN 'unknown'
        WHEN video_duration_ms <= 15000 THEN '00-15s'
        WHEN video_duration_ms <= 30000 THEN '15-30s'
        WHEN video_duration_ms <= 60000 THEN '30-60s'
        WHEN video_duration_ms <= 120000 THEN '60-120s'
        ELSE '120s+'
    END AS duration_band,
    COUNT(*)::BIGINT AS video_count,
    SUM(event_count)::BIGINT AS event_count,
    CAST(SUM(long_view_count) / NULLIF(SUM(event_count), 0) AS DOUBLE) AS exposure_weighted_long_view_rate,
    CAST(SUM(like_count) / NULLIF(SUM(event_count), 0) AS DOUBLE) AS exposure_weighted_like_rate,
    CAST(SUM(comment_count) / NULLIF(SUM(event_count), 0) AS DOUBLE) AS exposure_weighted_comment_rate,
    AVG(mean_watch_depth) FILTER (WHERE mean_watch_depth IS NOT NULL)::DOUBLE AS video_weighted_mean_watch_depth
FROM mart_content_video_base
GROUP BY duration_band;

CREATE OR REPLACE TABLE mart_content_tag_metrics AS
WITH exploded AS (
    SELECT
        TRIM(part.value) AS tag,
        b.event_count,
        b.long_view_count,
        b.like_count,
        b.comment_count
    FROM mart_content_video_base b
    CROSS JOIN UNNEST(STRING_SPLIT(COALESCE(b.tag, ''), ',')) AS part(value)
    WHERE TRIM(part.value) <> ''
)
SELECT
    tag,
    COUNT(*)::BIGINT AS video_count,
    SUM(event_count)::BIGINT AS event_count,
    CAST(SUM(long_view_count) / NULLIF(SUM(event_count), 0) AS DOUBLE) AS exposure_weighted_long_view_rate,
    CAST(SUM(like_count) / NULLIF(SUM(event_count), 0) AS DOUBLE) AS exposure_weighted_like_rate,
    CAST(SUM(comment_count) / NULLIF(SUM(event_count), 0) AS DOUBLE) AS exposure_weighted_comment_rate
FROM exploded
GROUP BY tag
HAVING SUM(event_count) >= {{ min_tag_exposures }}
ORDER BY event_count DESC;

CREATE OR REPLACE TABLE result_content_summary AS
SELECT
    (SELECT COUNT(*) FROM prepared_video_basic WHERE is_valid_video)::BIGINT AS basic_video_rows,
    (SELECT COUNT(*) FROM prepared_video_statistics WHERE is_valid_video_statistic)::BIGINT
        AS statistic_video_rows,
    (SELECT COUNT(*) FROM mart_video_performance)::BIGINT AS videos_with_standard_exposure,
    (SELECT COUNT(*) FROM mart_content_video_base WHERE video_type IS NULL)::BIGINT
        AS exposed_videos_without_basic_attributes,
    (
        SELECT SUM(counts)
        FROM prepared_video_statistics
        WHERE is_valid_video_statistic
    )::BIGINT AS sum_statistic_counts;

CREATE OR REPLACE TABLE result_content_type AS
SELECT * FROM mart_content_type_metrics
ORDER BY event_count DESC;

CREATE OR REPLACE TABLE result_content_duration AS
SELECT * FROM mart_content_duration_metrics
ORDER BY duration_band;

CREATE OR REPLACE TABLE result_content_tags AS
SELECT * FROM mart_content_tag_metrics
ORDER BY event_count DESC;

COPY result_content_summary
TO '{{ results_dir }}/content_summary.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY result_content_type
TO '{{ results_dir }}/content_type.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY result_content_duration
TO '{{ results_dir }}/content_duration.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY result_content_tags
TO '{{ results_dir }}/content_tags.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);
