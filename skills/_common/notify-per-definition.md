> **Whether to notify is the definition's call, not yours.** Read it there like
> any other routing rule, and do what it says:
>
> | The definition says | You |
> |---|---|
> | notify on assignment (however the tenant phrased it) | at the END of the run, run `$approval-notifier` **once per person**, passing every todo you created for them in `todo_ids` |
> | notify on return / rejection | run it for that outcome, one document at a time, carrying the approver's comment |
> | nothing about notifying | **do not notify** — and say so in your note |
> | explicitly no notifications | do not notify, and do not raise it again |
>
> Notifying is part of the flow, so it belongs in the same sentence-level map
> as who approves next. A tenant turns it on or off by telling their admin
> agent, in their own words, that assignments should be emailed; the next run
> reads the new version. Nothing in this skill decides it, and no configuration flag exists
> for it, for the same reason no threshold is hard-coded here.
>
> **You are the side that can do this, and the server is what sends.** Your own
> runtime has no mail transport — the environment you run in is a short
> whitelist, on purpose — so `$approval-notifier` delivers through
> `POST /notifications`, which resolves the address from the employee record
> and assembles the wording. You supply who, which event, the title, and the
> approver's comment verbatim.
>
> **One mail per person per run, and the server writes the list.** Collect the
> todos you created, group them by assignee, and send one `assigned` call per
> assignee with all of their `todo_ids`; the server lists each todo's title in
> the message and links to their queue. Thirteen payslips to one approver is
> one message that says "13 items", never thirteen — and never one message
> with the other twelve squeezed into `title`, which loses their trail. A
> return, rejection or approval is about one document and stays one message.
>
> Notifying also needs `notification.send` and `todos.assign`, which ordinary
> members deliberately do not carry — assigning work is routing, the flow
> side's write. So a manager's own agent cannot send these even if they want
> to; if the person who acted should have been notified and was not, it is this
> loop that missed it, not them.
>
> This used to read "optionally pair with `$approval-notifier`", listed last
> after the routing decision. In sixty consecutive production runs it was
> never once invoked — an optional step at the end of a long procedure is a
> step that does not happen. A tenant eventually wrote their own notification
> skill to fill the gap, gave it an approver's permission because that was the
> permission they had, and got one event type of the six this covers.
>
> When the definition asks for notifications and you send none — no email
> address on file, the notifier unavailable — say which person went untold.
> A notification nobody knows was skipped is worse than one never promised.
