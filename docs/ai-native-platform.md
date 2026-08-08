# AI-Native OA/BPM Positioning

## Summary

`oryh` is the system of record for AI-driven business operations.

It is not intended to become a traditional monolithic OA suite or a heavyweight BPM engine by itself. Instead, it works with AI agents, memory, skills, and external integrations to form an AI-native OA and BPM platform.

The platform split is:

- `oryh`: records business objects, object links, approval events, todos, bookings, and audit-friendly facts — and stores the tenant's structure and rules **as data**: object type definitions (schema + lifecycle state machines), versioned natural-language workflow definitions, roles/capabilities, and the skill registry
- AI agent: understands user intent, reads the tenant's workflow definition, decides next actions, and coordinates tools — the backend never interprets the rules it stores
- memory: softer per-agent context — contacts, preferences, conventions
- notifier and integrations: deliver emails, messages, reminders, escalations, and external system sync

In short:

- `oryh` stores truth **and the rules as data**
- AI agents read the rules and drive flow
- memory stores soft context
- skills execute focused capabilities

## What `oryh` Should Be

`oryh` should be the durable execution and recording layer for enterprise operations.

That means it should be strong at:

- tenant isolation
- API-based business operations
- recording structured business facts
- recording approval facts
- creating and completing employee todos
- preserving original natural-language source text
- storing audit-ready metadata
- supporting lightweight, reusable business objects

Examples already in scope:

- timesheets
- expense claims (with receipt attachments)
- purchase requests (with optional vendor/product/price)
- sales quotations (with customer/product snapshots, list-price facts, and revisions)
- sales orders (fulfilment of won quotations: SO numbers, promised dates, logistics facts to sign-off)
- invoices in both directions (销项/进项), with the tax document's own number and the order lines they bill
- payments and the 核销 ledger that says which documents each one settled
- business objects
- business object links
- resource bookings
- employee todos

Business processes that are specific to a customer or tenant should normally be represented as:

- a skill that describes the workflow
- memory that stores policy, contacts, routing, and tenant conventions
- generic records in `business_objects`
- typed relationships in `business_object_links`
- approval facts in `approval_records`
- human work items in `todos`

When a skill updates `business_objects.payload`, it must treat the API as a full payload replacement: read the object, merge changes in the agent, then send the complete payload back.

## What `oryh` Should Not Try to Be

`oryh` should not absorb every orchestration concern into its own tables and endpoints.

It should not be responsible for:

- full approval routing logic
- dynamic policy reasoning
- organization-wide escalation strategy
- all notification behavior
- all human-facing interaction flows
- giant master-data governance
- deeply customized BPM diagram execution

Those concerns belong mainly in the AI orchestration layer and supporting policy context.

## Layered Architecture

### 1. Record Layer: `oryh`

This layer keeps durable business state.

Typical responsibilities:

- create and update domain objects
- record approval events
- manage business objects
- manage business object links
- manage todos
- manage projects and resources
- manage bookings and business entries
- expose stable APIs

Examples in the current system:

- `timesheet_headers`
- `timesheet_entries`
- `expense_claims`
- `expense_items`
- `attachments`
- `vendors`
- `customers`
- `products`
- `purchase_requests`
- `purchase_request_items`
- `sales_quotations`
- `sales_quotation_items`
- `sales_orders`
- `sales_order_items`
- `invoices`
- `invoice_items`
- `payments`
- `payment_applications`
- `business_objects`
- `business_object_links`
- `approval_records`
- `todos`
- `resources`
- `resource_bookings`

### 2. Orchestration Layer: AI Agent

This layer interprets user intent and decides what to do next.

Typical responsibilities:

- interpret natural-language requests
- determine which business capability to invoke
- resolve missing context
- choose the right workflow
- decide the next approver
- decide whether to notify, remind, or escalate
- decide when to update final state in `oryh`

This is where OA and BPM behavior becomes flexible without turning the record system into a giant workflow engine.

### 3. Policy Layer — Now Mostly Tenant Data In oryh

