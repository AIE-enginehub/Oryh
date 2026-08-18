> **Check you are current before you work — one call, in the first wave.**
>
> ```text
> GET /my/skills/manifest
> ```
>
> Compare it against the `manifest.json` in this company's installed
> `oryh-skills-*/` directory: same `name`, same `version`, same `files_hash`.
> Send it WITH the other opening reads, not before them — it is independent of
> all of them, so it costs a slot in a batch you are already sending, not a
> round trip.
>
> Anything differs — a version moved, a hash changed, a skill appeared or
> disappeared — say so in one line, in the person's own language, and offer to
> refresh: *"2 of your oryh skills have updates (oryh-approve,
> oryh-expense-submit) — refresh now?"*
>
> On yes, run `$oryh-skill-sync`. Do NOT refresh silently: replacing the
> instructions mid-session changes how the agent behaves, and the person
> should know that happened.
>
> **Why this lives here rather than in the sync skill's own description.** That
> skill says it runs "on session start" — but nothing tells an agent a session
> started. An agent reaches a skill because the person's words matched it, and
> nobody opens with "session start"; they open by asking what they have to do.
> So the check has to hang off the skills they DO reach, or it never runs at
> all — which is what happened: installed skills stayed stale for weeks until
> somebody thought to ask for an update by name.
>
> A skill gained or lost is worth a sentence even when nothing else changed:
> it usually means the person's role or grants moved, and they may not know.
>
> **Once per session, not once per skill.** Several oryh skills carry this
> check, because a person's first sentence is as often "file my timesheet" as
> it is "what do I have to do". If you already compared the manifest in this
> session, you know the answer — do not send it again, and do not raise it a
> second time after the person has declined.
