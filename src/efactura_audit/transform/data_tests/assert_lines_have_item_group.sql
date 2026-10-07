-- Lines without an item group after an audit: they were imported after the last audit run.
{{ config(severity='warn') }}
select invoice_key, line_no
from {{ ref('fct_invoice_lines') }}
where item_group is null
  and exists (select 1 from {{ source('audit', 'item_groups') }})
