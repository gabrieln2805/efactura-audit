-- Invoices whose line amounts do not add up to the stated line total: lines may have been missed when reading the XML.
{{ config(severity='warn') }}
select i.invoice_key, i.number, i.line_total, sum(l.net_amount) as sum_of_lines
from {{ ref('stg_invoices') }} i
join {{ ref('stg_invoice_lines') }} l using (invoice_key)
group by i.invoice_key, i.number, i.line_total
having abs(sum(l.net_amount) - i.line_total) > 0.05
