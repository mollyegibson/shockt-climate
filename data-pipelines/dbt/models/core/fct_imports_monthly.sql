-- Country-level imports, one row per month × HS-10 × country × mode.
{{ unpivot_modes(ref('stg_census_hs'), ['month', 'hs10', 'hs6', 'census_cty_code'], charges=true) }}
