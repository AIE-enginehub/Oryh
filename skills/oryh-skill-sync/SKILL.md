---
name: oryh-skill-sync
description: Use when a person's AI agent should check whether its installed oryh skills for THIS company are current — on session start, periodically, or on demand ("更新一下 oryh 技能"). Compares the local bundle manifest against the server's per-user manifest and refreshes this company's bundle when anything changed. Read-only against business data; the only local write is replacing this company's own installed directory.
---

# Oryh Skill Sync

Tenant admins publish new skills and revise existing ones; this skill keeps your installed copy current without asking an admin. Syncing never rotates your API key — your other devices keep working.

This copy serves **one employer**. Its key, its manifest and its directory all belong to that company. Someone who works for two companies has two of these, one per directory, and each syncs only its own — never reach across into a sibling `oryh-skills-*` directory.

## Trigger Examples

- "我的 oryh 技能是最新的吗？"
- "更新一下 oryh 技能"
- On session start, before running any other oryh skill (cheap: one GET when current).

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"   # every path below hangs off THIS
  api_key: "{{ORYH_API_KEY}}"                # the principal's user-bound key, for THIS company
  install_dir: <where this company's {{INSTALL_DIR}}/ directory lives locally —
                the installed manifest.json carries it>
```

**Build every path on `api_base_url` as given.** A path built on the bare site
origin instead is not an error you will notice:
the server answers 200 with an HTML page, so `GET /my/skill-bundle` hands you
2.6 KB of web page where you expected a zip — and step 5 moves the live
directory aside before step 4's download is ever opened.

If the person has more than one employer installed, sync the one this request is about — or each in turn, each with its own key out of its own directory. Never call with another company's key.

## The Check

```text
1. Read the installed manifest:
   {{INSTALL_DIR}}/manifest.json →
     {generated_at,
      tenant: {id, slug, name},   ← which company this directory serves
      environment_id,            ← which DEPLOYMENT, not a company
      install_dir, site_base_url, api_base_url,
      skills: [{name, installed_as, version, files_hash}]}

2. GET {api_base_url}/my/skills/manifest
   → the server's current list for YOUR role, plus the same identity block:
     {"data": [{name, installed_as, title, version, files_hash}],
      "meta": {total, tenant: {id, slug, name}, environment_id, install_dir,
                site_base_url,
                api_base_url}}

3. Compare:
   - `meta.tenant.id` must equal the installed `tenant.id`. If it does not, this
     key does not belong to this directory — STOP, write nothing, and tell the
     person: two companies' wires have crossed.
   - Then compare skills by `name` (the stable registry name; `installed_as` is
     only what it is called on disk):
     - same names, same version + files_hash everywhere, and an unchanged tenant
       block → up to date. Say so in one line — UNLESS they named a skill they
       expected to get, in which case "你已经是最新的" answers the wrong
       question: go to `GET {api_base_url}/my/skills/reach` and tell them why
       that skill is not theirs (see "Why Don't You Have The X Skill?").
     - any version/files_hash differs, a skill appears/disappears (role changes
       move skills in and out of your entitlement), or the company renamed
       itself (`meta.tenant.name` differs) → refresh.
```

## The Refresh

```text
4. GET {api_base_url}/my/skill-bundle   (Accept: application/zip)
   → a freshly rendered bundle for you, using the same key you called with.
     It holds exactly ONE company directory, plus the shared `oryh-connect/`.
     Check it is really a zip before touching the installed directory; an HTML
     body means the URL was built on the site origin rather than
     `api_base_url`, not that the bundle is empty.

5. Replace THIS company's directory with the zip's — whole-directory swap,
   never file-by-file patching, so a half-updated skill can never run. Keep the
   old directory until the new one is fully extracted.
   - The zip's own top-level company directory is authoritative: install where
     it says, even if that differs from where you are installed today, and then
     remove the directory you came from.
   - Do not touch any sibling `oryh-skills-*/` directory. Those are other
     employers, with other keys.
   - `oryh-connect/` sits beside the company directories and belongs to no
     company. Replace it from the zip too — it is identical for every employer,
     so refreshing it from this one cannot harm another.

6. Delete the downloaded zip. It carries the principal's key in plaintext,
   and nothing needs it once the directory is in place.

7. Report what changed: skills added, removed, or bumped (old → new version),
   and name the company you synced.
   - **A skill DISAPPEARED → call `GET {api_base_url}/my/skills/reach` before
     you report.**
     "少了 X" on its own sounds like the skill was archived or re-aimed; far
     more often their permissions or their role changed. Name the reason, and
     say it is a change on the company's side rather than something they can
     re-sync their way out of.
