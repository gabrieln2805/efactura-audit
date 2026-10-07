-- Invoices without any line: price, duplicate and VAT-rate checks cannot look at them.
{{ config(severity='warn') }}
select i.invoice_key, i.number
from {{ ref('stg_invoices') }} i
where not exists (select 1 from {{ ref('stg_invoice_lines') }} l where l.invoice_key = i.invoice_key)
