-- One row per invoice or credit note: header, amounts and line count.
with line_counts as (
    select invoice_key, count(*) as n_lines
    from {{ ref('stg_invoice_lines') }}
    group by 1
)

select
    i.invoice_key,
    i.anaf_id,
    i.number,
    i.type_code,
    i.is_credit_note,
    i.issue_date,
    i.due_date,
    i.currency,
    i.supplier_cui,
    i.supplier_vat_id,
    i.supplier_name,
    i.supplier_reg_no,
    i.supplier_iban,
    i.supplier_city,
    i.buyer_cui,
    i.buyer_name,
    i.line_total,
    i.tax_exclusive,
    i.tax_total,
    i.tax_inclusive,
    i.payable,
    i.fx_to_ron,
    i.amount_ron,
    i.spend_ron,
    i.note,
    coalesce(l.n_lines, 0) as n_lines
from {{ ref('stg_invoices') }} i
left join line_counts l using (invoice_key)
