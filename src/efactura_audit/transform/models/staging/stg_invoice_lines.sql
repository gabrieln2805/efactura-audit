-- One row per invoice line, as on the document.
select
    invoice_key,
    line_no,
    item_name,
    item_norm,
    seller_item_id,
    quantity,
    unit_code,
    unit_price,
    unit_price_ron,
    base_quantity,
    net_amount,
    net_amount_ron,
    vat_category,
    vat_rate
from {{ source('raw', 'invoice_lines') }}
