# Shipped rule catalog

One file per seeded rule, `rules/<kind>/<object_type>.md`: a frontmatter
(`kind`, `entity_kind`, `object_type`, `name`, `title`, `title_zh`,
`visibility`) and a body in English, then `<!-- zh -->` and the same body in
Chinese. `provision_rule_catalog` picks the half the deployment's locale asks
for and seeds each file as a **draft** `business_rules` row — `origin:
catalog`, `catalog_hash` the body's hash — for every tenant, on creation and
on every deploy.

Drafts, not published rules, on purpose: the hosted runner drives a family
only when an `approval_flow` is published, and a default routing a workspace
never wrote must not decide who approves. What the seed buys is a starting
text: the administrator reads it, changes the sentences that are not theirs,
and publishes.

The sync rule is the product skills' (`provision_product_skills`): a seeded
draft the workspace has not touched follows the catalog on the next deploy; a
draft that was edited, or a scope that was ever published, is the workspace's
and is never touched again; a file withdrawn from the catalog soft-deletes the
untouched drafts it seeded. Only the three scoped kinds ship here — a policy
is the company's own code and category, and the catalog has none.

`tests/test_rule_catalog.py` reads every file: the frontmatter is complete,
the scope is a hosted builtin family, both language halves are present.
