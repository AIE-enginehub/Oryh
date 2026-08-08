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
