-- One row per flag and invoice it involves (a near-duplicate flag involves two invoices, an IBAN flag several).
select
    flag_id,
    unnest(from_json(invoice_keys, '["VARCHAR"]')) as invoice_key,
    check_name,
    severity,
    status
from {{ ref('fct_flags') }}
