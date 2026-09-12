---
name: oryh-crm
description: Use when a salesperson's agent works their own pipeline in oryh — capture leads ("展会上加了个微信,记一下"), advance them, convert a qualified lead into a customer and opportunity, close won or lost. No approvals; quoting and ordering hand off to oryh-quotation-submit and oryh-order-submit. Requires crm.own.
required_capability: crm.own
---

# Oryh CRM

Work the principal's own sales pipeline: leads in, opportunities through,
deals won or lost. The credential is the identity — the server only accepts
writes for the employee linked to this key — and there is no approval half:
qualification is the principal's judgment and a deal is won by the
customer's signature, so YOU advance the states as the facts happen.

{{include:_common/answer-the-question.md}}

{{include:_common/confirm-before-you-write.md}}

## The Vocabularies Are The Workspace's

Every `*_type`, `outcome`, `role`, `channel`, `lost_reason` and member
status in this skill is a type option family the workspace may have
renamed or extended: `GET /type-options?family=activity_type` (and
`activity_outcome`, `event_type`, `event_response`, `communication_channel`,
`opportunity_lost_reason`, `opportunity_contact_role`, `campaign_type`,
`campaign_member_status`) — read the family once per session, in the same
wave as the requirements, and use its `name` values. People are resolved
by `GET /employees?keyword=`; a next step is `POST /todos` on your own
employee (anyone may assign work to themselves). One open todo per person
per record: when a lead already has your open todo, a new next step is a
`PATCH /todos/{id}` of that one (the 409 names it), not a second row.

## Trigger Examples

- "Met someone at the fair, added them on WeChat — note it down"
- "Somebody asked for a quote — log the inquiry"
- "This one signed: open the customer and the deal"
- "We won this one" / "Budget was cut, we lost it"
- "Someone asked for a quote"
- "This one is decided — create the customer and open the deal"
- "We won this one"
- "Their budget got cut, this one is lost"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  api_key: "{{ORYH_API_KEY}}"            # the salesperson's personal key
  employee_id: "{{EMPLOYEE_ID}}"         # whose pipeline this is
