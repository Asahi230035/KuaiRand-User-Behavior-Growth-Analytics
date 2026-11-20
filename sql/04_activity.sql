-- User activity results. These are observed-sample metrics, not platform-wide growth.

CREATE OR REPLACE TABLE result_daily_activity AS
SELECT *
FROM mart_daily_activity
ORDER BY activity_date;

CREATE OR REPLACE TABLE result_activity_summary AS
WITH window_dates AS (
    SELECT * FROM observation_window
),
summary AS (
    SELECT
        COUNT(*)::INTEGER AS observed_days,
        SUM(event_count)::BIGINT AS total_events,
        AVG(dau)::DOUBLE AS mean_dau,
        MEDIAN(dau)::DOUBLE AS median_dau,
        MIN(dau)::INTEGER AS minimum_dau,
        MAX(dau)::INTEGER AS maximum_dau,
        ARG_MIN(activity_date, dau) AS minimum_dau_date,
        ARG_MAX(activity_date, dau) AS maximum_dau_date,
        AVG(event_count)::DOUBLE AS mean_daily_events,
        AVG(events_per_dau)::DOUBLE AS mean_events_per_dau,
        AVG(dau) FILTER (WHERE is_weekend)::DOUBLE AS mean_weekend_dau,
        AVG(dau) FILTER (WHERE NOT is_weekend)::DOUBLE AS mean_weekday_dau,
        SUM(first_observed_users)::BIGINT AS observed_first_appearances
    FROM mart_daily_activity
),
active_users AS (
    SELECT COUNT(*)::INTEGER AS active_users FROM mart_user_summary
),
peak_hour AS (
    SELECT ARG_MAX(activity_hour, total_events) AS peak_hour
    FROM (
        SELECT activity_hour, SUM(event_count)::BIGINT AS total_events
        FROM mart_hourly_activity
        GROUP BY activity_hour
    )
)
SELECT
    w.start_date AS observation_start,
    w.end_date AS observation_end,
    w.observed_dates,
    s.observed_days,
    a.active_users,
    s.total_events,
    s.mean_dau,
    s.median_dau,
    s.minimum_dau,
    s.minimum_dau_date,
    s.maximum_dau,
    s.maximum_dau_date,
    s.mean_daily_events,
    s.mean_events_per_dau,
    s.mean_weekend_dau,
    s.mean_weekday_dau,
    s.observed_first_appearances,
    p.peak_hour
FROM window_dates w
CROSS JOIN summary s
CROSS JOIN active_users a
CROSS JOIN peak_hour p;

CREATE OR REPLACE TABLE result_hourly_profile AS
WITH totals AS (
    SELECT SUM(event_count)::BIGINT AS total_events
    FROM mart_hourly_activity
)
SELECT
    activity_hour,
    COUNT(*)::INTEGER AS observed_date_count,
    SUM(event_count)::BIGINT AS total_events,
    AVG(event_count)::DOUBLE AS mean_events_per_observed_date,
    AVG(hourly_active_users)::DOUBLE AS mean_hourly_active_users,
    CAST(SUM(event_count) / NULLIF(MAX(t.total_events), 0) AS DOUBLE) AS event_share,
    CAST(SUM(long_view_count) / NULLIF(SUM(event_count), 0) AS DOUBLE) AS long_view_rate,
    CAST(SUM(like_count) / NULLIF(SUM(event_count), 0) AS DOUBLE) AS like_rate
FROM mart_hourly_activity
CROSS JOIN totals t
GROUP BY activity_hour
ORDER BY activity_hour;

CREATE OR REPLACE TABLE result_user_segments AS
SELECT
    active_segment,
    COUNT(*)::INTEGER AS user_count,
    CAST(COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0) AS DOUBLE) AS user_share,
    MIN(active_days)::INTEGER AS minimum_active_days,
    MAX(active_days)::INTEGER AS maximum_active_days,
    AVG(active_days)::DOUBLE AS mean_active_days,
    MIN(event_count)::BIGINT AS minimum_event_count,
    MAX(event_count)::BIGINT AS maximum_event_count,
    SUM(event_count)::BIGINT AS event_count,
    CAST(SUM(event_count) / NULLIF(SUM(SUM(event_count)) OVER (), 0) AS DOUBLE) AS event_share,
    AVG(event_count)::DOUBLE AS mean_events_per_user
FROM mart_user_summary
GROUP BY active_segment
ORDER BY active_segment;

CREATE OR REPLACE TABLE result_weekday_activity AS
SELECT *
FROM mart_weekday_activity
ORDER BY weekday_number;

COPY result_daily_activity
TO '{{ results_dir }}/daily_activity.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY result_activity_summary
TO '{{ results_dir }}/activity_summary.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY result_hourly_profile
TO '{{ results_dir }}/hourly_profile.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY result_user_segments
TO '{{ results_dir }}/user_segments.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY result_weekday_activity
TO '{{ results_dir }}/weekday_activity.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);
