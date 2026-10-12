-- Imports by state of destination, one row per month × HS-6 × country × state × mode.
{{ unpivot_modes(ref('stg_census_statehs'), ['month', 'hs6', 'census_cty_code', 'state']) }}
