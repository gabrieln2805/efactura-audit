-- Bank accounts each supplier used, with first and last use, and how many suppliers share the account.
select
    supplier_cui,
    supplier_iban,
    count(*) as invoices,
    min(issue_date) as first_used,
    max(issue_date) as last_used,
    sum(spend_ron) as spend_ron,
    count(*) over (partition by supplier_iban) as suppliers_on_account
from {{ ref('stg_invoices') }}
where coalesce(supplier_iban, '') <> ''
group by supplier_cui, supplier_iban