The original design kept all policy in agent memory. Experience with multiple
local agents changed that: an agent's memory is private and volatile, while
routing rules are tenant assets. Durable policy therefore moved into oryh
as versioned tenant data, still interpreted only by agents:

- **workflow definitions** (`/workflow-definitions`): natural-language process
  maps, append-only versions, history queryable — "which requests require
  manager and finance approval" lives here
- **roles and capabilities** (`/roles`, `/capabilities`): who may do what
- **object type definitions**: payload schema + lifecycle state machines
- **the skill registry**: the process contracts themselves

What stays in agent memory: contact habits, phrasing preferences,
conversational context — soft knowledge that does not need tenant-level
durability or versioning.

### 4. Skill and Integration Layer

This layer exposes specialized execution capabilities to the agent.

Product skills shipped in this repository (provisioned into every tenant's
registry, delivered to users as capability-derived personal bundles with
their credential rendered in):

- `oryh-my-work`
- `oryh-timesheet-submit`
- `oryh-approve` (one approval contract for every document type)
- `oryh-timesheet-approval-flow`
- `approval-notifier`
- `oryh-resource-booking`
- `oryh-business-object`
- `oryh-business-object-summary`
- `oryh-skill-sync`
- `oryh-order-submit` / `oryh-order-approval-flow`
- `oryh-master-data` (gated on `master_data.manage`: spreadsheet import and
  upkeep for products, vendors, and customers)
- `oryh-skill-author` (admin-gated: compiles natural-language process
  requirements into workflow definitions or customer workflow skills)

Skill distribution has two deliberately separate paths:

- **Issuance** (`POST /users/{id}/skill-bundle`, admin console): mints the
  user's personal key — rotating any previous one — and renders their
  eligible skills into a downloadable bundle. This is the only path that
  creates or revokes credentials.
