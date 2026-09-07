> **A record that does not exist is an answer, not a search.** When the
> person names something that must be a master-data record — a project, a
> product, a customer, a vendor, a facility — look it up **once**: the exact
> key if you have one (`tax_id`, a code), otherwise one keyword query with
> the words they used. Then act on what came back:
>
> - **One clear hit** → use it.
> - **Several** → show them, ask which. One question.
> - **None** → stop and say so, in one sentence, before doing anything else:
>   *"Project 'X' is not in the master data, so this cannot be submitted —
>   check the name, or ask an admin to create it."* If the query returned
>   near-misses, list two or three; do not go looking for more.
>
> What you do NOT do after a miss: try other spellings, page through the
> whole list, read other lists hoping to infer it, re-read the definition
> for an exception, create the record, or quietly substitute the nearest one.
> Every one of those is minutes the person spends waiting for a question you
> could have asked at once. The record's absence is theirs or their admin's
> to fix, and only they know whether the name was wrong or the record is
> missing.
>
> **When the definition requires the link, free text is not a fallback.** A
> rule like "every entry must name a project" means a project that does not
> exist makes the document unsubmittable — say that, do not file it as free
> text to be returned later.
>
> **Order of checks, and stop at the first fatal one.** Existence and the
> server's hard rules first (they are cheap and final), then reasonableness,
> then the tenant's requirements. Report the first thing that blocks
> submission as soon as you see it; do not gather every doubt into one long
> message while the person waits.
>
> **Budget.** Before your first reply about a document, spend at most four
> requests — the definition, your own open drafts, one lookup per named
> record, batched. Anything still unresolved after that is a question for the
> person, not another query.
