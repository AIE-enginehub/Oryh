# Campaign API

Every path hangs off `api_base_url` exactly as given — no version prefix to add.

{{include:_common/api-conventions.md}}

## Campaigns

```text
GET    /campaigns?employee_id=&campaign_type=&parent_campaign_id=&status=&keyword=
POST   /campaigns                    → {name, employee_id, campaign_type?, parent_campaign_id?, start_date?, end_date?, budget?, actual_cost?, expected_revenue?, currency?, description?}
GET    /campaigns/{id}
PATCH  /campaigns/{id}               → fields + status (planned → active → completed | cancelled by default)
GET    /campaigns/{id}/detail        → members_total, members_by_status, leads_total, leads_converted, opportunities_total, opportunities_won, won_expected_amount
DELETE /campaigns/{id}               → soft delete; POST /campaigns/{id}/restore undoes
```

## Members

```text
GET    /campaign-members?campaign_id=&lead_id=&customer_id=&contact_id=&member_status=
POST   /campaign-members             → {campaign_id, lead_id | customer_id (+contact_id?), member_status?, responded_at?, remarks?}
PATCH  /campaign-members/{id}        → member_status, responded_at, contact_id, remarks
DELETE /campaign-members/{id}
```

## Vocabularies And What It Produced

```text
GET    /type-options?family=campaign_type
GET    /type-options?family=campaign_member_status
GET    /leads?campaign_id=            GET /opportunities?campaign_id=
GET    /sales-orders?opportunity_id=  → the money behind a won deal
GET    /workflow-definitions?entity_kind=builtin&object_type=campaign
```