```

## What Sync Covers — And What Never Needs It

Skills carry the **mechanism**: which endpoint to call, what to ask before
writing, what to check. The tenant's **rules** — who approves, at what
threshold, what a submission must contain — are NOT in these files. Every
skill that needs them fetches them at the moment it runs
(`GET /workflow-definitions?entity_kind=builtin&object_type=…`), so a rule
change is live immediately, for everyone, with nothing to install.

| The admin changed… | Does sync report a change? | When does it take effect? |
|---|---|---|
| a **workflow definition** (审批人、阈值、提交要求) | **No** — no skill file moved | already in effect; the next run reads it |
| an **object type definition** (字段、状态机) | **No** — same reason | already in effect |
| a **tenant skill** in `/skills` (new, revised, archived) | Yes | after this sync |
| **who a skill is aimed at** (audience / distribution mode) | Yes | after this sync |
| the **shipped product catalog** (a deploy) | Yes | after this sync |
| **your role** (skills gained or lost) | Yes | after this sync |

So "everything is current" is the expected answer after a workflow-definition
edit — and it is not the same as "your change did nothing". **When someone
asks you to sync right after editing a rule, say both**: the installed skills
are unchanged *because rules do not live in them*, and their edit is already
live. Offer to read the definition back so they can see it landed.

## "Why Don't You Have The X Skill?"

Sync answers "am I current". This answers "why is that skill not here at
all" — a different question, and one you could previously only guess at.

```text
GET {api_base_url}/my/skills/reach
```

**Call it in three situations, not only when asked outright:**

1. The person names a skill they expect and sync reports no change. "你已经是
   最新的" is then the literally correct answer and the single most misleading
   thing you can say — it reads as "sync is broken" when the real answer is
   "that skill was never sent to you". Answer the question they asked.
2. **A skill disappeared during sync.** Reporting "少了 X" alone sounds like
   the skill was archived or re-aimed; usually their permissions changed. Say
   which.
3. They ask directly.

Each withheld skill carries **every** reason that applies, in `reasons`:

- `missing_capability` — their role does not grant the skill's
  `required_capability`.
- `not_in_audience` — they could run it, but the admin aimed it elsewhere.
  A capability grant does nothing here.

**Both can be present at once, and then both must be fixed.** Relay every
reason in `reasons`. Passing on one of two sends the person to their admin
for half a fix; they wait, re-sync, still do not have it, and come back.

`granted_by_roles` names the roles that hold the capability **today**. It is
context, not an instruction: those roles are usually more privileged than
the person asking, and "申请转成合伙人" to get a meeting-room skill back is an
escalation, not a fix. Ask for **the capability**, and name the roles only if
the admin needs a precedent to copy.

**If the skill was there yesterday and is gone today, that is a role change,
not a missing entitlement** — say so plainly and let them ask their admin why
it changed. Do not turn it into a request for a bigger role.

Never offer to fix any of this yourself. All of it is the admin's to change,
and none of it is something a re-sync can produce — syncing again after this
answer just wastes the person's time.

## A Legacy Unprefixed `oryh-skills/` Directory

Bundles used to install into a single `oryh-skills/` whose skills carried no
company in their names — the reason two employers could not coexist. If you are
running from one, step 5 migrates you: the zip now names its directory
`oryh-skills-<slug>/`. Install that, verify it, then delete the legacy
`oryh-skills/`. Never leave both — two live copies of every skill under two
different names is precisely the ambiguity the company prefix exists to remove.

## Failure Handling

- `401 invalid API key`: this device's key was rotated (an admin issued a new bundle) or deactivated. Stop syncing and hand over to `$oryh-connect` — the shared, company-agnostic bootstrap skill; the principal reconnects through the browser, no admin needed. If it is not installed, it is a public download that needs no credential: `GET {{ORYH_API_BASE_URL}}/connect-skill`.
- `403 a user-bound API key is required`: the configured key is a tenant service key; this skill only works with a personal bundle key.
- Network failure mid-refresh: keep the currently installed skills; retry the whole check next session.

## What This Skill Never Does

- Rotate or request credentials (keys are minted by admin issuance or by the principal approving `$oryh-connect` in the browser — never by syncing).
- Edit skill content locally (tenant admins own skill content; local edits are overwritten on the next sync).
- Touch anything outside this company's own installed directory.

## Reference

- [references/api.md](references/api.md): the exact endpoints and response shapes.
