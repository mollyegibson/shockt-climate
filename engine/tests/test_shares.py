from datetime import date

import pytest

from shockt_engine import ShareError, Window, diversion_rate, share_change, shares, window_summary


def test_shares_divide_by_the_total() -> None:
    assert shares({"TWN": 3.0, "MEX": 1.0}) == {"TWN": 0.75, "MEX": 0.25}


def test_shares_need_a_positive_total() -> None:
    with pytest.raises(ShareError):
        shares({"TWN": 0.0})


def test_diversion_rate_matches_the_proposals_worked_example() -> None:
    # Air share by weight rose from 20% to 35%, so 0.15 of the 0.80 sea share moved: 18.75%.
    assert diversion_rate(s_from_baseline=0.80, s_to_baseline=0.20, s_to_response=0.35) == (
        pytest.approx(0.1875)
    )


def test_a_negative_diversion_rate_is_a_shift_the_other_way() -> None:
    assert diversion_rate(0.5, 0.5, 0.4) == pytest.approx(-0.2)


def test_share_change_treats_a_missing_category_as_zero() -> None:
    change = share_change({"TWN": 0.6, "MEX": 0.4}, {"TWN": 0.5, "THA": 0.5})

    assert change == pytest.approx({"TWN": -0.1, "MEX": -0.4, "THA": 0.5})


def test_window_summary_weights_the_mean_and_keeps_the_extremes() -> None:
    values = {date(2025, 1, 1): 10.0, date(2025, 2, 1): 20.0, date(2025, 5, 1): 99.0}
    weights = {date(2025, 1, 1): 1.0, date(2025, 2, 1): 3.0, date(2025, 5, 1): 1.0}
    baseline = Window("baseline", date(2025, 1, 1), date(2025, 2, 1))
    empty = Window("anticipation", date(2025, 3, 1), date(2025, 4, 1))

    summary = window_summary(values, [baseline, empty], weights)

    assert summary["baseline"].mean == pytest.approx(17.5)
    assert (summary["baseline"].low, summary["baseline"].high, summary["baseline"].months) == (
        10.0,
        20.0,
        2,
    )
    assert "anticipation" not in summary


def test_windows_are_whole_months() -> None:
    with pytest.raises(ValueError, match="first of a month"):
        Window("baseline", date(2025, 1, 15), date(2025, 2, 1))
