-- Flags from the latest audit with the reviewer's decision.
select
    f.flag_id,
    f.run_id,
    f.check_name,
    f.rule,
    f.severity,
    f.score,
    f.supplier_cui,
    f.supplier_name,
    f.invoice_keys,
    f.invoice_numbers,
    f.issue_date,
    f.amount_at_risk_ron,
    f.title_en,
    f.title_ro,
    f.evidence,
    f.created_at,
    coalesce(fb.status, 'open') as status,
    fb.note as review_note
from {{ source('audit', 'flags') }} f
left join {{ source('audit', 'flag_feedback') }} fb using (flag_id)
