-- One row per invoice line with its invoice header, unit price in lei and matched item group.
select
    l.*,
    g.item_group,
    g.item_label,
    g.xgroup
from {{ ref('int_invoice_lines') }} l
left join {{ source('audit', 'item_groups') }} g using (invoice_key, line_no)
