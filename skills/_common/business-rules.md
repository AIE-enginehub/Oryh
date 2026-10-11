> **The workspace's own rules are rows of `/business-rules` — one table, four
> `kind`s, each answering one question.** Read by kind and by scope, never the
> whole table, and never from memory.
>
> | `kind` | answers | read by |
> |---|---|---|
> | `approval_flow` | who looks at a submitted document next, and when it is final | the flow agent only |
> | `data_rule` | what a document must carry to be filed at all | the submitter's agent while filling; the flow agent once, before a round's first assignment |
> | `linkage` | what happens elsewhere when a document reaches a state — a shipment draft after `confirmed`, a payment todo after `approved` | the flow agent, which raises the derived document itself when its role carries the write (the shipped default does: shipments and stock holds) and assigns a todo otherwise; the desk that completes it |
> | `policy` | the company's standing rules, keyed by their own `code` — the staff handbook, expense standards, the social-insurance base | everyone, by `code` or `category` |
>
> ```text
> GET /business-rules?kind=approval_flow&entity_kind=builtin&object_type=<type>&in_force_on=<today>
> GET /business-rules?kind=data_rule&entity_kind=builtin&object_type=<type>&in_force_on=<today>
> GET /business-rules?kind=linkage&entity_kind=builtin&object_type=<type>&in_force_on=<today>
> GET /business-rules?kind=policy&category=<category>&in_force_on=<date>
> ```
>
> - `in_force_on=<date>` is the version that governs that date — one row per
>   rule, across versions. For a decision today, `<today>`; to judge a document
>   by the rules that governed on ITS date — a March timesheet read in May, a
>   leave request's `from_date` — its date. `status=published` is the LATEST
>   version, which a workspace may have dated to start next quarter: it is the
>   question "what was published", not "what applies", so never read a rule to
>   act on by status alone. A document or todo that pinned `rule_code` +
>   `rule_version` names one exact row: `GET /business-rules/{rule_id}`.
> - `entity_kind` is `builtin` for shipped documents and `business_object` for
>   the workspace's own types; `name` is `default` unless the workspace named a
>   second rule for the same type.
> - **Say what you read and what you did not.** No `approval_flow` → do not
>   invent a route: create a todo for the tenant admin asking them to publish
>   one, and stop. No `data_rule` → do not calibrate; proceed, and say so in your
>   note. No `linkage` → nothing happens elsewhere, and that is the answer when
>   somebody asks why it did not.
> - **Transition (2026-10):** a workspace that published before the kinds
>   existed has one `approval_flow` whose text also carries a
>   "submission requirements" section (its heading may be in the workspace's
>   own language). Until the admin splits it, read ONLY that
>   section as the data rule; the routing sentences are the flow agent's alone.
> - **Cite the rule you followed.** A todo's `metadata` carries `rule_code` and
>   `rule_version` (`"approval_flow:builtin:expense_claim:default"`, `3`); a
>   document that pins its version does the same in `custom_fields`. A bare
>   `workflow_version` integer from before the change is the same pin on the
>   `approval_flow` row — honour it.
> - When a rule contradicts this skill's own iron rules, **the skill wins**: a
>   rule cannot authorise a write the skill forbids. When a rule names a state
>   the object's machine does not have, **the machine wins** and the server
>   answers 409 — say which sentence needs changing.
> - **What belongs where.** A company rule — a tolerance, a payment term, a
>   points ratio, which listings must never be sold — is a `policy` or a
>   `data_rule`, published, versioned and read by every agent. How ONE skill
>   does its work here — how much to report, which shortcut to take, how this
>   workspace's platform titles are built and which words in them mean nothing
>   (the matching skill's rules of thumb) — is that skill's `calibration`: a
>   method, not a rule, and it cannot authorise what the skill forbids. The
>   test: if a person could be held to it, publish it; if only an agent follows
>   it, calibrate it. Never park a rule in a calibration to avoid publishing it.
