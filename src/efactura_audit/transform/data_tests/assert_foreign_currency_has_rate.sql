-- Invoices in a foreign currency without a RON rate (no RON VAT total on the document): their amounts stay in the document currency.
{{ config(severity='warn') }}
select invoice_key, number, currency
from {{ ref('stg_invoices') }}
where currency <> 'RON' and fx_to_ron is null
