## The stale-todo sweep

Not an approval flow: a periodic pass that closes work items nobody can act on.

```text
GET /todos?status=open&entity_type={this family}&include=target
```

`include=target` returns each todo's document inline, so the whole sweep is one
call plus the workflow definition you already read.

Close a todo — `PATCH /todos/{id}` with `{"status": "cancelled"}` — when its
target has stopped being actionable:

- the document sits in a state the tenant's definition treats as **dead**
  (voided, cancelled, abandoned — whatever this workspace calls it). Only you can judge
  this: the state names are the tenant's and the server has no opinion about
  what they mean.
- the document reached a **terminal state** the todo's work belonged before —
  a rework todo on a document that is now `approved`, an approval todo on one
  already `paid`. The queue is telling somebody to redo a decision that has
  been made.

A **deleted** document needs nothing from you: the server cancels those todos
when the delete happens, because a work item whose subject is gone cannot be
done. The target tells you which case you are in:

```json
{"target": {"object_type": "invoice", "status": "issued", "deleted": true}}
```

- `"deleted": true` — the row is there and soft-deleted, so its own detail
  endpoint answers 404. An OPEN todo in this state should not exist: deleting
  a document cancels them. Finding one means it predates that rule or
  something reached the database directly. **Report it with the todo id and
  the target id. Do not cancel it** — you would erase the only evidence of
  whatever produced it, and a person can close it in a second once they know.
- `"missing": true` — no row of that type carries that id at all. That is not
  a stale todo, it is a broken reference; report it the same way and expect
  someone to want the id.

Neither is a judgment call, which is why neither is yours to close.

Three things this sweep must not do:

- **Never close on age.** An old todo is usually a slow approver, not a stale
  one, and closing it silently removes the only trace that somebody owes work.
- **Never close one whose document is still live and mid-flow**, even if a
  newer document appears to supersede it. "This payslip replaces that one" is a
  claim about intent, and the person who voided the original is the one who
  should have said so. Report the suspicion; do not act on it.
- **`cancelled`, never `completed`.** Nobody did this work. A queue history
  that cannot tell the two apart cannot answer what a person actually did.

Say what you closed and why, per item — a sweep that reports "cleaned 12 todos"
is indistinguishable from a bug that deleted 12 people's work.
