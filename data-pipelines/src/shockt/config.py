import re
from collections.abc import Sequence
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from shockt.settings import PROJECT_ROOT

CONFIG_DIR = PROJECT_ROOT / "config"

CensusDataset = Literal["hs", "porths", "statehs"]


class ConfigModel(BaseModel):
    """A config section; an unknown key is an error, so a misspelled setting can't be ignored."""

    model_config = ConfigDict(extra="forbid")


MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class DateRange(ConfigModel):
    start_month: str = Field(pattern=MONTH_PATTERN)
    end_month: str | None = Field(default=None, pattern=MONTH_PATTERN)


class CountryFilter(ConfigModel):
    """Keep only countries whose Census code starts with one of `code_prefixes` or is in `codes`."""

    code_prefixes: list[str] = []
    codes: list[str] = []


class OriginRegion(ConfigModel):
    """Countries in one origin region, by Census Schedule C code."""

    census_code_prefixes: list[str] = []
    census_codes: list[str] = []

    def contains(self, code: str) -> bool:
        return code in self.census_codes or code.startswith(tuple(self.census_code_prefixes))


class OriginsConfig(ConfigModel):
    """The origin regions in scope; `config/origins.yaml` is the only place they are defined."""

    regions: dict[str, OriginRegion]

    def region_of(self, code: str) -> str | None:
        return next((name for name, r in self.regions.items() if r.contains(code)), None)

    def country_filter(self, extra_codes: Sequence[str] = ()) -> CountryFilter:
        """The origin countries as a `CountryFilter`, plus `extra_codes` (e.g. a total row)."""
        return CountryFilter(
            code_prefixes=[p for r in self.regions.values() for p in r.census_code_prefixes],
            codes=[c for r in self.regions.values() for c in r.census_codes] + list(extra_codes),
        )


class CensusRowFilter(ConfigModel):
    """Rows dropped as a Census response is parsed into raw, with the countries resolved."""

    drop_country_groups: bool
    drop_all_zero: bool
    countries: CountryFilter | None = None


CENSUS_ALL_COUNTRIES = "-"


class CensusFilterConfig(ConfigModel):
    """A Census endpoint's load filter as configured."""

    drop_country_groups: bool
    drop_all_zero: bool
    origins_only: bool = False
    """Keep only countries in `config/origins.yaml`, and the all-countries total."""

    def row_filter(self, origins: OriginsConfig) -> CensusRowFilter:
        return CensusRowFilter(
            drop_country_groups=self.drop_country_groups,
            drop_all_zero=self.drop_all_zero,
            countries=origins.country_filter([CENSUS_ALL_COUNTRIES]) if self.origins_only else None,
        )


class CensusApiConfig(ConfigModel):
    base_url: str
    timeout_seconds: float
    filters: dict[CensusDataset, CensusFilterConfig]


class BtsTransborderConfig(ConfigModel):
    manual_dir: str
    """Directory of monthly ZIPs downloaded from bts.gov, relative to `data-pipelines/`."""
    tables: list[Literal["dot2", "dot3"]]


class CensusStatePortConfig(ConfigModel):
    url_template: str
    """Quarterly ZIP URL with `{yy}` for the two-digit year and `{quarter}` for 1–4."""
    origins_only: bool
    """Keep only countries in `config/origins.yaml`."""
    states: list[str]
    drop_rows_without_air_or_vessel_weight: bool


class BtsT100Config(ConfigModel):
    form_url: str
    """TranStats download form for T-100 International Segment (All Carriers)."""
    origins_only: bool
    """Keep only segments from airports in countries in `config/origins.yaml`."""
    drop_rows_without_freight: bool


class PortwatchConfig(ConfigModel):
    query_url: str
    chokepoints: list[str]
    """PortWatch `portid`s; their names come from the source's `portname`."""


class ClimateTraceConfig(ConfigModel):
    table: str
    """Fully qualified BigQuery table, project.dataset.table."""


class CensusSchedulesConfig(ConfigModel):
    schedule_c_url: str
    schedule_d_url: str
    iso3_overrides: dict[str, str]
    """Census-specific ISO2 code → the ISO3 code other sources use, where ISO 3166 has none."""


class OurAirportsConfig(ConfigModel):
    url: str


class GeonamesCitiesConfig(ConfigModel):
    url: str
    countries: list[str]


