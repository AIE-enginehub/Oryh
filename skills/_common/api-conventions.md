> **How this API works — read once, then never guess a parameter.** Every
> endpoint this skill names is listed with its exact parameters, types and
> required fields in `references/api-contract.md`, generated from the
> server's own contract. Look there before trying a call; a parameter that
> is not in it does not exist.
> <!-- only: bundle -->
> If your runtime runs shell commands, one call
> is one command — `python3 scripts/oryh_request.py GET /todos status=open`,
> in this skill's own directory — not a script written per request.
> <!-- /only -->
> <!-- only: mcp -->
> Every call is one `oryh_request` tool call — `{"method", "path",
> "query", "body"}` — whatever the paths below are written as.
> <!-- /only -->
>
> - **Envelope.** Every response is `{"data": …, "meta": {…}}`. A list's
>   `data` is an array; one record's `data` is an object; `meta` carries
>   counts and paging. Errors are `{"detail": "…"}` with the status code
>   saying what kind (below).
> - **Ids** are UUID strings, always from a previous response — never
>   composed, never guessed. A wrong-shaped id is a 422 naming the field.
> - **What you can read.** A person's documents — timesheets, leave, expense
>   claims, purchase requests, quotations, sales orders and returns, leads,
>   opportunities and the record of contact on them — are read by the person
>   they belong to, by whoever they were routed to (a todo or an approval
>   fact on the document), and by a credential that holds the family's
>   `read_all` grant or a desk that cannot work without it (whoever advances,
>   ships, invoices or pays). Lines, approval facts, todos, attachments and
>   the audit trail follow their document. A list shows what this credential
>   may read — an empty list is not "there are none in the company" — and a
>   document it may not read is a 404, the same as one that does not exist.
>   Never tell the person a colleague's document is missing; say you cannot
>   read it and name the grant.
> - **Lists.** Filters are query parameters, exact-match unless the contract
>   says otherwise. `keyword=` is a case-insensitive word match across the
>   names the contract lists — every word must land, order and gaps do not
>   matter, so send the words the person used, once. `status=all` includes
>   archived master data; `include_deleted=true` includes soft-deleted
>   documents; the default of both is the live rows only.
> - **Ranges.** Every date or timestamp column a list carries is a range:
>   `<column>_from=` (inclusive lower bound) and `<column>_thru=`
>   (inclusive upper bound), either or both — `order_date_from=2026-09-01`,
>   `effective_at_thru=2026-09-30T23:59:59Z`. Date columns take a date,
>   timestamp columns take an ISO timestamp; a wrong-shaped value is a 422.
>   Every paged list has `created_at_from`/`created_at_thru`; the contract
>   lists the document's own dates (order, promised, due, effective,
>   signed…). References (`customer_id`, `contract_id`, `project_id`,
>   `currency`…) are exact-match filters named after the column.
> - **Paging.** `page` (from 1) or `size` (1–200; larger is clamped and
>   `meta.page_size` says so) — either one turns paging on and the response
>   then carries `meta.total`, `meta.page`, `meta.page_size`. Omit both for
>   the complete list, which on a large collection is the slow mistake. To
>   count, send `page=1&size=1` and read `meta.total`.
> - **Sorting.** `order_by=` a column name, `-` prefix for descending,
>   comma-separated for several (`-created_at,order_no`). Any column of the
>   row may be named; an unknown one answers 422 listing the sortable
>   columns. Omit it for the collection's own order.
> - **Detail.** The record's own URL (collection plus id) is the record; its
>   `/detail` sibling, where the contract lists one, is the record with its
>   lines, applications and trail in one read. Take the one that answers the
>   question.
> - **Writes.** Create the whole document in one POST with its lines inline
>   where the contract has an `items`/`entries` field; the response is the
>   read-back. `?validate_only=true` on every inline create runs every
>   server check and writes nothing — the answer is what would have landed,
>   with `meta.validate_only: true, written: false`. Where the contract lists
>   `POST …/{id}/save`, a document's lines (and adjustments) are restated in
>   one call as a diff against the live rows — a row naming an `id` is that
>   line, changed only in the fields the row states (state a field as null
>   to clear it); a row without an id is a new line and goes through the
>   create rules; a live row not listed is removed — guarded by the
>   `revision` the document's detail (or its single read) returns; a stale
>   revision is a 409, so read it first. What a line IS (its product on a
>   shipment, its document) cannot change in place: leave the row out and
>   add a new one. Every document with lines has one: timesheets, expense
>   claims (header fields too), invoices, quotations, orders, purchase
>   requests and orders, contracts, recipes, picklists, shipments, deals.
> - **Retries.** Every write (POST, PATCH, PUT, DELETE) takes an
>   `Idempotency-Key` header — a token you choose for that one act, a UUID
>   will do. Send it on every write; if the answer never arrives, send the
>   identical request again with the same key: the server replays the first
>   attempt's response (status, body, `Idempotency-Replayed: true`) and
>   writes nothing twice. The same key with a different request is a 422
>   (`idempotency_key_reused`) — a new act takes a new key; the same key
>   while the first attempt is still running is a 409 — wait and retry. Keys
>   are scoped to your credential and kept 24 hours. Money-moving endpoints
>   also take a body `idempotency_key` bound to their rows; send both.
> - **Computed fields.** A line's `amount` is quantity × unit_price: the
>   server computes and stores it — leave it out. A stated amount that does
>   not equal the product is a 422 with the arithmetic; a line-level discount
>   is an adjustment, not a different amount. A line without a unit price
>   keeps a stated amount as its lump sum. `tax_amount` is what the invoice
>   says (tax-inclusive practice varies), never derived. Document totals
>   (`total_amount`) are the agreed figure; null means the line sum is the
>   total, and every detail reports both.
> - **Dates and money.** Dates are `YYYY-MM-DD`; timestamps are ISO-8601
>   with a timezone; amounts are decimal numbers with at most two decimals,
>   never strings with currency signs.
> - **Status codes tell you what to do next.** `401` — the credential, not
>   the request: do not retry it (see how this skill authenticates above).
>   `403` — the detail names the missing capability: stop and say so;
>   no other route grants it. `404` — the id is not this tenant's or the
>   record is gone: say so, do not search for it elsewhere. `409` — the
>   state or a uniqueness rule refuses it, and the detail names the existing
>   record or the state: read it, it usually IS the answer. `422` — a field
>   is wrong and the detail names it: fix that field, do not reshape the
>   request.
> - **One try per fact.** A call that answered — even with 404 or 409 —
>   answered. Repeating it with the parameters reshuffled does not change the
>   fact; it spends the person's time. Ask them instead.
