-- Shared facts, dimensions, metric marts, and leak-free return samples.

CREATE OR REPLACE VIEW prepared_standard AS
SELECT * FROM read_parquet('{{ processed_dir }}/standard_events.parquet');

CREATE OR REPLACE VIEW prepared_random AS
SELECT * FROM read_parquet('{{ processed_dir }}/random_events.parquet');

CREATE OR REPLACE VIEW prepared_users AS
SELECT * FROM read_parquet('{{ processed_dir }}/user_features.parquet');

CREATE OR REPLACE VIEW prepared_video_basic AS
SELECT * FROM read_parquet('{{ processed_dir }}/video_basic.parquet');

CREATE OR REPLACE VIEW prepared_video_statistics AS
SELECT * FROM read_parquet('{{ processed_dir }}/video_statistics.parquet');

CREATE OR REPLACE TABLE observation_window AS
SELECT
    MIN(event_date) AS start_date,
    MAX(event_date) AS end_date,
    COUNT(DISTINCT event_date) AS observed_dates
FROM prepared_standard
WHERE is_valid_event;

CREATE OR REPLACE TABLE mart_user_day AS
SELECT
    event_date AS activity_date,
    user_id,
    COUNT(*)::BIGINT AS event_count,
    BIT_COUNT(BIT_OR(CAST(1 AS BIGINT) << tab))::INTEGER AS active_tab_count,
    SUM(is_click)::BIGINT AS click_count,
    SUM(is_like)::BIGINT AS like_count,
    SUM(is_comment)::BIGINT AS comment_count,
    SUM(is_forward)::BIGINT AS share_count,
    SUM(is_follow)::BIGINT AS follow_count,
    SUM(is_hate)::BIGINT AS hate_count,
    SUM(long_view)::BIGINT AS long_view_count,
    SUM(is_profile_enter)::BIGINT AS profile_enter_count,
    SUM(play_time_ms)::BIGINT AS play_time_sum_ms,
    SUM(profile_stay_time)::BIGINT AS profile_stay_time_sum_ms,
    SUM(comment_stay_time)::BIGINT AS comment_stay_time_sum_ms,
    CAST(SUM(is_click) / NULLIF(COUNT(*), 0) AS DOUBLE) AS click_rate,
    CAST(SUM(is_like) / NULLIF(COUNT(*), 0) AS DOUBLE) AS like_rate,
    CAST(SUM(is_comment) / NULLIF(COUNT(*), 0) AS DOUBLE) AS comment_rate,
    CAST(SUM(is_forward) / NULLIF(COUNT(*), 0) AS DOUBLE) AS share_rate,
    CAST(SUM(is_follow) / NULLIF(COUNT(*), 0) AS DOUBLE) AS follow_rate,
    CAST(SUM(is_hate) / NULLIF(COUNT(*), 0) AS DOUBLE) AS hate_rate,
    CAST(SUM(long_view) / NULLIF(COUNT(*), 0) AS DOUBLE) AS long_view_rate,
    CAST(SUM(is_profile_enter) / NULLIF(COUNT(*), 0) AS DOUBLE) AS profile_enter_rate
FROM prepared_standard
WHERE is_valid_event
GROUP BY event_date, user_id;

CREATE OR REPLACE TABLE mart_user_summary_base AS
SELECT
    user_id,
    MIN(activity_date) AS first_seen_date,
    MAX(activity_date) AS last_seen_date,
    COUNT(*)::INTEGER AS active_days,
    SUM(event_count)::BIGINT AS event_count,
    SUM(click_count)::BIGINT AS click_count,
    SUM(like_count)::BIGINT AS like_count,
    SUM(comment_count)::BIGINT AS comment_count,
    SUM(share_count)::BIGINT AS share_count,
    SUM(follow_count)::BIGINT AS follow_count,
    SUM(hate_count)::BIGINT AS hate_count,
    SUM(long_view_count)::BIGINT AS long_view_count,
    SUM(profile_enter_count)::BIGINT AS profile_enter_count,
    SUM(play_time_sum_ms)::BIGINT AS play_time_sum_ms
FROM mart_user_day
GROUP BY user_id;

