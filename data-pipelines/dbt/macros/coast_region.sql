{#-
  US coast region of a port from its coordinates. Checked in order:
    noncontiguous  Hawaii (south of 25°N, west of 150°W), Alaska (north of 51°N, west of 129°W),
                   Puerto Rico and the US Virgin Islands (17–19°N, 64–68°W)
    west           Pacific coast: 24–50°N, west of 114°W
    gulf           Gulf of Mexico, Texas to Florida's west coast: 24–31°N, 81.8–98°W
    inland         Great Lakes and inland waterways: north of 41°N and west of 75.5°W, or anything left over
    east           Atlantic coast: 24–48°N, east of 81.8°W
  Missing coordinates give `unknown`.
-#}
{% macro coast_region(lon, lat) %}
    case
        when {{ lon }} is null or {{ lat }} is null then 'unknown'
        when {{ lat }} < 25 and {{ lon }} < -150 then 'noncontiguous'
        when {{ lat }} > 51 and {{ lon }} < -129 then 'noncontiguous'
        when {{ lat }} between 17 and 19 and {{ lon }} between -68 and -64 then 'noncontiguous'
        when {{ lat }} between 24 and 50 and {{ lon }} <= -114 then 'west'
        when {{ lat }} between 24 and 31 and {{ lon }} between -98 and -81.8 then 'gulf'
        when {{ lat }} >= 41 and {{ lon }} < -75.5 then 'inland'
        when {{ lat }} between 24 and 48 and {{ lon }} > -81.8 then 'east'
        else 'inland'
    end
{% endmacro %}
