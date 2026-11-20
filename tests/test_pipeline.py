from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import yaml

from kuairand_analysis.config import AnalysisConfig
from kuairand_analysis.pipeline import AnalysisPipeline


LOG_COLUMNS = [
    "user_id",
    "video_id",
    "date",
    "hourmin",
    "time_ms",
    "is_click",
    "is_like",
    "is_follow",
    "is_comment",
    "is_forward",
    "is_hate",
    "long_view",
    "play_time_ms",
    "duration_ms",
    "profile_stay_time",
    "comment_stay_time",
    "is_profile_enter",
    "is_rand",
    "tab",
]

USER_COLUMNS = [
    "user_id",
    "user_active_degree",
    "is_lowactive_period",
    "is_live_streamer",
    "is_video_author",
    "follow_user_num",
    "follow_user_num_range",
    "fans_user_num",
    "fans_user_num_range",
    "friend_user_num",
    "friend_user_num_range",
    "register_days",
    "register_days_range",
    *[f"onehot_feat{index}" for index in range(18)],
]

VIDEO_BASIC_COLUMNS = [
    "video_id",
    "author_id",
    "video_type",
    "upload_dt",
    "upload_type",
    "visible_status",
    "video_duration",
    "server_width",
    "server_height",
    "music_id",
    "music_type",
    "tag",
]

VIDEO_STAT_COLUMNS = [
    "video_id",
    "counts",
    "show_cnt",
    "show_user_num",
    "play_cnt",
    "play_user_num",
    "play_duration",
    "complete_play_cnt",
    "complete_play_user_num",
    "valid_play_cnt",
    "valid_play_user_num",
    "long_time_play_cnt",
    "long_time_play_user_num",
    "short_time_play_cnt",
    "short_time_play_user_num",
    "play_progress",
    "comment_stay_duration",
    "like_cnt",
    "like_user_num",
    "click_like_cnt",
    "double_click_cnt",
    "cancel_like_cnt",
    "cancel_like_user_num",
    "comment_cnt",
    "comment_user_num",
    "direct_comment_cnt",
    "reply_comment_cnt",
    "delete_comment_cnt",
    "delete_comment_user_num",
    "comment_like_cnt",
    "comment_like_user_num",
    "follow_cnt",
    "follow_user_num",
    "cancel_follow_cnt",
    "cancel_follow_user_num",
    "share_cnt",
    "share_user_num",
    "download_cnt",
    "download_user_num",
    "report_cnt",
    "report_user_num",
    "reduce_similar_cnt",
    "reduce_similar_user_num",
    "collect_cnt",
    "collect_user_num",
    "cancel_collect_cnt",
    "cancel_collect_user_num",
    "direct_comment_user_num",
    "reply_comment_user_num",
    "share_all_cnt",
    "share_all_user_num",
    "outsite_share_all_cnt",
]


def _write_csv(path: Path, columns: list[str], rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)


def _event_time(day: int) -> int:
    local_noon_utc = datetime(2022, 4, day, 4, 0, tzinfo=timezone.utc)
    return int(local_noon_utc.timestamp() * 1000)


def _log_row(
    user_id: int,
    video_id: int,
    day: int,
    is_rand: int = 0,
    tab: int = 1,
) -> list[object]:
    return [
        user_id,
        video_id,
        20220400 + day,
        1200,
        _event_time(day),
        1,
        1 if user_id == 1 else 0,
        0,
        0,
        0,
        0,
        1,
        12000,
        15000,
        100,
        0,
        1,
        is_rand,
        tab,
    ]


