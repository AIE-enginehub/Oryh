## Leave No Orphan Work

A returned document can be answered two ways, and only one of them used to
clean up after itself. **Fixing** the original closes the rework todo as part
of resubmitting. **Voiding it and filing a fresh one** leaves the todo pointing
at a document nobody is going to touch again — and it stays in somebody's queue
forever, saying work is outstanding when it was finished under a different
number.

That is exactly what happened: five payslips returned, five voided, five
replacements approved, five todos still open.

So whenever you retire a record that had work outstanding on it:

- **Deleting it is handled for you.** The server cancels the open todos that
  pointed at it, because a work item whose subject is gone cannot be done. You
  will see them come back `cancelled`, not `completed` — nobody did that work.
- **Retiring it BY STATUS is handled too, when the state is an ending.** The
  server still has no opinion about what 作废 or 已完成 mean to you. It asks
  your workspace's own state machine two questions instead: does any transition
  leave this state, and is it editable? If the answer is no to both, nothing
  can happen to the document, so the open todos on it are cancelled with it.
  A state your machine can still move out of is not an ending, and work there
  is left alone.
- **A state you treat as dead but your machine can still leave is yours to
  clean up.** That is the gap the two questions above cannot close: `PATCH
  /todos/{id}` with `{"status": "cancelled"}`. If you meet this often, the
  machine is describing a lifecycle your workspace no longer runs — fix the
  definition rather than sweeping after it.
- **Resubmitting closes the rework todo.** The server completes the open
  `rework` todos on a document the moment it is submitted again — `completed`,
  because the work was done. You do not send a second call for it, and a
  resubmit that returns 200 has already cleared the queue entry.
- **Say where the work went.** Put the replacement's number in the void reason
  and the original's number in the replacement's `remarks`. "Why were there ten
  payslips for June" is a question somebody will ask, and the two documents
  should answer it without anyone reconstructing the week.

`cancelled` rather than `completed`, always. They are not two words for closed:
one says the work was done, the other says it stopped being work. A queue
history that cannot tell them apart cannot answer what a person actually did.

If the todo is somebody else's — an approver's, when you are the filer — you
cannot close it and should not try. Say plainly that it is stale and who holds
it; the workflow admin agent sweeps those.
