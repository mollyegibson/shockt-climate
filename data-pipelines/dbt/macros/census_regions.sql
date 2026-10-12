{#- Origin region of a Census Schedule C country code, from the regions in config/origins.yaml (the `origins` var); `other` outside them. -#}
{% macro census_country_region(code) %}
    case
        {% for region, spec in var('origins')['regions'].items() %}
        {% for census_code in spec['census_codes'] %}
        when {{ code }} = '{{ census_code }}' then '{{ region }}'
        {% endfor %}
        {% for prefix in spec['census_code_prefixes'] %}
        when {{ code }} like '{{ prefix }}%' then '{{ region }}'
        {% endfor %}
        {% endfor %}
        else 'other'
    end
{% endmacro %}