class BorderCrossingsConfig(ConfigModel):
    url: str
    border: str
    page_size: int


class ImportConcordanceConfig(ConfigModel):
    url_template: str
    """Workbook URL with `{yy}` for the two-digit year."""


class DenueConfig(ConfigModel):
    url: str
    industry_digits: int
    """Industry-code prefix length at which DENUE's SCIAN is matched to the concordance's NAICS."""
    cases: list[str]
    """Cases whose HS prefixes select DENUE industries: those with a Mexican assembly site."""


class ReferenceSourcesConfig(ConfigModel):
    ourairports: OurAirportsConfig
    geonames_cities: GeonamesCitiesConfig
    bts_border_crossings: BorderCrossingsConfig
    census_import_concordance: ImportConcordanceConfig
    denue: DenueConfig


class FactorSource(ConfigModel):
    url: str
    version: str
    publication: str


class EmissionFactorsConfig(ConfigModel):
    uk: FactorSource
    epa: FactorSource


class SeaDistancesConfig(ConfigModel):
    scenarios: dict[str, list[str]]
    """Scenario name → the `searoute` passages closed in it; the generator checks the names
    against the library's own list."""

    @model_validator(mode="after")
    def _token_names(self) -> "SeaDistancesConfig":
        bad = [name for name in self.scenarios if not re.fullmatch(r"[a-z][a-z0-9_]*", name)]
        if bad or not self.scenarios:
            raise ValueError(f"scenario names must be lower-case tokens: {bad or 'none given'}")
        return self


class RoadDistancesConfig(ConfigModel):
    matrix_url: str
    """openrouteservice matrix endpoint, with the routing profile in its path."""
    max_cells_per_request: int = Field(gt=0)
    """Origins × destinations the API accepts in one matrix request."""


class RailDistancesConfig(ConfigModel):
    lines_url: str
    nodes_url: str
    """ArcGIS FeatureServer layers of the BTS North American Rail Network."""
    track_classes: list[str]
    """`NET` codes of the track a route may use."""
    page_size: int = Field(gt=0)
    max_snap_km: float = Field(gt=0)
    """Farthest a node may be from track; pairs with an end farther away get no rail distance."""


class ThetisMrvConfig(ConfigModel):
    downloadable_files_url: str
    download_url_template: str
    """URL with ``{year}`` and ``{version}`` placeholders."""
    start_year: int
    end_year: int | None = None


class ComextConfig(ConfigModel):
    base_url: str
    """Comext SDMX 2.1 REST API base."""
    dataset: str
    flow: str
    indicators: list[str]
    timeout_seconds: float
    partner_overrides: dict[str, str | None] = Field(default_factory=dict)
    """Map non-standard ISO-2 codes to Comext partner codes (or None to drop)."""


class EuReportersConfig(ConfigModel):
    reporters: list[str]
    """ISO 3166-1 alpha-2 codes of EU member states used as Comext reporters."""


class DistancesConfig(ConfigModel):
    sea: SeaDistancesConfig
    road: RoadDistancesConfig
    rail: RailDistancesConfig


class SourcesConfig(ConfigModel):
    date_range: DateRange
    census_api: CensusApiConfig
    census_state_port: CensusStatePortConfig
    bts_transborder: BtsTransborderConfig
    bts_t100: BtsT100Config
    portwatch: PortwatchConfig
    climatetrace: ClimateTraceConfig
    census_schedules: CensusSchedulesConfig
    reference_sources: ReferenceSourcesConfig
    emission_factors: EmissionFactorsConfig
    thetis_mrv: ThetisMrvConfig
    comext: ComextConfig
    distances: DistancesConfig


class AirPortsConfig(ConfigModel):
    airport_types: list[str]
    """OurAirports `type` values that can be air gateways."""
    scheduled_service_only: bool
    city_radius_km: float
    """Radius around a Census port's city within which its large airport is chosen."""
    max_unmatched_share: float
    """Largest share of case air tonnage allowed at Census ports with no matched airport."""


class CensusPortsConfig(ConfigModel):
    max_unlocated_share: float
    """Largest share of case vessel or air tonnage allowed at Census ports with no point."""


class ClimateTraceTransformsConfig(ConfigModel):
    max_contradicting_end_point_share: float
    """Largest share of container voyages excluded for an end point that contradicts the end
    port."""


