## Who You Are Acting As

One key, one identity, and the server decides it — not you.

`GET /auth/me` answers who the key you hold belongs to. That answer is fixed
for the whole session: nothing you do earlier in a conversation changes who a
later write is attributed to. For a **user-bound key the server records the
authenticated user and ignores any identity you supply**, so a write signed as
somebody else is not something you can do by mistake.

That matters most in the case that looks alarming and is not: **one person
holding several roles.** A 总经理 who is also the workspace's flow admin is one
user with one immutable id. Having used an administrative capability earlier in
the session does not turn their own later approval into someone else's — a role
is a set of permissions, not evidence about which human is present. Do not
infer "the person changed" from your own tool history, and do not stall a
legitimate approval over it.

The genuine impersonation risk has a different shape, and it is worth checking
once rather than worrying about continuously:

| `GET /auth/me` says | What a write is attributed to |
|---|---|
| a user-bound key | that user, always — supplied ids are ignored |
| ORYH's hosted flow agent | the agent itself, always |
| the tenant's own **service** key | whoever the call names — this is the one that can sign as a person |

So: if you are on a **service key** and about to record an approval, a
timesheet, or anything else that carries a person's name, stop and say so. That
credential can attribute a decision to a colleague who never made it. On a
user-bound key, proceed — the question is already answered.

When you must state whose decision it is, compare **ids**, never names or
wording: `auth/me` `user_id` against the record's `approver_id` / `employee_id`.
Two people share a surname; nobody shares an id.

### Which workspace, and where it runs

Two separate facts, and the manifest states them separately:

| Field | Answers |
|---|---|
| `tenant.id`, `tenant.slug`, `tenant.name` | WHICH COMPANY this bundle serves |
| `environment_id` | WHICH DEPLOYMENT serves it — a test box, a private install |

A deployment name is not a company. A city, "test", "staging" name machines;
they never appear as a party to a document, and a record is not another
workspace's because it was reached through a server with a place in its name.
An agent that read the environment as a tenant refused a legitimate payment on
cross-tenant grounds — nothing leaked, but a real approval stalled on a
distinction that did not exist.

**Cross-tenant means one thing: a `tenant_id` different from the one in your
manifest.** That is the only comparison. Not the environment, not the URL, not
a city in how somebody phrased the request. In practice you will almost never
see one — every credential belongs to exactly one workspace and the server
filters everything else out before you see it, so a document you can read is a
document in your tenant. `environment_id` may be absent; that means the
deployment has no name of its own, not that anything is wrong.
