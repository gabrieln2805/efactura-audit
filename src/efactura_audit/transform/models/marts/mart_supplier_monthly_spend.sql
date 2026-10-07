-- Spend per supplier and calendar month (lei incl. VAT; credit notes count negative).
select
    supplier_cui,
    strftime(issue_date, '%Y-%m') as month,
    count(*) as invoices,
    sum(spend_ron) as spend_ron
from {{ ref('stg_invoices') }}
group by 1, 2
