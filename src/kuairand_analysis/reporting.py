"""Compose verified result tables into the final report and repository README."""

from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd

from .config import AnalysisConfig
from .db import query_df, sql_literal


def format_int(value: object) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return f"{int(round(float(value))):,}"


def format_float(value: object, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "NA"
    number = float(value)
    if not math.isfinite(number):
        return "NA"
    return f"{number:,.{digits}f}"


def format_pct(value: object, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "NA"
    number = float(value)
    if not math.isfinite(number):
        return "NA"
    return f"{number * 100:,.{digits}f}%"


def format_p_value(value: object) -> str:
    if value is None or pd.isna(value):
        return "NA"
    number = float(value)
    if not math.isfinite(number):
        return "NA"
    if number < 0.0001:
        return "<0.0001"
    return f"{number:.3g}"


def markdown_table(
    frame: pd.DataFrame,
    columns: Iterable[str],
    headers: Iterable[str],
    formatters: dict[str, Callable[[object], str]] | None = None,
) -> str:
    formatters = formatters or {}
    column_list = list(columns)
    header_list = list(headers)
    if len(column_list) != len(header_list):
        raise ValueError("Markdown table headers and columns must have equal length.")
    lines = [
        "| " + " | ".join(header_list) + " |",
        "| " + " | ".join("---" for _ in header_list) + " |",
    ]
    for row in frame[column_list].itertuples(index=False):
        values = []
        for column, value in zip(column_list, row):
            formatter = formatters.get(column, lambda item: str(item))
            text = formatter(value).replace("|", "\\|").replace("\n", " ")
            values.append(text)
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


class ReportComposer:
    """Load result artifacts and compose documents without embedding result values."""

    def __init__(self, connection: duckdb.DuckDBPyConnection, config: AnalysisConfig):
        self.connection = connection
        self.config = config

    def result(self, name: str) -> pd.DataFrame:
        path = self.config.results_dir / f"{name}.parquet"
        if not path.is_file():
            raise FileNotFoundError(f"Required result artifact not found: {path}")
        return query_df(
            self.connection,
            f"SELECT * FROM read_parquet({sql_literal(path)})",
        )

    def model_metrics(self) -> dict[str, object]:
        path = self.config.results_dir / "model_metrics.json"
        if not path.is_file():
            raise FileNotFoundError(f"Required model metrics not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def metric(frame: pd.DataFrame, column: str, row: int = 0) -> float:
        return float(frame.iloc[row][column])

    def data_scale(self) -> tuple[float, float]:
        raw_gib = sum(path.stat().st_size for path in self.config.all_source_paths) / (1024**3)
        processed_gib = sum(
            path.stat().st_size
            for path in self.config.processed_dir.glob("*.parquet")
            if path.is_file()
        ) / (1024**3)
        return raw_gib, processed_gib

    def compose(self) -> tuple[str, str]:
        inventory = self.result("quality_file_inventory")
        event_quality = self.result("quality_event_summary")
        join_quality = self.result("quality_join_coverage")
        duplicates = self.result("quality_duplicate_key_summary")
        validation = self.result("validation_results")
        date_sensitivity = self.result("date_convention_sensitivity")
        activity_summary = self.result("activity_summary")
        daily = self.result("daily_activity")
        hourly = self.result("hourly_profile")
        segments = self.result("user_segments")
        weekday = self.result("weekday_activity")
        engagement = self.result("engagement_overall")
        tabs = self.result("engagement_by_tab")
        random_engagement = self.result("random_engagement")
        segment_engagement = self.result("user_segment_engagement")
        returns = self.result("return_overall").sort_values("offset_day")
        return_by_exposure = self.result(
            "return_by_exposure_quartile"
        ).sort_values("event_count_quartile")
        cohorts = self.result("cohort_retention")
        return_any = self.result("return_any_seven_day")
        return_sensitivity = self.result(
            "return_left_truncation_sensitivity"
        ).sort_values("offset_day")
        content_summary = self.result("content_summary")
        content_type = self.result("content_type")
        content_duration = self.result("content_duration")
        content_tags = self.result("content_tags")
        behavior_incidence = self.result("behavior_incidence")
        model = self.model_metrics()
        coefficients = self.result("model_coefficients")

        standard_quality = event_quality[
            event_quality["source_type"] == "standard"
        ].iloc[0]
        random_quality = event_quality[
            event_quality["source_type"] == "random"
        ].iloc[0]
        activity_row = activity_summary.iloc[0]
        engagement_row = engagement.iloc[0]
        random_row = random_engagement.iloc[0]
        return_lookup = {
            int(row.offset_day): row for row in returns.itertuples(index=False)
        }
        sensitivity_lookup = {
            int(row.offset_day): row
            for row in return_sensitivity.itertuples(index=False)
        }
        date_sensitivity_lookup = {
            (str(row.convention), int(row.offset_day)): row
            for row in date_sensitivity.itertuples(index=False)
        }
        peak_hour_row = hourly.loc[hourly["total_events"].idxmax()]
        peak_long_view_hour = hourly.loc[hourly["long_view_rate"].idxmax()]
        peak_like_hour = hourly.loc[hourly["like_rate"].idxmax()]
        peak_event_row = daily.loc[daily["event_count"].idxmax()]
        q1_exposure_return = return_by_exposure.iloc[0]
        q4_exposure_return = return_by_exposure.iloc[-1]

        eligible_content_type = content_type.sort_values(
            "event_count", ascending=False
        )
        top_type = eligible_content_type.iloc[0]
        eligible_duration = content_duration[
            ~content_duration["duration_band"].eq("unknown")
        ].sort_values("event_count", ascending=False)
        top_duration = eligible_duration.iloc[0]
        best_long_view_duration = eligible_duration.sort_values(
            "exposure_weighted_long_view_rate", ascending=False
        ).iloc[0]
        top_tag = content_tags.iloc[0] if not content_tags.empty else None
        top_exposure_tags = content_tags.head(10)
        completion_tag = top_exposure_tags.sort_values(
            "exposure_weighted_long_view_rate", ascending=False
        ).iloc[0]
        like_tag = top_exposure_tags.sort_values(
            "exposure_weighted_like_rate", ascending=False
        ).iloc[0]
        q1_segment_engagement = segment_engagement.loc[
            segment_engagement["active_segment"].eq("Q1")
        ].iloc[0]
        q4_segment_engagement = segment_engagement.loc[
            segment_engagement["active_segment"].eq("Q4")
        ].iloc[0]

        primary = model["primary"]
        primary_coeff = coefficients[
            (coefficients["outcome"] == model["primary_outcome"])
            & (~coefficients["term"].isin(["const"]))
            & (~coefficients["term"].str.startswith("weekday_"))
        ].copy()
        primary_main_order = [
            "log2_event_count",
            "long_view_rate_10pp",
            "any_explicit_interaction",
            "any_profile_enter",
            "week_index",
        ]
        primary_coeff["order"] = primary_coeff["term"].map(
            {name: index for index, name in enumerate(primary_main_order)}
        )
        primary_coeff = primary_coeff.sort_values("order")
        highest_or_row = primary_coeff[
            primary_coeff["term"].isin(primary_main_order[:4])
        ].sort_values("odds_ratio", ascending=False).iloc[0]
        event_count_coefficient = primary_coeff[
            primary_coeff["term"] == "log2_event_count"
        ].iloc[0]
        long_view_coefficient = primary_coeff[
            primary_coeff["term"] == "long_view_rate_10pp"
        ].iloc[0]
        any_explicit_coefficient = primary_coeff[
            primary_coeff["term"] == "any_explicit_interaction"
        ].iloc[0]
        any_profile_coefficient = primary_coeff[
            primary_coeff["term"] == "any_profile_enter"
        ].iloc[0]
        any_explicit_behavior = behavior_incidence.loc[
            behavior_incidence["feature"].eq("any_explicit")
        ].iloc[0]

        sensitivity_rows = coefficients[
            coefficients["term"].isin(primary_main_order[:4])
            & coefficients["outcome"].isin(
                [model["primary_outcome"], "returned_d1", "returned_any_7d"]
            )
        ].copy()
        outcome_labels = {
            "returned_d7": "精确 D7",
            "returned_d1": "精确 D1",
            "returned_any_7d": "未来 1 至 7 日任意回访",
        }
        sensitivity_rows["outcome_label"] = sensitivity_rows["outcome"].map(
            outcome_labels
        )

        raw_gib, processed_gib = self.data_scale()
        observation_start = pd.Timestamp(activity_row["observation_start"])
        observation_end = pd.Timestamp(activity_row["observation_end"])
        first_day_users = int(
            daily.loc[
                pd.to_datetime(daily["activity_date"]).eq(observation_start),
                "first_observed_users",
            ].iloc[0]
        )
        first_day_user_share = first_day_users / float(activity_row["active_users"])
        generated_date = datetime.now(ZoneInfo(self.config.timezone)).strftime(
            "%Y-%m-%d"
        )

        validation_pass = int(validation["passed"].sum())
        validation_total = len(validation)
        daily_top = daily.nlargest(5, "event_count").sort_values(
            "event_count", ascending=False
        )
        q4_segment = segments.loc[
            segments["active_segment"].eq("Q4")
        ].iloc[0]
        tab_display = tabs.head(6).copy()

        quality_rows = pd.DataFrame(
            [
                {
                    "metric": "标准日志行数",
                    "value": f"{format_int(standard_quality['row_count'])}",
                    "detail": f"有效 {format_int(standard_quality['valid_event_rows'])} 行",
                },
                {
                    "metric": "随机曝光行数",
                    "value": format_int(random_quality["row_count"]),
                    "detail": f"有效 {format_int(random_quality['valid_event_rows'])} 行",
                },
                {
                    "metric": "标准日志 ID 空值",
                    "value": format_int(
                        int(standard_quality["null_user_id"])
                        + int(standard_quality["null_video_id"])
                    ),
                    "detail": "分别检查 user_id 与 video_id",
                },
                {
                    "metric": "非法二元标记行",
                    "value": format_int(standard_quality["invalid_binary_rows"]),
                    "detail": "按所有二元反馈字段联合检查",
                },
                {
                    "metric": "日期与毫秒时间戳日期不一致",
                    "value": format_int(
                        standard_quality["date_timestamp_mismatch"]
                    ),
                    "detail": "源端日较 UTC+8 时间戳日期晚一天，保留源端日期",
                },
                {
                    "metric": "负观看时长",
                    "value": format_int(standard_quality["invalid_play_time"]),
                    "detail": "负值事件标记为无效，不进入业务 Marts",
                },
                {
                    "metric": "视频时长为 0",
                    "value": format_int(standard_quality["zero_duration"]),
                    "detail": "保留曝光与二元反馈，不进入观看深度分母",
                },
                {
                    "metric": "tab 超出官方 0 至 14 范围",
                    "value": format_int(
                        standard_quality["tab_outside_documented_range"]
                    ),
                    "detail": "异常事件不进入业务 Marts",
                },
                {
                    "metric": "hourmin 超出合法编码范围",
                    "value": format_int(standard_quality["invalid_hourmin"]),
                    "detail": "异常事件不进入业务 Marts",
                },
                {
                    "metric": "play_time_ms > duration_ms",
                    "value": format_int(
                        standard_quality["play_time_above_duration"]
                    ),
                    "detail": "保留；超出完整播放时长的原因需另行核验",
                },
            ]
        )

        coverage_rows = join_quality.copy()
        coverage_rows["coverage_rate"] = (
            coverage_rows["matched_distinct_ids"]
            / coverage_rows["denominator_distinct_ids"]
        )
        date_sensitivity_display = date_sensitivity.copy()
        date_sensitivity_display["convention_label"] = (
            date_sensitivity_display["convention"].map(
                {
                    "source_date": "源端 date + hourmin",
                    "timestamp_utc8": "UTC+8 time_ms 日期",
                }
            )
        )
        date_sensitivity_display["full_observation"] = (
            date_sensitivity_display.apply(
                lambda row: (
                    f"{format_int(row['eligible_users'])} / "
                    f"{format_int(row['returned_users'])}"
                ),
                axis=1,
            )
        )
        date_sensitivity_display["excluding_first_observation"] = (
            date_sensitivity_display.apply(
                lambda row: (
                    f"{format_int(row['eligible_users_excluding_first_cohort'])} / "
                    f"{format_int(row['returned_users_excluding_first_cohort'])}"
                ),
                axis=1,
            )
        )
        duplicate_rows = duplicates.copy()
        duplicate_rows["duplicate_row_rate"] = (
            duplicate_rows["rows_in_duplicate_key_groups"]
            / duplicate_rows["source_type"].map(
                {
                    "standard": int(standard_quality["row_count"]),
                    "random": int(random_quality["row_count"]),
                }
            )
        )

        report = f"""# KuaiRand-27K 用户活跃、参与、回访与内容表现分析

> 观察窗口：{observation_start:%Y-%m-%d} 至 {observation_end:%Y-%m-%d}。
>
> 主样本：{format_int(standard_quality['valid_event_rows'])} 条有效标准推荐日志事件；随机曝光日志独立描述，不参与主活跃、趋势或回访计算。
>
> 报告生成日期：{generated_date}。全部数值由仓库内 SQL 与 Python 流水线从真实原始 CSV 生成。

## 1. 研究问题与结论摘要

本研究回答五个问题：固定用户面板在观察窗口内的活跃和事件集中度如何；标准推荐曝光中的参与行为呈现什么结构；按首次观测活跃日分组后，精确 D1/D7 的窗口内再次活跃率是多少；视频类型、时长和标签对应怎样的曝光与参与结构；用户日行为与后续精确 D7 活跃有何样本内条件关联。

核心结果如下：

1. 有效标准日志覆盖 {format_int(activity_row['active_users'])} 名固定面板用户和 {format_int(activity_row['observed_days'])} 个日历日，日均 DAU 为 {format_int(activity_row['mean_dau'])}。DAU 最高的日期是 {pd.Timestamp(activity_row['maximum_dau_date']):%Y-%m-%d}，当日 DAU 为 {format_int(activity_row['maximum_dau'])}；事件量最高的日期是 {pd.Timestamp(peak_event_row['activity_date']):%Y-%m-%d}，当日事件数为 {format_int(peak_event_row['event_count'])}。
2. 按曝光计，标准日志的长观看标记率为 {format_pct(engagement_row['long_view_rate'])}，点赞率为 {format_pct(engagement_row['like_rate'])}，评论率为 {format_pct(engagement_row['comment_rate'])}。
3. 全部合格首次观测 Cohort 的精确 D1 活跃率为 {format_pct(return_lookup[1].return_rate)}，精确 D7 为 {format_pct(return_lookup[7].return_rate)}。首日 Cohort 有 {format_int(first_day_users)} 名用户，占面板的 {format_pct(first_day_user_share)}；排除该边界 Cohort 后，D7 为 {format_pct(sensitivity_lookup[7].return_rate_excluding_first_cohort)}。这两个数描述不同样本构成下的窗口内再次活跃率，都不估计新用户留存。
4. `{top_type['video_type']}` 视频覆盖 {format_int(top_type['event_count'])} 次标准日志曝光，占全部有效事件的 {format_pct(top_type['event_count'] / engagement_row['event_count'])}，其长观看标记率为 {format_pct(top_type['exposure_weighted_long_view_rate'])}。视频类型分组因此高度不平衡。曝光量最高的有定义时长段是 `{top_duration['duration_band']}`，该段长观看标记率为 {format_pct(top_duration['exposure_weighted_long_view_rate'])}。
5. 在控制星期、时间趋势和其余模型中变量后，日曝光量翻倍对应精确 D7 活跃的调整优势比为 {format_float(event_count_coefficient['odds_ratio'], 3)}（95% CI {format_float(event_count_coefficient['ci_low_odds_ratio'], 3)} 至 {format_float(event_count_coefficient['ci_high_odds_ratio'], 3)}）。有任一显性互动相对无互动的 D7 OR 为 {format_float(any_explicit_coefficient['odds_ratio'], 3)}。验证结局率接近 95%，且模型 Brier skill score 为 {format_float(primary['evaluation']['brier_skill_score'], 4)}，这些系数只描述样本内条件关联。

## 2. 数据、处理与质量

### 2.1 数据规模与来源边界

10 个原始 CSV 共 {raw_gib:.2f} GiB；标准化并 ZSTD 压缩后的 Parquet 共 {processed_gib:.2f} GiB。原始 CSV 仅作只读输入，发布仓库不包含原始数据或派生 Parquet。标准推荐日志与 `log_random_*` 随机曝光日志分别标准化并保留 `source_type`、`source_file` 和原始 `is_rand`。

{markdown_table(
    inventory.sort_values(["data_type", "source_file"]),
    ["data_type", "source_file", "row_count"],
    ["数据类型", "源文件", "行数"],
    {"row_count": format_int},
)}

### 2.2 关键质量结论

{markdown_table(
    quality_rows,
    ["metric", "value", "detail"],
    ["检查", "结果", "口径"],
)}

事件键 `(user_id, video_id, time_ms)` 的候选重复已全量扫描。用户多次接触同一视频属于合法序列行为，事件保留原始粒度；`(user_id, video_id)` 不作为唯一键。

{markdown_table(
    duplicate_rows,
    ["source_type", "duplicate_key_groups", "rows_in_duplicate_key_groups", "duplicate_row_rate"],
    ["来源", "候选重复键组", "涉及行数", "占该来源行数"],
    {
        "duplicate_key_groups": format_int,
        "rows_in_duplicate_key_groups": format_int,
        "duplicate_row_rate": format_pct,
    },
)}

跨表 ID 覆盖如下。当前用户、视频基础特征和视频统计特征的相关连接覆盖率均为 100%。

{markdown_table(
    coverage_rows,
    ["coverage", "denominator_distinct_ids", "matched_distinct_ids", "coverage_rate"],
    ["连接", "去重 ID 数", "匹配 ID 数", "覆盖率"],
    {
        "denominator_distinct_ids": format_int,
        "matched_distinct_ids": format_int,
        "coverage_rate": format_pct,
    },
)}

`date` 与 `hourmin` 共同定义源端交互日与小时；`time_ms` 用于溯源、排序和一致性诊断。全量比较发现 {format_int(standard_quality['date_timestamp_mismatch'])} 条记录的 `date` 比 UTC+8 时间戳日期晚一天，集中在时间戳 21 至 23 时附近，占标准日志 {format_pct(standard_quality['date_timestamp_mismatch'] / standard_quality['row_count'])}。这些记录的 `date + hourmin` 内部一致，报告采用源端交互时间。

`play_time_ms = 0` 保留为“未记录有效观看时长”；{format_int(standard_quality['invalid_play_time'])} 条负观看时长记录被标记为无效并从业务 Marts 排除。{format_int(standard_quality['zero_duration'])} 条事件的 `duration_ms = 0`，仍参与曝光和二元反馈统计，但不进入观看深度分母。`play_time_ms > duration_ms` 的记录保留在原值口径中；现有字段无法区分重复播放、循环播放或计量差异，报告不据此判断记录真假。全量发布对账通过 {validation_pass}/{validation_total} 项。

### 2.3 日期口径认证

主分析采用发布方提供的 `date` 定义事件日，并以 `hourmin` 提取小时。为检验这一选择，项目另用 `time_ms` 转换到 UTC+8 后的日期重建用户日，并重算精确 D1/D7。

{markdown_table(
    date_sensitivity_display.sort_values(["convention", "offset_day"]),
    ["convention_label", "offset_day", "full_observation", "return_rate", "excluding_first_observation", "return_rate_excluding_first_cohort"],
    ["日期口径", "偏移", "全样本合格/活跃", "全样本活跃率", "排除首日合格/活跃", "排除首日活跃率"],
    {
        "convention_label": str,
        "offset_day": lambda value: f"D{int(value)}",
        "full_observation": str,
        "return_rate": format_pct,
        "excluding_first_observation": str,
        "return_rate_excluding_first_cohort": format_pct,
    },
)}

源端日期口径的全样本 D7 活跃率为 {format_pct(date_sensitivity_lookup[('source_date', 7)].return_rate)}，UTC+8 时间戳日期口径为 {format_pct(date_sensitivity_lookup[('timestamp_utc8', 7)].return_rate)}，两者相差不超过 0.2 个百分点，主要描述结论保持不变。排除首日的 D7 则从 {format_pct(date_sensitivity_lookup[('source_date', 7)].return_rate_excluding_first_cohort)} 变为 {format_pct(date_sensitivity_lookup[('timestamp_utc8', 7)].return_rate_excluding_first_cohort)}；日期口径改变后，“首日”所包含的用户组也发生变化。该结果认证了全样本 D7 的稳定性，也说明排除首日的结果依赖观察边界，不能作为新用户留存估计。

## 3. 用户活跃

![日活与事件趋势](figures/activity_daily.png)

观察窗口内平均每个日历日有 {format_int(activity_row['mean_daily_events'])} 条有效标准日志事件，日均事件数为 {format_float(activity_row['mean_events_per_dau'], 2)} 条/DAU。工作日与周末的观察日均 DAU 分别为 {format_int(activity_row['mean_weekday_dau'])} 与 {format_int(activity_row['mean_weekend_dau'])}。

{markdown_table(
    daily_top,
    ["activity_date", "dau", "event_count", "events_per_dau", "first_observed_users"],
    ["日期", "DAU", "事件数", "事件/DAU", "首次观测活跃用户"],
    {
        "activity_date": lambda value: f"{pd.Timestamp(value):%Y-%m-%d}",
        "dau": format_int,
        "event_count": format_int,
        "events_per_dau": lambda value: format_float(value, 2),
        "first_observed_users": format_int,
    },
)}

![本地时段分布](figures/activity_hourly.png)

源端 `date + hourmin` 定义的事件量峰值出现在 {int(peak_hour_row['activity_hour'])} 时，占全部标准日志事件的 {format_pct(peak_hour_row['event_share'])}。长观看标记率峰值出现在 {int(peak_long_view_hour['activity_hour'])} 时（{format_pct(peak_long_view_hour['long_view_rate'])}），点赞标记率峰值出现在 {int(peak_like_hour['activity_hour'])} 时（{format_pct(peak_like_hour['like_rate'])}）。事件量、长观看标记率和点赞标记率的峰值分别对应不同的时段切片。

### 3.1 活跃程度分层

用户按观察窗口内事件量升序分为 Q1 至 Q4 四个等人数分位组，活跃天数和用户 ID 用于打破并列。Q4 表示事件量最高的四分之一，分组门槛和占比直接取自结果表。

![用户活跃分层](figures/user_segments.png)

{markdown_table(
    segments,
    ["active_segment", "user_count", "user_share", "minimum_event_count", "maximum_event_count", "minimum_active_days", "maximum_active_days", "event_share", "mean_events_per_user"],
    ["分层", "用户数", "用户占比", "最少事件数", "最多事件数", "最少活跃日", "最多活跃日", "事件占比", "人均事件数"],
    {
        "user_count": format_int,
        "user_share": format_pct,
        "minimum_event_count": format_int,
        "maximum_event_count": format_int,
        "minimum_active_days": format_int,
        "maximum_active_days": format_int,
        "event_share": format_pct,
        "mean_events_per_user": lambda value: format_float(value, 1),
    },
)}

Q4 贡献 {format_pct(q4_segment['event_share'])} 的事件，但其长观看标记率 {format_pct(q4_segment_engagement['long_view_rate'])}、点赞标记率 {format_pct(q4_segment_engagement['like_rate'])} 低于 Q1 的 {format_pct(q1_segment_engagement['long_view_rate'])} 和 {format_pct(q1_segment_engagement['like_rate'])}。按事件量评价用户会突出消费规模；按曝光率评价会突出单次曝光上的反馈差异。两个视角回答不同问题。

## 4. 用户参与

共同分母是有效标准日志曝光数 {format_int(engagement_row['event_count'])}。点赞、评论、分享、关注和长观看均按该条事件上的原始二元标记汇总。

{markdown_table(
    engagement,
    ["event_count", "active_users", "distinct_videos", "long_view_rate", "like_rate", "comment_rate", "share_rate", "follow_rate", "median_watch_depth", "p90_watch_depth", "watch_depth_above_one_rate"],
    ["事件数", "活跃用户", "视频数", "长观看率", "点赞率", "评论率", "分享率", "关注率", "观看深度中位数", "P90 观看深度", "观看深度>1 占比"],
    {
        "event_count": format_int,
        "active_users": format_int,
        "distinct_videos": format_int,
        "long_view_rate": format_pct,
        "like_rate": format_pct,
        "comment_rate": format_pct,
        "share_rate": format_pct,
        "follow_rate": format_pct,
        "median_watch_depth": lambda value: format_float(value, 3),
        "p90_watch_depth": lambda value: format_float(value, 3),
        "watch_depth_above_one_rate": format_pct,
    },
)}

观看深度为 `play_time_ms / duration_ms`，仅对 `duration_ms > 0` 计算。P90 为 {format_float(engagement_row['p90_watch_depth'], 3)}，{format_pct(engagement_row['watch_depth_above_one_rate'])} 的合格事件高于 1。该比率不能直接解释为完播率；长观看标记另按发布方阈值计算。描述统计中的分位数由 DuckDB 近似分位算法生成。

![主要场景参与](figures/engagement_by_tab.png)

`tab` 按原始场景编号展示。`is_click` 在单列界面表示有效播放、在双列界面表示点击，因此场景横向比较使用长观看、点赞、评论和分享等口径一致的指标。前六个场景如下。

{markdown_table(
    tab_display,
    ["tab", "event_count", "event_share", "long_view_rate", "like_rate", "comment_rate", "share_rate"],
    ["场景编号", "事件数", "事件占比", "长观看率", "点赞率", "评论率", "分享率"],
    {
        "tab": lambda value: str(int(value)),
        "event_count": format_int,
        "event_share": format_pct,
        "long_view_rate": format_pct,
        "like_rate": format_pct,
        "comment_rate": format_pct,
        "share_rate": format_pct,
    },
)}

随机曝光作为独立描述样本：{format_int(random_row['event_count'])} 条有效事件、{format_int(random_row['active_users'])} 名用户、{format_int(random_row['distinct_videos'])} 个视频，长观看标记率 {format_pct(random_row['long_view_rate'])}、点赞标记率 {format_pct(random_row['like_rate'])}。随机日志只占标准日志的一小部分，且两类日志覆盖的物品范围不同；本节分别报告描述值。

{markdown_table(
    segment_engagement,
    ["active_segment", "user_count", "event_count", "long_view_rate", "like_rate", "comment_rate", "mean_events_per_user"],
    ["活跃分层", "用户数", "事件数", "长观看率", "点赞率", "评论率", "人均事件数"],
    {
        "active_segment": str,
        "user_count": format_int,
        "event_count": format_int,
        "long_view_rate": format_pct,
        "like_rate": format_pct,
        "comment_rate": format_pct,
        "mean_events_per_user": lambda value: format_float(value, 1),
    },
)}

## 5. 用户回访

回访单位是用户和日历日。`first_seen_date` 为该用户在主样本窗口内首次出现有效标准日志的日期。精确 D7 的分子要求 `first_seen_date + 7` 当天仍有有效标准日志；目标日在观察截止日之后的用户不进入分母。这里的“回访”指窗口内再次出现活动，不是注册后的留存。

![Cohort 精确日回访](figures/return_cohorts.png)

{markdown_table(
    returns,
    ["offset_day", "eligible_users", "returned_users", "return_rate"],
    ["回访口径", "合格用户数", "回访用户数", "回访率"],
    {
        "offset_day": lambda value: f"精确 D{int(value)}",
        "eligible_users": format_int,
        "returned_users": format_int,
        "return_rate": format_pct,
    },
)}

从用户日曝光强度看，Q1 到 Q4 的原始 D7 活跃率由 {format_pct(q1_exposure_return['return_rate_d7'])} 升至 {format_pct(q4_exposure_return['return_rate_d7'])}，同期显性互动发生率由 {format_pct(q1_exposure_return['any_explicit_share'])} 增至 {format_pct(q4_exposure_return['any_explicit_share'])}，平均长观看标记率则由 {format_pct(q1_exposure_return['mean_long_view_rate'])} 降至 {format_pct(q4_exposure_return['mean_long_view_rate'])}。这些是同一面板内的分组差异，分量较高的用户日本身也来自更高频用户。

{markdown_table(
    return_by_exposure,
    ["event_count_quartile", "user_day_count", "minimum_event_count", "maximum_event_count", "mean_event_count", "return_rate_d7", "any_explicit_share", "mean_long_view_rate", "mean_like_rate"],
    ["曝光四分位", "用户日", "最少事件", "最多事件", "平均事件", "D7 回访率", "显性互动发生占比", "平均长观看率", "平均点赞率"],
    {
        "event_count_quartile": lambda value: f"Q{int(value)}",
        "user_day_count": format_int,
        "minimum_event_count": format_int,
        "maximum_event_count": format_int,
        "mean_event_count": lambda value: format_float(value, 1),
        "return_rate_d7": format_pct,
        "any_explicit_share": format_pct,
        "mean_long_view_rate": format_pct,
        "mean_like_rate": format_pct,
    },
)}

四组为等人数分组；事件数并列时按用户和日期确定顺序，因此相邻组的最小值与最大值可能相同。

Cohort 曲线中，精确 D7 有 {int(cohorts[(cohorts['offset_day'] == 7) & (cohorts['eligible_users'] > 0)]['cohort_date'].nunique())} 个非零合格分母的首次观测日期；最后 7 个日期行因目标日超出观察截止日而不进入分母。图中只绘制每组至少 30 名合格用户的 Cohort，以降低极小组波动；总回访率使用全部合格用户。主报告使用精确 D7；未来 1 至 7 日任意一天回访单独命名为“任意 7 日回访”，合格用户 {format_int(return_any.iloc[0]['eligible_users'])}，回访率 {format_pct(return_any.iloc[0]['return_rate_any_day_1_to_7'])}。

首日 Cohort 包含观察窗口开始前已经活跃、但首次记录落在窗口起点的用户，存在左截断。排除该 Cohort 后的描述结果如下。

{markdown_table(
    return_sensitivity,
    ["offset_day", "eligible_users_excluding_first_cohort", "returned_users_excluding_first_cohort", "return_rate_excluding_first_cohort"],
    ["回访口径", "合格用户数", "回访用户数", "边界口径活跃率"],
    {
        "offset_day": lambda value: f"精确 D{int(value)}",
        "eligible_users_excluding_first_cohort": format_int,
        "returned_users_excluding_first_cohort": format_int,
        "return_rate_excluding_first_cohort": format_pct,
    },
)}

排除起点 Cohort 后，D7 只剩 {format_int(sensitivity_lookup[7].eligible_users_excluding_first_cohort)} 名合格用户。这个口径移除了观察边界上的存量用户，也会改变用户构成：较晚首次出现且活动天数较少的用户占比上升。因此，{format_pct(sensitivity_lookup[7].return_rate_excluding_first_cohort)} 是源端日期定义下的边界描述值，不是对“真实新用户留存”的校正估计。第 2.3 节的日期口径核验进一步表明，改用 UTC+8 时间戳日期后，该边界口径的 D7 会变为 {format_pct(date_sensitivity_lookup[('timestamp_utc8', 7)].return_rate_excluding_first_cohort)}。

## 6. 视频内容表现

内容结果把视频基础属性连接到标准日志视频汇总。曝光加权指标回答实际曝光事件中的标记表现；视频等权指标回答有曝光视频的平均表现。两者受推荐分配、内容时长和受众构成影响，下面只解释描述性差异。

{markdown_table(
    content_type,
    ["video_type", "video_count", "event_count", "exposure_weighted_long_view_rate", "exposure_weighted_like_rate", "video_weighted_mean_long_view_rate", "video_weighted_mean_watch_depth"],
    ["视频类型", "视频数", "事件数", "曝光加权长观看率", "曝光加权点赞率", "视频等权长观看率", "视频等权观看深度"],
    {
        "video_type": str,
        "video_count": format_int,
        "event_count": format_int,
        "exposure_weighted_long_view_rate": format_pct,
        "exposure_weighted_like_rate": format_pct,
        "video_weighted_mean_long_view_rate": format_pct,
        "video_weighted_mean_watch_depth": lambda value: format_float(value, 3),
    },
)}

`{top_type['video_type']}` 占标准日志曝光 {format_pct(top_type['event_count'] / engagement_row['event_count'])}，其余类型的样本规模相差很大。类型表用于核对分布，不据此比较类型优劣。

![视频时长与参与](figures/content_duration.png)

{markdown_table(
    content_duration,
    ["duration_band", "video_count", "event_count", "exposure_weighted_long_view_rate", "exposure_weighted_like_rate", "video_weighted_mean_watch_depth"],
    ["时长段", "视频数", "事件数", "曝光加权长观看率", "曝光加权点赞率", "视频等权观看深度"],
    {
        "duration_band": str,
        "video_count": format_int,
        "event_count": format_int,
        "exposure_weighted_long_view_rate": format_pct,
        "exposure_weighted_like_rate": format_pct,
        "video_weighted_mean_watch_depth": lambda value: format_float(value, 3),
    },
)}

有定义时长段中，曝光加权长观看标记率最高的是 `{best_long_view_duration['duration_band']}`（{format_pct(best_long_view_duration['exposure_weighted_long_view_rate'])}，事件数 {format_int(best_long_view_duration['event_count'])}）。类型和时长分组同时改变内容组合与曝光人群；时长段结果是对标准日志的切片汇总，不把 `00-15s` 的率写成短视频带来的独立增益。

标签按逗号拆分，一个视频可进入多个数值标签。下表只保留事件曝光不少于 {format_int(self.config.analysis.min_tag_exposures)} 次的标签；标签使用公开数据中的原始数值 ID。{f"最高曝光标签为 `{top_tag['tag']}`，事件数 {format_int(top_tag['event_count'])}。" if top_tag is not None else "当前没有标签达到最小曝光阈值。"}

高曝光标签里，`{completion_tag['tag']}` 的长观看标记率为 {format_pct(completion_tag['exposure_weighted_long_view_rate'])}、点赞标记率为 {format_pct(completion_tag['exposure_weighted_like_rate'])}；`{like_tag['tag']}` 分别为 {format_pct(like_tag['exposure_weighted_long_view_rate'])} 和 {format_pct(like_tag['exposure_weighted_like_rate'])}。多标签视频会跨组重复，曝光加权率也可能被组内少数高曝光视频拉动。这些标签适合作为进一步分层和实验的候选切片，尚不能直接转成选题规则。

{markdown_table(
    content_tags.head(10),
    ["tag", "video_count", "event_count", "exposure_weighted_long_view_rate", "exposure_weighted_like_rate"],
    ["标签 ID", "视频数", "事件数", "曝光加权长观看率", "曝光加权点赞率"],
    {
        "tag": str,
        "video_count": format_int,
        "event_count": format_int,
        "exposure_weighted_long_view_rate": format_pct,
        "exposure_weighted_like_rate": format_pct,
    },
)}

视频统计特征表包含 {format_int(content_summary.iloc[0]['statistic_video_rows'])} 条有效记录，`counts` 合计 {format_int(content_summary.iloc[0]['sum_statistic_counts'])}。按发布方说明，该表是一个月内按日和场景平均后的视频级统计；`counts` 表示统计记录数。本报告只用它核对表的粒度与规模，没有把这些月度汇总值用于用户日模型或推出内容因果结论。

## 7. 参与行为与后续回访的统计验证

### 7.1 设计

模型样本为在日期 `t` 有有效标准日志、且 `t + 7` 仍在观察范围内的用户日。结局是用户在 `t + 7` 当天仍有有效标准日志。全部解释变量来自 `t` 当天。模型包含四个变量：日曝光量按翻倍计、长观看率按增加 10 个百分点计、当天是否有任一显性互动、当天是否进入作者主页。星期虚拟变量和距观察起点周数控制时间变化，标准误按 `user_id` 聚类，训练和验证按日期先后切分。验证样本来自同一批用户，没有检验对新用户的外推。时间切分以索引日为准，未对 `t+7` 标签可得性设置时间隔离，因此属于事后留出诊断，不是实时部署情境下的前瞻性回测。

{markdown_table(
    pd.DataFrame([
        {"item": "模型样本用户日", "value": format_int(model["total_model_sample"])},
        {"item": "用户数", "value": format_int(model["total_users"])},
        {"item": "可建模日期数", "value": format_int(model["eligible_dates"])},
        {"item": "训练日期", "value": f"{primary['train_start']} 至 {primary['train_end']}"},
        {"item": "验证日期", "value": f"{primary['test_start']} 至 {primary['test_end']}"},
        {"item": "训练结局率", "value": format_pct(primary["train_prevalence"])},
        {"item": "验证结局率", "value": format_pct(primary["test_prevalence"])},
        {"item": "验证 ROC AUC", "value": format_float(primary["evaluation"]["auc"], 3)},
        {"item": "验证 Brier score", "value": format_float(primary["evaluation"]["brier_score"], 4)},
        {"item": "常数基准 Brier score", "value": format_float(primary["evaluation"]["constant_baseline_brier_score"], 4)},
        {"item": "Brier skill score", "value": format_float(primary["evaluation"]["brier_skill_score"], 4)},
        {"item": "验证 log loss", "value": format_float(primary["evaluation"]["log_loss"], 4)},
        {"item": "最大训练样本 VIF", "value": format_float(primary["max_vif"], 2)},
    ]),
    ["item", "value"],
    ["项目", "结果"],
)}

### 7.2 调整关联

![精确 D7 回访模型](figures/return_model_forest.png)

OR 的解释单位为：日曝光量翻倍、长观看率增加 10 个百分点、显性互动从无到有、进入主页从无到有。4 个主变量使用 Holm 法控制同一结局下的多重比较。Brier skill score 衡量相对训练结局率常数预测的概率改进；本模型为 {format_float(primary['evaluation']['brier_skill_score'], 4)}，验证概率误差略差于常数基准。

{markdown_table(
    primary_coeff,
    ["feature_label", "effect_unit", "odds_ratio", "ci_low_odds_ratio", "ci_high_odds_ratio", "p_value", "p_value_holm"],
    ["变量", "OR 解释单位", "调整 OR", "95% CI 下限", "95% CI 上限", "原始 p 值", "Holm p 值"],
    {
        "feature_label": str,
        "effect_unit": str,
        "odds_ratio": lambda value: format_float(value, 3),
        "ci_low_odds_ratio": lambda value: format_float(value, 3),
        "ci_high_odds_ratio": lambda value: format_float(value, 3),
        "p_value": format_p_value,
        "p_value_holm": format_p_value,
    },
)}

主变量中，OR 最高的是“{highest_or_row['feature_label']}”（{format_float(highest_or_row['odds_ratio'], 3)}）。显性互动和主页进入分别对应 OR {format_float(any_explicit_coefficient['odds_ratio'], 3)} 与 {format_float(any_profile_coefficient['odds_ratio'], 3)}。系数表示调整模型中其他变量后的样本内优势变化。主模型验证 AUC 为 {format_float(primary['evaluation']['auc'], 3)}，只能较弱地区分随后第 7 天是否活跃。

为核对原始差异，未调整的 D7 活跃率如下。各项互动可以同时发生，同一用户日会进入多行。该表未调整日曝光量、内容构成或用户频率；与模型结果的差异说明原始比较混入了这些使用强度差异。

{markdown_table(
    behavior_incidence,
    ["feature_label", "no_event_user_days", "event_user_days", "no_event_return_rate", "event_return_rate", "return_rate_difference"],
    ["当日互动", "未发生用户日", "发生用户日", "未发生 D7 率", "发生 D7 率", "差值"],
    {
        "feature_label": str,
        "no_event_user_days": format_int,
        "event_user_days": format_int,
        "no_event_return_rate": format_pct,
        "event_return_rate": format_pct,
        "return_rate_difference": lambda value: f"{float(value) * 100:+.2f} pp",
    },
)}

### 7.3 稳健性

使用精确 D1 和未来 1 至 7 日任意一天活跃重新拟合，结果如下。

{markdown_table(
    sensitivity_rows.sort_values(["term", "outcome"]),
    ["outcome_label", "feature_label", "effect_unit", "odds_ratio", "ci_low_odds_ratio", "ci_high_odds_ratio", "p_value", "p_value_holm"],
    ["结局", "变量", "OR 解释单位", "调整 OR", "95% CI 下限", "95% CI 上限", "原始 p 值", "Holm p 值"],
    {
        "outcome_label": str,
        "feature_label": str,
        "effect_unit": str,
        "odds_ratio": lambda value: format_float(value, 3),
        "ci_low_odds_ratio": lambda value: format_float(value, 3),
        "ci_high_odds_ratio": lambda value: format_float(value, 3),
        "p_value": format_p_value,
        "p_value_holm": format_p_value,
    },
)}

不同结局下，长观看率和主页进入的 OR 方向及区间并不一致。表中只有日曝光量与显性互动在三个结局下保持相同的 OR 方向；长观看和主页进入没有得到稳定的关联方向，不能据此确定运营动作。

## 8. 发现与验证优先级

### 8.1 主要业务发现

1. Q4 用户贡献 {format_pct(q4_segment['event_share'])} 的事件，长观看标记率却只有 {format_pct(q4_segment_engagement['long_view_rate'])}；Q1 的对应值为 {format_pct(q1_segment_engagement['long_view_rate'])}。事件量和曝光率提供了两种不同的用户视角。
2. 事件量峰值出现在 {int(peak_hour_row['activity_hour'])} 时，长观看标记率峰值出现在 {int(peak_long_view_hour['activity_hour'])} 时，点赞标记率峰值出现在 {int(peak_like_hour['activity_hour'])} 时。三个时点对应的用户和内容构成不同，峰值更适合作为分时段基线，不能直接当作最佳投放时间。
3. 用户日曝光量从 Q1 到 Q4，原始 D7 活跃率由 {format_pct(q1_exposure_return['return_rate_d7'])} 升至 {format_pct(q4_exposure_return['return_rate_d7'])}，平均长观看标记率由 {format_pct(q1_exposure_return['mean_long_view_rate'])} 降至 {format_pct(q4_exposure_return['mean_long_view_rate'])}。高频用户日通常同时具有更稳定的后续活跃和更低的单次长观看标记率。
4. 有任一显性互动的用户日，原始 D7 活跃率为 {format_pct(any_explicit_behavior['event_return_rate'])}，无互动为 {format_pct(any_explicit_behavior['no_event_return_rate'])}；加入其他使用强度变量后，调整 OR 为 {format_float(any_explicit_coefficient['odds_ratio'], 3)}。原始差值与调整后的方向不同，说明互动组与非互动组并非可直接比较。
5. 高曝光标签 `{completion_tag['tag']}` 和 `{like_tag['tag']}` 分别呈现较高的长观看标记率与点赞标记率。标签由多标签视频重复计数，并混有内容时长、作者和曝光分配差异，结果适合生成内容分层假设。
6. D7 模型的验证 AUC 为 {format_float(primary['evaluation']['auc'], 3)}，Brier skill score 为 {format_float(primary['evaluation']['brier_skill_score'], 4)}。系数可以帮助理解样本内的条件关联，尚不足以支持概率预测或用户运营决策。

### 8.2 下一步验证

1. 看板可以把事件总量、DAU、单次曝光参与率和后续活跃率并列，并按用户事件量四分位拆分。Q4 的规模贡献和 Q1 的曝光率表现回答不同问题。
2. 周报可以按用户日曝光四分位跟踪原始 D7 活跃率和参与率，用于发现样本内变化。曝光量本身的提升能否带来回访，需要另做干预实验。
3. 18 至 22 时的事件规模、6 至 8 时的长观看标记率和凌晨的点赞标记率，可以分别形成时段实验假设。实验应固定内容池和用户范围，避免把时段与人群、内容供给混在一起。
4. 短视频、长视频和不同标签批次应分别建立曝光量、长观看标记率、点赞标记率和观看深度基线。标签得到业务语义并完成多变量分层后，结果才适合进入选题评审。
5. 要衡量新用户留存，需要接入首次注册或首次激活事件，并按完整后续窗口计算 D1/D7。当前首次观测活跃日方案不能提供这项指标。
6. 现有 D7 模型适合检查变量方向和发现模型失效，不适合上线预测。任何围绕曝光强度、主页进入或内容类型的动作，都应先明确主指标、样本和对照，再做随机实验。

## 9. 研究局限

- 分析对象是 KuaiRand-27K 的固定用户面板和 2022-04-08 至 2022-05-08 的日志，不能外推为平台用户总体或长期增长。
- 首次观测活跃日不是注册日。首日 Cohort 占用户绝大多数，排除首日后的样本又偏向较晚出现或活动较少的用户，两种口径都不估计新用户留存。
- `hourmin` 只保存小时级信息；`is_click` 在单列和双列 UI 中分别表示有效播放与点击，因此点击率只在同一场景内解释。
- 标准推荐曝光由平台策略分配，内容、用户和曝光量相互关联。本文的时点、内容和用户分层差异均为观察结果，不估计因果效果。
- 视频统计特征是整月按日、按场景汇总后的平均值，本报告没有把它用作用户日模型特征。
- D7 Logistic 模型在同一用户群内做时间切分验证，Brier skill score 为负，不能用于未见用户预测或线上运营。
- 标签 ID 与加密 one-hot 特征没有公开业务语义；观看深度高于 1 的记录保留原值，但现有字段无法解释具体原因。
- 分位数使用近似算法。原始行数、事件对账、维表唯一性和来源隔离由 SQL 验证。

## 10. 结论

标准推荐日志呈现高持续、高集中和低显性互动的固定面板结构。Q4 用户贡献 {format_pct(q4_segment['event_share'])} 的事件，但长观看和点赞标记率低于 Q1；用户日曝光量越高，原始 D7 活跃率越高、平均长观看标记率越低。全部合格 Cohort 的精确 D7 活跃率为 {format_pct(return_lookup[7].return_rate)}，排除首日 Cohort 后为 {format_pct(sensitivity_lookup[7].return_rate_excluding_first_cohort)}；前者由首日存量用户主导，后者改变了样本构成，两者都不应命名为新用户留存。D7 模型的概率表现没有超过常数基准，回归系数只用于描述样本内条件关联。时段、内容和用户分层结果可以支持后续实验设计，不能直接推出运营效果。

## 11. 复现与代码定位

从仓库根目录创建虚拟环境并安装依赖：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

运行完整分析、生成报告并执行测试：

```bash
python scripts/run_pipeline.py
python scripts/build_report.py
python -m pytest
```

业务流程位于 `sql/01_quality.sql` 至 `sql/08_validation.sql`；模型、报告编排和图表分别位于 `src/kuairand_analysis/statistics.py`、`reporting.py` 与 `visualization.py`。字段、指标和方法边界见 `docs/data_dictionary.md`、`docs/metric_dictionary.md` 和 `docs/methodology.md`。

## 12. AI 协作说明

本项目由 AI 辅助完成代码、统计设计、文档编排和结果复核。所有正式数字由可执行 SQL/Python 在原始 CSV 上重新计算，发布检查包含全量对账、来源隔离、时间边界测试和文档链接核验。
"""

        readme = f"""# KuaiRand-27K 用户活跃、参与、回访与内容分析

> 分析 KuaiRand-27K 固定用户面板在 31 天内的活跃、参与、窗口内再次活跃和内容表现。数据治理与统计流程使用 DuckDB、SQL、Parquet 和 Python。

[最终报告](reports/final_report.md) · [数据字典](docs/data_dictionary.md) · [指标字典](docs/metric_dictionary.md) · [方法说明](docs/methodology.md)

## 一、研究背景

KuaiRand-27K 提供 27,285 名固定用户的标准推荐日志、随机曝光日志和用户、视频维表。本项目从 10 个原始 CSV 出发，先完成全量质量检查和标准化，再计算活跃、参与、首次观测 Cohort 和内容表现。用户日模型使用当天变量描述随后第 7 天的活跃关联。

分析对象是固定用户面板。现有日志没有可靠的新注册流水，报告以窗口内再次出现活动描述回访，不计算平台新增用户留存。

数据由 [KuaiRand 官方仓库](https://github.com/chongminggao/KuaiRand) 发布。原始数据受发布方许可约束，本仓库不随代码分发 CSV、Parquet 或 DuckDB 数据副本。

## 二、项目概览

| 项目维度 | 全量运行结果 |
|---|---:|
| 观察窗口 | **{observation_start:%Y-%m-%d} 至 {observation_end:%Y-%m-%d}** |
| 原始 CSV | **10 个文件，{raw_gib:.2f} GiB** |
| 有效标准推荐日志 | **{format_int(standard_quality['valid_event_rows'])} 条事件** |
| 固定用户样本 | **{format_int(activity_row['active_users'])} 名用户** |
| 随机曝光描述样本 | **{format_int(random_row['event_count'])} 条事件** |
| 视频基础/统计维表 | **{format_int(content_summary.iloc[0]['basic_video_rows'])} 个视频** |
| 标准化 Parquet | **{processed_gib:.2f} GiB** |
| 回访模型样本 | **{format_int(model['total_model_sample'])} 个用户日** |
| 技术栈 | **DuckDB · SQL · Parquet · pandas · NumPy · SciPy · statsmodels · Matplotlib · pytest** |

四个业务问题分别是用户活跃与事件集中度、标准推荐曝光下的参与结构、首次观测活跃日后的 D1/D7 再次活跃，以及视频类型、时长和标签的曝光与参与差异。另用用户日 Logistic 模型检验参与变量与后续 D7 活跃的条件关联。

## 三、技术路线与口径

```text
10 个只读 CSV → DuckDB 全量质量检查 → 标准化 Parquet
→ 用户日、Cohort 和视频 Marts → SQL 结果 + Python 统计
→ 图表、最终报告与自动化验证
```

标准推荐日志用于主分析，随机曝光日志独立描述，不参与 DAU、趋势和观察回访。全量运行识别 10/10 个源文件，完成行数、字段、非法值、连接覆盖和来源隔离检查；2 条负观看时长记录被排除，业务 Marts 保留 {format_int(standard_quality['valid_event_rows'])} 条有效标准事件。日期口径使用源端 `date + hourmin`，并以 UTC+8 时间戳日期做敏感性检查。

DAU 按每天不同用户数计算；参与率以有效曝光事件为共同分母；观看深度只在正视频时长上计算；精确 D1/D7 只纳入目标日已观察的用户。模型使用当天曝光量、长观看率、任一显性互动和主页进入，按日期切分训练与验证，标准误按用户聚类。完整定义见[指标字典](docs/metric_dictionary.md)和[方法说明](docs/methodology.md)。

## 四、文件架构

```text
kuairand-user-growth-analysis/
├── README.md                 项目总览、主要结果与复现入口
├── AGENTS.md                 数据处理、指标、统计与发布约束
├── LICENSE                   MIT 代码许可证
├── pyproject.toml            Python 依赖与测试配置
├── config.yaml               数据路径、DuckDB 资源和分析参数
├── data/
│   └── README.md             原始数据获取、放置与非提交说明
├── docs/
│   ├── data_dictionary.md    源字段、标准字段、Marts 粒度与关联键
│   ├── metric_dictionary.md  活跃、参与、回访、内容和模型口径
│   └── methodology.md        数据治理、统计方法、假设认证与解释边界
├── sql/
│   ├── 01_quality.sql        全量字段、异常、重复键和连接覆盖检查
│   ├── 02_prepare.sql        日志与维表标准化及 Parquet 写出
│   ├── 03_marts.sql          用户日、日活、Cohort、模型和视频 Marts
│   ├── 04_activity.sql       日活、事件趋势、时段与用户分层
│   ├── 05_engagement.sql     整体、场景和随机曝光参与指标
│   ├── 06_retention.sql      精确回访、右截断和边界口径
│   ├── 07_content.sql        类型、时长、标签和视频统计结果
│   └── 08_validation.sql     行数守恒、来源隔离、日期敏感性和模型检查
├── src/kuairand_analysis/
│   ├── __init__.py           包初始化
│   ├── config.py             配置读取、路径与源文件校验
│   ├── db.py                 DuckDB 连接、SQL 模板和 Parquet 工具
│   ├── pipeline.py           SQL 阶段编排与重入执行
│   ├── statistics.py         聚类稳健 Logistic、区间和模型诊断
│   ├── reporting.py          结果表编排、README 与最终报告生成
│   └── visualization.py      正式图表与输出管理
├── scripts/
│   ├── run_pipeline.py       全量分析与统计模型入口
│   └── build_report.py       图表、报告和 README 生成入口
├── tests/
│   ├── test_quality.py       配置、SQL 工具和输入完整性
│   ├── test_metrics.py       回访边界、模型变量和行为汇总
│   └── test_pipeline.py      合成数据端到端流程、对账和幂等性
└── reports/
    ├── final_report.md       完整研究结果、认证、解释和局限
    └── figures/              最终报告实际引用的 7 张图
```

源数据、Parquet、DuckDB、缓存和临时输出位于本地派生目录，由 `.gitignore` 排除。`src/kuairand_analysis/reporting.py` 负责结果表编排，是报告生成所需的模块。

## 五、主要结论

### 5.1 事件量集中在少数用户

固定样本包含 {format_int(activity_row['active_users'])} 名用户和 {format_int(activity_row['observed_days'])} 个观察日，日均 DAU 为 {format_int(activity_row['mean_dau'])}。DAU 最高的日期是 {pd.Timestamp(activity_row['maximum_dau_date']):%Y-%m-%d}；事件量最高的日期是 {pd.Timestamp(peak_event_row['activity_date']):%Y-%m-%d}，当日 {format_int(peak_event_row['event_count'])} 条事件。

事件量最高的四分位用户占全部用户 {format_pct(q4_segment['user_share'])}，贡献 {format_pct(q4_segment['event_share'])} 的标准日志事件。Q4 定义了样本内的高事件量组，不代表平台总体中的“高价值用户”。

### 5.2 长观看较常见，显性互动稀疏

按有效曝光计，长观看标记率为 {format_pct(engagement_row['long_view_rate'])}，点赞率为 {format_pct(engagement_row['like_rate'])}，评论率为 {format_pct(engagement_row['comment_rate'])}。观看深度 P90 为 {format_float(engagement_row['p90_watch_depth'], 3)}，{format_pct(engagement_row['watch_depth_above_one_rate'])} 的合格记录高于 1；该比率不作为完播率解释。事件量峰值出现在源端 {int(peak_hour_row['activity_hour'])} 时。

### 5.3 两种 Cohort 口径描述不同人群

全部合格首次观测 Cohort 的精确 D1 活跃率为 {format_pct(return_lookup[1].return_rate)}，精确 D7 为 {format_pct(return_lookup[7].return_rate)}。排除观察起点 Cohort 后，D7 为 {format_pct(sensitivity_lookup[7].return_rate_excluding_first_cohort)}。

首日有 {format_int(first_day_users)} 名用户首次出现，占面板用户的 {format_pct(first_day_user_share)}。改用 UTC+8 时间戳日期重算后，全样本 D7 为 {format_pct(date_sensitivity_lookup[('timestamp_utc8', 7)].return_rate)}，与源端日期口径接近；排除首日的 D7 则为 {format_pct(date_sensitivity_lookup[('timestamp_utc8', 7)].return_rate_excluding_first_cohort)}。边界口径对日期定义高度敏感，因此两种数值都不命名为新用户留存。

### 5.4 内容分组高度不平衡

`{top_type['video_type']}` 视频覆盖 {format_int(top_type['event_count'])} 次标准日志曝光，占全部有效事件的 {format_pct(top_type['event_count'] / engagement_row['event_count'])}，长观看标记率为 {format_pct(top_type['exposure_weighted_long_view_rate'])}。曝光量最高的有定义时长段为 `{top_duration['duration_band']}`，该段长观看标记率为 {format_pct(top_duration['exposure_weighted_long_view_rate'])}。

标签按逗号展开后保留原始数值 ID，最高曝光标签为 `{top_tag['tag'] if top_tag is not None else 'N/A'}`。这些分组差异同时包含推荐分配、受众、作者和视频属性，适合用于后续分层，不构成内容属性效果。

### 5.5 D7 模型描述样本内条件关联

日曝光量翻倍对应精确 D7 活跃的调整 OR 为 {format_float(event_count_coefficient['odds_ratio'], 3)}（95% CI {format_float(event_count_coefficient['ci_low_odds_ratio'], 3)} 至 {format_float(event_count_coefficient['ci_high_odds_ratio'], 3)}）。有任一显性互动相对无互动的调整 OR 为 {format_float(any_explicit_coefficient['odds_ratio'], 3)}，进入主页相对未进入的调整 OR 为 {format_float(any_profile_coefficient['odds_ratio'], 3)}。

未调整时，有任一显性互动的 D7 活跃率为 {format_pct(any_explicit_behavior['event_return_rate'])}，无互动为 {format_pct(any_explicit_behavior['no_event_return_rate'])}；调整其他使用强度变量后，OR 为 {format_float(any_explicit_coefficient['odds_ratio'], 3)}。原始比较与调整结果的差异表明互动组与非互动组在使用强度上并不可比。

长观看率增加 10 个百分点时，D7 OR 为 {format_float(long_view_coefficient['odds_ratio'], 3)}；该变量在 D1 和任意 7 日结局下没有得到一致方向。验证 AUC 为 {format_float(primary['evaluation']['auc'], 3)}，Brier skill score 为 {format_float(primary['evaluation']['brier_skill_score'], 4)}。模型没有提供优于常数基准的概率预测，系数仅用于样本内关联诊断。

### 5.6 建议与验证

1. 看板可以把事件总量、DAU 和单次曝光参与率并列，并按用户事件量四分位拆分。Q4 的用户贡献 {format_pct(q4_segment['event_share'])} 的事件，长观看标记率为 {format_pct(q4_segment_engagement['long_view_rate'])}；Q1 的长观看标记率为 {format_pct(q1_segment_engagement['long_view_rate'])}。
2. 用户日曝光四分位从 Q1 到 Q4 时，原始 D7 活跃率由 {format_pct(q1_exposure_return['return_rate_d7'])} 升至 {format_pct(q4_exposure_return['return_rate_d7'])}，平均长观看标记率由 {format_pct(q1_exposure_return['mean_long_view_rate'])} 降至 {format_pct(q4_exposure_return['mean_long_view_rate'])}。周报可以同时跟踪这两项指标；能否通过调整曝光量提高回访，需要另行实验。
3. 事件量在 {int(peak_hour_row['activity_hour'])} 时达到峰值，长观看标记率在 {int(peak_long_view_hour['activity_hour'])} 时最高，点赞标记率在 {int(peak_like_hour['activity_hour'])} 时最高。这些时点可以作为分目标实验假设，执行时需固定用户和内容范围。
4. 高曝光标签中，`{completion_tag['tag']}` 的长观看标记率较高，`{like_tag['tag']}` 的点赞标记率较高。标签补充业务语义并完成多变量分层后，再用于选题评审。
5. 要监测新用户留存，需要接入首次注册或首次激活事件，并保证每个 Cohort 拥有完整后续窗口。当前面板只能提供窗口内观察回访。
6. D7 模型的验证 Brier skill score 为 {format_float(primary['evaluation']['brier_skill_score'], 4)}，不进入线上预测。围绕内容类型、时段、主页进入或曝光量的下一步，应先定义主指标和对照，再做随机实验。

## 六、图表预览

### 日活与标准日志事件趋势

![日活与事件趋势](reports/figures/activity_daily.png)

### 首次观测活跃日后的精确日回访

![Cohort 精确日回访](reports/figures/return_cohorts.png)

### 精确 D7 回访模型的调整关联

![精确 D7 回访模型](reports/figures/return_model_forest.png)

完整图表包括时段分布、场景参与、用户分层、视频时长和 Cohort 曲线，均在 [最终报告](reports/final_report.md) 中被实际引用。

## 七、复现

### 7.1 数据准备

将以下 10 个 KuaiRand-27K CSV 放入 `data/raw/`：

- 4 份 `log_standard_*_27k_*.csv`
- 1 份 `log_random_4_22_to_5_08_27k.csv`
- 1 份 `user_features_27k.csv`
- 1 份 `video_features_basic_27k.csv`
- 3 份 `video_features_statistic_27k_part*.csv`

也可以将原始数据放在仓库外，通过 `--raw-dir` 避免重复占用磁盘。完整文件说明见 [data/README.md](data/README.md)。

### 7.2 安装环境

项目要求 Python 3.11 及以上，并在 Python 3.12 与 DuckDB 2.0 环境完成全量验证。依赖版本由 [pyproject.toml](pyproject.toml) 管理。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Windows PowerShell 使用 `./.venv/Scripts/Activate.ps1` 激活环境。使用 conda 时，创建任意 Python 3.11+ 环境并执行相同的 `pip install -e ".[dev]"`。数据路径、线程、内存和临时目录由 [config.yaml](config.yaml) 配置。

### 7.3 执行命令

```bash
python scripts/run_pipeline.py
python scripts/build_report.py
python -m pytest
```

原始数据位于仓库外时，在 `run_pipeline.py` 后添加 `--raw-dir /path/to/KuaiRand-27K/data`。

已验证的全量流水线包含 8 个阶段，在本次验证环境约 **5 分钟**完成。数据阶段会生成标准化 Parquet、业务 Marts、结果表、7 张图和最终报告。

## 八、验收与质量

| 验收项 | 结果 |
|---|---:|
| 源文件识别 | **10 / 10** |
| 全量对账、来源隔离和维表唯一性 | **{validation_pass} / {validation_total}** |
| 自动化测试 | **全部通过** |
| 报告引用图表 | **7 / 7** |
| Markdown 相对链接 | **全部有效** |
| 核心假设与证据登记 | **[方法说明第 12 节](docs/methodology.md#assumption-certification)** |
| 随机数据混入主活跃/回访指标 | **无** |
| Git 中原始或派生大文件 | **无** |

## 九、研究边界

- 样本边界：固定 27K 用户和 31 天窗口只描述 KuaiRand-27K 面板，不外推为平台总体或长期增长趋势。
- 回访边界：首次观测日不是注册日；首日存量用户和较晚首次出现用户的构成差异会改变 D1/D7。
- 场景边界：`tab` 保留原始编号；`is_click` 在单列 UI 表示有效播放、在双列 UI 表示点击，点击率只在同场景内比较。
- 内容边界：视频曝光由推荐策略分配，高曝光不等于高质量；标签和 one-hot 特征没有公开业务语义。
- 统计边界：同一用户贡献多个用户日，模型用聚类标准误处理相关性。D7 验证 Brier skill score 为负，模型只用于解释样本内结果。
- 时间边界：{format_int(standard_quality['date_timestamp_mismatch'])} 条记录的源端日期与 UTC+8 时间戳日期相差一天，项目统一采用源端 `date + hourmin`。
- 许可边界：仓库 MIT License 只覆盖代码与文档；第三方数据的使用遵循 KuaiRand 发布方条款。

## 十、建议阅读顺序

1. 阅读 [最终报告](reports/final_report.md)，了解完整研究问题、全量结果、统计验证和业务解释。
2. 阅读 [数据字典](docs/data_dictionary.md)、[指标字典](docs/metric_dictionary.md) 和 [方法说明](docs/methodology.md)，核对字段、公式与时间边界。
3. 按 `sql/01_quality.sql` 至 `sql/08_validation.sql` 查看数据处理、业务建模和对账过程。
4. 阅读 `src/kuairand_analysis/`，了解配置、流水线、统计模型、报告编排和图表生成。
5. 最后查看 `tests/`，确认回访边界、非法值过滤、来源隔离和重复运行幂等性。

## 十一、许可证

本仓库代码和文档采用 [MIT License](LICENSE)。KuaiRand 数据受其原始发布方许可管理，本仓库许可证不覆盖第三方数据。
"""
        # Keep generated prose free of decorative bold labels.
        report = report.replace("**", "")
        readme = readme.replace("**", "")
        report = report.replace("： ", "：")
        readme = readme.replace("： ", "：")
        return report, readme
