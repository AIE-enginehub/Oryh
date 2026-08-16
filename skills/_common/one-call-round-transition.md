## A Round Transition Is One Call

Returning a document, or finalizing it, is three facts: the approval record,
the document's new status, and whoever holds it next. They used to be three
calls, which is three chances for the first to land and the rest not to. That
is not hypothetical — a production timesheet ended up with a `returned` trail,
a `submitted` status and nobody assigned, and it took a human opening a console
three weeks later to notice.

`POST /approval-records` carries all three:

```json
{
  "entity_type": "…", "entity_id": "…",
  "round_no": 2, "sequence_no": 1,
  "action": "returned",
  "approver_role": "workflow-admin",
  "comment": "为什么退回，用定义自己的措辞",
  "document_status": "returned",
  "handoff": {
    "employee_id": "…",
    "title": "…",
    "description": "把 comment 里的要求原样重复一遍",
    "todo_type": "rework"
  }
}
```

**Nothing about the decision moved to the server.** Which status, and whose
queue — still yours, still read off the workspace's own definition. Every guard
the separate calls enforced still runs: the state machine, the advance
permission, the employee's existence, the open-todo key. The single change is
that the three facts share a commit, so a refusal on any one of them leaves
none of them behind.

**Both fields are optional.** Omit them and the call behaves exactly as it
always did; send the two follow-up calls yourself if that is what your flow
needs. What you cannot do is send the first and skip the rest.

**The whole call is the retry unit.** Repeating it is safe in every part: the
approval fact is idempotent on its natural key, a status already at the target
is a no-op, and an identical open todo is handed back rather than duplicated.
After a crash, resend the same body — including when the fact went through and
nothing else did, which is the case the coupling exists for.

**Two things the server now does without being asked**, so do not send calls
for them:

- The approver's own approval todo is completed by the decision, and a
  `returned` fact cancels the round's approval todos.
- A resubmission completes the open `rework` todos on that document.
