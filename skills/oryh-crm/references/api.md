# Oryh CRM API Reference

{{include:_common/api-auth-principal.md}}

## Leads And Opportunities

```text
GET    /leads?employee_id=&status=&source=&keyword=
POST   /leads                        → 422 unless it names a company or a person
PATCH  /leads/{id}                   → fields + status; `converted` only via the bridge
POST   /leads/{id}/convert           → {customer_id | customer_name?, opportunity_title?, expected_amount?, expected_close_date?}
DELETE /leads/{id}                   → soft delete; /restore undoes

GET    /opportunities?employee_id=&customer_id=&lead_id=&status=&keyword=
POST   /opportunities                → title required; customer matched or snapshot, the quotation convention
PATCH  /opportunities/{id}           → won/lost stamps closed_at (literal names)
```

Everyone in the workspace reads the pipeline; only `crm.own` (or an
admin acting for any employee) writes, and only their own records.
