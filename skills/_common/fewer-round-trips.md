> **Two turns you do not need to spend.** Every request you make is a few
> seconds of the person's time, and the count is what they feel — not the
> server, which answers in tens of milliseconds.
>
> **You already know who you are.** This bundle was rendered for one person,
> and their employee id is in this file: `{{EMPLOYEE_ID}}`. Use it wherever a
> call wants `employee_id`; do not spend a request on `GET /auth/me` to learn
> it. (If that value came out blank, this principal has no employee record
> linked — that is a real condition to report, not something to retry another
> way. Only an admin can link one.)
>
> **Reads that do not feed each other go out together.** Issue every
> independent request in one batch and wait for them as a group. Sequence only
> what genuinely depends on an earlier answer — a detail lookup that needs an
> id you just received. Ten independent queries sent one at a time is ten
> waits; sent together it is one.
