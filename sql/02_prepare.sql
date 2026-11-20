-- Standardize source fields and build compressed event/dimension Parquet files.

COPY (
    SELECT
        CAST(user_id AS BIGINT) AS user_id,
        CAST(video_id AS BIGINT) AS video_id,
        'standard'::VARCHAR AS source_type,
        parse_filename(filename) AS source_file,
        TRY_STRPTIME(CAST(date AS VARCHAR), '%Y%m%d')::DATE AS event_date,
        CAST(epoch_ms(time_ms) + INTERVAL 8 HOUR AS TIMESTAMP) AS event_ts_local,
        CAST(floor(hourmin / 100) AS INTEGER) AS source_hour,
        CAST(hourmin AS INTEGER) AS hourmin,
        CAST(time_ms AS BIGINT) AS time_ms,
        CAST(is_click AS INTEGER) AS is_click,
        CAST(is_like AS INTEGER) AS is_like,
        CAST(is_follow AS INTEGER) AS is_follow,
        CAST(is_comment AS INTEGER) AS is_comment,
        CAST(is_forward AS INTEGER) AS is_forward,
        CAST(is_hate AS INTEGER) AS is_hate,
        CAST(long_view AS INTEGER) AS long_view,
        CAST(play_time_ms AS BIGINT) AS play_time_ms,
        CAST(duration_ms AS BIGINT) AS duration_ms,
        CAST(profile_stay_time AS BIGINT) AS profile_stay_time,
        CAST(comment_stay_time AS BIGINT) AS comment_stay_time,
        CAST(is_profile_enter AS INTEGER) AS is_profile_enter,
        CAST(is_rand AS INTEGER) AS is_rand,
        CAST(tab AS INTEGER) AS tab,
        CAST(play_time_ms / NULLIF(duration_ms, 0) AS DOUBLE) AS watch_depth_ratio,
        (
            TRY_STRPTIME(CAST(date AS VARCHAR), '%Y%m%d')::DATE
            = CAST(epoch_ms(time_ms) + INTERVAL 8 HOUR AS DATE)
        ) AS is_date_time_consistent,
        (
            user_id IS NOT NULL
            AND video_id IS NOT NULL
            AND TRY_STRPTIME(CAST(date AS VARCHAR), '%Y%m%d') IS NOT NULL
            AND time_ms > 0
            AND tab BETWEEN 0 AND 14
            AND hourmin BETWEEN 0 AND 2359
            AND hourmin % 100 BETWEEN 0 AND 59
            AND is_click IN (0, 1)
            AND is_like IN (0, 1)
            AND is_follow IN (0, 1)
            AND is_comment IN (0, 1)
            AND is_forward IN (0, 1)
            AND is_hate IN (0, 1)
            AND long_view IN (0, 1)
            AND is_profile_enter IN (0, 1)
            AND is_rand = 0
            AND play_time_ms >= 0
            AND duration_ms >= 0
            AND profile_stay_time >= 0
            AND comment_stay_time >= 0
        ) AS is_valid_event
    FROM raw_standard
) TO '{{ processed_dir }}/standard_events.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY (
    SELECT
        CAST(user_id AS BIGINT) AS user_id,
        CAST(video_id AS BIGINT) AS video_id,
        'random'::VARCHAR AS source_type,
        parse_filename(filename) AS source_file,
        TRY_STRPTIME(CAST(date AS VARCHAR), '%Y%m%d')::DATE AS event_date,
        CAST(epoch_ms(time_ms) + INTERVAL 8 HOUR AS TIMESTAMP) AS event_ts_local,
        CAST(floor(hourmin / 100) AS INTEGER) AS source_hour,
        CAST(hourmin AS INTEGER) AS hourmin,
        CAST(time_ms AS BIGINT) AS time_ms,
        CAST(is_click AS INTEGER) AS is_click,
        CAST(is_like AS INTEGER) AS is_like,
        CAST(is_follow AS INTEGER) AS is_follow,
        CAST(is_comment AS INTEGER) AS is_comment,
        CAST(is_forward AS INTEGER) AS is_forward,
        CAST(is_hate AS INTEGER) AS is_hate,
        CAST(long_view AS INTEGER) AS long_view,
        CAST(play_time_ms AS BIGINT) AS play_time_ms,
        CAST(duration_ms AS BIGINT) AS duration_ms,
        CAST(profile_stay_time AS BIGINT) AS profile_stay_time,
        CAST(comment_stay_time AS BIGINT) AS comment_stay_time,
        CAST(is_profile_enter AS INTEGER) AS is_profile_enter,
        CAST(is_rand AS INTEGER) AS is_rand,
        CAST(tab AS INTEGER) AS tab,
        CAST(play_time_ms / NULLIF(duration_ms, 0) AS DOUBLE) AS watch_depth_ratio,
        (
            TRY_STRPTIME(CAST(date AS VARCHAR), '%Y%m%d')::DATE
            = CAST(epoch_ms(time_ms) + INTERVAL 8 HOUR AS DATE)
        ) AS is_date_time_consistent,
        (
            user_id IS NOT NULL
            AND video_id IS NOT NULL
            AND TRY_STRPTIME(CAST(date AS VARCHAR), '%Y%m%d') IS NOT NULL
            AND time_ms > 0
            AND tab BETWEEN 0 AND 14
            AND hourmin BETWEEN 0 AND 2359
            AND hourmin % 100 BETWEEN 0 AND 59
            AND is_click IN (0, 1)
            AND is_like IN (0, 1)
            AND is_follow IN (0, 1)
            AND is_comment IN (0, 1)
            AND is_forward IN (0, 1)
            AND is_hate IN (0, 1)
            AND long_view IN (0, 1)
            AND is_profile_enter IN (0, 1)
            AND is_rand = 1
            AND play_time_ms >= 0
            AND duration_ms >= 0
            AND profile_stay_time >= 0
            AND comment_stay_time >= 0
        ) AS is_valid_event
    FROM raw_random
) TO '{{ processed_dir }}/random_events.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY (
    SELECT
        CAST(user_id AS BIGINT) AS user_id,
        CAST(user_active_degree AS VARCHAR) AS user_active_degree,
        CAST(is_lowactive_period AS INTEGER) AS is_lowactive_period,
        CAST(is_live_streamer AS INTEGER) AS is_live_streamer,
        CAST(is_video_author AS INTEGER) AS is_video_author,
        CAST(follow_user_num AS BIGINT) AS follow_user_num,
        follow_user_num_range,
        CAST(fans_user_num AS BIGINT) AS fans_user_num,
        fans_user_num_range,
        CAST(friend_user_num AS BIGINT) AS friend_user_num,
        friend_user_num_range,
        CAST(register_days AS BIGINT) AS register_days,
        register_days_range,
        CAST(onehot_feat0 AS DOUBLE) AS onehot_feat0,
        CAST(onehot_feat1 AS DOUBLE) AS onehot_feat1,
        CAST(onehot_feat2 AS DOUBLE) AS onehot_feat2,
        CAST(onehot_feat3 AS DOUBLE) AS onehot_feat3,
        CAST(onehot_feat4 AS DOUBLE) AS onehot_feat4,
        CAST(onehot_feat5 AS DOUBLE) AS onehot_feat5,
        CAST(onehot_feat6 AS DOUBLE) AS onehot_feat6,
        CAST(onehot_feat7 AS DOUBLE) AS onehot_feat7,
        CAST(onehot_feat8 AS DOUBLE) AS onehot_feat8,
        CAST(onehot_feat9 AS DOUBLE) AS onehot_feat9,
        CAST(onehot_feat10 AS DOUBLE) AS onehot_feat10,
        CAST(onehot_feat11 AS DOUBLE) AS onehot_feat11,
        CAST(onehot_feat12 AS DOUBLE) AS onehot_feat12,
        CAST(onehot_feat13 AS DOUBLE) AS onehot_feat13,
        CAST(onehot_feat14 AS DOUBLE) AS onehot_feat14,
        CAST(onehot_feat15 AS DOUBLE) AS onehot_feat15,
        CAST(onehot_feat16 AS DOUBLE) AS onehot_feat16,
        CAST(onehot_feat17 AS DOUBLE) AS onehot_feat17,
        parse_filename(filename) AS source_file,
        (user_id IS NOT NULL) AS is_valid_user
    FROM raw_users
) TO '{{ processed_dir }}/user_features.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY (
    SELECT
        CAST(video_id AS BIGINT) AS video_id,
        CAST(author_id AS BIGINT) AS author_id,
        CAST(video_type AS VARCHAR) AS video_type,
        CAST(upload_dt AS DATE) AS upload_date,
        CAST(upload_type AS VARCHAR) AS upload_type,
        CAST(visible_status AS DOUBLE) AS visible_status,
        CAST(video_duration AS DOUBLE) AS video_duration_ms,
        CAST(server_width AS DOUBLE) AS server_width,
        CAST(server_height AS DOUBLE) AS server_height,
        CAST(music_id AS BIGINT) AS music_id,
        CAST(music_type AS DOUBLE) AS music_type,
        CAST(tag AS VARCHAR) AS tag,
        parse_filename(filename) AS source_file,
        (video_id IS NOT NULL) AS is_valid_video
    FROM raw_video_basic
) TO '{{ processed_dir }}/video_basic.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);

