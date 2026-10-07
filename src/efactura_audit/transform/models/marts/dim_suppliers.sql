-- One row per supplier (CUI): latest name, activity, spend, bank accounts and flags not dismissed.
with activity as (
    select
        supplier_cui,
        first(supplier_name order by issue_date desc, number desc) as supplier_name,
        count(*) as invoices,
        count(*) filter (where is_credit_note) as credit_notes,
        sum(spend_ron) as total_spend_ron,
        avg(spend_ron) as average_invoice_ron,
        min(issue_date) as first_invoice,
        max(issue_date) as last_invoice,
        count(distinct nullif(supplier_iban, '')) as bank_accounts
    from {{ ref('stg_invoices') }}
    group by 1
),

-- a shared-account flag names several suppliers ("cui1,cui2"): it counts for each of them
supplier_flags as (
    select
        unnest(string_split(supplier_cui, ',')) as supplier_cui,
        severity,
        amount_at_risk_ron
    from {{ ref('fct_flags') }}
    where status <> 'dismissed' and supplier_cui is not null
),

flag_totals as (
    select
        supplier_cui,
        count(*) as flags,
        count(*) filter (where severity = 'high') as high_flags,
        sum(coalesce(amount_at_risk_ron, 0)) as amount_to_review_ron
    from supplier_flags
    group by 1
)

select
    a.*,
    coalesce(f.flags, 0) as flags,
    coalesce(f.high_flags, 0) as high_flags,
    coalesce(f.amount_to_review_ron, 0) as amount_to_review_ron
from activity a
left join flag_totals f using (supplier_cui)
