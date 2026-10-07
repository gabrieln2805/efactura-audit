-- More than one buyer company in the workspace: use one workspace per client, or import with a buyer filter.
{{ config(severity='warn') }}
select buyer_cui, any_value(buyer_name) as buyer_name, count(*) as invoices
from {{ ref('stg_invoices') }}
group by buyer_cui
having (select count(distinct buyer_cui) from {{ ref('stg_invoices') }}) > 1