CREATE OR REPLACE TABLE mart_user_summary AS
WITH ranked AS (
    SELECT
        *,
        NTILE(4) OVER (ORDER BY event_count, active_days, user_id) AS active_quartile_number
    FROM mart_user_summary_base
)
SELECT
    *,
    'Q' || CAST(active_quartile_number AS VARCHAR) AS active_segment,
    CAST(click_count / NULLIF(event_count, 0) AS DOUBLE) AS click_rate,
    CAST(like_count / NULLIF(event_count, 0) AS DOUBLE) AS like_rate,
    CAST(comment_count / NULLIF(event_count, 0) AS DOUBLE) AS comment_rate,
    CAST(share_count / NULLIF(event_count, 0) AS DOUBLE) AS share_rate,
    CAST(follow_count / NULLIF(event_count, 0) AS DOUBLE) AS follow_rate,
    CAST(hate_count / NULLIF(event_count, 0) AS DOUBLE) AS hate_rate,
    CAST(long_view_count / NULLIF(event_count, 0) AS DOUBLE) AS long_view_rate,
    CAST(profile_enter_count / NULLIF(event_count, 0) AS DOUBLE) AS profile_enter_rate
FROM ranked;

CREATE OR REPLACE TABLE mart_daily_activity AS
WITH first_days AS (
    SELECT first_seen_date, COUNT(*)::INTEGER AS first_observed_users
    FROM mart_user_summary
    GROUP BY first_seen_date
),
daily AS (
    SELECT
        activity_date,
        COUNT(DISTINCT user_id)::INTEGER AS dau,
        SUM(event_count)::BIGINT AS event_count,
        SUM(click_count)::BIGINT AS click_count,
        SUM(like_count)::BIGINT AS like_count,
        SUM(comment_count)::BIGINT AS comment_count,
        SUM(share_count)::BIGINT AS share_count,
        SUM(follow_count)::BIGINT AS follow_count,
        SUM(long_view_count)::BIGINT AS long_view_count
    FROM mart_user_day
    GROUP BY activity_date
)
SELECT
    d.*,
    CAST(d.event_count / NULLIF(d.dau, 0) AS DOUBLE) AS events_per_dau,
    CAST(d.click_count / NULLIF(d.event_count, 0) AS DOUBLE) AS click_rate,
    CAST(d.like_count / NULLIF(d.event_count, 0) AS DOUBLE) AS like_rate,
    CAST(d.comment_count / NULLIF(d.event_count, 0) AS DOUBLE) AS comment_rate,
    CAST(d.share_count / NULLIF(d.event_count, 0) AS DOUBLE) AS share_rate,
    CAST(d.follow_count / NULLIF(d.event_count, 0) AS DOUBLE) AS follow_rate,
    CAST(d.long_view_count / NULLIF(d.event_count, 0) AS DOUBLE) AS long_view_rate,
    COALESCE(f.first_observed_users, 0)::INTEGER AS first_observed_users,
    DAYOFWEEK(d.activity_date) IN (0, 6) AS is_weekend
FROM daily d
LEFT JOIN first_days f
    ON f.first_seen_date = d.activity_date;

CREATE OR REPLACE TABLE mart_hourly_activity AS
SELECT
    event_date,
    source_hour AS activity_hour,
    COUNT(DISTINCT user_id)::INTEGER AS hourly_active_users,
    COUNT(*)::BIGINT AS event_count,
    COUNT(*) FILTER (WHERE is_like = 1)::BIGINT AS like_count,
    COUNT(*) FILTER (WHERE long_view = 1)::BIGINT AS long_view_count
FROM prepared_standard
WHERE is_valid_event
GROUP BY event_date, activity_hour;

