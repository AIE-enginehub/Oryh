# Shared fragments

Files here are pulled into product skills at seed time by an include marker
alone on its line:

```text
{{include:_common/api-auth-principal.md}}
```

`read_skill_dir` replaces the marker with the fragment's text verbatim before
anything else sees the skill — the registry, `files_hash`, sync, and rendering
all operate on finished text and do not know fragments exist. Editing a
fragment therefore bumps the version of every skill that includes it on the
next provision, and skill-sync carries the change to installed copies.

Rules, in order of importance:

- **Only verbatim-stable text belongs here.** A fragment is for contract
  wording that must never drift apart across skills (auth headers, idempotency
  rules). Anything calibrated per object or per audience — action catalogs,
  example values, tone — stays in the skill that owns it, even when the
  copies look similar today. Flattening calibrated text into a generic
  fragment trades agent quality for tidiness; don't.
- **No parameters, no nesting.** A fragment cannot include another fragment
  and has no template variables (bundle placeholders like `{{ORYH_BASE_URL}}`
  still render later as usual). If text needs per-skill variation, it is
  calibrated content and does not belong here.
- This directory has no SKILL.md on purpose: provisioning skips it, so it
  never becomes a skill in any tenant's registry.

`tests/test_skill_docs.py` fails on unexpanded or malformed markers and keeps
fragment API references honest against the live routes.

## Text for one delivery

A skill reaches an agent as a downloaded bundle (key rendered in, HTTP calls,
bundled scripts, re-sync) or over MCP (the connection carries the sign-in,
every call is the `oryh_request` tool). Text true of only one sits between
marker lines, each alone on its line — indented inside a list item or after
`> ` inside a quote is fine:

```text
<!-- only: bundle -->
…key, header, script, re-sync…
<!-- /only -->
<!-- only: mcp -->
…the tool that does the same job…
<!-- /only -->
```

Markers survive provisioning; each delivery's renderer keeps its own blocks
and drops the other's (`app/services/delivery.py`). Provisioning and
`POST /skills` refuse markers that do not pair up, and
`tests/test_skill_delivery.py` fails when MCP-rendered text still names a key,
a header, a script or a bundle to re-sync.

## The flow fragments

`rounds-start-over.md`, `one-call-round-transition.md`, `stale-todo-sweep.md`,
`page-to-the-end.md` and `service-key-bundle.md` are included by the eight
approval-flow skills (`oryh-*-approval-flow`), `money-flow-model.md` by the
invoice and payment flows. Each is a rule bought with a production incident —
a return that landed one write of three and left a document nobody was
assigned to; a new round that resumed mid-chain and would have approved a
document its first approver never re-read; todos left open on work that had
moved on; a trail on page two read as an absent trail. Anyone writing their
own flow skill against this API needs those rules.
