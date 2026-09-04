<!-- generated from docs/manual/workspace.md by the help-references sync (sync_help_references) — edit the source, not this file -->

# Set up the workspace

A new workspace holds nothing. This page is the order in which to fill it, and
what each piece is actually for.

Almost all of it can be done by asking an administrator's agent rather than by
clicking — `oryh-master-data` loads products, vendors and customers,
`oryh-access-admin` changes who may do what, `oryh-policy` writes company
rules. The console is where you check the result and handle the exceptions.

If you would rather be walked through it, that is a skill too: ask an
administrator's agent to initialise the workspace and `oryh-workspace-setup`
reads what is already configured, interviews you about what the company
actually does, and drives the rest. Later it answers the other half of the
question — what is still missing.

## People: two different records

The distinction catches everyone once, so learn it first.

- A **user** is a sign-in identity: an email address, a password, a role.
  Someone who never signs in does not need one.
- An **employee** is a personnel record: name, employee number, the person the
  documents refer to. Timesheets, leave balances and payslips hang off this.

They are linked, but they are not the same record, and either can exist
without the other. A contractor you pay but who never signs in is an employee
with no user. An external auditor who signs in to read approval history is a
user with no employee profile — and the console will tell them so on the
to-dos screen, because a personal work queue needs a personnel record to be
about.

**Invite users** under *People & access → Users & invitations*. The invitation
is an emailed link. With the standalone default `ORYH_EMAIL_BACKEND=console`
nothing is actually sent — the message, link included, is printed to the API
log:

```bash
docker compose logs api | grep -A6 "\[oryh email\]"
```

Hand that link to the person however you normally would. Configure SMTP (see
install) before inviting more than a handful of people.

**Create employee profiles** under *People & access → Employee profiles*, or
have an agent import them in bulk with `oryh-master-data`.

## Access: roles and capabilities

Under *People & access → Roles & permissions*.

A role is a named bundle of capabilities. Capabilities are verbs, sometimes
scoped to an object type — `timesheet.submit_own`, `payroll.read`,
`purchase_order.manage`. A person's agent can do exactly what that person's
role grants, never more: the credential decides, not what the agent says about
itself.

Start with the roles the workspace was provisioned with, and add capabilities
as real work demands them rather than up front. The fastest route is a
sentence to an administrator's agent — "let Xie Ting place purchase orders" —
which `oryh-access-admin` turns into the right grant.

Two rules worth knowing before you design a permission scheme:

- **Reads are permissions too.** `payroll.read` is as consequential as writing
  pay, which is why some capabilities are granted to no shipped role at all —
  naming who holds them is your decision, not a default.
- **Prose cannot widen a grant.** Skill instructions and calibration change how
  work is done; the server decides what is allowed, regardless of any
  instruction. That is what makes editing skill text safe to do casually.

## Master data

Under the master-data screens, or in bulk through an agent with
`oryh-master-data`:

| Screen | Holds |
|---|---|
| Projects | What time and cost get booked against |
| Customers | Retail and B2B on one table |
| Vendors | Who you buy from |
| Products & SKUs | What you sell and stock — with a category tree, pictures by kind, and materials as products of type `raw_material` |
| Bills of materials | What a made good is made of; one active recipe per product, exploded to a shortage when you plan a run |
| Customer contacts, price agreements | The people at a B2B customer, and the price you agreed with them per product |
| Sales channels, stores, facilities | Where you sell (a channel's code is the key platform orders arrive under; a store hangs under it) and where you ship from |
| Resources | Meeting rooms, vehicles, equipment — anything bookable |

Load only what the first real documents need. This is not a system that wants
six months of master-data configuration before it will hold a record.

## Company rules

`oryh-policy` records the company's own rules — the employee handbook, the
expense policy, purchase approval authority — as published documents with
versions. They are not decoration: agents read them at decision time, so
"reimbursement is capped at 500 per day" written as a policy is a rule an
agent applies rather than a paragraph nobody opens. See
company rules.

## Your own object types

Under *Objects & rules → Object types & workflows*. The shipped documents
cover the common ones; a warranty card, a site survey or an equipment handover
is yours to define — a JSON schema for the fields, a state machine for the
lifecycle, in your own vocabulary. `oryh-business-object` then records and
queries them like anything else.

Two guards stand in front of that door, and they are the same in every
workspace. The server refuses a custom object named after something it
already ships — `customer`, `product`, `quote`, `sales_order`, `supplier` and
their kin — and points at the real screen instead. And an agent about to
create any custom object must first say so plainly: what it will be called,
how many rows are about to go there, and what shipped collection could hold
them instead; when a shipped twin exists it asks you for the reason and
records it on the type. Legacy customers and products are never custom
objects — they are the Customers and Products screens, loaded in bulk.

## Historical data

If you are migrating from an older system, `oryh-data-migration` exists for
exactly that — bulk historical quotations, orders and invoices, at a scale
where clicking is not an option.

## Next

Daily use — what the workspace looks like once it is loaded.
