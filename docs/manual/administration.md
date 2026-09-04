# Administration

The console administers the workspace. It is not where the work happens — that
is [daily use](daily-use.md) — but it is where you check what the work did,
and where the exceptions get handled.

It is available in Chinese and English; the switch is in the interface.

## Dashboard

Workspace status and the latest overview, plus the way into everything below.
A screen you check, not one you work in.

## People & access

| Screen | What it is for |
|---|---|
| **Users & invitations** | Sign-in identities. Invite, disable, set roles. |
| **Roles & permissions** | Named bundles of capabilities. |
| **Employee profiles** | Personnel records — name, employee number, the person documents refer to. |

Users and employees are different records and either can exist without the
other; [set up the workspace](workspace.md) explains why that matters.

Role names are lowercase with underscores. A capability is a verb, sometimes
scoped to an object type. What a person's agent may do is exactly what their
role grants — decided by the credential presented, never by what the caller
claims about itself.

## Master data

Projects, vendors, products and SKUs (with their category tree, pictures and
bills of materials), sales channels, stores, facilities, resources — each
with filtering and paging. Customers have their own screen, with their
contacts and price agreements. These are reference screens; bulk loading
belongs to `oryh-master-data`.

## Objects & rules

| Screen | What it is for |
|---|---|
| **Object types & workflows** | Field rules, status flow, workflow versions — for shipped documents and your own types alike. |
| **Business objects** | Every record in the workspace, with a detail view. |

Built-in entities require a state-machine definition; your own types need a
field schema and a lifecycle in your own vocabulary. Both are administrator
territory, and both are gated: an account without workspace-configuration
permission is told so rather than shown a broken screen. A custom type may
not take the name of something shipped (`customer`, `product`, `quote`…);
the server refuses it and names the real collection.

## Activity records

| Screen | What it is for |
|---|---|
| **To-dos** | The human work queue — the workspace's, and your own. |
| **Approval log** | The complete, immutable approval history. |

The approval log is a read-only audit view, and reading it is itself a
permission. An account without it is told it lacks permission rather than
shown an empty table.

"My to-dos" needs an employee profile to be about. An account with no linked
employee record is told exactly that — it is a real state, not an error.

## Skills, distribution and credentials

| Screen | What it is for |
|---|---|
| **Skills** | Which skills exist and who each one reaches. |
| **Access credentials** | API keys. Issue, label, disable. |
| **Flow agent** | Whether unattended flow driving moved anything, and whether more is waiting. |

The skills screen exists to answer one question at a glance: **who does this
skill reach?** A skill aimed at named people with nobody actually named is
shown as *targeted · nobody* — a real state, and one worth catching, because
it reaches no one while looking configured.

Access credentials is where you issue an agent key without needing the
bootstrap key from first boot, and where you disable one that leaked. A key
can be unusable for reasons that are not about the key — its user is disabled,
or was never activated — and the screen distinguishes those cases rather than
reporting a flat failure.

## The API

The console is compiled against the same contract you can read:

- `/redoc` — the API, documented from the schema
- `/openapi.json` — the contract itself

Anything the console does, an agent can do.

## Next

[Operations](operations.md) — keeping it running.
