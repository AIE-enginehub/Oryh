> **A round is the whole chain, from the top.** `round_no` increments when a
> returned document is resubmitted, and the new round is a fresh run at the
> definition's node list — not a resumption of where the last one stopped. The
> submitter changed the document; every node the definition names has to see
> the version it will be approving.
>
> Two rules follow, and both are about reading the trail:
>
> - **"Which nodes have passed" means passed IN THIS ROUND.** Filter the trail
>   to `round_no == <the current round>` before deciding anything. A node that
>   approved in an earlier round has approved an earlier document.
> - **`sequence_no` restarts at 1 each round.** The submission is seq 1, the
>   first approver seq 2, and so on. Carrying the last round's numbering
>   forward leaves gaps that make the trail unreadable — and a todo stamped
>   with the previous round's number contradicts the fact it belongs to.
>
> This cost a production timesheet its first approver. After a return and a
> rework that changed seven lines, the flow agent read the whole trail, saw the
> first approver's round-1 approval, and routed straight to the second — whose
> own round-1 sequence number it also reused, so the new round ran s1 → s3 with
> no s2 and a todo claiming to belong to round 1. Had the last approver signed,
> the document would have been `approved` with the first approver never having
> seen the seven changed lines.
>
> Where the tenant's definition states its own re-approval rule, that rule
> wins — say in your note which one you followed. Where it is silent, start the
> chain over: it is the reading that cannot approve a document nobody looked at.