CREATE OR REPLACE TABLE mart_engagement_overall AS
SELECT
    COUNT(*)::BIGINT AS event_count,
    COUNT(DISTINCT user_id)::INTEGER AS active_users,
    COUNT(DISTINCT video_id)::BIGINT AS distinct_videos,
    SUM(is_click)::BIGINT AS click_count,
    SUM(is_like)::BIGINT AS like_count,
    SUM(is_comment)::BIGINT AS comment_count,
    SUM(is_forward)::BIGINT AS share_count,
    SUM(is_follow)::BIGINT AS follow_count,
    SUM(is_hate)::BIGINT AS hate_count,
    SUM(long_view)::BIGINT AS long_view_count,
    SUM(is_profile_enter)::BIGINT AS profile_enter_count,
    SUM(play_time_ms)::BIGINT AS play_time_sum_ms,
    AVG(play_time_ms)::DOUBLE AS mean_play_time_ms,
    APPROX_QUANTILE(play_time_ms, 0.5)::DOUBLE AS median_play_time_ms,
    APPROX_QUANTILE(play_time_ms, 0.9)::DOUBLE AS p90_play_time_ms,
    COUNT(*) FILTER (WHERE duration_ms > 0)::BIGINT AS watch_depth_denominator,
    AVG(watch_depth_ratio) FILTER (WHERE duration_ms > 0)::DOUBLE AS mean_watch_depth,
    APPROX_QUANTILE(
        watch_depth_ratio, 0.5
    ) FILTER (WHERE duration_ms > 0)::DOUBLE AS median_watch_depth,
    APPROX_QUANTILE(
        watch_depth_ratio, 0.9
    ) FILTER (WHERE duration_ms > 0)::DOUBLE AS p90_watch_depth,
    APPROX_QUANTILE(
        watch_depth_ratio, 0.99
    ) FILTER (WHERE duration_ms > 0)::DOUBLE AS p99_watch_depth,
    COUNT(*) FILTER (
        WHERE duration_ms > 0 AND watch_depth_ratio > 1
    )::BIGINT AS watch_depth_above_one_count,
    CAST(SUM(is_click) / NULLIF(COUNT(*), 0) AS DOUBLE) AS click_rate,
    CAST(SUM(is_like) / NULLIF(COUNT(*), 0) AS DOUBLE) AS like_rate,
    CAST(SUM(is_comment) / NULLIF(COUNT(*), 0) AS DOUBLE) AS comment_rate,
    CAST(SUM(is_forward) / NULLIF(COUNT(*), 0) AS DOUBLE) AS share_rate,
    CAST(SUM(is_follow) / NULLIF(COUNT(*), 0) AS DOUBLE) AS follow_rate,
    CAST(SUM(is_hate) / NULLIF(COUNT(*), 0) AS DOUBLE) AS hate_rate,
    CAST(SUM(long_view) / NULLIF(COUNT(*), 0) AS DOUBLE) AS long_view_rate,
    CAST(SUM(is_profile_enter) / NULLIF(COUNT(*), 0) AS DOUBLE) AS profile_enter_rate,
    CAST(
        COUNT(*) FILTER (WHERE duration_ms > 0 AND watch_depth_ratio > 1)
        / NULLIF(COUNT(*) FILTER (WHERE duration_ms > 0), 0)
        AS DOUBLE
    ) AS watch_depth_above_one_rate
FROM prepared_standard
WHERE is_valid_event;

CREATE OR REPLACE TABLE mart_engagement_by_tab AS
SELECT
    tab,
    COUNT(*)::BIGINT AS event_count,
    COUNT(DISTINCT user_id)::INTEGER AS active_users,
    COUNT(DISTINCT video_id)::BIGINT AS distinct_videos,
    CAST(SUM(is_click) / NULLIF(COUNT(*), 0) AS DOUBLE) AS click_rate,
    CAST(SUM(is_like) / NULLIF(COUNT(*), 0) AS DOUBLE) AS like_rate,
    CAST(SUM(is_comment) / NULLIF(COUNT(*), 0) AS DOUBLE) AS comment_rate,
    CAST(SUM(is_forward) / NULLIF(COUNT(*), 0) AS DOUBLE) AS share_rate,
    CAST(SUM(long_view) / NULLIF(COUNT(*), 0) AS DOUBLE) AS long_view_rate,
    AVG(watch_depth_ratio) FILTER (WHERE duration_ms > 0)::DOUBLE AS mean_watch_depth,
    APPROX_QUANTILE(
        watch_depth_ratio, 0.5
    ) FILTER (WHERE duration_ms > 0)::DOUBLE AS median_watch_depth
FROM prepared_standard
WHERE is_valid_event
GROUP BY tab;

CREATE OR REPLACE TABLE mart_user_segment_engagement AS
SELECT
    active_segment,
    COUNT(*)::INTEGER AS user_count,
    MIN(active_days)::INTEGER AS minimum_active_days,
    MAX(active_days)::INTEGER AS maximum_active_days,
    SUM(event_count)::BIGINT AS event_count,
    CAST(AVG(event_count) AS DOUBLE) AS mean_events_per_user,
    MEDIAN(event_count)::DOUBLE AS median_events_per_user,
    CAST(SUM(click_count) / NULLIF(SUM(event_count), 0) AS DOUBLE) AS click_rate,
    CAST(SUM(like_count) / NULLIF(SUM(event_count), 0) AS DOUBLE) AS like_rate,
    CAST(SUM(comment_count) / NULLIF(SUM(event_count), 0) AS DOUBLE) AS comment_rate,
    CAST(SUM(share_count) / NULLIF(SUM(event_count), 0) AS DOUBLE) AS share_rate,
    CAST(SUM(long_view_count) / NULLIF(SUM(event_count), 0) AS DOUBLE) AS long_view_rate
