-- Per invoice: stated VAT total vs the sum of its VAT subtotals, and net + VAT vs gross, in lei.
with subtotals as (
    select invoice_key, sum(tax) as subtotal_tax
    from {{ ref('stg_vat_breakdown') }}
    group by 1
)

select
    i.invoice_key,
    i.tax_exclusive,
    i.tax_total,
    i.tax_inclusive,
    s.subtotal_tax,
    abs(s.subtotal_tax - i.tax_total) * coalesce(i.fx_to_ron, 1.0) as subtotal_difference_ron,
    abs(i.tax_exclusive + i.tax_total - i.tax_inclusive) * coalesce(i.fx_to_ron, 1.0) as gross_difference_ron
from {{ ref('stg_invoices') }} i
left join subtotals s using (invoice_key)
