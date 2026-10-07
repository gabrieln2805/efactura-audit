-- One row per supplier and bank account used, with first and last use.
select
    supplier_cui,
    supplier_iban,
    invoices,
    first_used,
    last_used,
    spend_ron,
    suppliers_on_account
from {{ ref('int_supplier_ibans') }}