FROM mart_user_summary
GROUP BY active_segment;

CREATE OR REPLACE TABLE mart_weekday_activity AS
SELECT
    DAYOFWEEK(activity_date) AS weekday_number,
    DAYNAME(activity_date) AS weekday_name,
    is_weekend,
    COUNT(*)::INTEGER AS observed_day_count,
    AVG(dau)::DOUBLE AS mean_dau,
    AVG(event_count)::DOUBLE AS mean_event_count,
    AVG(events_per_dau)::DOUBLE AS mean_events_per_dau,
    CAST(SUM(long_view_count) / NULLIF(SUM(event_count), 0) AS DOUBLE) AS long_view_rate
FROM mart_daily_activity
GROUP BY DAYOFWEEK(activity_date), DAYNAME(activity_date), is_weekend;

CREATE OR REPLACE TABLE mart_cohort_return AS
WITH offsets AS (
    SELECT UNNEST([1, 3, 7])::INTEGER AS offset_day
),
user_offsets AS (
    SELECT
        u.user_id,
        u.first_seen_date,
        o.offset_day,
        CAST(u.first_seen_date + o.offset_day AS DATE) AS target_date,
        w.end_date AS observation_end
    FROM mart_user_summary u
    CROSS JOIN offsets o
    CROSS JOIN observation_window w
)
SELECT
    u.user_id,
    u.first_seen_date,
    u.offset_day,
    u.target_date,
    u.observation_end,
    (u.target_date <= u.observation_end) AS eligible,
    (d.user_id IS NOT NULL) AS returned_exactly,
    COALESCE(d.event_count, 0)::BIGINT AS target_day_event_count
FROM user_offsets u
LEFT JOIN mart_user_day d
    ON d.user_id = u.user_id
   AND d.activity_date = u.target_date;

CREATE OR REPLACE TABLE mart_return_overall AS
SELECT
    offset_day,
    COUNT(*) FILTER (WHERE eligible)::BIGINT AS eligible_users,
    COUNT(*) FILTER (WHERE eligible AND returned_exactly)::BIGINT AS returned_users,
    CAST(
        COUNT(*) FILTER (WHERE eligible AND returned_exactly)
        / NULLIF(COUNT(*) FILTER (WHERE eligible), 0)
        AS DOUBLE
    ) AS return_rate
FROM mart_cohort_return
GROUP BY offset_day;

CREATE OR REPLACE TABLE mart_return_left_truncation_sensitivity AS
WITH window_dates AS (
    SELECT start_date, end_date FROM observation_window
)
SELECT
    offset_day,
    COUNT(*) FILTER (
        WHERE eligible AND first_seen_date > (SELECT start_date FROM window_dates)
    )::BIGINT AS eligible_users_excluding_first_cohort,
    COUNT(*) FILTER (
        WHERE eligible
          AND first_seen_date > (SELECT start_date FROM window_dates)
          AND returned_exactly
    )::BIGINT AS returned_users_excluding_first_cohort,
    CAST(
        COUNT(*) FILTER (
            WHERE eligible
              AND first_seen_date > (SELECT start_date FROM window_dates)
              AND returned_exactly
        )
        / NULLIF(
            COUNT(*) FILTER (
                WHERE eligible
                  AND first_seen_date > (SELECT start_date FROM window_dates)
            ),
            0
        )
        AS DOUBLE
    ) AS return_rate_excluding_first_cohort
FROM mart_cohort_return
GROUP BY offset_day;

CREATE OR REPLACE TABLE mart_cohort_retention AS
SELECT
    first_seen_date AS cohort_date,
    offset_day,
    COUNT(*) FILTER (WHERE eligible)::BIGINT AS eligible_users,
    COUNT(*) FILTER (WHERE eligible AND returned_exactly)::BIGINT AS returned_users,
    CAST(
        COUNT(*) FILTER (WHERE eligible AND returned_exactly)
        / NULLIF(COUNT(*) FILTER (WHERE eligible), 0)
        AS DOUBLE
    ) AS return_rate
FROM mart_cohort_return
GROUP BY first_seen_date, offset_day;

