---
name: oryh-access-admin
description: Use when an administrator's AI agent needs to change who can do what in oryh — granting someone a capability ("let Xie Ting place purchase orders too"), creating or adjusting roles ("make a procurement-officer role"), inviting colleagues or outside vendors, moving someone to a new role, disabling a departed employee's account, or reissuing a skill bundle or access credential. Covers the capability catalog, roles as the unit of grant, user lifecycle, and what each change does to the person's installed skills. Requires users.manage. It never approves, never files documents, and never grants itself more than it already holds.
required_capability: users.manage
---

# Oryh Access Admin

Who can do what is decided in exactly three places, and confusing them is the
most common way this goes wrong:

- **Capability** — one verb, such as `purchase_order.manage`. System
  capabilities are enforced by the server; a tenant's own custom capabilities
  take effect **only in skill distribution and flow routing — the core server
  API never checks them**.
- **Role** — a set of capabilities. **The only unit of grant.**
- **User** — a person, who **holds exactly one role**.

So "give Xie Ting one more permission" has no direct counterpart in the system.
See "Three ways to grant" below — **choosing between them is the most important
judgment this skill makes**, not a mechanical step.

{{include:_common/answer-the-question.md}}

## Trigger Examples

- "Let Xie Ting place purchase orders and receive goods"
- "Create a procurement-officer role"
- "Li has moved to sales, change her permissions"
- "Invite Zhang Wei from Tai'an — he only handles warranty cards"
- "Wang has left, disable the account"
- "Who can approve expenses? Show me the permission matrix"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # the administrator's own user-bound key (needs users.manage)
```

Reissuing a skill bundle (`POST /users/{id}/skill-bundle`) **also needs
`keys.manage`**; without it you get a 403, which is role configuration rather
than something to retry.

## Steps

1. **See the current state before discussing a change.** Three read calls:
   `GET /capabilities` (system and custom capabilities, and which are scopable),
   `GET /roles` (which capabilities each role holds, and whether it is a system
   role), `GET /auth/users` (who holds which role).
   Count who can already do this thing and tell the principal — counting often
   reveals that the problem is not a missing permission but a permission held
   by too many people.

2. **Decide which of the three ways to take** (next section), **and state the
   cost before acting**. Authorization changes reach far: describe the approach
   and its consequences, get explicit agreement, then write.

3. **Execute**, one change at a time, reading it back afterwards.

4. **Tell the principal what happens next**: once the role changes, that
   person's agent picks up any newly available skills on its next
   `$oryh-skill-sync` run — **you do not need to reissue a skill bundle, and
   you should not** (see "Skill bundles and credentials").

## Three ways to grant

A user holds one role, so "let Xie Ting place purchase orders too" has three
implementations with very different costs:

| Way | How | Cost | When to choose it |
|---|---|---|---|
| **A — widen her existing role** | `PATCH /roles/{role_ref}` adding the capability to her current role | **Everyone** holding that role gets it, now and in future | The capability genuinely belongs to that position |
| **B — move her to another existing role** | `PATCH /auth/users/{id}` changing `role` | She **loses** everything her old role held | This is a transfer, not an additional duty |
| **C — create a new role** | `POST /roles`, then move her into it | One more role to maintain | This is a new responsibility that should not carry anything else with it |

**Default to C**, unless the capability genuinely belongs to that position. The
reason: A widens quietly — today one person holds `finance_reviewer`, tomorrow
a new finance hire automatically gains purchase-ordering as well.

**Treat B as a trap to guard against**: changing `role` overwrites, it does not
add. Before changing it, read out the capabilities of her current role and
confirm those are acceptable to lose.

**But compute containment first**: if the target role's capabilities are a
**superset** of her current role's — common for `member` → "member baseline
plus one" — then B is purely additive with nothing lost, and you should **not**
create a near-identical role for it. That would only be one more role to
maintain. A set comparison of the two `permissions` arrays answers this; read
the result out.

**Holding two roles at once is not possible in this model** — one person, one
role. Genuine dual duty requires a new role that unions both sets (way C). That
is a model limitation: say so plainly rather than pretending otherwise.

## Three things to say out loud before writing

- **Least privilege**: grant only what the task needs. To enable purchase
  ordering, add `purchase_order.manage` and nothing else — do not reach for
  admin.
- **Incompatible duties**: some capabilities together let one person both make
  a commitment and confirm it. The classic case is `purchase_order.manage` — it
  covers **both** placing an order and receiving against it, which is "order it
  yourself, confirm its arrival yourself". This is the textbook procurement
  control gap: **point it out**, and let the principal decide whether to accept
  it or assign receiving to somebody else. (Note: this capability cannot
  currently be split; separation of duties has to come from assigning different
  people.)
- **Who else gains it**: on way A, list everyone currently holding that role.
  `GET /roles` returns `user_count` directly — say the number first, then the
  names.

## Revoking: three more things that must be said

The three above are shaped for granting. **Revoking is not their mirror image**
and has pitfalls of its own:

- **Who loses it** — `GET /roles` gives `user_count`; say the number and the
  role name (name individuals with `GET /auth/users?role=<name>`). Nobody
  reports "I quietly lost a permission"; they discover it the next time they
  need it.
- **Whether work in flight breaks**: is this capability holding up a half-done
  process somewhere. Revoking `booking.own`, for example, also removes
  **rescheduling and cancelling** — `booking.own` bundles book/change/cancel and
  cannot be split. Check for future bookings and open todos first.
- **Whether the capability carries others with it**: capabilities do not always
  split along the line you want. `booking.own` does not distinguish resource
  types, so revoking meeting rooms revokes every bookable resource. **Say what
  cannot be done** rather than letting the principal believe they got something
  finer-grained.

**`PATCH /roles/{role_ref}` replaces the whole array.** Read `permissions` with
`GET /roles` first, remove the one entry, and write the result back —
reconstructing that array from memory makes an accidentally omitted capability
and a deliberately removed one look identical to the server and to the audit
trail. Read it back afterwards and confirm only the intended entry is gone.

**Changing a system role (`is_system: true`, especially `member`) deserves its
own sentence.** The server will not stop you — it is a legitimate administrator
action — but `member` is most people's role and the default for **every future
hire**. Changing it changes the company's default. The audit entry
`role.updated` now carries `added`/`removed`/`is_system` in its detail; read it
back to the principal.

## Where the server will stop you (explain, do not retry)

- **Lockout protection**: the `admin` role cannot lose `users.manage`, and no
  change may leave the tenant without a last active user holding `users.manage`
  (all three paths hit this — editing role permissions, changing a user's role,
  disabling a user) → **422**. This is not a bug, it prevents locking yourself
  out; explain it and offer an alternative.
- **System roles cannot be deleted** (409); **a role somebody holds cannot be
  deleted** (409) — move people off it first.
- **Custom capabilities**: cannot be deleted while any role grants them or any
  skill names them as `required_capability` (409); cannot be created with a name
  that collides with a system capability (409).
- **Capability names must exist**: naming a capability that does not exist in a
  role → 422, and the message says which one. Do not guess names; take them
  from `GET /capabilities`.
- **Scope syntax**: only capabilities with `scopable: true` may be written as
  `verb:scope` (such as `business_object.write:warranty_card`); a colon on a
  non-scopable capability → 422. Scope values come from the `object_types` in
  the `GET /capabilities` response.
- **User activation**: an account that has not accepted its invitation cannot be
  set to `active` (422) — they have to accept it first.

## User lifecycle

- **Invite**: `POST /auth/invitations` (email plus role, optionally
  `employee_id` to bind an employee record). **Invitations deliberately do not
  validate the company email domain** — an outside vendor joining with a
  personal address is exactly this path. Use
  `POST /auth/users/{id}/resend-invitation` when a link has expired.
- **Transfer or disable**: `PATCH /auth/users/{id}` (`role` / `status` /
  `employee_id`). Disabling also **clears unused invitations and reset tokens**,
  so an old link cannot come back to life if the account is re-enabled later.
- **Forgotten password**: `POST /auth/users/{id}/password-reset-email`. **Do
  not** set a password for someone; this skill does not touch passwords.

## What leaves a trail, and what does not

Afterwards the principal usually asks how to look this up later. **Answer
accurately rather than vaguely**:

| Action | Audited? |
|---|---|
| Create/change/delete a role (including its `description`) | **Yes** — `role.created` / `role.updated` / `role.deleted`; `role.updated` carries `added` / `removed` / `is_system` |
| **Changing which role a person holds**, their status, or their email | **Yes** — `user.updated`, with `{"from": …, "to": …}` for every changed field |
| Issuing a skill bundle | **Yes** — `skill_bundle.issued` |
| Inviting somebody | **No** — `POST /auth/invitations` writes no audit entry today |

So "who moved whom from member to partner, and when" **is** answerable:

```text
GET /audit-logs?action=user.updated&entity_id={user_id}
→ detail: {"role": {"from": "member", "to": "partner"}, "email": "…"}
```

**There is no endpoint that writes audit entries** — `GET /audit-logs` is
read-only, so do not invent a write path. And **do not** put explanatory text
into a role's `description` to "make up for" a missing trail: permission and
role changes are already audited, and doing so only pushes a sentence into the
tenant's configuration that somebody will later read as fact, which nobody
asked for.

## Skill bundles and credentials

Changing a role immediately changes **which skills that person can receive**.
The two ways of delivering them cost wildly different amounts:

- **Let them sync** (the default, and almost always right): their agent runs
  `$oryh-skill-sync` once and the new skills arrive. **Their key is unchanged
  and their other devices are unaffected.**
- **Reissue as administrator** with `POST /users/{id}/skill-bundle`: this
  **rotates their key**, and every bundle they already have **stops working
  immediately and must be reinstalled**. Use it only for a leaked credential or
  when they genuinely cannot fetch a bundle, and **tell them before you do**.

**Capability is not the only axis**: a skill can also be **targeted** at named
roles or individuals (`distribution_mode: "targeted"`). The two are ANDed —
targeting can only narrow within what capability already allows, never exceed
it. So "they have the capability but do not receive the skill" is an *audience*
question, not a permission one, and belongs to `$oryh-skill-author`; the reverse
— "they are in the audience but still do not receive it" — is this skill's
problem: they lack the capability that skill requires.

**Do not reason it out, ask the server**:

```text
GET /users/{id}/skills     → received[] + withheld[], each with a reason
```

`reasons` lists **every** thing blocking them, not just the first. When both
axes block, both have to change: granting the capability alone means another
sync still delivers nothing.

`missing_capability` is yours. The `granted_by_roles` in the response is which
roles hold that capability **today** — use it as a reference for granting, not
as a suggestion to move the person into one of those roles, which is usually a
privilege escalation rather than a fix.

**Read that field with particular care just after revoking**: you have narrowed
a capability to two or three roles, and `granted_by_roles` now lists exactly
those two or three — which looks like "just move them into one of these", and
that is precisely what the change was meant to prevent. It answers "who has
this now", not "who should". `not_in_audience` is not yours and no permission
change fixes it; hand it to `$oryh-skill-author`. Deriving a capability matrix
by hand and getting it wrong costs somebody a permission they did not need,
and nobody notices.

**Revoking needs this step too**: read it back afterwards and confirm you did
not remove something else along the way. `PATCH /roles/{role_ref}` replaces the
whole array, and an omitted entry looks exactly like a deliberate removal to
both the server and the audit trail.

## What This Skill Never Does

- Give itself, or its own role, a capability it does not already hold. Privilege
  escalation is for another administrator to perform.
- Approve any document, write approval facts on someone's behalf, or assign work
  todos — those belong to the agents of the roles that own them.
- Delete a system role, or leave the tenant without an administrator.
- Invent capability names or scope values: always take them from
  `GET /capabilities`.
- Set a password for somebody, or rotate another person's key without telling
  them.
- Change permissions before the blast radius has been stated and explicitly
  agreed.

## Reference

- [references/api.md](references/api.md): the capability catalog, read/write
  templates for roles and users, and the message behind every refusal.
