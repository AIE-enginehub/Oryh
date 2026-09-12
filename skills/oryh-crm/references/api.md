# Oryh CRM API Reference

{{include:_common/api-auth-principal.md}}

{{include:_common/api-conventions.md}}

## People, Work, Vocabularies

```text
GET    /employees?keyword=           → resolve a colleague's name to employee_id
GET    /type-options?family=         → the workspace's names for activity_type, activity_outcome, event_type, event_response, communication_channel, opportunity_lost_reason, opportunity_contact_role, campaign_type, campaign_member_status
POST   /todos                        → {employee_id (your own, or todos.assign for others), entity_type, entity_id, title, due_at?}
GET    /todos?employee_id=&status=open   PATCH /todos/{id} {"status": "completed"}
GET    /customers/{id}/detail        → customer, contacts, opportunities, last activities, events, communications, quotations, orders, territory — the visit brief in one read
```

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

## Activities, Events, Communications

```text
GET    /activities?customer_id=&lead_id=&opportunity_id=&contact_id=&employee_id=&activity_type=&outcome=&occurred_from=&occurred_thru=&keyword=
POST   /activities                   → {customer_id | lead_id | opportunity_id (≥1), contact_id?, employee_id, activity_type, occurred_at, subject, content?, source_text?, outcome?, next_action?, next_action_at?, event_id?, communication_event_id?}
PATCH  /activities/{id}              → any field; DELETE soft-deletes
GET    /events?employee_id=&customer_id=&lead_id=&opportunity_id=&event_type=&status=&starts_from=&starts_thru=&keyword=
POST   /events                       → {employee_id, subject, starts_at, ends_at?, event_type?, location?, customer_id?, lead_id?, opportunity_id?, description?}
PATCH  /events/{id}                  → fields while planned; status planned → held | cancelled (cancelled → planned)
POST   /events/{id}/log              → {content?, outcome?, next_action?, next_action_at?, subject?}; 201 the activity, the event now held
GET    /event-participants?event_id=
POST   /event-participants           → {event_id, employee_id | contact_id, response?, remarks?}
PATCH  /event-participants/{id}      → response, remarks; DELETE removes
GET    /communication-events?channel=&direction=&customer_id=&lead_id=&opportunity_id=&contact_id=&employee_id=&thread_id=&message_id=&occurred_from=&occurred_thru=&keyword=
POST   /communication-events         → {channel, direction, occurred_at, customer_id | lead_id | opportunity_id | contact_id (≥1), subject?, body?, from_address?, to_addresses?, cc_addresses?, message_id?, thread_id?, employee_id?}
PATCH  /communication-events/{id}    → linkage and text; DELETE soft-deletes
```

`crm.own` writes one's own (the `employee_id` is the writer's unless the
credential may act for anyone); everyone reads. A `message_id` seen twice
answers 409 with the existing row.

## Deal Lines, Cast, Detail, Quote Bridge

```text
GET    /opportunities/{id}/detail       → opportunity, items, contacts (with names), quotations, orders, campaign
GET    /opportunity-items?opportunity_id=
POST   /opportunity-items               → {opportunity_id, product_id | product_name_snapshot, quantity, unit_price?, sku_id?, spec?, unit?, notes?}
PATCH  /opportunity-items/{id}          → any line field; amount recomputes from quantity × unit_price unless given
DELETE /opportunity-items/{id}
GET    /opportunity-contacts?opportunity_id=&role=
POST   /opportunity-contacts            → {opportunity_id, contact_id, role?, is_primary?, remarks?}; contact must be the deal's customer's
PATCH  /opportunity-contacts/{id}       → role, is_primary (demotes the previous primary), remarks
DELETE /opportunity-contacts/{id}
POST   /opportunities/{id}/quote        → {title?, quote_date?, valid_until?, payment_terms?, delivery_terms?, remarks?}
                                          201: the quotation draft with items, each carrying price_basis
                                          (opportunity_line | customer_agreement | price_book | unpriced); the deal enters quoting
```

`PATCH /opportunities/{id}` also takes `probability` (0–100), `lost_reason`
(from `opportunity_lost_reason` options), `competitor`, `source`.
Quotations and orders carry `opportunity_id` (`?opportunity_id=` on both
lists); an order created from a quotation inherits it.

## Campaigns And Attribution

```text
GET    /campaigns?employee_id=&campaign_type=&parent_campaign_id=&status=&keyword=
POST   /campaigns                    → needs campaign.manage; name, employee_id (owner); campaign_type from the campaign_type options
PATCH  /campaigns/{id}               → fields + status (planned → active → completed | cancelled by default)
GET    /campaigns/{id}/detail        → members_total, members_by_status, leads_total, leads_converted, opportunities_total, opportunities_won, won_expected_amount
DELETE /campaigns/{id}               → soft delete; /restore undoes

GET    /campaign-members?campaign_id=&lead_id=&customer_id=&member_status=
POST   /campaign-members             → {campaign_id, lead_id | customer_id (+contact_id?), member_status?, responded_at?, remarks?}
PATCH  /campaign-members/{id}        → member_status, responded_at, contact_id, remarks
DELETE /campaign-members/{id}
```

A lead's `campaign_id` (on `POST /leads` and `PATCH /leads/{id}`) and an
opportunity's are the attribution; `?campaign_id=` filters both lists.
The opportunity the conversion bridge opens inherits the lead's.
