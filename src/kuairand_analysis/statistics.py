"""Leakage-aware statistical validation for observed return behavior."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import rankdata

from .config import AnalysisConfig
from .db import copy_table_to_parquet, query_df


FEATURE_LABELS = {
    "log2_event_count": "日曝光量",
    "long_view_rate_10pp": "长观看率",
    "any_explicit_interaction": "当日有任何显性互动",
    "any_profile_enter": "当日进入主页",
    "week_index": "距观察起点周数",
}

PRIMARY_FEATURES = (
    "log2_event_count",
    "long_view_rate_10pp",
    "any_explicit_interaction",
    "any_profile_enter",
)

DESCRIPTIVE_BEHAVIOR_COLUMNS = (
    ("like", "like_count", "当日有点赞"),
    ("comment", "comment_count", "当日有评论"),
    ("share", "share_count", "当日有分享"),
    ("follow", "follow_count", "当日有关注"),
    ("profile_enter", "profile_enter_count", "当日进入主页"),
)

EFFECT_UNITS = {
    "log2_event_count": "日曝光量翻倍",
    "long_view_rate_10pp": "长观看率 +10 个百分点",
    "any_explicit_interaction": "有显性互动 vs 无",
    "any_profile_enter": "进入主页 vs 未进入",
    "week_index": "每增加 1 周",
}


def _roc_auc(y_true: np.ndarray, probabilities: np.ndarray) -> float:
    """Compute ROC AUC from ranks without an optional ML dependency."""

    y = np.asarray(y_true, dtype=int)
    p = np.asarray(probabilities, dtype=float)
    positives = int(y.sum())
    negatives = int(len(y) - positives)
    if positives == 0 or negatives == 0:
        raise ValueError("ROC AUC requires both outcome classes.")
    ranks = rankdata(p, method="average")
    return float(
        (ranks[y == 1].sum() - positives * (positives + 1) / 2)
        / (positives * negatives)
    )


def _holm_adjust_pvalues(p_values: np.ndarray) -> np.ndarray:
    """Holm step-down adjusted p-values."""

    values = np.asarray(p_values, dtype=float)
    count = len(values)
    order = np.argsort(values)
    adjusted_sorted = np.empty(count, dtype=float)
    running_maximum = 0.0
    for rank, index in enumerate(order):
        candidate = min(1.0, (count - rank) * values[index])
        running_maximum = max(running_maximum, candidate)
        adjusted_sorted[rank] = running_maximum
    adjusted = np.empty(count, dtype=float)
    adjusted[order] = adjusted_sorted
    return adjusted


def _behavior_incidence_table(
    frame: pd.DataFrame, outcome_column: str
) -> pd.DataFrame:
    rows = []
    behaviors = list(DESCRIPTIVE_BEHAVIOR_COLUMNS)
    explicit_counts = [
        "like_count", "comment_count", "share_count", "follow_count"
    ]
    behaviors.append(
        (
            "any_explicit",
            "__explicit__",
            "当日有任何显性互动",
        )
    )
    for feature, action_count, label in behaviors:
        if action_count == "__explicit__":
            occurred = frame[explicit_counts].max(axis=1).astype(float) > 0
        else:
            occurred = frame[action_count].astype(float) > 0
        no_event = frame.loc[~occurred, outcome_column]
        event = frame.loc[occurred, outcome_column]
        rows.append(
            {
                "feature": feature,
                "feature_label": label,
                "no_event_user_days": int(len(no_event)),
                "event_user_days": int(len(event)),
                "no_event_return_rate": float(no_event.mean()),
                "event_return_rate": float(event.mean()),
                "return_rate_difference": float(event.mean() - no_event.mean()),
            }
        )
    return pd.DataFrame(rows)


def _variance_inflation_factors(matrix: np.ndarray, names: list[str]) -> dict[str, float]:
    """Calculate VIF for non-intercept columns."""

    values: dict[str, float] = {}
    for index, name in enumerate(names):
        target = matrix[:, index]
        if np.nanstd(target) <= 1e-12:
            continue
        others = np.delete(matrix, index, axis=1)
        others = sm.add_constant(others, has_constant="add")
        coefficients, *_ = np.linalg.lstsq(others, target, rcond=None)
        fitted = others @ coefficients
        residual_sum = float(np.square(target - fitted).sum())
        total_sum = float(np.square(target - target.mean()).sum())
        r_squared = 1.0 - residual_sum / total_sum if total_sum > 0 else math.nan
        if r_squared < 1.0 - 1e-12:
            values[name] = 1.0 / (1.0 - r_squared)
    return values


def _build_design(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    design = pd.DataFrame(index=frame.index)
    design["log2_event_count"] = np.log2(frame["event_count"].astype(float))
    design["long_view_rate_10pp"] = frame["long_view_rate"].astype(float) * 10
    explicit_columns = ["like_count", "comment_count", "share_count", "follow_count"]
    design["any_explicit_interaction"] = (
        frame[explicit_columns].max(axis=1).astype(float) > 0
    ).astype(float)
    design["any_profile_enter"] = (
        frame["profile_enter_count"].astype(float) > 0
    ).astype(float)
    design["week_index"] = frame["days_since_start"].astype(float) / 7

    weekday_dummies = pd.get_dummies(
        frame["weekday_number"].astype(int),
        prefix="weekday",
        drop_first=True,
        dtype=float,
    )
    design = pd.concat([design, weekday_dummies], axis=1)

    if design.isna().any().any():
        missing = design.columns[design.isna().any()].tolist()
        raise ValueError(f"Return model design contains missing values: {missing}")
    return design, design.columns.tolist()


def _fit_clustered_logit(
    train_design: pd.DataFrame,
    train_users: pd.Series,
    train_outcome: pd.Series,
    test_design: pd.DataFrame,
    test_outcome: pd.Series,
) -> tuple[Any, np.ndarray, pd.DataFrame, dict[str, float]]:
    train_matrix = sm.add_constant(train_design, has_constant="add")
    test_matrix = sm.add_constant(test_design, has_constant="add")
    model = sm.GLM(
        train_outcome.astype(float),
        train_matrix,
        family=sm.families.Binomial(),
    )
    result = model.fit(
        method="lbfgs",
        maxiter=250,
        cov_type="cluster",
        cov_kwds={"groups": train_users.to_numpy()},
        disp=False,
    )
    convergence = getattr(result, "mle_retvals", {}).get("converged")
    if convergence is False:
        raise RuntimeError("Clustered logistic regression did not converge.")

    probabilities = np.asarray(result.predict(test_matrix), dtype=float)
    y_true = test_outcome.to_numpy(dtype=int)
    clipped = np.clip(probabilities, 1e-12, 1 - 1e-12)
    evaluation = {
        "auc": _roc_auc(y_true, probabilities),
        "brier_score": float(np.mean(np.square(y_true - probabilities))),
        "log_loss": float(
            -np.mean(y_true * np.log(clipped) + (1 - y_true) * np.log(1 - clipped))
        ),
    }
    baseline_probability = float(train_outcome.mean())
    baseline_probability = min(max(baseline_probability, 1e-12), 1 - 1e-12)
    evaluation["constant_baseline_probability"] = baseline_probability
    evaluation["constant_baseline_brier_score"] = float(
        np.mean(np.square(y_true - baseline_probability))
    )
    evaluation["constant_baseline_log_loss"] = float(
        -np.mean(
            y_true * np.log(baseline_probability)
            + (1 - y_true) * np.log(1 - baseline_probability)
        )
    )
    evaluation["brier_skill_score"] = float(
        1
        - evaluation["brier_score"]
        / evaluation["constant_baseline_brier_score"]
    )

    confidence = np.asarray(result.conf_int(), dtype=float)
    coefficient_frame = pd.DataFrame(
        {
            "term": result.params.index,
            "coefficient": np.asarray(result.params, dtype=float),
            "standard_error": np.asarray(result.bse, dtype=float),
            "p_value": np.asarray(result.pvalues, dtype=float),
            "ci_low_log_odds": confidence[:, 0],
            "ci_high_log_odds": confidence[:, 1],
        }
    )
    return result, probabilities, coefficient_frame, evaluation


def _fit_outcome(
    frame: pd.DataFrame,
    outcome_column: str,
    train_dates: list[Any],
) -> dict[str, Any]:
    train_mask = frame["activity_date"].isin(train_dates)
    test_mask = ~train_mask
    train = frame.loc[train_mask].copy()
    test = frame.loc[test_mask].copy()
    if train.empty or test.empty:
        raise ValueError("The time split produced an empty train or test sample.")

    train_raw_design, feature_names = _build_design(train)
    test_raw_design, _ = _build_design(test)
    test_raw_design = test_raw_design.reindex(
        columns=feature_names, fill_value=0.0
    )
    result, probabilities, coefficients, evaluation = _fit_clustered_logit(
        train_raw_design,
        train["user_id"],
        train[outcome_column],
        test_raw_design,
        test[outcome_column],
    )
    vif = _variance_inflation_factors(
        train_raw_design.to_numpy(dtype=float), feature_names
    )
    coefficients["outcome"] = outcome_column
    coefficients["odds_ratio"] = np.exp(coefficients["coefficient"])
    coefficients["ci_low_odds_ratio"] = np.exp(coefficients["ci_low_log_odds"])
    coefficients["ci_high_odds_ratio"] = np.exp(coefficients["ci_high_log_odds"])
    coefficients["feature_label"] = coefficients["term"].map(FEATURE_LABELS)
    coefficients["effect_unit"] = coefficients["term"].map(EFFECT_UNITS)
    coefficients["p_value_holm"] = np.nan
    primary_mask = coefficients["term"].isin(PRIMARY_FEATURES)
    coefficients.loc[primary_mask, "p_value_holm"] = _holm_adjust_pvalues(
        coefficients.loc[primary_mask, "p_value"].to_numpy(dtype=float)
    )

    return {
        "outcome": outcome_column,
        "coefficients": coefficients,
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_users": int(train["user_id"].nunique()),
        "test_users": int(test["user_id"].nunique()),
        "train_start": str(train["activity_date"].min()),
        "train_end": str(train["activity_date"].max()),
        "test_start": str(test["activity_date"].min()),
        "test_end": str(test["activity_date"].max()),
        "train_prevalence": float(train[outcome_column].mean()),
        "test_prevalence": float(test[outcome_column].mean()),
        "converged": bool(
            getattr(result, "mle_retvals", {}).get("converged", True)
        ),
        "iterations": int(
            getattr(result, "fit_history", {}).get("iteration", -1)
        ),
        "log_likelihood": float(result.llf),
        "mcfadden_pseudo_r2": float(1.0 - result.llf / result.llnull),
        "evaluation": evaluation,
        "vif": vif,
        "max_vif": float(max(vif.values())) if vif else math.nan,
    }


def fit_return_models(
    connection: duckdb.DuckDBPyConnection,
    config: AnalysisConfig,
) -> dict[str, Any]:
    """Fit the primary D7 model and D1/any-seven-day robustness models."""

    frame = query_df(connection, "SELECT * FROM mart_return_model")
    if frame.empty:
        raise ValueError("mart_return_model is empty; the return model cannot be fit.")
    frame["activity_date"] = pd.to_datetime(frame["activity_date"]).dt.date

    primary_outcome = f"returned_d{config.analysis.outcome_offset}"
    if primary_outcome not in frame:
        raise ValueError(f"Missing primary outcome column: {primary_outcome}")
    if frame[primary_outcome].nunique() < 2:
        raise ValueError("The primary return outcome has only one class.")

    dates = sorted(pd.to_datetime(frame["activity_date"]).dt.date.unique().tolist())
    if len(dates) < config.analysis.min_eligible_dates:
        raise ValueError(
            f"Only {len(dates)} eligible model dates; "
            f"{config.analysis.min_eligible_dates} are required."
        )
    train_date_count = max(1, math.floor(len(dates) * config.analysis.train_fraction))
    train_dates = dates[:train_date_count]
    if len(train_dates) >= len(dates):
        raise ValueError("The training split must leave at least one test date.")

    fitted: dict[str, Any] = {}
    outcomes = [primary_outcome]
    for sensitivity_outcome in ("returned_d1", "returned_any_7d"):
        if sensitivity_outcome != primary_outcome:
            outcomes.append(sensitivity_outcome)

    for outcome in outcomes:
        fitted[outcome] = _fit_outcome(frame, outcome, train_dates)

    primary = fitted[primary_outcome]
    all_coefficients = []
    for outcome, fitted_outcome in fitted.items():
        table = fitted_outcome["coefficients"].copy()
        table["sample_role"] = "primary" if outcome == primary_outcome else "sensitivity"
        all_coefficients.append(table)
    coefficient_table = pd.concat(all_coefficients, ignore_index=True)

    connection.register("model_coefficient_frame", coefficient_table)
    copy_table_to_parquet(
        connection,
        "model_coefficient_frame",
        config.results_dir / "model_coefficients.parquet",
    )
    connection.unregister("model_coefficient_frame")

    behavior_incidence = _behavior_incidence_table(frame, primary_outcome)
    connection.register("behavior_incidence_frame", behavior_incidence)
    copy_table_to_parquet(
        connection,
        "behavior_incidence_frame",
        config.results_dir / "behavior_incidence.parquet",
    )
    connection.unregister("behavior_incidence_frame")

    model_metrics: dict[str, Any] = {
        "primary_outcome": primary_outcome,
        "total_model_sample": int(len(frame)),
        "total_users": int(frame["user_id"].nunique()),
        "eligible_dates": len(dates),
        "train_date_count": len(train_dates),
        "test_date_count": len(dates) - len(train_dates),
        "primary": {
            key: value
            for key, value in primary.items()
            if key != "coefficients"
        },
        "sensitivity": {
            outcome: {
                key: value
                for key, value in result.items()
                if key != "coefficients"
            }
            for outcome, result in fitted.items()
            if outcome != primary_outcome
        },
        "feature_labels": FEATURE_LABELS,
        "effect_units": EFFECT_UNITS,
        "model_specification": {
            "estimator": "Binomial GLM / logistic regression",
            "standard_errors": "cluster-robust by user_id",
            "split": "chronological calendar-date holdout",
            "multiple_comparison": "Holm adjustment across the four primary predictors within each outcome",
            "continuous_features": "daily exposure volume, long-view rate and week index in directly interpretable units",
            "binary_incidence_features": "any explicit interaction and any profile entry",
            "binary_predictors": "odds ratio for any occurrence versus no occurrence",
            "weekday_controls": "dummy variables, Sunday as reference",
        },
    }
    metrics_path = config.results_dir / "model_metrics.json"
    metrics_path.write_text(
        json.dumps(model_metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return model_metrics


def exact_return_rate(
    activity_dates: pd.DataFrame,
    first_seen_dates: pd.DataFrame,
    observation_end: Any,
    offset_days: int,
) -> tuple[int, int]:
    """Small, independently testable implementation of the exact-day denominator rule."""

    active = {
        (int(row.user_id), pd.Timestamp(row.activity_date).date())
        for row in activity_dates.itertuples(index=False)
    }
    eligible = 0
    returned = 0
    end = pd.Timestamp(observation_end).date()
    for row in first_seen_dates.itertuples(index=False):
        user_id = int(row.user_id)
        first_seen = pd.Timestamp(row.first_seen_date).date()
        target_date = first_seen + pd.Timedelta(days=offset_days)
        if target_date > end:
            continue
        eligible += 1
        returned += int((user_id, target_date) in active)
    return returned, eligible
