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
    "master_data":   {"status": "ready", "facts": {"products": 120, "customers": 40,
                       "vendors": 8, "custom_type_options": 2}, "next": "..."},
    "expense_claim": {"status": "partial",                    // one area per document family,
                      "facts": {"filing_capability": "expense.submit_own",   // derived from the registry
                                "staffed_by": {"roles": ["clerk", "member"], "active_users": 1},
                                "workflow_definitions": {"expense_claim": false},
                                "documents": 0}, "next": "publish a workflow definition ..."},
    "sales_order":   {"facts": {"documents": 12, "returns": 2,   // kind-split families count both
                                "workflow_definitions": {"sales_order": true, "sales_return": false}}},
    "flow_driving":  {"status": "ready", "facts": {"enabled": ["expense_claim", "..."], "disabled": []}},
    "ecommerce":     {"status": "untouched", "optional": true,
                      "facts": {"channel_product_maps": 0, "external_document_links": 0}}
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

Only the workflow definitions the admin phrases:

```json
POST /workflow-definitions
{
  "entity_kind": "builtin",
  "object_type": "expense_claim",
  "definition_text": "Expenses: the direct manager approves; above 5,000 add finance review."
}
```

Versions are append-only: publishing again supersedes; history stays. Every
other write — invitations, roles, master data, machine renames — belongs to
the skill this one hands off to ($oryh-access-admin, $oryh-master-data),
plus `PATCH /object-type-definitions/{id}` for state renames as taught in
the SKILL body.
