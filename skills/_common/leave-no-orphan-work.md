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
- **Retiring it BY STATUS is not.** A document moved to a state your workspace
  treats as dead — 作废, 已取消, 已废弃 — is still a live row, and the server has
  no opinion about what your state names mean. Close your own todos on it
  yourself: `PATCH /todos/{id}` with `{"status": "cancelled"}`.
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
