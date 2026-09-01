# User manual

This manual is for the person who deployed oryh from the public repository and
now has to make it useful to a company. It covers the self-hosted product end
to end: installing it, giving it its first workspace, connecting agents,
loading the company's own records, and keeping it running.

It is not a manual for the hosted service at <https://oryh.ai>. That service
runs the same product, but registration, billing and the platform operator's
side of it are not part of what you deployed.

## The shape of the thing

oryh is headless. The documents a business runs on live here — employees,
customers and vendors, products, quotations, orders, invoices in both
directions, payments, payroll, timesheets, expense claims, leave — but the
work of creating and moving them happens through **agents**, not through
pages. A person asks their own AI agent to file a timesheet; the agent uses a
skill your workspace issued it, and the server records the fact.

That leaves the browser console with a narrower job than an ERP's UI usually
has: it administers the workspace. Who exists, what they may do, which skills
reach them, what the master data is, and what actually happened. Read
[administration](administration.md) for what each screen is for.

Two consequences worth absorbing before you start:

- **A fresh workspace is empty on purpose.** No employees, no customers, no
  documents. The first useful step after signing in is not clicking around —
  it is [connecting an agent](connect-agent.md).
- **Most of "how we do it here" is prose, not configuration.** Skills are
  markdown, approval routing is a document the flow agent reads, lifecycle
  state names are your own words. Changing behaviour is usually a sentence to
  an agent rather than a change request.

## Read in order

| Step | Page |
|---|---|
| 1 | [Install](install.md) — requirements, the four services, configuration |
| 2 | [First boot](first-boot.md) — the credentials printed once, and signing in |
| 3 | [Connect your agent](connect-agent.md) — the device flow and the skill bundle |
| 4 | [Set up the workspace](workspace.md) — people, access, master data, rules |
| 5 | [Daily use](daily-use.md) — what each role actually does |
| 6 | [Administration](administration.md) — the console, screen by screen |
| 7 | [Operations](operations.md) — backup, upgrade, email, troubleshooting |

For why things are modelled the way they are, the design notes are separate
reading: [capabilities and skills](../capabilities-skills-api.md),
[the device flow](../device-flow.md), and the business-object notes.
