{#- Analysis region of a Census Schedule C country code: Asia is the 5xxx block (including the Middle East and South Asia). -#}
{% macro census_country_region(code) %}
    case
        when {{ code }} = '2010' then 'mexico'
        when {{ code }} like '5%' then 'asia'
        else 'other'
    end
{% endmacro %}

{#-
  Coast region of a Census port from its customs district (the first two digits of the port code).
  Assigned per district, so a district's land-border crossings and airports share its region; the mode
  in the trade data says whether freight arrived by vessel, air or land.
-#}
{% macro census_district_coast_region(district) %}
    case
        when {{ district }} in ('01', '04', '05', '10', '11', '13', '14', '15', '16', '17', '52', '54') then 'east'
        when {{ district }} in ('18', '19', '20', '21', '53') then 'gulf'
        when {{ district }} in ('25', '27', '28', '29', '30') then 'west'
        when {{ district }} in ('23', '24', '26') then 'border_south'
        when {{ district }} in ('02', '07', '09', '33', '34', '36', '38') then 'border_north'
        when {{ district }} in ('35', '37', '39', '41', '45', '55') then 'inland'
        when {{ district }} in ('31', '32', '49', '51') then 'noncontiguous'
        else 'other'
    end
{% endmacro %}
