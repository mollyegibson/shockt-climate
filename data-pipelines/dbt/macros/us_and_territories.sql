{#- ISO2 codes of the United States (Schedule C 1000) and its territories (Schedule C's 9 block: Puerto Rico, the US Virgin Islands, Guam, American Samoa, the Northern Mariana Islands, the Minor Outlying Islands), from seed_census_countries. -#}
{% macro us_and_territories_iso2() %}
    select iso2
    from {{ ref('seed_census_countries') }}
    where (census_cty_code = '1000' or census_cty_code like '9%') and iso2 is not null
{% endmacro %}