- **Sync** (`GET /my/skills/manifest` + `GET /my/skill-bundle`,
  authenticated by the bundle's own user-bound key): the local agent
  compares the server's per-user manifest (name, version, content hash)
  against the bundle's `manifest.json` and re-downloads when anything
  changed. The refresh is rendered with the key the agent presented, so
  syncing never rotates credentials and a person's other devices keep
  working. Eligibility is evaluated per request, so role changes propagate
  the same way content updates do. `oryh-skill-sync` packages this
  routine so every agent knows to run it.

A bundle is scoped to one employer, and says so in every name it installs: the
directory is `oryh-skills-<slug>/`, each skill is `oryh-<slug>-timesheet-submit`,
and the description opens with the company. That is what lets one agent serve a
person who works for two companies — the name and description are all it sees
when it picks a skill, and the key inside that skill can only reach that
company's oryh. The slug is derived once from the tenant's email domain and is
immutable; the namespacing happens at render time only, so the registry keeps
canonical names and tenant-independent content hashes. `oryh-connect` is the one
exception: it runs before any tenant is known, so it is machine-level, shared,
and unprefixed. See [device-flow.md](device-flow.md#two-employers-one-agent).

This split follows the same state-based philosophy as agent coordination:
there is no push channel and no delivery tracking — an installed bundle is
a cache, the registry is the source of truth, and any agent can ask "am I
current?" at any time and converge.

Customer workflow skills stored as tenant data in the `/api/v1/skills` registry (demo examples seeded per tenant from `demo/skills/<tenant-slug>/`):

- `jc-warranty-card-apply` / `jc-warranty-card-approve` / `jc-warranty-card-flow` / `jc-warranty-repair-record`
- `jc-quote` — the Guiyi-style quote-to-cash skill: one bundle line for the salesperson's whole arc, phase details in references (`intake.md`: dirty model-code resolution with a correction-confirm gate feeding `oryh-quotation-submit`; `follow-up.md`: deal-won → SO number → logistics-to-signoff over a tenant-defined `sales_order` object)
- `sb-quote` — the consulting flavor of the same pattern: rate-card capture, then deal → contract link → kickoff → milestones

Skill granularity is a first-class rule (encoded in `oryh-skill-author`'s
authoring guide): split by role (submit/approve/flow), merge one role's
phases into a single skill with per-phase references, and never mint a skill
per object type — `oryh-business-object` covers any custom type by reading
its object-type definition and workflow definition at use time. An ordinary
member's bundle should stay well under ten skills.

The quote-to-cash customization demonstrates the layering end to end: policy (discount tiers, OCR-confirm requirement, freight notes) lives in the tenants' workflow definitions; process contracts live in these skills; deterministic needs (price matrices, exact code parsers, PDF templates) are named as agent-side tools, deliberately outside both. `oryh-skill-author` is how a tenant admin's agent produces this kind of configuration from plain language.

Typical responsibilities:

- package stable input and output contracts
- guide agents to use APIs correctly
- narrow execution behavior for a specific business capability
- encode customer-specific workflows without adding backend business tables
- connect the agent to external delivery channels or system APIs

Skill layering should stay explicit:

- Base record skills wrap reusable oryh API patterns, such as `oryh-business-object` (write one at a time) and its read/aggregate counterpart `oryh-business-object-summary` (summarize many, gated separately by `business_object.summarize` so read-only distribution can differ from write access — e.g. a manager summarizing daily reports without needing to author them).
- Standard business skills describe built-in product capabilities, such as `oryh-timesheet-submit`, `oryh-approve`, `oryh-timesheet-approval-flow`, and `oryh-resource-booking`.
- Customer workflow skills describe tenant-specific process logic, such as the JC warranty skills. They are tenant data: stored per tenant in the `/api/v1/skills` registry, versioned, and invisible to other tenants — defining a new workflow never touches the shared codebase.
- Integration skills perform external side effects, such as `approval-notifier`.

For timesheets specifically, the split is enforced by capabilities, not just
convention:

- my-work skill: the check-in — my todos, my in-flight progress (everyone)
- submit skill: capture and submit own timesheet facts (`timesheet.submit_own`)
- approve skill: record exactly one approval fact and complete own todo
  (`approval.record`) — never advances the flow
- approval-flow skill: the workflow admin's loop — work queue → trail →
  workflow definition → next todo or final status (`timesheet.advance`,
  normally a service credential)

The JC warranty flow follows the same split:

- application skill: capture and register warranty card facts
- approve skill: execute one approver action
- flow skill: orchestrate routing and registration completion
- repair-record skill: record service-provider repair facts and link them to cards

This separation is important: a customer workflow skill may call a base record skill, but the backend should not absorb that workflow just because it is useful for one customer.

Skill input names should be read as execution contracts. Some map directly to records, while others are agent context:

- record ids such as `header_id` and `warranty_card_id` map to `timesheet_headers.id` or `business_objects.id`
- generic entity APIs store those ids as `entity_id` plus an `entity_type`
- actor fields such as `actor_id` are execution metadata and only land in fields such as `created_by`, `submitted_by`, `completed_by`, or `metadata` when an API supports that usage
- role fields such as `approver_role` are approval-event snapshots, not necessarily master data

## How This Becomes an OA Platform

Traditional OA platforms usually combine:

- forms
- workflow rules
- notifications
- approvals
- records

In an AI-native model, those concerns are distributed differently:

- the user talks to the AI agent
- the AI agent structures the request
- `oryh` records the request and its state
- the AI agent drives approval and operational steps
- notification skills contact the right people
- memory stores business-specific routing and policy

This allows OA-like coverage without requiring a rigid page-first product for every process.

Example:

- A service provider submits a JC warranty card application in natural language.
- Their agent uses the `jc-warranty-card-apply` skill (from their personal bundle) to create a `warranty_card` business object and records the `submitted` fact.
- The tenant's flow agent finds it in the work queue, reads the tenant's warranty workflow definition, and creates the approver's todo.
- The notifier skill pushes the assignment to the approver's channel.
- The approver's agent records the approval fact and completes its own todo; the flow agent finalizes the status and registration fields follow.
- Later repairs are stored through `jc-warranty-repair-record` as `warranty_repair` business objects and linked with `repair_of`.

## How This Becomes a BPM Engine

The BPM behavior comes from the combination of:

- business objects, approval records, and todos in `oryh`
- versioned natural-language workflow definitions in `oryh` (data, not engine)
- a flow agent that derives the position from the trail and decides the next node
- lifecycle state machines that guard coarse legality (409 on illegal transitions)
- state-based coordination: work-queue queries and todos, no event cursors

Two principles proved out in review and are now load-bearing:

- **Workflow nodes are not object states.** A node can repeat (finance review
  twice after an override) or run in parallel; no status field can express
  that. Nodes passed = approval records; current holder = open todos;
  possible next = the workflow definition. The record stays `submitted`
  while the flow runs.
- **Coordination is level-triggered state, not delivered events.** Todos make
  "handled or not" a first-class fact; a crashed agent loses nothing because
  the queue query is self-healing. The audit trail exists for accountability,
  explicitly not as a delivery mechanism.

This is a different shape from traditional BPM, but it can support many BPM use cases with better flexibility for AI-led interaction.

## Core Design Principle

Keep long-lived business facts in `oryh`.

Keep long-lived rules in `oryh` too — but **as versioned tenant data the
backend never interprets**. Agents read the rules and act; the record layer
guards legality (permissions, lifecycle transitions, isolation) without
executing workflow logic.

That principle prevents the system from collapsing into either:

- an underpowered data store with no operational value
- or an overgrown monolith that tries to own every workflow rule

## Current Fit

The current implementation already fits this architecture well:

- timesheets are recorded as business facts; approvals as append-only, idempotent events
- todos represent work waiting on a person, with due dates for escalation
- business objects + links handle tenant-specific records without dedicated tables; type definitions add optional schema and lifecycle guards
- workflow definitions make routing rules durable, versioned tenant data
- roles/capabilities make the permission surface tenant-configurable, with scoped grants extending automatically to new object types
- skills are tenant data with capability gates — including object-type-scoped gates (`business_object.write:daily_report`), matched by the same grammar the API enforces — authorable in the React console (`/console/skills`) and delivered as credential-embedded personal bundles that self-update via per-user manifest sync (no credential rotation, no push channel)
- onboarding is self-service end to end: the credential-free `oryh-connect` skill (public download at `/web/connect`) runs a browser device flow that mints a per-device key and pulls the person's bundle — no admin in the loop, admin issuance remains the rotate-all lever
- multi-tenant isolation is enforced twice: application filtering and Postgres RLS
- the multi-agent scenario simulation (`scripts/agent_scenario_test.py`) exercises this whole architecture end to end

## Gaps to Expect If the Platform Expands

Built since this document was first written: audit trail with policy version
references, role and permission models (tenant-defined RBAC), skill
versioning and per-tenant registries, workflow definitions with version
pinning, member self-service onboarding (browser device flow + per-device
keys, [device-flow.md](device-flow.md)), object-type-scoped skill gates with
a console skill editor ([scoped-skill-capabilities.md](scoped-skill-capabilities.md)).
Explicit event streams were built and then deliberately **rejected**
in favor of state-based coordination — cursors and delivery tracking do not
fit unreliable LLM-agent consumers.

Remaining likely needs:

- reporting views across objects, approvals, and todos
- org structure (`employees.manager_id`) so routing rules resolve from data
- rate limiting, a real email provider, HTTPS deployment hardening
- platform-operator action auditing

These should be added carefully so the record layer stays stable.

## Practical Product Statement

The most accurate description is:

`oryh` is a multi-tenant, AI-native enterprise record system: it stores each tenant's facts, structure, and rules as isolated data, and — together with the local AI agents that read those rules and the skills that contract their behavior — enables OA approval workflows and BPM-style execution without a workflow engine.

That framing is stronger and more sustainable than describing `oryh` alone as a full traditional OA or BPM engine.
