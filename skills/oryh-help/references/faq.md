# Questions People Ask About oryh

Answers first, in the words the person used; the mechanism second. Add a
question here when it has been asked twice — the admin's `oryh-skill-author`
path is the way to grow this file.

## Permissions and roles

**"To let a member create customers, do I have to make them an admin?"**
No. Capabilities are the unit of grant; a role is just a bundle of them, and
`admin` is only the name of one shipped bundle. Creating customers needs
`master_data.manage`, and that capability can sit in any role — the shipped
`admin`, or a new role such as "catalog desk" holding exactly it. A user
holds exactly one role, so "add one permission to this person" means one of
three things: put the capability into the role they already hold (everyone
in that role gets it), move them to another role that has it, or create a
role for them. Which of the three is right is a judgement about blast radius
that the person makes; changing roles is `oryh-access-admin`'s work and
needs `users.manage`.

**"What can a plain member do?"** Everything the shipped `member` role
carries: file their own timesheets, expenses, purchase requests, leave,
quotations and orders; work their own leads and opportunities (`crm.own`);
book resources; read master data and the object directory; complete their
own todos. They cannot approve, move money, curate the catalogue, or change
anyone's access.

**"Why did the agent get a 403?"** The credential lacks the capability the
route needs, and the response names it. The right move is to say so and
hand the task to the desk that holds it — never to try another route or
another credential.

**"Who can see payroll?"** Only `payroll.read`. Payslips, pay histories and
payouts that settle a payslip are hidden from everyone else, including the
money handlers once the payout is applied.

## Objects and data

**"Can I create a custom object called `customer` / `product` / `quote`?"**
No. The server refuses a generic object named after a shipped collection and
names the real route. Legacy customers and products go into the shipped
collections through their bulk imports (`/customers/bulk`,
`/products/bulk`), history through `oryh-data-migration`. Custom objects are
for what oryh has no shape for — and creating one is never silent: the agent
says what it is about to create and, when a shipped twin exists, asks for
the reason.

**"Is a material a product?"** Yes — `product_type: raw_material`. There is
no materials table; the same catalogue, stock ledger, supplier links and
purchase lines apply.

**"Where does the Tmall order number live?"** On the order, as an external
document link (`external_document_links`); the listing-to-product
translation lives in the external product map, keyed by listing id or by
verbatim title.

**"How many stores can a channel have?"** Any number: a sales channel is
master data, its code is the key orders arrive under, and each store hangs
under one channel.

**"I deleted a bank account / a product — why does it still show?"** Master
data is never deleted, it is archived, and archived rows leave the default
lists (`status=all` brings them back, marked). An archived account's register
lines and an archived position's movements leave with their parent and come
back only when that parent is named — every such row says `archived` on it.
The mistake is undone the same way: set the status back to active.

## Money

**"Do bank fees need a payment or a vendor for the bank?"** No. A bank
charge is a `fee` row on the register — a fact about the account. A charge
netted out of a receipt rides that receipt's line as gross / fee / net.

**"Ten salaries, one bank debit — how do they match?"** The payments share
a `reference_no` (the bank batch number); the register line links to that
batch and the server checks the members sum to the debit exactly.

**"Is an invoice paid when its status says paid?"** No. Settlement is a
ledger: `outstanding_amount` is derived from the applications; `paid` is only
the flow's marker.

## Process

**"Where do the approval rules live?"** In the workflow definition for that
document family, in the company's own words. The hosted flow agent reads it;
the server never interprets it.

**"Documents are sitting in submitted and the flow agent is not moving
them."** Read `GET /workspace/setup-report` → `flow_driving.facts.parked`.
If the family is listed, the runner parked its subscription after several
runs that found work and moved nothing — nearly always a workflow definition
that does not say where those documents go. Publishing the next version of
that family's definition lifts the park by itself; if the definition was
already right and the cause was elsewhere, `PATCH /flow-subscriptions/{id}`
with `{"clear_park": true}` (needs `keys.manage`). If nothing is parked,
check the definition exists (`GET /workflow-definitions?entity_kind=builtin&object_type=…`)
and read the latest `GET /flow-runs` row for that family.

**"Can the system be configured to skip a step?"** There are no switches.
Whether a workspace picks before shipping, needs a second approver, or bills
expense claims before paying them is a sentence in a workflow definition or
a calibration line in a skill — read by agents, never stored as a flag.
