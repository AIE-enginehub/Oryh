# oryh

**Agent-native business records for one company, self-hosted.**

oryh is a **headless ERP/CRM** — the system of record that AI agents operate
against. Customers and vendors, products and inventory, quotations, orders,
invoices in both directions, payments and settlement, payroll: the documents a
business actually runs on, behind an API designed to be driven by an agent
rather than clicked through by a person. It stores facts and state; the agents
your people already use drive the flow.

**Bring your own agent.** Skills are markdown instructions plus plain HTTP —
no SDK, no client library, nothing to keep in step with a release. So most
general-purpose agents work as they are: Claude Code, Codex, Hermes and others
of that class. Connect one once, and it works your company's records through
skills your workspace owns.

**Just want to look?** <https://oryh.ai> runs the same product as a hosted
service — nothing to install.

```bash
git clone https://github.com/AIE-enginehub/Oryh.git
cd oryh
docker compose up -d --build
docker compose logs api | grep -A6 "standalone workspace created"
```

The first build takes a few minutes; migrations then run on start. When
`docker compose ps` shows four healthy services, open
<http://127.0.0.1:8080/>.

That `grep` is the whole point of the second command: first boot creates one
workspace, its administrator and a service key for agents, and prints them
**once** — after a hundred lines of migration output. Store both before you
move on. Change the password after signing in.

The workspace starts **empty**: no employees, no customers, no documents. It is
your company's records, waiting for your company's records. Which is why the
next step is not clicking around the console — it is connecting an agent.

## Connect your agent

`oryh-connect` is a bootstrap skill that carries **no credential** — only this
deployment's address. The agent installs it, opens the approval page, you sign
in and approve, and only then does the agent receive its own key and personal
skill bundle. Nothing is copied and pasted between the two.

```bash
curl -O http://127.0.0.1:8080/api/v1/connect-skill   # oryh-connect.zip
```

<http://127.0.0.1:8080/web/connect> serves the same download in the browser.
Unzip it where your agent looks for skills:

| Agent runtime | Skill directory |
|---|---|
| Claude Code | `~/.claude/skills` |
| Codex (app, CLI, IDE) | `~/.agents/skills` |
| Copilot CLI | `~/.agents/skills` |
| Hermes | `~/.hermes/skills` |
| OpenClaw | `openclaw skills install ./oryh-connect --global` |

Then ask the agent to connect — `/oryh-connect` in the runtimes that take slash
commands, or plain words in the ones that don't. It opens a page in your
browser; you approve there. See [device flow](docs/device-flow.md) for what the
approval actually establishes, and [capabilities and
skills](docs/capabilities-skills-api.md) for how a bundle is scoped to what its
principal holds.

Because the bundle carries this deployment's address, a copy downloaded from
one environment should not be reused against another.

## What you get

- **Documents that already know their shape** — timesheets, expense claims
  with receipt extraction, purchase requests and orders, sales quotations and
  orders, invoices in both directions, payments with an append-only settlement
  ledger, payroll, billing accounts for charge-to-account and points.
- **Your own object types** on top: a warranty card, a site survey, whatever
  the business actually tracks, with a JSON schema and a lifecycle you define.
- **Tenant-defined authorization** — capabilities, roles, and per-credential
  scoping, so an agent holds exactly what its principal holds.
- **Skills, not an SDK** — an agent downloads a bundle of instructions written
  for your workspace, with its credential rendered in. No CLI to install, no
  client library to keep in step.
- **An audit trail with server-side attribution**: who did what is decided by
  the credential, never by what the caller says about itself.

## What this is not

Headless is the substance of the claim, not a label: no page-first OA suite,
no BPM engine, and none of the six-month master-data configuration a
traditional ERP asks for before it holds a single document. There is a
console, and it is for administering the workspace — the work itself happens
through agents.

## Running it

Requires Docker and about 2 GB of RAM. Configuration lives in `.env`; see
[`.env.example`](.env.example) for what a real deployment sets — at minimum
`ORYH_BASE_URL` and SMTP, once the deployment is reachable by more than you.

Upgrade by pulling a newer release and restarting: migrations run on start and
are idempotent. Back up with `pg_dump` against the `db` service; the database
is the whole state.

Optional: an unattended flow runner (`--profile flow-runner`) that drives
queues with your own agent runtime and model key. It idles until your
workspace has a flow skill and a subscription.

## Documentation

Design notes for the parts where the modelling is the interesting bit:

- [Receivables and payables](docs/receivables-payables.md) — invoices,
  payments, and why settlement is never a status
- [Billing accounts](docs/billing-accounts.md) — one shape for money and points
- [Customers](docs/customers.md) — retail and B2B on one table, and why not a
  Party layer
- [Payroll](docs/payroll.md) · [Policies](docs/policies.md) ·
  [Device flow](docs/device-flow.md) ·
  [Capabilities and skills](docs/capabilities-skills-api.md)

The API documents itself at `/redoc`, and `/openapi.json` is the contract the
console is compiled against.

## Development

```bash
uv sync --extra dev
uv run --extra dev pytest
```

The suite runs on in-memory SQLite and needs no services. Postgres is what
deployments run on; `sql/schema.sql` is the snapshot the tests pin the ORM
against.

## Relationship to the hosted service

<https://oryh.ai> is that hosted service, and the fastest way to see what this
is before cloning anything.

This repository is the product, exported from a private trunk at each release.
What stays private is the layer that runs it as a hosted multi-tenant service
for strangers — self-service registration and its review queue, the platform
operator console, and our own operations — plus the approval-flow skills the
hosted service maintains and calibrates.

Everything here is a complete single-company deployment, not a trimmed one.
Nothing is held back to sell you an upgrade. If you would rather build your
own multi-tenant service on top of it, the licence permits that and we do not
object; you will be rebuilding that operating layer, which is the honest
description of what we kept.

## Licence

[Apache-2.0](LICENSE). The name and logo are not covered — see
[TRADEMARK.md](TRADEMARK.md). Security reports:
[SECURITY.md](SECURITY.md). Contributing: [CONTRIBUTING.md](CONTRIBUTING.md).
