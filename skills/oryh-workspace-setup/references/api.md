# Oryh Workspace Setup API Reference

{{include:_common/api-auth-principal.md}}

## The One Read

```text
GET /workspace/setup-report      → {areas: {...}} — derived fresh on every call, stored nowhere
GET /tenant                      → workspace name and domain
GET /capabilities                → the capability catalog, for explaining grants in plain words
```

Report shape, per area:

```jsonc
{
  "areas": {
    "organization":  {"status": "partial", "facts": {"employees": 3, "active_non_admin_users": 0,
                       "users_linked_to_employees": 0, "custom_roles": 1,
                       "capabilities_reaching_nobody": ["leave.submit_own"]}, "next": "..."},
    "master_data":   {"status": "ready", "facts": {"products": 120, "product_categories": 9,
                       "customers": 40, "customer_contacts": 12, "customer_products": 5,
                       "vendors": 8, "stores": 2, "facilities": 3,
                       "custom_type_options": 2}, "next": "..."},
    "expense_claim": {"status": "partial",                    // one area per document family,
                      "facts": {"filing_capability": "expense.submit_own",   // derived from the registry
                                "staffed_by": {"roles": ["clerk", "member"], "active_users": 1},
                                "workflow_definitions": {"expense_claim": false},
                                "documents": 0}, "next": "publish a workflow definition ..."},
    "sales_order":   {"facts": {"documents": 12, "returns": 2,   // kind-split families count both
                                "workflow_definitions": {"sales_order": true, "sales_return": false}}},
    "picklist":      {"status": "ready",                       // approval-free families (shipment,
                      "facts": {"filing_capability": "inventory.manage",   // picklist, lead, opportunity,
                                "staffed_by": {"roles": ["keeper"], "active_users": 1},  // purchase_order)
                                "workflow_definitions": {"picklist": false}, "documents": 0}},  // are ready on staffing alone
    "flow_driving":  {"status": "ready", "facts": {"enabled": ["expense_claim", "..."], "disabled": []}},
    "treasury":      {"status": "untouched",                  // fin_account.manage reaches nobody
                      "facts": {"filing_capability": "fin_account.manage",   // until the admin names
                                "staffed_by": {"roles": [], "active_users": 0},  // the cashier
                                "fin_accounts": 0, "register_rows": 0}, "next": "grant fin_account.manage ..."},
    "ecommerce":     {"status": "untouched", "optional": true,
                      "facts": {"online_stores": 0, "channel_product_maps": 0,
                                "external_document_links": 0}}
  }
}
```

- `status` is shorthand; the FACTS are the answer. A family is `ready` when
  a person-holdable role with at least one active person carries its filing
  capability (the system admin role never counts) and, where the family has
  a flow, an active workflow definition exists.
- `untouched` states data, never intent. Whether the company USES an area is
  the administrator's judgment — keep it in your own context; the server
  stores no such decision, by design.
- `staffed_by.roles` may list shipped roles with nobody in them (`member`);
  `active_users` is the truth.

## Writes This Skill Makes Directly

Exactly two, both in the admin's own words. The workflow definitions:

```json
POST /workflow-definitions
{
  "entity_kind": "builtin",
  "object_type": "expense_claim",
  "definition_text": "Expenses: the direct manager approves; above 5,000 add finance review."
}
```

Versions are append-only: publishing again supersedes; history stays. And
the state renames: `PATCH /object-type-definitions/{id}` with a `roles`
map, as taught in the SKILL body. Every other write — invitations, roles,
master data — belongs to the skill this one hands off to
($oryh-access-admin, $oryh-master-data, $oryh-treasury, $oryh-crm,
$oryh-inventory).
