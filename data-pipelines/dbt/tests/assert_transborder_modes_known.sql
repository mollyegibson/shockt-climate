-- Fails when a TransBorder mode code isn't in the BTS codes document's list (`transborder_mode` gives null).
select disagmot, count(*) as rows
from {{ ref('stg_bts_transborder') }}
where mode is null
group by disagmot
