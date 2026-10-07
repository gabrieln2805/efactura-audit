-- VAT subtotals with the VAT expected from taxable amount x rate and the difference in lei.
-- Zero-rated and exempt categories without VAT, and subtotals without a rate, are not checkable.
select
    v.invoice_key,
    v.category,
    v.category_code,
    v.rate,
    v.taxable,
    v.tax,
    round_even(v.taxable * coalesce(v.rate, 0) / 100, 2) as expected_tax,
    abs(round_even(v.taxable * coalesce(v.rate, 0) / 100, 2) - v.tax) * coalesce(i.fx_to_ron, 1.0) as difference_ron,
    v.rate is null
        or (v.category_code in ('Z', 'E', 'AE', 'K', 'G', 'O') and v.tax = 0) as not_checkable
from {{ ref('stg_vat_breakdown') }} v
join {{ ref('stg_invoices') }} i using (invoice_key)
