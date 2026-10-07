-- VAT subtotals per invoice, category and rate, as stated on the document.
select
    invoice_key,
    category,
    upper(coalesce(category, '')) as category_code,
    rate,
    taxable,
    tax
from {{ source('raw', 'vat_breakdown') }}
