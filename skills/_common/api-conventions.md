> **How this API works — read once, then never guess a parameter.** Every
> endpoint this skill names is listed with its exact parameters, types and
> required fields in `references/api-contract.md`, generated from the
> server's own contract. Look there before trying a call; a parameter that
> is not in it does not exist. If your runtime runs shell commands, one call
> is one command — `python3 scripts/oryh_request.py GET /todos status=open`,
> in this skill's own directory — not a script written per request.
>
> - **Envelope.** Every response is `{"data": …, "meta": {…}}`. A list's
>   `data` is an array; one record's `data` is an object; `meta` carries
>   counts and paging. Errors are `{"detail": "…"}` with the status code
>   saying what kind (below).
> - **Ids** are UUID strings, always from a previous response — never
>   composed, never guessed. A wrong-shaped id is a 422 naming the field.
> - **Lists.** Filters are query parameters, exact-match unless the contract
>   says otherwise. `keyword=` is a case-insensitive word match across the
>   names the contract lists — every word must land, order and gaps do not
>   matter, so send the words the person used, once. `status=all` includes
>   archived master data; `include_deleted=true` includes soft-deleted
>   documents; the default of both is the live rows only.
> - **Paging.** `page` (from 1) or `size` (1–200; larger is clamped and
>   `meta.page_size` says so) — either one turns paging on and the response
>   then carries `meta.total`, `meta.page`, `meta.page_size`. Omit both for
>   the complete list, which on a large collection is the slow mistake. To
>   count, send `page=1&size=1` and read `meta.total`.
> - **Detail.** The record's own URL (collection plus id) is the record; its
>   `/detail` sibling, where the contract lists one, is the record with its
>   lines, applications and trail in one read. Take the one that answers the
>   question.
> - **Writes.** Create the whole document in one POST with its lines inline
>   where the contract has an `items`/`entries` field; the response is the
>   read-back. `?validate_only=true`, where the contract offers it, runs every
>   server check and writes nothing. Money-moving endpoints take an
>   `idempotency_key`; always send one, so a retry cannot apply twice.
> - **Dates and money.** Dates are `YYYY-MM-DD`; timestamps are ISO-8601
>   with a timezone; amounts are decimal numbers with at most two decimals,
>   never strings with currency signs.
> - **Status codes tell you what to do next.** `401` — the credential, not
>   the request: expired means refresh, invalid means reconnect; do not
>   retry. `403` — the detail names the missing capability: stop and say so;
>   no other route grants it. `404` — the id is not this tenant's or the
>   record is gone: say so, do not search for it elsewhere. `409` — the
>   state or a uniqueness rule refuses it, and the detail names the existing
>   record or the state: read it, it usually IS the answer. `422` — a field
>   is wrong and the detail names it: fix that field, do not reshape the
>   request.
> - **One try per fact.** A call that answered — even with 404 or 409 —
>   answered. Repeating it with the parameters reshuffled does not change the
>   fact; it spends the person's time. Ask them instead.
