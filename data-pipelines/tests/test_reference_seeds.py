from pathlib import Path

import pytest

from shockt.config import hs_codes_config
from shockt.reference import census_schedules, config_seeds
from tests.conftest import PROJECT_ROOT

SEEDS = PROJECT_ROOT / "dbt" / "seeds"


@pytest.mark.parametrize(
    ("seed", "write"),
    [
        (
            "seed_hs_case_codes.csv",
            lambda p: config_seeds.write_hs_case_codes(hs_codes_config(), p),
        ),
    ],
)
def test_committed_config_seeds_match_their_generator(seed: str, write, tmp_path: Path) -> None:
    generated = tmp_path / seed
    write(generated)

    assert generated.read_text() == (SEEDS / seed).read_text(), (
        f"{seed} differs from its config; run `shockt ref config-seeds` instead of editing it"
    )


SCHEDULE_C = """----------------------------------------------------------------------
Schedule C - Country List (by code) [Produced: 31JAN14]
Code     |    Name                                                | ISO Code
1220     |    Canada                                              | CA
2010     |    Mexico                                              | MX
4803     |    Kosovo                                              | KV
5830     |    Taiwan                                              | TW
9999     |    Unknown with no ISO                                 |
"""


def test_parse_schedule_c_maps_iso3_including_census_specific_codes() -> None:
    lines = SCHEDULE_C + "\n".join(f"{1000 + i:04d} | Filler {i} | US" for i in range(200))

    countries = {c.census_code: c for c in census_schedules.parse_schedule_c(lines)}

    assert countries["5830"].iso3 == "TWN"
    assert countries["4803"].iso3 == "XKX"
    assert countries["9999"].iso2 is None and countries["9999"].iso3 is None


def test_parse_schedule_c_rejects_a_page_that_isnt_the_schedule() -> None:
    with pytest.raises(census_schedules.ScheduleError):
        census_schedules.parse_schedule_c(SCHEDULE_C)


def test_parse_schedule_d_reads_district_and_port_entries() -> None:
    entries = ["DISTRICT", "PORTLAND, ME", "0101", "Port", "BANGOR, ME", "0102"] + [
        x for i in range(300) for x in ("Port", f"PORT {i}", f"{2700 + i:04d}")
    ]
    page = "<table>" + "".join(f"<td>{e}</td>" for e in entries) + "</table>"

    ports = census_schedules.parse_schedule_d(page)

    assert ports[0] == census_schedules.Port("0101", "PORTLAND, ME", "01")
    assert ports[1] == census_schedules.Port("0102", "BANGOR, ME", "01")