def _build_fixture(tmp_path: Path) -> tuple[AnalysisConfig, Path]:
    raw = tmp_path / "raw"
    raw.mkdir()
    standard_rows = [
        _log_row(1, 101, 1),
        _log_row(1, 102, 2),
        _log_row(1, 101, 8),
        _log_row(2, 101, 1),
        _log_row(2, 103, 8, tab=3),
        _log_row(3, 104, 1),
        _log_row(4, 102, 2),
        _log_row(4, 103, 3),
        _log_row(4, 104, 9),
    ]
    invalid_play_time = _log_row(3, 104, 2)
    invalid_play_time[12] = -1
    standard_rows.append(invalid_play_time)
    standard_names = [
        "log_standard_4_08_to_4_21_27k_part1.csv",
        "log_standard_4_08_to_4_21_27k_part2.csv",
        "log_standard_4_22_to_5_08_27k_part1.csv",
        "log_standard_4_22_to_5_08_27k_part2.csv",
    ]
    for index, name in enumerate(standard_names):
        _write_csv(raw / name, LOG_COLUMNS, standard_rows[index::4])

    _write_csv(
        raw / "log_random_4_22_to_5_08_27k.csv",
        LOG_COLUMNS,
        [_log_row(1, 101, 9, is_rand=1, tab=0)],
    )

    user_rows = []
    for user_id in range(1, 5):
        user_rows.append(
            [
                user_id,
                "full_active",
                0,
                0,
                1,
                10,
                "(0,10]",
                2,
                "[1,10)",
                1,
                "[1,5)",
                100,
                "91-180",
                *([1.0] * 18),
            ]
        )
    _write_csv(raw / "user_features_27k.csv", USER_COLUMNS, user_rows)

    video_rows = [
        [101, 9001, "NORMAL", "2022-03-01", "ShortImport", 1, 15000, 720, 1280, 11, 1, "10,20"],
        [102, 9001, "NORMAL", "2022-03-02", "ShortImport", 1, 30000, 720, 1280, 12, 2, "10"],
        [103, 9002, "AD", "2022-03-03", "LongImport", 1, 20000, 720, 1280, 13, 3, "20"],
        [104, 9003, "NORMAL", "2022-03-04", "ShortImport", 1, 50000, 720, 1280, 14, 4, "30"],
    ]
    _write_csv(
        raw / "video_features_basic_27k.csv",
        VIDEO_BASIC_COLUMNS,
        video_rows,
    )

    statistic_rows = [
        [video_id, 10, 100.0, 90.0, 50.0, 45.0, 500000.0, *([1.0] * 45)]
        for video_id in (101, 102, 103, 104)
    ]
    for part, rows in enumerate(
        (statistic_rows[:1], statistic_rows[1:3], statistic_rows[3:]), start=1
    ):
        _write_csv(
            raw / f"video_features_statistic_27k_part{part}.csv",
            VIDEO_STAT_COLUMNS,
            rows,
        )

    config_data = {
        "project": {"name": "test", "timezone": "Asia/Shanghai"},
        "paths": {
            "raw_dir": str(raw),
            "processed_dir": str(tmp_path / "processed"),
            "marts_dir": str(tmp_path / "marts"),
            "results_dir": str(tmp_path / "results"),
            "figures_dir": str(tmp_path / "figures"),
        },
        "duckdb": {
            "database": ":memory:",
            "memory_limit": "1GB",
            "threads": 2,
            "temp_directory": str(tmp_path / "tmp"),
            "min_free_gb": 0,
        },
        "analysis": {
            "cohort_offsets": [1, 3, 7],
            "modeling": {
                "outcome_offset": 7,
                "train_fraction": 0.8,
                "min_eligible_dates": 2,
            },
            "content": {"min_tag_exposures": 0},
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(config_data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return AnalysisConfig.from_yaml(config_path), config_path


def test_pipeline_boundaries_idempotence_and_quality(tmp_path: Path) -> None:
    config, _ = _build_fixture(tmp_path)
    pipeline = AnalysisPipeline(
        config,
        run_statistics=False,
        sql_dir=Path(__file__).resolve().parents[1] / "sql",
    )
    pipeline.run()

    connection = duckdb.connect(":memory:")
    results = config.results_dir
    returns = connection.execute(
        f"SELECT offset_day, eligible_users, returned_users "
        f"FROM read_parquet('{results / 'return_overall.parquet'}') ORDER BY offset_day"
    ).fetchall()
    assert returns == [(1, 4, 2), (3, 4, 0), (7, 4, 3)]

    quality = connection.execute(
        f"SELECT row_count, valid_event_rows, invalid_play_time FROM "
        f"read_parquet('{results / 'quality_event_summary.parquet'}') "
        f"WHERE source_type = 'standard'"
    ).fetchone()
    assert quality == (10, 9, 1)

    inventory_count = connection.execute(
        f"SELECT COUNT(*) FROM read_parquet('{results / 'quality_file_inventory.parquet'}')"
    ).fetchone()[0]
    validation_failures = connection.execute(
        f"SELECT COUNT(*) FROM read_parquet('{results / 'validation_results.parquet'}') "
        f"WHERE passed IS DISTINCT FROM TRUE"
    ).fetchone()[0]
    assert inventory_count == 10
    assert validation_failures == 0

    exposure_quartiles = connection.execute(
        f"SELECT COUNT(*), SUM(user_day_count) FROM "
        f"read_parquet('{results / 'return_by_exposure_quartile.parquet'}')"
    ).fetchone()
    assert exposure_quartiles == (4, 5)

    hourly_columns = {
        row[0]
        for row in connection.execute(
            f"DESCRIBE SELECT * FROM "
            f"read_parquet('{results / 'hourly_profile.parquet'}')"
        ).fetchall()
    }
    assert {"long_view_rate", "like_rate"}.issubset(hourly_columns)

    before = connection.execute(
        f"SELECT SUM(event_count) FROM read_parquet('{config.marts_dir / 'user_day.parquet'}')"
    ).fetchone()[0]
    pipeline.run()
    after = connection.execute(
        f"SELECT SUM(event_count) FROM read_parquet('{config.marts_dir / 'user_day.parquet'}')"
    ).fetchone()[0]
    assert before == after == 9