COPY (
    SELECT
        CAST(video_id AS BIGINT) AS video_id,
        CAST(counts AS BIGINT) AS counts,
        CAST(show_cnt AS DOUBLE) AS show_cnt,
        CAST(show_user_num AS DOUBLE) AS show_user_num,
        CAST(play_cnt AS DOUBLE) AS play_cnt,
        CAST(play_user_num AS DOUBLE) AS play_user_num,
        CAST(play_duration AS DOUBLE) AS play_duration,
        CAST(complete_play_cnt AS DOUBLE) AS complete_play_cnt,
        CAST(complete_play_user_num AS DOUBLE) AS complete_play_user_num,
        CAST(valid_play_cnt AS DOUBLE) AS valid_play_cnt,
        CAST(valid_play_user_num AS DOUBLE) AS valid_play_user_num,
        CAST(long_time_play_cnt AS DOUBLE) AS long_time_play_cnt,
        CAST(long_time_play_user_num AS DOUBLE) AS long_time_play_user_num,
        CAST(short_time_play_cnt AS DOUBLE) AS short_time_play_cnt,
        CAST(short_time_play_user_num AS DOUBLE) AS short_time_play_user_num,
        CAST(play_progress AS DOUBLE) AS play_progress,
        CAST(comment_stay_duration AS DOUBLE) AS comment_stay_duration,
        CAST(like_cnt AS DOUBLE) AS like_cnt,
        CAST(like_user_num AS DOUBLE) AS like_user_num,
        CAST(click_like_cnt AS DOUBLE) AS click_like_cnt,
        CAST(double_click_cnt AS DOUBLE) AS double_click_cnt,
        CAST(cancel_like_cnt AS DOUBLE) AS cancel_like_cnt,
        CAST(cancel_like_user_num AS DOUBLE) AS cancel_like_user_num,
        CAST(comment_cnt AS DOUBLE) AS comment_cnt,
        CAST(comment_user_num AS DOUBLE) AS comment_user_num,
        CAST(direct_comment_cnt AS DOUBLE) AS direct_comment_cnt,
        CAST(reply_comment_cnt AS DOUBLE) AS reply_comment_cnt,
        CAST(delete_comment_cnt AS DOUBLE) AS delete_comment_cnt,
        CAST(delete_comment_user_num AS DOUBLE) AS delete_comment_user_num,
        CAST(comment_like_cnt AS DOUBLE) AS comment_like_cnt,
        CAST(comment_like_user_num AS DOUBLE) AS comment_like_user_num,
        CAST(follow_cnt AS DOUBLE) AS follow_cnt,
        CAST(follow_user_num AS DOUBLE) AS follow_user_num,
        CAST(cancel_follow_cnt AS DOUBLE) AS cancel_follow_cnt,
        CAST(cancel_follow_user_num AS DOUBLE) AS cancel_follow_user_num,
        CAST(share_cnt AS DOUBLE) AS share_cnt,
        CAST(share_user_num AS DOUBLE) AS share_user_num,
        CAST(download_cnt AS DOUBLE) AS download_cnt,
        CAST(download_user_num AS DOUBLE) AS download_user_num,
        CAST(report_cnt AS DOUBLE) AS report_cnt,
        CAST(report_user_num AS DOUBLE) AS report_user_num,
        CAST(reduce_similar_cnt AS DOUBLE) AS reduce_similar_cnt,
        CAST(reduce_similar_user_num AS DOUBLE) AS reduce_similar_user_num,
        CAST(collect_cnt AS DOUBLE) AS collect_cnt,
        CAST(collect_user_num AS DOUBLE) AS collect_user_num,
        CAST(cancel_collect_cnt AS DOUBLE) AS cancel_collect_cnt,
        CAST(cancel_collect_user_num AS DOUBLE) AS cancel_collect_user_num,
        CAST(direct_comment_user_num AS DOUBLE) AS direct_comment_user_num,
        CAST(reply_comment_user_num AS DOUBLE) AS reply_comment_user_num,
        CAST(share_all_cnt AS DOUBLE) AS share_all_cnt,
        CAST(share_all_user_num AS DOUBLE) AS share_all_user_num,
        CAST(outsite_share_all_cnt AS DOUBLE) AS outsite_share_all_cnt,
        parse_filename(filename) AS source_file,
        (video_id IS NOT NULL AND counts > 0) AS is_valid_video_statistic
    FROM raw_video_statistics
) TO '{{ processed_dir }}/video_statistics.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE TRUE);
