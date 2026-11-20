from __future__ import annotations

import pandas as pd
import pytest

from kuairand_analysis.statistics import (
    _behavior_incidence_table,
    _build_design,
    _holm_adjust_pvalues,
    exact_return_rate,
)


def test_exact_return_uses_eligible_calendar_denominator_and_deduplicates_days() -> None:
    activity = pd.DataFrame(
        {
            "user_id": [1, 1, 1, 1, 2, 2, 3, 4, 4, 4, 5],
            "activity_date": pd.to_datetime(
                [
                    "2022-04-01",
                    "2022-04-01",
                    "2022-04-02",
                    "2022-04-08",
                    "2022-04-01",
                    "2022-04-08",
                    "2022-04-01",
                    "2022-04-02",
                    "2022-04-09",
                    "2022-04-03",
                    "2022-04-08",
                ]
            ),
        }
    )
    first_seen = pd.DataFrame(
        {
            "user_id": [1, 2, 3, 4, 5],
            "first_seen_date": pd.to_datetime(
                [
                    "2022-04-01",
                    "2022-04-01",
                    "2022-04-01",
                    "2022-04-02",
                    "2022-04-08",
                ]
            ),
        }
    )

    returned_d1, eligible_d1 = exact_return_rate(
        activity, first_seen, "2022-04-09", 1
    )
    returned_d7, eligible_d7 = exact_return_rate(
        activity, first_seen, "2022-04-09", 7
    )

    assert (returned_d1, eligible_d1) == (2, 5)
    assert (returned_d7, eligible_d7) == (3, 4)


def test_right_censored_cohort_is_excluded() -> None:
    activity = pd.DataFrame(
        {
            "user_id": [10],
            "activity_date": pd.to_datetime(["2022-04-01"]),
        }
    )
    first_seen = pd.DataFrame(
        {
            "user_id": [10],
            "first_seen_date": pd.to_datetime(["2022-04-08"]),
        }
    )

    returned, eligible = exact_return_rate(
        activity, first_seen, "2022-04-09", 7
    )

    assert returned == 0
    assert eligible == 0


def test_holm_adjustment_is_monotonic_and_controls_familywise_error() -> None:
    adjusted = _holm_adjust_pvalues(
        pd.Series([0.01, 0.04, 0.03]).to_numpy()
    )

    assert adjusted.tolist() == pytest.approx([0.03, 0.06, 0.06])


def test_sparse_engagement_uses_business_incidence_and_interpretable_units() -> None:
    frame = pd.DataFrame(
        {
            "event_count": [1, 20],
            "long_view_rate": [0.2, 0.4],
            "like_count": [0, 1],
            "comment_count": [0, 0],
            "share_count": [0, 2],
            "follow_count": [0, 0],
            "profile_enter_count": [0, 3],
            "active_tab_count": [1, 2],
            "days_since_start": [0, 1],
            "weekday_number": [5, 6],
        }
    )

    design, _ = _build_design(frame)

    assert design["any_explicit_interaction"].tolist() == [0.0, 1.0]
    assert design["any_profile_enter"].tolist() == [0.0, 1.0]
    assert design["long_view_rate_10pp"].tolist() == [2.0, 4.0]


def test_behavior_summary_uses_user_day_grain() -> None:
    frame = pd.DataFrame(
        {
            "returned_d7": [1, 0, 1, 0],
            "like_count": [0, 1, 0, 1],
            "comment_count": [0, 0, 0, 0],
            "share_count": [0, 0, 0, 0],
            "follow_count": [0, 0, 0, 0],
            "profile_enter_count": [0, 1, 1, 0],
        }
    )

    summary = _behavior_incidence_table(frame, "returned_d7")

    assert "no_event_user_days" in summary.columns
    assert "event_user_days" in summary.columns
    like_row = summary.loc[summary["feature"] == "like"].iloc[0]
    assert like_row["no_event_user_days"] == 2
    assert like_row["event_user_days"] == 2
