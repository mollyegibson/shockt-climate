import pytest

from shockt_engine import (
    EmissionsError,
    Leg,
    break_even_km,
    lane_intensity,
    mix_intensity,
    pair_weighted_distance,
    sea_leg_distance,
    weighted_leg_distance,
)


def test_leg_distance_weights_pairs_by_both_ends() -> None:
    distances = {("a", "x"): 100.0, ("a", "y"): 200.0, ("b", "x"): 300.0, ("b", "y"): 400.0}

    leg = weighted_leg_distance(distances, {"a": 3.0, "b": 1.0}, {"x": 1.0, "y": 1.0})

    # Pair weights 0.375, 0.375, 0.125, 0.125.
    assert leg.km == pytest.approx(0.375 * 100 + 0.375 * 200 + 0.125 * 300 + 0.125 * 400)
    assert leg.covered_share == pytest.approx(1.0)


def test_leg_distance_renormalises_over_pairs_with_a_distance() -> None:
    leg = weighted_leg_distance({("a", "x"): 100.0}, {"a": 1.0, "b": 1.0}, {"x": 1.0})

    assert leg.km == 100.0
    assert leg.covered_share == pytest.approx(0.5)


def test_leg_distance_fails_with_no_pair_measured() -> None:
    with pytest.raises(EmissionsError, match="no node pair"):
        weighted_leg_distance({}, {"a": 1.0}, {"x": 1.0})


def test_lane_intensity_sums_distance_times_factor() -> None:
    legs = [Leg(km=10_000, kg_co2e_per_tkm=1.0), Leg(km=500, kg_co2e_per_tkm=0.2)]

    assert lane_intensity(legs) == pytest.approx(10_100)


def test_mix_intensity_weights_lanes_by_share() -> None:
    assert mix_intensity({"air": 0.25, "truck": 0.75}, {"air": 8.0, "truck": 0.4}) == (
        pytest.approx(2.3)
    )


def test_mix_intensity_needs_shares_that_sum_to_one_and_an_intensity_for_each() -> None:
    with pytest.raises(EmissionsError, match="sum"):
        mix_intensity({"air": 0.5}, {"air": 1.0})
    with pytest.raises(EmissionsError, match="no intensity"):
        mix_intensity({"air": 1.0}, {})


def test_break_even_km_is_the_advantage_over_the_factor() -> None:
    assert break_even_km(10_000, 1.25) == pytest.approx(8_000)


def test_pair_weighted_distance_uses_the_known_pairs() -> None:
    distances = {("plant", "laredo"): 400.0, ("plant", "pharr"): 300.0}

    leg = pair_weighted_distance(distances, {("plant", "laredo"): 9.0, ("plant", "pharr"): 1.0})

    assert leg.km == pytest.approx(390.0)


def test_sea_leg_uses_observed_distances_and_falls_back_to_modelled_ones() -> None:
    observed = {"la": 10_000.0}
    modelled = {("busan", "savannah"): 19_000.0, ("pusan2", "savannah"): 21_000.0}

    leg = sea_leg_distance(
        observed, modelled, {"busan": 3.0, "pusan2": 1.0}, {"la": 1.0, "savannah": 1.0}
    )

    # Savannah: 0.75 × 19,000 + 0.25 × 21,000 = 19,500; the leg: half each.
    assert leg.km == pytest.approx(14_750.0)
    assert leg.observed_share == pytest.approx(0.5)
    assert leg.covered_share == pytest.approx(1.0)