class OverlandWeightConfig(ConfigModel):
    min_air_vessel_value_usd: float
    """An origin's air and vessel value of a code needed for its own kg per dollar to be used."""
    range_percentiles: list[float]
    """Value-weighted percentiles of kg per dollar across origins that bound an estimate's range."""
    max_non_crossing_share: float = Field(ge=0, le=1)
    """Largest share of a code's Mexican overland value allowed to enter away from a US–Mexico
    crossing, which the Mexico overland leg leaves out, before a warning."""

    @model_validator(mode="after")
    def _ordered_percentiles(self) -> "OverlandWeightConfig":
        if len(self.range_percentiles) != 2:
            raise ValueError(f"range_percentiles must be two values: {self.range_percentiles}")
        low, high = self.range_percentiles
        if not 0 <= low < high <= 1:
            raise ValueError(f"range_percentiles must satisfy 0 <= low < high <= 1: {low}, {high}")
        return self


class UnplacedShareConfig(ConfigModel):
    vessel: float = Field(ge=0, le=1)
    air: float = Field(ge=0, le=1)


class DepartureNodesConfig(ConfigModel):
    max_unplaced_share: UnplacedShareConfig
    """Largest share of case tonnage, by mode, allowed from origins with no departure node before
    a warning."""


class DestinationStatesConfig(ConfigModel):
    max_unidentified_share: float = Field(ge=0, le=1)
    """Largest share of state-level case tonnage allowed in the unidentified state `XX` before a
    warning."""


class ArrivalPortsConfig(ConfigModel):
    voyage_radius_km: float = Field(gt=0)
    """Distance from a Census port of unlading within which a container voyage's end point counts
    toward that port's observed sea distance."""


class MexicoSitesConfig(ConfigModel):
    min_employees: int = Field(gt=0)
    """Smallest DENUE employee band, by its lower bound, whose establishments are assembly sites."""


class TransformsConfig(ConfigModel):
    """Settings the dbt models read; `shockt build` passes them to dbt as vars."""

    air_ports: AirPortsConfig
    census_ports: CensusPortsConfig
    climatetrace: ClimateTraceTransformsConfig
    overland_weight: OverlandWeightConfig
    mexico_sites: MexicoSitesConfig
    arrival_ports: ArrivalPortsConfig
    departure_nodes: DepartureNodesConfig
    destination_states: DestinationStatesConfig


class HsPrefix(ConfigModel):
    prefix: str = Field(pattern=r"^\d{2,10}$")
    cases: list[str]


class HsCodesConfig(ConfigModel):
    prefixes: list[HsPrefix]

    @model_validator(mode="after")
    def _no_nested_prefixes(self) -> "HsCodesConfig":
        """Loads are requested per prefix, so a prefix inside another would load rows twice."""
        codes = [p.prefix for p in self.prefixes]
        nested = sorted({(a, b) for a in codes for b in codes if a != b and b.startswith(a)})
        if nested or len(codes) != len(set(codes)):
            raise ValueError(f"HS prefixes must be distinct and not nested: {nested or codes}")
        return self

    def hs2_chapters(self) -> list[str]:
        """The HS-2 chapters of every case prefix, e.g. 84 for 847150."""
        return sorted({p.prefix[:2] for p in self.prefixes})

    def for_cases(self, cases: Sequence[str]) -> list[str]:
        """Prefixes belonging to any of `cases`."""
        return [p.prefix for p in self.prefixes if set(p.cases) & set(cases)]


def _load_yaml(path: Path) -> object:
    with path.open() as f:
        return yaml.safe_load(f)


@cache
def sources_config() -> SourcesConfig:
    return SourcesConfig.model_validate(_load_yaml(CONFIG_DIR / "sources.yaml"))


@cache
def hs_codes_config() -> HsCodesConfig:
    return HsCodesConfig.model_validate(_load_yaml(CONFIG_DIR / "hs_codes.yaml"))


@cache
def origins_config() -> OriginsConfig:
    return OriginsConfig.model_validate(_load_yaml(CONFIG_DIR / "origins.yaml"))


@cache
def eu_reporters_config() -> EuReportersConfig:
    return EuReportersConfig.model_validate(_load_yaml(CONFIG_DIR / "eu_reporters.yaml"))


@cache
def transforms_config() -> TransformsConfig:
    return TransformsConfig.model_validate(_load_yaml(CONFIG_DIR / "transforms.yaml"))