```

## The three rules

- **Capture fast, qualify slowly.** A lead needs only a company OR a person
  (server refuses a lead that names nobody) — record the scrap of contact
  the moment it exists, enrich later. Whether it is worth pursuing is
  judgment, not data entry: `qualified` is you saying so.
- **Convert through the bridge, never by hand.** `POST /leads/{id}/convert`
  is the ONE way a lead becomes a customer: it creates (or names) the
  Customer, carries the lead's person into the contact rolodex, optionally
  opens the Opportunity — one transaction, and the lead lands in
  `converted` holding `converted_customer_id`. A bare status write to
  `converted` is refused because it would lose WHICH customer. You do not
  need master-data authority for this; the bridge is the promotion.
- **Estimates are not money.** An opportunity's `expected_amount` is your
  guess for pipeline reading; real amounts live in the quotations and orders
  the deal produces. When the deal reaches quoting, hand off to
  $oryh-quotation-submit with the opportunity's customer — and record the
  outcome back here (`won`/`lost`), which stamps `closed_at`. A lost deal
  that comes back later is a NEW opportunity; a disqualified lead that
  comes back revives (`disqualified → contacted`).

## Working the pipeline

1. **Requirements**: `GET /workflow-definitions?entity_kind=builtin&object_type=lead`
   (and `=opportunity`) — once per session, in the same wave as the dedup
   lookups, never as a separate wait; the defaults below hold unless it says
   otherwise, and a 409 on a status you assumed is the cheap way to learn the
   tenant renamed one. Default lead life:
   `new → contacted → qualified → converted / disqualified`; default
   opportunity life: `open → quoting → negotiating → won / lost`. `won`
   and `lost` are literal — `closed_at` stamps on those two names whatever
   else the tenant renames.
2. **Dedup before create**: `GET /leads?keyword={phone or company}` — the
   same inquiry arriving twice is one lead worked twice, not two. Also
   check `GET /customers?keyword=` — somebody already in master data is
   not a lead; open an opportunity for them directly.
3. **Capture**: `POST /leads {"employee_id": "{{EMPLOYEE_ID}}", "company_name"/"contact_name", "phone", "source": "trade_fair", "geo_id": …, "campaign_id": …}`.
   Keep `source` values consistent within the workspace — the vocabulary
   is habit, not a table, and "fair"/"trade fair"/"trade-show" splitting
   one channel three ways ruins the question "where do our leads come
   from".
4. **Advance**: `PATCH /leads/{id} {"status": ...}` as facts happen. Field
   edits obey the machine's editable states; terminal states freeze the
   record (a revival is a status move, not an edit).
5. **Convert** (from `qualified`): `POST /leads/{id}/convert` with either
   `customer_id` (they were in master data all along) or nothing/`customer_name`
   (create). Add `opportunity_title` (+`expected_amount`,
   `expected_close_date`) to open the deal in the same call.
6. **Drive the deal**: `PATCH /opportunities/{id}` — stage moves, estimate
   updates, `remarks` for why. On `won`/`lost`, say the why in `remarks`
   out loud before writing it; `closed_at` stamps itself.

## Where A Lead Is, And Whose It Becomes

A lead's `geo_id` is where the inquiry is from — a geo from `GET /geos?keyword=`
(the city or district the person named; never a geo you made up from an
address). It rides the conversion bridge into the customer, together with
the lead's owner as the customer's `owner_employee_id` and, when exactly one
territory covers the place, its `territory_id`. When the bridge leaves
`territory_id` empty, `GET /territory-resolution?geo_id=` says why: nothing
covers it, or several do — and assigning it is a person's call by the
workspace's rule, through $oryh-master-data. "My customers" is
`GET /customers?owner_employee_id={{EMPLOYEE_ID}}`; "my territory's" is
`?territory_id=`.

## The Record Of Contact: Activities, Events, Messages

Three facts, three tables, one rule — **it is recorded after the person
confirms what happened**, never from your own reading of a chat log alone:

- **An activity** (`POST /activities`) is a contact that already happened —
  a call, a visit, a meeting, a message — on a customer, a lead or an
  opportunity (at least one), with `activity_type` from the workspace's
  options, when it happened, the `subject` and the `content` **the person
  confirmed**, their own words in `source_text`, the `outcome`, and
  `next_action` with `next_action_at` when there is one. When there is a
  next action, create the todo for it (`POST /todos`, `entity_type`
  the customer/lead/opportunity the activity hangs off) — the server does
  not do that for you. This is the plan's "customer follow-up log": what "prepare
  me for the visit" and "what did we last say to them" read.
- **An event** (`POST /events`) is something scheduled: subject, `starts_at`
  (and `ends_at`), `event_type`, location, the customer/lead/deal it is
  about (optional — internal events are legal), and participants
  (`POST /event-participants`: one of our people OR one of the customer's
  contacts per row, with a `response`). It walks `planned → held |
  cancelled`. **When it was held, log it**: `POST /events/{id}/log` writes
  the activity from the event (its subject, time, first customer
  participant) with the `content` and `next_action` you pass, and moves
  the event to `held`, one transaction. Never write `held` and then a
  separate activity by hand.
- **A communication event** (`POST /communication-events`) is one message
  that passed — an email, a text, a chat message — `channel`, `direction`
  (inbound/outbound), addresses, `occurred_at`, subject and body, the
  channel's own `message_id` (an email's Message-ID; the same mail
  recorded twice is one row) and `thread_id`. **Oryh does not send
  mail to customers.** The person's mail client or your own channel does,
  under the person's explicit authorisation; this row is the record. A
  message worth a follow-up becomes an activity naming it
  (`communication_event_id`).

Reading before a visit: `GET /activities?customer_id=&order_by=-occurred_at&size=10`,
`GET /events?customer_id=&status=planned`, `GET /communication-events?customer_id=&order_by=-occurred_at&size=10`,
and the open todos — one wave, then the brief.

## A Deal's Lines, Its Cast, And The Quote Bridge

An opportunity is more than a title and an estimate once it is real:

- **Lines** (`POST /opportunity-items`): what the deal is expected to be
  for — a product (by id when the catalog has it, by name when it does
  not), a quantity, a price when one was stated. "About 200 units" is
  legal here; the rigour arrives with the quotation. Lines obey the deal's
  editable states like its own fields.
- **Cast** (`POST /opportunity-contacts`): who on the customer's side
  matters and how — `role` from the workspace's `opportunity_contact_role`
  options (decision maker, influencer, champion, end user, procurement,
  finance, gatekeeper), one primary. The people must be in the customer's
  rolodex ($oryh-master-data / the lead's conversion put them there). The
  cast may change after the lines freeze.
- **Close details on the deal itself**: `probability` (0–100, your read
  by the workflow definition's stage guidance, never computed by the
  server), `lost_reason` from the `opportunity_lost_reason` options and
  `competitor` when it is lost, `source` for a deal that came without a
  lead. Say the reason out loud before writing `lost`.
- **The quote bridge** — `POST /opportunities/{id}/quote` — is the ONE
  way a deal becomes a quotation draft: the lines are copied, each priced
  from its own stated price, else the customer's agreed price, else the
  catalog (the response names the basis per line, `unpriced` when none
  applies), the primary contact goes on the quotation, and the deal moves
  to `quoting`, one transaction. It needs `quotation.submit_own` as well
  as the deal. From then on the quotation is the priced truth — work it
  with $oryh-quotation-submit; the deal's lines stay its original
  expectation. `GET /opportunities/{id}/detail` reads all of it — lines,
  cast with names, quotations, orders, campaign — in one call.

## Campaigns: Where Leads Come From

A campaign is a marketing effort — a trade fair, a webinar, a mailing, an
ad run — that leads and deals are **attributed** to. `source` on a lead
stays the free text it always was; `campaign_id` is the record behind it
when there is one, and it is what makes "did the Shanghai fair pay for
itself" a count instead of a recollection.

- **Attribute at capture.** When the person says where a lead came from
  and a campaign exists for it (`GET /campaigns?keyword=` in the same wave
  as the dedup lookups), put its id in `campaign_id`. Never invent a
  campaign to attribute to: a source with no campaign is just `source`.
- **Conversion carries it.** The opportunity the bridge opens inherits
  the lead's `campaign_id`; a deal that arrived without a lead may name
  one directly.
- **Members are who was reached.** `POST /campaign-members` with the
  campaign and ONE party — a lead, or a customer (+ optionally one of its
  contacts) — and `member_status` from the workspace's
  `campaign_member_status` options (targeted / sent / responded /
  attended / converted / declined by default). Your `crm.own` may add
  your own lead; the list as a whole is marketing's (`campaign.manage`).
- **What it earned is read, never written.** `GET /campaigns/{id}/detail`
  counts members by status, leads and how many converted, deals and how
  many were won, and sums the won deals' estimates. Report the counts;
  say out loud that the amount is estimates, not revenue.
- **Running the campaign** (create, dates, budget, `planned → active →
  completed | cancelled`) needs `campaign.manage`; without it, say who
  holds it rather than working around it.

## What This Skill Never Does

- Write `converted` by hand, or create the customer through master data —
  the bridge is the promotion.
- Work anyone else's pipeline, or quote and order from here — those are
  $oryh-quotation-submit and $oryh-order-submit.
- Treat `expected_amount` as money owed or earned.
- Invent a campaign to attribute a lead to, or report a campaign's `won_expected_amount` as revenue.
- Build a quotation by hand from a deal's lines, or set `probability` from a formula; the bridge quotes, the person judges.
- Record an activity's `content` the person has not confirmed, send a message to a customer, or mark an event `held` without logging it.

## Reference

- [references/api.md](references/api.md): request templates.
