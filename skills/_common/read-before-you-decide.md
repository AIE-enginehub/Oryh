## Read Before You Decide

**What you wrote is not what you remember.** Before submitting a record,
changing it, or telling the principal what is in it — above all before refusing
on the grounds of what it contains — fetch it and read the response. Not the
plan you made, not the echo of an earlier reply: the document as the server
holds it now.

This is not caution about a rare case. An agent in a live session created a
claim, wrote three lines into it including one it had been asked about
explicitly, and then twice told the person that the third line had never been
written. It refused a submission they had just confirmed, on the strength of a
recollection the database contradicted. Nothing was lost and nothing wrong was
filed — and the person was still told the opposite of the truth about their own
money, then blocked from finishing.

So, after every write, keep the authoritative facts where you can see them
rather than where you have to recall them:

| Keep | From |
|---|---|
| the record's id | the create response |
| how many lines it has, and each line's id | the same response, or the re-read |
| its current status | the same |
| what the last call actually did | its status code, not your intent |

Then, at the decision:

```text
GET  <the record>/detail      ← immediately before submit / edit / refuse
```

and speak from what came back. Quote the count you just read, not the count you
expected. It costs one call, and it is the call that makes the difference
between reporting the system and narrating yourself.

**If the re-read disagrees with your recollection, the re-read wins.** Say what
is actually there — "the draft has three lines; the taxi line is on it, without
an invoice number" — and carry on. A write you have forgotten is far more
likely than a write that did not happen: the server answered you at the time,
and that answer is in the record. Never tell somebody a line is missing without
having just looked, and never treat your own uncertainty as evidence about
their data.