CREATE OR REPLACE TABLE mart_cohort_any_seven_day AS
WITH eligible AS (
    SELECT u.user_id, u.first_seen_date
    FROM mart_user_summary u
    CROSS JOIN observation_window w
    WHERE CAST(u.first_seen_date + 7 AS DATE) <= w.end_date
),
future_activity AS (
    SELECT
        e.user_id,
        e.first_seen_date,
        COUNT(d.activity_date) > 0 AS returned_any_day_1_to_7
    FROM eligible e
    LEFT JOIN mart_user_day d
        ON d.user_id = e.user_id
       AND d.activity_date BETWEEN e.first_seen_date + 1 AND e.first_seen_date + 7
    GROUP BY e.user_id, e.first_seen_date
)
SELECT
    COUNT(*)::BIGINT AS eligible_users,
    COUNT(*) FILTER (WHERE returned_any_day_1_to_7)::BIGINT AS returned_users,
    CAST(
        COUNT(*) FILTER (WHERE returned_any_day_1_to_7) / NULLIF(COUNT(*), 0)
        AS DOUBLE
    ) AS return_rate_any_day_1_to_7
FROM future_activity;

CREATE OR REPLACE TABLE mart_return_model AS
WITH eligible_index_days AS (
    SELECT d.*
    FROM mart_user_day d
    CROSS JOIN observation_window w
    WHERE d.activity_date <= w.end_date - 7
),
any_future_activity AS (
    SELECT
        i.user_id,
        i.activity_date,
        COUNT(f.activity_date) > 0 AS returned_any_7d
    FROM eligible_index_days i
    LEFT JOIN mart_user_day f
        ON f.user_id = i.user_id
       AND f.activity_date BETWEEN i.activity_date + 1 AND i.activity_date + 7
    GROUP BY i.user_id, i.activity_date
)
SELECT
    i.*,
    w.start_date AS observation_start,
    w.end_date AS observation_end,
    (d1.user_id IS NOT NULL)::INTEGER AS returned_d1,
    (d7.user_id IS NOT NULL)::INTEGER AS returned_d7,
    a.returned_any_7d::INTEGER AS returned_any_7d,
    CAST(DAYOFWEEK(i.activity_date) AS INTEGER) AS weekday_number,
    CAST(i.activity_date - w.start_date AS INTEGER) AS days_since_start
FROM eligible_index_days i
CROSS JOIN observation_window w
LEFT JOIN mart_user_day d1
    ON d1.user_id = i.user_id
   AND d1.activity_date = i.activity_date + 1
LEFT JOIN mart_user_day d7
    ON d7.user_id = i.user_id
   AND d7.activity_date = i.activity_date + 7
LEFT JOIN any_future_activity a
    ON a.user_id = i.user_id
   AND a.activity_date = i.activity_date;

COPY (
    SELECT
        video_id,
        COUNT(*)::BIGINT AS event_count,
        SUM(is_click)::BIGINT AS click_count,
        SUM(is_like)::BIGINT AS like_count,
        SUM(is_comment)::BIGINT AS comment_count,
        SUM(is_forward)::BIGINT AS share_count,
        SUM(is_follow)::BIGINT AS follow_count,
        SUM(long_view)::BIGINT AS long_view_count,
        AVG(play_time_ms)::DOUBLE AS mean_play_time_ms,
        AVG(watch_depth_ratio) FILTER (WHERE duration_ms > 0)::DOUBLE AS mean_watch_depth,
        CAST(SUM(is_click) / NULLIF(COUNT(*), 0) AS DOUBLE) AS click_rate,
        CAST(SUM(is_like) / NULLIF(COUNT(*), 0) AS DOUBLE) AS like_rate,
        CAST(SUM(is_comment) / NULLIF(COUNT(*), 0) AS DOUBLE) AS comment_rate,
        CAST(SUM(is_forward) / NULLIF(COUNT(*), 0) AS DOUBLE) AS share_rate,
        CAST(SUM(long_view) / NULLIF(COUNT(*), 0) AS DOUBLE) AS long_view_rate
    FROM prepared_standard
    WHERE is_valid_event
    GROUP BY video_id
) TO '{{ marts_dir }}/video_performance.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

CREATE OR REPLACE VIEW mart_video_performance AS
SELECT * FROM read_parquet('{{ marts_dir }}/video_performance.parquet');

COPY mart_user_day
TO '{{ marts_dir }}/user_day.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY mart_user_summary
TO '{{ marts_dir }}/user_summary.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY mart_daily_activity
TO '{{ marts_dir }}/daily_activity.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY mart_cohort_return
TO '{{ marts_dir }}/cohort_return.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);
