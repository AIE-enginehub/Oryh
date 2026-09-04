<!-- generated from docs/manual/daily-use.md by the help-references sync (sync_help_references) — edit the source, not this file -->

# Daily use

Day to day, nobody opens the console. People talk to their own agent, and the
agent uses the skills your workspace issued it. This page is what that looks
like, by role.

The skills below are the ones the current public release ships. `skills/` in
the repository is the authority on what your copy actually has — the list
grows between releases.

## Everyone

| Ask for | Skill |
|---|---|
| "What do I need to do?" | `oryh-my-work` |
| "How does oryh work?" / "what does this permission mean?" / "do I need admin for that?" | `oryh-help` |
| "Book meeting room B for Thursday" | `oryh-resource-booking` |
| "How much was I paid this month?" | `oryh-payslip` |
| "Connect me" / "my key stopped working" | `oryh-connect` |
| Keeping installed skills current | `oryh-skill-sync` |

`oryh-my-work` is the one worth teaching people first. It answers "what should
I do" from the server's own queues — what is waiting for their approval, what
they submitted that came back, what is due. Agents that support session-start
hooks run it at the beginning of a session, so the person is told rather than
having to ask.

## Filing your own documents

Each of these covers one document, for the person filing it: draft it, amend
it, query it, submit it.

| Document | Skill |
|---|---|
| Timesheet | `oryh-timesheet-submit` |
| Expense claim (reads the receipt) | `oryh-expense-submit` |
| Leave request, and the balance behind it | `oryh-leave-submit` |
| Purchase request | `oryh-purchase-submit` |
| Sales quotation | `oryh-quotation-submit` |
| Sales order | `oryh-order-submit` |

The input is ordinary speech. "Monday to Wednesday on the Globex integration,
eight hours a day, Thursday I was in interviews" is a timesheet. The agent
turns it into fields and reads the result back — and reading it back is the
important half, because the structure is the agent's interpretation and only
the person can confirm it is what they meant.

## Approving

| Ask for | Skill |
|---|---|
| Approve, reject or return one document | `oryh-approve` |
| Tell the participants something moved | `approval-notifier` |

`oryh-approve` is one skill for every document type — a timesheet, an expense
claim and a purchase request are approved the same way, because approval is
the same act. What differs is the routing, and routing is a document your
workspace writes rather than a graph someone draws.

**Routing itself is not shipped.** The hosted service maintains its own
approval-flow skills; a self-hosted deployment writes its own with
`oryh-skill-author`, or approves directly. If you want it unattended, the
optional flow runner drives queues with your own agent runtime and model key —
see operations.

## Sales pipeline

| Ask for | Skill |
|---|---|
| Capture and advance leads, convert one into a customer and an opportunity | `oryh-crm` |
| Record orders from Tmall, JD or another platform — dedup by the platform number, translate listings through the product map, confirm the unmapped ones once | `oryh-order-submit` |

## Procurement and stock

| Ask for | Skill |
|---|---|
| Place and maintain purchase orders, receive against them; hand an OEM factory the material advice from the bill of materials | `oryh-purchase-order` |
| File a contract's original and its key terms, then ask "what is the payment schedule on this one" | `oryh-contracts` |
| Goods in, goods out, counts, adjustments; reservations, picklists, shipments and their stock posting | `oryh-inventory` |

## Finance

| Ask for | Skill |
|---|---|
| Bill a customer, register receipts, settle | `oryh-receivables` |
| Book what a supplier billed, check it against the PO, pay it | `oryh-payables` |
| Customer deposits and credit lines | `oryh-billing-account` |
| Where the money sits and moves — bank and platform accounts, statement import, bank charges as register facts, reconciliation of a line to a payment or to a whole payroll batch | `oryh-treasury` |

Settlement is a ledger, not a status field — an invoice is not "paid" because
somebody set it to paid, it is paid because payments were matched against it.
The reasoning is in invoices, payments and
settlement and billing
accounts.

## HR and pay

| Ask for | Skill |
|---|---|
| Set or revise someone's pay terms | `oryh-payroll` |
| Read pay — your own, or a batch if you hold `payroll.read` | `oryh-payslip` |

Pay is the sharpest example of reads being permissions: `oryh-payslip` shows a
person their own payslip with no special grant, and shows a batch only to
someone the workspace deliberately named. See payroll.

## Administrators

| Ask for | Skill |
|---|---|
| "We just deployed — where do I start?" | `oryh-workspace-setup` |
| "Let Xie Ting place purchase orders" | `oryh-access-admin` |
| Write, publish, amend or repeal a company rule | `oryh-policy` |
| Load or maintain master data | `oryh-master-data` |
| Turn a process requirement into workspace configuration | `oryh-skill-author` |
| Bulk-import history from an old system | `oryh-data-migration` |
| Record or query any workspace-defined object | `oryh-business-object` |
| Summarise a set of them — "this week's site surveys" | `oryh-business-object-summary` |

## Changing how it behaves

Most of what a company calls "our process" is prose here, so changing it is
usually a sentence to an agent rather than a project:

> "When you report my todos, list titles and due dates only — do not expand
> the linked record."

> "Pay approved expense claims directly. We do not raise reimbursement
> invoices."

> "Call the post-approval invoice state `approved`, not `issued`."

Those land on three different knobs — a skill's calibration, the workflow
definition, the lifecycle machine — and an administrator's agent knows which.
All three take effect immediately, for everyone, with no fork and no deploy.
Agents pick the change up on their next session and are told what changed.

**Where prose stops:** calibration cannot widen what a skill may do. The
server enforces permissions, state transitions, settlement arithmetic and
attribution regardless of what any instruction says. Natural language decides
how work is done; it never decides what is allowed.

## Next

Administration — the console, screen by screen.
