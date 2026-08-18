---
name: oryh-my-work
description: Use when a person's AI agent needs to check what its principal should do in oryh — on session start (check-in), on demand ("我有什么要办的"), or periodically. Reads the principal's open todos, overdue items, and the approval progress of their in-flight records, then reports a concise briefing. Read-mostly; the only write it may perform is completing a todo the principal says is done.
---

# Oryh My Work

The check-in routine for every employee's local agent (WorkBuddy-style), approver or not. Everything is a state query: no cursors, no local files, nothing to remember between sessions — ask any time, from any machine, and the answer is correct.

## Trigger Examples

- "What is on my plate today?"
- "Has my timesheet been approved?"
- "Check oryh for my tasks when I start"
- "Is there anything returned that I need to fix?"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"          # the principal's user-bound key
```

## The Check-in

{{include:_common/answer-the-question.md}}

{{include:_common/fewer-round-trips.md}}

{{include:_common/stay-current.md}}

Three waves, not eleven. Everything inside a wave is independent — send it
together. Only wave 2 needs wave 1's answer, and only because it looks up ids
wave 1 returned.

```text
WAVE 1 — one batch. Your employee id is {{EMPLOYEE_ID}}; no call for it.

   GET /my/skills/manifest
     → are my installed skills current? Compare with the installed
       manifest.json (name/version/files_hash). Differences are reported to
       the person, never fixed silently — see above. This rides along in the
       batch; it costs no extra round trip.

   GET /todos?employee_id={me}&status=open&include=target
     → my inbox WITH its context: each todo carries a `target` summary —
       whose document, its title, amount (or hours), status, and the latest
       approval position (`target.last_approval`). That is the whole
       "one line of context per todo"; do NOT follow up with per-todo detail
       calls. due_at tells urgency; anything past due leads the briefing.
       `target.missing: true` means the document is gone — say so, do not
       retry the lookup.

   my in-flight items (did my own submissions move? was anything returned
   to me? — a rework todo usually points at returned documents, but do not
   bet the briefing on someone having created it):
   GET /timesheet-headers?employee_id={me}&status=submitted   (+ &status=returned, same batch)
   GET /expense-claims?employee_id={me}&status=submitted      (+ returned)
   GET /purchase-requests?employee_id={me}&status=submitted   (+ returned)
   GET /sales-quotations?employee_id={me}&status=submitted    (+ returned)
   GET /sales-orders?employee_id={me}&status=submitted        (+ returned)

   this workspace's own state names, for wave 3 (see step 5):
   GET /object-type-definitions?object_type=sales_quotation
   GET /object-type-definitions?object_type=sales_order

WAVE 2 — one batch, built from the ids wave 1 returned: the approval trail
of each of MY in-flight submissions. (Todo context needs nothing here — wave
1's `include=target` already carried it. Reach for a document's full
`/detail` only when the person drills into that one item.)

   per in-flight item:
   GET /approval-records?entity_type=…&entity_id=…
   → "the manager approved it; finance is reviewing" — position is read from the trail, never
     from the status field.
   Zero in-flight items → wave 2 is zero requests. Skip it; never spend a
   turn on an empty batch to honor the structure.

WAVE 3 — one batch, using the state names wave 1 read. See step 5.
```

5. My deals awaiting the other side (WAVE 3 — one batch). The intents are
   fixed; the state NAMES are not — wave 1 already fetched this workspace's
   own in `state_machine.states`. **Substitute from those before you send**;
   the defaults in parentheses are what an untouched workspace calls them,
   not what this one necessarily does:

   quotation cleared-but-unsent  (default `approved`)  → approved, not yet sent
   quotation with the customer   (default `sent`)      → awaiting the customer
   order awaiting fulfilment     (default `confirmed`) → awaiting shipment
   order in transit              (default `shipped` — often renamed, e.g.
                                  `in_delivery`)       → in transit (followed to sign-off)

   as `GET /sales-quotations?employee_id={me}&status=<name>` etc., all four
   in one batch.
   → a 422 here means the substitution was skipped or wrong; the error lists
     the real states — map the intent and retry. **Never report "no orders in transit"
     off a failed or empty query you did not check** — that is the same
     sentence whether there is nothing to chase or you asked about a state
     this company does not have.

Report a short briefing ordered by urgency alone, whatever the source: an
overdue todo and a quotation past its `valid_until` compete on the same
scale — most overdue first, then due-today, then open items with context,
then in-flight progress, then deals waiting on the other side. If everything
is empty, say so in one line.

## Optional Write

If the principal confirms an item is done (non-approval todos like follow-ups), complete it: `PATCH /todos/{todo_id}` with `{"status": "completed"}`. For approval todos, hand over to `$oryh-approve` instead — approving has its own contract, whatever the document type.

## What This Skill Never Does

- Submit or modify timesheets, expense claims, purchase requests, quotations, or orders (that is `$oryh-timesheet-submit` / `$oryh-expense-submit` / `$oryh-purchase-submit` / `$oryh-quotation-submit` / `$oryh-order-submit`).
- Record approval facts (that is the `*-approve` skills).
- Route or assign work (that is the workflow admin's `*-approval-flow` skills).

## Reference

- [references/api.md](references/api.md): the exact queries with parameters.
