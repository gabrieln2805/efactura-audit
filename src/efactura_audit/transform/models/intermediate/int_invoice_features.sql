-- Per-invoice features for the unusual-amount check (invoices with a positive amount only).
-- Log transforms and per-supplier z-scores stay in Python, next to the models that use them.
with line_counts as (
    select invoice_key, count(*) as n_lines
    from {{ ref('stg_invoice_lines') }}
    group by 1
)

select
    i.invoice_key,
    i.supplier_cui,
    i.supplier_name,
    i.number,
    i.issue_date,
    i.spend_ron,
    coalesce(l.n_lines, 1) as n_lines,
    greatest(coalesce(date_diff('day',
        lag(i.issue_date) over (partition by i.supplier_cui order by i.issue_date, i.invoice_key),
        i.issue_date), 30), 0) as gap_days,
    day(i.issue_date) as day_of_month,
    least(greatest(coalesce(i.tax_total / nullif(i.tax_exclusive, 0), 0), -1), 1) as vat_ratio
from {{ ref('stg_invoices') }} i
left join line_counts l using (invoice_key)
where not i.is_credit_note and i.spend_ron > 0
