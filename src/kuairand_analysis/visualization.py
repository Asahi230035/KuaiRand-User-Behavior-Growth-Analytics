"""Publication figures generated from verified result tables."""

from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter

from .config import AnalysisConfig
from .db import query_df, sql_literal


COLORS = {
    "navy": "#274C77",
    "teal": "#2A9D8F",
    "gold": "#E9C46A",
    "orange": "#F4A261",
    "red": "#E76F51",
    "gray": "#6C757D",
    "light": "#DDE7F0",
}

FIGURE_FILES = {
    "daily": "activity_daily.png",
    "hourly": "activity_hourly.png",
    "tabs": "engagement_by_tab.png",
    "segments": "user_segments.png",
    "cohorts": "return_cohorts.png",
    "content": "content_duration.png",
    "forest": "return_model_forest.png",
}

FEATURE_PLOT_LABELS = {
    "log2_event_count": "Daily events (2x)",
    "long_view_rate_10pp": "Long-view rate (+10 pp)",
    "any_explicit_interaction": "Any explicit interaction",
    "any_profile_enter": "Profile entry",
    "week_index": "Week index",
}


class VisualizationBuilder:
    """Build only the figures referenced by the final report."""

    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        config: AnalysisConfig,
    ):
        self.connection = connection
        self.config = config
        self.figure_dir = config.figures_dir
        self.figure_dir.mkdir(parents=True, exist_ok=True)
        plt.rcParams.update(
            {
                "figure.dpi": 130,
                "savefig.dpi": 190,
                "font.family": "DejaVu Sans",
                "axes.titlesize": 12,
                "axes.labelsize": 10,
                "xtick.labelsize": 9,
                "ytick.labelsize": 9,
                "legend.fontsize": 9,
                "axes.spines.top": False,
                "axes.spines.right": False,
            }
        )

    def _result(self, name: str) -> pd.DataFrame:
        path = self.config.results_dir / f"{name}.parquet"
        if not path.is_file():
            raise FileNotFoundError(f"Result table not found: {path}")
        return query_df(
            self.connection,
            f"SELECT * FROM read_parquet({sql_literal(path)})",
        )

    def _save(self, figure: plt.Figure, key: str) -> Path:
        path = self.figure_dir / FIGURE_FILES[key]
        figure.savefig(path, bbox_inches="tight", facecolor="white")
        plt.close(figure)
        return path

    def build_daily_activity(self) -> Path:
        data = self._result("daily_activity")
        dates = pd.to_datetime(data["activity_date"])
        figure, axes = plt.subplots(
            2,
            1,
            figsize=(10.5, 6.1),
            sharex=True,
            gridspec_kw={"height_ratios": [1.45, 1]},
        )
        axes[0].bar(
            dates,
            data["event_count"] / 1_000_000,
            color=COLORS["light"],
            width=0.8,
            label="Standard-log events",
        )
        axes[0].set_ylabel("Events (million)")
        axes[0].set_title("Daily activity in the observed standard-recommendation sample")
        axes[0].grid(axis="y", color="#E8EDF2", linewidth=0.8)

        axes[1].plot(
            dates,
            data["dau"] / 1_000,
            color=COLORS["navy"],
            marker="o",
            markersize=3,
            linewidth=1.8,
        )
        axes[1].set_ylabel("DAU (thousand)")
        axes[1].fill_between(
            dates,
            data["dau"] / 1_000,
            color=COLORS["navy"],
            alpha=0.10,
        )
        axes[1].grid(axis="y", color="#E8EDF2", linewidth=0.8)
        for axis in axes:
            axis.axvspan(
                pd.Timestamp("2022-04-22") - pd.Timedelta(hours=12),
                dates.max() + pd.Timedelta(hours=12),
                color=COLORS["gold"],
                alpha=0.08,
                label="Second file period",
            )
        axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        axes[1].xaxis.set_major_locator(mdates.DayLocator(interval=3))
        axes[0].legend(loc="upper left", frameon=False)
        figure.tight_layout()
        return self._save(figure, "daily")

    def build_hourly_activity(self) -> Path:
        data = self._result("hourly_profile").sort_values("activity_hour")
        figure, axes = plt.subplots(1, 3, figsize=(12.5, 3.8))
        axes[0].bar(
            data["activity_hour"],
            data["event_share"],
            color=COLORS["teal"],
            width=0.78,
        )
        axes[0].set_title("Share of standard-log events by source hour")
        axes[0].set_xlabel("Hour from date + hourmin")
        axes[0].set_ylabel("Share of events")
        axes[0].yaxis.set_major_formatter(PercentFormatter(1.0))
        axes[0].set_xticks(range(0, 24, 3))
        axes[0].grid(axis="y", color="#E8EDF2", linewidth=0.8)

        axes[1].plot(
            data["activity_hour"],
            data["long_view_rate"],
            color=COLORS["teal"],
            marker="o",
            linewidth=1.8,
        )
        axes[1].set_title("Long-view rate by source hour")
        axes[1].set_xlabel("Hour from date + hourmin")
        axes[1].set_ylabel("Long-view rate")
        axes[1].yaxis.set_major_formatter(PercentFormatter(1.0))
        axes[1].set_xticks(range(0, 24, 3))
        axes[1].grid(axis="y", color="#E8EDF2", linewidth=0.8)

        axes[2].plot(
            data["activity_hour"],
            data["like_rate"],
            color=COLORS["gold"],
            marker="o",
            linewidth=1.8,
        )
        axes[2].set_title("Like rate by source hour")
        axes[2].set_xlabel("Hour from date + hourmin")
        axes[2].set_ylabel("Like rate")
        axes[2].yaxis.set_major_formatter(PercentFormatter(1.0))
        axes[2].set_xticks(range(0, 24, 3))
        axes[2].grid(axis="y", color="#E8EDF2", linewidth=0.8)
        figure.tight_layout()
        return self._save(figure, "hourly")

    def build_engagement_tabs(self) -> Path:
        data = self._result("engagement_by_tab").head(8).copy()
        data = data.sort_values("event_count")
        labels = [f"tab {int(value)}" for value in data["tab"]]
        figure, axes = plt.subplots(1, 2, figsize=(10.5, 4.1), sharey=True)
        axes[0].barh(labels, data["event_share"], color=COLORS["navy"])
        axes[0].set_title("Share of exposure events")
        axes[0].set_xlabel("Share")
        axes[0].xaxis.set_major_formatter(PercentFormatter(1.0))

        axes[1].barh(
            labels,
            data["long_view_rate"],
            color=COLORS["teal"],
            label="Long-view rate",
        )
        axes[1].barh(
            labels,
            data["like_rate"],
            height=0.42,
            color=COLORS["gold"],
            label="Like rate",
        )
        axes[1].set_title("Long-view and like flags per exposure")
        axes[1].set_xlabel("Event-weighted flag rate")
        axes[1].xaxis.set_major_formatter(PercentFormatter(1.0))
        axes[1].legend(loc="lower right", frameon=False)
        for axis in axes:
            axis.grid(axis="x", color="#E8EDF2", linewidth=0.8)
        figure.tight_layout()
        return self._save(figure, "tabs")

    def build_user_segments(self) -> Path:
        segments = self._result("user_segments")
        engagement = self._result("user_segment_engagement")
        data = segments.merge(
            engagement[
                ["active_segment", "long_view_rate", "like_rate"]
            ],
            on="active_segment",
            how="left",
        ).sort_values("active_segment")
        figure, axes = plt.subplots(1, 2, figsize=(10.5, 3.9))
        width = 0.34
        x = np.arange(len(data))
        axes[0].bar(
            x - width / 2,
            data["user_share"],
            width=width,
            color=COLORS["navy"],
            label="User share",
        )
        axes[0].bar(
            x + width / 2,
            data["event_share"],
            width=width,
            color=COLORS["orange"],
            label="Event share",
        )
        axes[0].set_xticks(x, data["active_segment"])
        axes[0].set_title("User and event concentration by activity quartile")
        axes[0].set_ylabel("Share")
        axes[0].yaxis.set_major_formatter(PercentFormatter(1.0))
        axes[0].legend(frameon=False)
        axes[0].grid(axis="y", color="#E8EDF2", linewidth=0.8)

        axes[1].bar(
            x - 0.18,
            data["long_view_rate"],
            color=COLORS["teal"],
            width=0.36,
            label="Long-view rate",
        )
        axes[1].bar(
            x + 0.18,
            data["like_rate"],
            color=COLORS["gold"],
            width=0.36,
            label="Like rate",
        )
        axes[1].set_xticks(x, data["active_segment"])
        axes[1].set_title("Per-exposure engagement by activity quartile")
        axes[1].set_ylabel("Event-weighted flag rate")
        axes[1].yaxis.set_major_formatter(PercentFormatter(1.0))
        axes[1].legend(frameon=False)
        axes[1].grid(axis="y", color="#E8EDF2", linewidth=0.8)
        figure.tight_layout()
        return self._save(figure, "segments")

    def build_return_cohorts(self) -> Path:
        data = self._result("cohort_retention")
        data = data[data["eligible_users"] >= 30].copy()
        data["cohort_date"] = pd.to_datetime(data["cohort_date"])
        pivot = data.pivot_table(
            index="cohort_date",
            columns="offset_day",
            values="return_rate",
            aggfunc="first",
        )
        figure, axis = plt.subplots(figsize=(10.5, 4.3))
        styles = {
            1: (COLORS["navy"], "o"),
            3: (COLORS["gold"], "s"),
            7: (COLORS["teal"], "^"),
        }
        for offset in [1, 3, 7]:
            if offset not in pivot.columns:
                continue
            series = pivot[offset].dropna()
            color, marker = styles[offset]
            axis.plot(
                series.index,
                series.values,
                label=f"Exact D{offset}",
                color=color,
                marker=marker,
                markersize=4,
                linewidth=1.8,
            )
        axis.set_title(
            "Observed exact-day return by cohort (at least 30 eligible users)"
        )
        axis.set_ylabel("Return rate among eligible users")
        axis.yaxis.set_major_formatter(PercentFormatter(1.0))
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        axis.xaxis.set_major_locator(mdates.DayLocator(interval=3))
        axis.grid(axis="y", color="#E8EDF2", linewidth=0.8)
        axis.legend(frameon=False, ncols=3, loc="upper right")
        figure.tight_layout()
        return self._save(figure, "cohorts")

    def build_content_duration(self) -> Path:
        data = self._result("content_duration").copy()
        order = ["unknown", "00-15s", "15-30s", "30-60s", "60-120s", "120s+"]
        data["duration_band"] = pd.Categorical(
            data["duration_band"], categories=order, ordered=True
        )
        data = data.sort_values("duration_band")
        x = np.arange(len(data))
        figure, axes = plt.subplots(1, 2, figsize=(10.5, 4.0))
        axes[0].bar(
            x - 0.18,
            data["exposure_weighted_long_view_rate"],
            width=0.36,
            color=COLORS["teal"],
            label="Long-view rate",
        )
        axes[0].bar(
            x + 0.18,
            data["exposure_weighted_like_rate"],
            width=0.36,
            color=COLORS["gold"],
            label="Like rate",
        )
        axes[0].set_xticks(x, data["duration_band"].astype(str), rotation=25, ha="right")
        axes[0].set_title("Exposure-weighted engagement by video duration")
        axes[0].yaxis.set_major_formatter(PercentFormatter(1.0))
        axes[0].legend(frameon=False)
        axes[0].grid(axis="y", color="#E8EDF2", linewidth=0.8)

        axes[1].bar(
            x,
            data["video_weighted_mean_watch_depth"],
            color=COLORS["orange"],
            width=0.62,
        )
        axes[1].set_xticks(x, data["duration_band"].astype(str), rotation=25, ha="right")
        axes[1].set_title("Video-weighted mean watch depth")
        axes[1].set_ylabel("play_time_ms / duration_ms")
        axes[1].grid(axis="y", color="#E8EDF2", linewidth=0.8)
        figure.tight_layout()
        return self._save(figure, "content")

    def build_return_forest(self) -> Path:
        path = self.config.results_dir / "model_coefficients.parquet"
        data = query_df(
            self.connection,
            f"SELECT * FROM read_parquet({sql_literal(path)}) "
            "WHERE outcome = 'returned_d7' "
            "AND term IN ("
            "'log2_event_count', 'long_view_rate_10pp', "
            "'any_explicit_interaction', 'any_profile_enter'"
            ")",
        )
        data = data[
            np.isfinite(data["odds_ratio"])
            & np.isfinite(data["ci_low_odds_ratio"])
            & np.isfinite(data["ci_high_odds_ratio"])
        ].copy()
        data = data.sort_values("odds_ratio")
        labels = data["term"].map(FEATURE_PLOT_LABELS).fillna(data["term"])
        y = np.arange(len(data))
        figure, axis = plt.subplots(figsize=(8.4, 5.2))
        axis.errorbar(
            data["odds_ratio"],
            y,
            xerr=np.vstack(
                [
                    data["odds_ratio"] - data["ci_low_odds_ratio"],
                    data["ci_high_odds_ratio"] - data["odds_ratio"],
                ]
            ),
            fmt="o",
            color=COLORS["navy"],
            ecolor=COLORS["gray"],
            capsize=3,
            markersize=5,
        )
        axis.axvline(1.0, color=COLORS["red"], linestyle="--", linewidth=1)
        axis.set_xscale("log")
        axis.set_yticks(y, labels)
        axis.set_xlabel("Adjusted odds ratio in stated business units (95% cluster-robust CI)")
        axis.set_title("Exact D7 return model: adjusted associations")
        axis.grid(axis="x", which="both", color="#E8EDF2", linewidth=0.8)
        figure.tight_layout()
        return self._save(figure, "forest")

    def build_all(self) -> dict[str, Path]:
        builders = {
            "daily": self.build_daily_activity,
            "hourly": self.build_hourly_activity,
            "tabs": self.build_engagement_tabs,
            "segments": self.build_user_segments,
            "cohorts": self.build_return_cohorts,
            "content": self.build_content_duration,
            "forest": self.build_return_forest,
        }
        outputs: dict[str, Path] = {}
        for key, builder in builders.items():
            outputs[key] = builder()
        return outputs
