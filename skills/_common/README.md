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

## Fragments no skill here includes

Four of these are included only by the approval-flow skills, which the hosted
service maintains and this repository does not carry:
`rounds-start-over.md`, `one-call-round-transition.md`, `stale-todo-sweep.md`,
`money-flow-model.md`.

They ship anyway, on purpose. Driving an approval flow correctly is the part
that is easy to get subtly wrong, and each of these is a rule bought with a
production incident — a return that landed one write of three and left a
document nobody was assigned to; a new round that resumed mid-chain and would
have approved a document its first approver never re-read; todos left open on
work that had moved on. Anyone writing their own flow skill against this API
needs those rules, and there is no version of "nothing is held back" that
withholds them.

Read them as documentation of how the approval API expects to be driven, not
as includes waiting for a skill.
