-- Invoice lines with their invoice header and a unit price in lei. Input to item-name matching.
select
    l.invoice_key,
    l.line_no,
    l.item_name,
    l.item_norm,
    l.seller_item_id,
    l.quantity,
    l.unit_code,
    l.unit_price,
    l.unit_price_ron,
    l.base_quantity,
    l.net_amount,
    l.net_amount_ron,
    l.vat_category,
    l.vat_rate,
    i.supplier_cui,
    i.supplier_name,
    i.issue_date,
    i.number,
    i.is_credit_note,
    i.currency,
    coalesce(l.unit_price_ron, case when i.currency = 'RON' then l.unit_price end) as price_ron
from {{ ref('stg_invoice_lines') }} l
join {{ ref('stg_invoices') }} i using (invoice_key)
