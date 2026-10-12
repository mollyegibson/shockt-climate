-- UK government GHG conversion factors from the current load, one row per factor, with labels cleaned of stray spaces.
select
    u.id,
    u.scope,
    {{ clean_label('u.level_1') }} as level_1,
    {{ clean_label('u.level_2') }} as level_2,
    {{ clean_label('u.level_3') }} as level_3,
    {{ clean_label('u.level_4') }} as level_4,
    {{ clean_label('u.column_text') }} as column_text,
    u.uom,
    u.ghg_unit,
    u.factor,
    u.load_id
from {{ source('raw', 'uk_ghg_conversion_factors') }} as u
where u.load_id in ({{ succeeded_loads('uk_ghg_conversion_factors') }})
