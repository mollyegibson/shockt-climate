import pytest

from shockt_engine import EmissionsError, LaneInputs, lane_legs

FACTORS = {"ocean": 0.02, "air": 1.0, "truck": 0.16, "rail": 0.02}


def test_air_lane_flies_to_the_gateway_then_trucks_to_the_state() -> None:
    inputs = LaneInputs(
        weights={
            "departure_airport": {"tpe": 1.0},
            "air_gateway": {"lax": 3.0, "ord": 1.0},
            "destination_state": {"ca": 1.0},
        },
        distances={
            "air": {("tpe", "lax"): 10_000.0, ("tpe", "ord"): 12_000.0},
            "road": {("lax", "ca"): 100.0, ("ord", "ca"): 3_000.0},
        },
        factors=FACTORS,
    )

    lane = lane_legs("air", inputs)

    assert [leg.name for leg in lane.legs] == ["airport → gateway", "gateway → state"]
    assert lane.legs[0].km == pytest.approx(10_500.0)
    assert lane.legs[1].km == pytest.approx(825.0)
    assert lane.kg_co2e_per_t == pytest.approx(10_500.0 * 1.0 + 825.0 * 0.16)


def test_vessel_lane_uses_observed_sea_distances_where_it_has_them() -> None:
    inputs = LaneInputs(
        weights={
            "departure_port": {"kao": 1.0},
            "arrival_seaport": {"la": 1.0},
            "destination_state": {"va": 1.0},
        },
        distances={"sea": {("kao", "la"): 99_999.0}, "road": {("la", "va"): 4_000.0}},
        factors=FACTORS,
        observed_sea={"la": 11_000.0},
    )

    lane = lane_legs("vessel", inputs)

    assert lane.legs[0].km == 11_000.0
    assert lane.legs[0].observed_share == 1.0


def test_vessel_lane_can_go_inland_by_rail() -> None:
    inputs = LaneInputs(
        weights={
            "departure_port": {"kao": 1.0},
            "arrival_seaport": {"la": 1.0},
            "destination_state": {"va": 1.0},
        },
        distances={
            "sea": {("kao", "la"): 11_000.0},
            "road": {("la", "va"): 4_000.0},
            "rail": {("la", "va"): 4_500.0},
        },
        factors=FACTORS,
    )

    lane = lane_legs("vessel", inputs, inland="rail")

    assert (lane.legs[1].factor_mode, lane.legs[1].km) == ("rail", 4_500.0)
    assert lane.kg_co2e_per_t == pytest.approx(11_000.0 * 0.02 + 4_500.0 * 0.02)


def test_only_vessel_lanes_go_inland_by_rail() -> None:
    inputs = LaneInputs(weights={}, distances={}, factors=FACTORS)

    with pytest.raises(EmissionsError):
        lane_legs("air", inputs, inland="rail")


def test_mexico_rail_lane_starts_at_each_crossings_plant_by_truck() -> None:
    inputs = LaneInputs(
        weights={
            "border_crossing": {"laredo": 3.0, "eagle": 1.0},
            "destination_state": {"tx": 1.0},
        },
        distances={
            "road": {("apodaca", "laredo"): 400.0, ("apodaca", "eagle"): 500.0},
            "rail": {("laredo", "tx"): 500.0, ("eagle", "tx"): 600.0},
        },
        factors=FACTORS,
        crossing_plants={"laredo": "apodaca", "eagle": "apodaca"},
    )

    lane = lane_legs("rail", inputs)

    assert [(leg.name, leg.factor_mode) for leg in lane.legs] == [
        ("plant → crossing", "truck"),
        ("crossing → state", "rail"),
    ]
    assert lane.legs[0].km == pytest.approx(425.0)
    assert lane.legs[1].km == pytest.approx(525.0)


def test_a_lane_without_plants_leaves_out_the_mexican_leg_and_says_so() -> None:
    inputs = LaneInputs(
        weights={"border_crossing": {"laredo": 1.0}, "destination_state": {"tx": 1.0}},
        distances={"road": {("laredo", "tx"): 500.0}},
        factors=FACTORS,
    )

    lane = lane_legs("truck", inputs)

    assert lane.missing_legs == ("plant → crossing",)
    assert lane.kg_co2e_per_t == pytest.approx(500.0 * 0.16)
