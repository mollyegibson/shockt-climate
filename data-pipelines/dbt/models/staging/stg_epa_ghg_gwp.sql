-- EPA Hub Table 11 from the current load: 100-year GWP by chemical formula.
select
    {{ clean_label('g.common_name') }} as common_name,
    {{ clean_label('g.chemical_formula') }} as chemical_formula,
    g.gwp_100yr,
    g.load_id
from {{ source('raw', 'epa_ghg_gwp') }} as g
where g.load_id in ({{ succeeded_loads('epa_ghg_gwp') }})
