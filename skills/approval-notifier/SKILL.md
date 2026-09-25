---
name: approval-notifier
description: Use to tell people about approval activity on any oryh document — the new approver, the submitter of a returned or rejected one, the filer of an approved one. Sends through POST /notifications, one message per person per run; the server picks the address and writes the body. Requires todos.assign, notification.send.
required_capability: todos.assign
---

# Approval Notifier

Tell a person about approval work that concerns them: the todos a run just
assigned, a return or rejection with the approver's comment, an approval. A
flow-side skill: it runs beside the approval-flow skills on the workflow
admin agent, and is gated like them (`todos.assign` — the routing capability,
not in the default member role). It ships only to admins and to roles a
tenant explicitly grants `todos.assign`.

Division of labour:

- the flow skill decides what happened and who is next; oryh's todos and
  approval records are the source of what there is to tell
- **this skill sends** — through `POST /notifications`, which resolves the
  address from the employee record and writes the message. You supply who,
  which event, the document, and the approver's comment verbatim
- nothing is remembered here: no addresses, no delivery log. A retry sends
  the same message again, which is the acceptable worst case

## Trigger Examples

- "Tell the manager to approve the timesheet"
- "Notify the JC approver about the warranty card"
- "Tell the filer the outcome"
- "Notify the next approver"
- "Let Zhang San know his claim came back"

{{include:_common/api-conventions.md}}

## Required Inputs

```yaml
oryh:
<!-- only: bundle -->
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
<!-- /only -->
  base_url: "{{ORYH_BASE_URL}}"          # the console address, the links in the message point here
<!-- only: bundle -->
  api_key: "{{ORYH_API_KEY}}"        # tenant service key; the notifier reads queues for the tenant
<!-- /only -->
notify:
  employee_id: "the person this concerns"
  event: "assigned | returned | approved | rejected"
  todo_ids: ["…"]                    # assigned: every todo this run gave them
  entity_type: "timesheet_header"    # the document family
  entity_id: "…"                     # returned / approved / rejected: the one document
  detail: "the approver's comment, verbatim"   # required for a return
  actor_name: "the approver's display name"
```

## Sending: the server does it

```json
POST /notifications
{
  "employee_id": "the person this concerns",
  "event": "assigned | returned | approved | rejected",
  "title": "Rework: timesheet 08/03-08/07",
  "detail": "<the approver's comment, verbatim — required for a return>",
  "actor_name": "the approver's display name",
  "entity_type": "timesheet_header",
  "entity_id": "…",
  "todo_id": "…"
}
→ 202 {"delivered": true,  "employee_id", "employee_name"}
   202 {"delivered": false, "reason": "no email address on the employee record", …}
```

**Assignments: one call per person per run, all their todos in it.** The
server writes "N items await you" and lists each todo's own title; `title` is
optional then, and every id must be an open todo of that same person or the
whole call is refused (404) — so a message never names fewer items than you
think it does. Do not send one call per todo when the run assigned several
to the same approver, and do not squeeze several documents into `title`.

```json
POST /notifications
{
  "employee_id": "the approver",
  "event": "assigned",
  "todo_ids": ["…", "…", "…"],
  "entity_type": "invoice"
}
```

Returns, rejections and approvals concern one document each and stay one
call each, carrying the approver's comment.

**You do not pass an address and you do not write the body.** The server
resolves the recipient from the employee record and assembles the wording. That
is deliberate: an agent that cannot choose an address cannot send to a guessed
one, and an endpoint that accepted arbitrary text to arbitrary recipients would
be an open mail relay wearing a business API's clothes.

`delivered: false` is not a failure to retry — it means that employee has no
address on file. Report **who** went untold, by name, so somebody can fix the
record. Retrying will produce the same answer.

The four events are the only ones the server sends. A reminder is an
`assigned` message sent again for todos still open (`GET
/todos?status=open&due_before=<now>`); there is no separate reminder or
escalation event, and no message the server does not write.

## Returns, specifically

A return is the one outcome whose message has a job beyond informing: the
person has to act on it. Three rules, learned from a customer who wrote their
own return-notification skill because this one was not reaching them:

- **Quote the approver's `comment` verbatim** in `detail`. Do not summarise
  it, tidy its grammar, or drop the parts that look redundant. It is the
  instruction for what to fix, written by the person who will judge the fix;
  a paraphrase is a different instruction. If it is empty, say that it is
  empty rather than inventing a reason.
- **Only notify while it still needs doing.** Check the document's current
  status first — a return that has already been reworked and resubmitted, or
  one on a document since approved, is history. Notifying about it sends
  someone to look at a queue where nothing is waiting.
- **Never guess an address.** No email on the employee record means say so and
  name the person, so somebody can fix the record. A message sent to a guessed
  address is worse than one not sent: it looks delivered.

The server points the person at their queue; the rework todo the flow agent
opened is already there, and it carries the same text.

## Steps

1. **Collect what the run did**: the todos it created, grouped by assignee;
   the documents it returned or rejected, each with the approver's comment;
   the documents it approved, each with the filer.
2. **Send**: one `assigned` call per assignee with all of their `todo_ids`;
   one `returned` / `rejected` / `approved` call per document.
3. **Report**: who was told, and — by name — who has no address on file.

## What This Skill Never Does

- Decide the workflow, the next approver or a document's status — that is
  the flow skill's.
- Record approval facts — `$oryh-approve` and the flow skills do.
- Hold addresses, channels or a delivery log — the employee record holds the
  address and the server holds the wording.
- Send to anyone the run did not assign, return, reject or approve.

## Pairing With The Flow Skills

The flow skills (`oryh-*-approval-flow`) run this skill at the end of a run
when the workflow definition asks for notifications, once per person, with
every todo the run assigned to them — and once per returned, rejected or
approved document, carrying the approver's comment. Whether to notify at all
is the definition's call, read there like any other routing rule.
