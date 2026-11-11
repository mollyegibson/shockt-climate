# Refrigerator-component compressor analysis

Start with the [2024–2025 country trends](COUNTRY_TRENDS.md) or the [full emissions report and nine color charts](outputs/emissions/README.md).

- [Executed notebook](compressor_emissions.ipynb)
- [Standalone HTML](compressor_emissions.html) — download and open in a browser
- [Monthly country/mode data](outputs/emissions/country_mode_monthly_trends_2024_2025.csv)
- [Factors, route scenarios, coverage and decomposition](outputs/emissions/)

Air and sea are separate in the trend panels. These are aggregate HS 841430 transport scenarios,
using observed Census weight and arrival ports and assumed foreign departure allocations. They do
not establish company emissions, a production transfer, or tariff causation. The report names
missing route coverage, excludes manufacturing and refrigerant emissions, and keeps inland estimates separate.

The international comparison uses common supported origin/mode/arrival cells. Other charts use all
supported observations and are labeled accordingly. The six-country trend chart is a selected view;
the monthly CSV includes every configured country with observations.

Reproduction: run `prepare_emission_sources.py` in the existing data-pipelines environment, then
`calculate_compressor_emissions.py` in the existing analysis environment. Run `verify_emissions.py`
for weight, factor, route and decomposition checks. Frozen official sources, input archives and the
distance seeds for this run are packaged in `outputs/emissions/source_archive.zip`; extract at the
repository root before reproduction. Build the main report, then country trends, then execute/export
the notebook. The source manifest preserves the archived run's hashes; updated public references may differ.
