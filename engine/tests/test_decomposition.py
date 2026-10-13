import pytest

from shockt_engine import EmissionsError, MixCell, mix_decomposition

BASELINE = {
    ("A", "air"): MixCell(tonnes=1, intensity={"leg": 10}),
    ("A", "sea"): MixCell(tonnes=1, intensity={"leg": 2}),
    ("B", "sea"): MixCell(tonnes=2, intensity={"leg": 1}),
}


def test_effects_are_shapley_values_and_sum_to_the_change() -> None:
    """Baseline (10 + 2 + 2) / 4 = 3.5; window (30 + 2 + 6) / 10 = 3.8. Origin alone: shares
    0.4 / 0.6 with A's baseline modes (worth 6) gives 3.0; mode alone: A's modes 0.75 / 0.25
    (worth 8) gives 4.5. Origin = ((3.0 − 3.5) + (3.8 − 4.5)) / 2; mode = ((4.5 − 3.5) +
    (3.8 − 3.0)) / 2. The leg intensities don't change, so their effect is 0."""
    window = {
        ("A", "air"): MixCell(tonnes=3, intensity={"leg": 10}),
        ("A", "sea"): MixCell(tonnes=1, intensity={"leg": 2}),
        ("B", "sea"): MixCell(tonnes=6, intensity={"leg": 1}),
    }

    result = mix_decomposition(BASELINE, window, ["origin", "mode"])

    assert (result.baseline, result.window) == pytest.approx((3.5, 3.8))
    assert result.effects["origin"] == pytest.approx(-0.6)
    assert result.effects["mode"] == pytest.approx(0.9)
    assert result.effects["leg"] == pytest.approx(0.0)
    assert sum(result.effects.values()) == pytest.approx(result.window - result.baseline)


def test_the_intensity_effect_holds_the_shares() -> None:
    window = {**BASELINE, ("B", "sea"): MixCell(tonnes=2, intensity={"leg": 3})}

    result = mix_decomposition(BASELINE, window, ["origin", "mode"])

    assert result.effects["leg"] == pytest.approx(1.0)
    assert result.effects["origin"] == pytest.approx(0.0)


def test_a_cell_new_in_the_window_uses_its_window_values() -> None:
    """Only the origin shares change (A 0.25, B 0.25, C 0.5), and C's modes come from the window:
    0.25 × 6 + 0.25 × 1 + 0.5 × 20 = 11.75."""
    window = {**BASELINE, ("C", "air"): MixCell(tonnes=4, intensity={"leg": 20})}

    result = mix_decomposition(BASELINE, window, ["origin", "mode"])

    assert result.window == pytest.approx((10 + 2 + 2 + 80) / 8)
    assert result.effects["origin"] == pytest.approx(11.75 - 3.5)
    assert result.effects["mode"] == pytest.approx(0.0)


def test_cells_need_one_value_per_dimension() -> None:
    with pytest.raises(EmissionsError):
        mix_decomposition(BASELINE, {("A",): MixCell(1, {"leg": 1})}, ["origin", "mode"])


def test_dimension_names_cant_clash_with_a_component() -> None:
    with pytest.raises(EmissionsError):
        mix_decomposition(BASELINE, BASELINE, ["origin", "leg"])


def test_each_component_of_the_intensity_is_its_own_effect() -> None:
    """Same shares; the international leg rises by 1 and the inland leg falls by 1 in every cell,
    so the total doesn't move but each component's effect shows."""
    base = {
        ("A", "sea"): MixCell(tonnes=1, intensity={"international": 4, "inland": 2}),
        ("B", "sea"): MixCell(tonnes=3, intensity={"international": 8, "inland": 2}),
    }
    window = {
        ("A", "sea"): MixCell(tonnes=1, intensity={"international": 5, "inland": 1}),
        ("B", "sea"): MixCell(tonnes=3, intensity={"international": 9, "inland": 1}),
    }

    result = mix_decomposition(base, window, ["origin", "mode"])

    assert result.window - result.baseline == pytest.approx(0.0)
    assert result.effects["international"] == pytest.approx(1.0)
    assert result.effects["inland"] == pytest.approx(-1.0)
