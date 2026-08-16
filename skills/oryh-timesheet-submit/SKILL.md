---
name: oryh-timesheet-submit
description: Use when a person's AI agent needs to fill, update, query, or submit that person's own timesheet in oryh. Covers natural-language timesheet capture, validating the input and confirming anything unusual with the principal before writing, draft reuse, line entries, free-text project capture, submission, and fixing a returned timesheet. It records the submitter's facts only — routing and approval belong to other roles.
required_capability: timesheet.submit_own
---

# Oryh Timesheet Submit

Record and submit the principal's own timesheet. The credential is the identity: the server only accepts writes for the employee linked to this key, so never ask "for whom" — it is always the principal.

## Trigger Examples

- "File my timesheet" / "Submit this week's hours"
- "Add today's hours"
- "Amend this timesheet" / "It came back — fix it and resubmit"
- "Look up my timesheets"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # the principal's user-bound key
```

Everything else comes from conversation: the period, the hours, the original description.

## Steps

{{include:_common/answer-the-question.md}}

{{include:_common/fewer-round-trips.md}}

{{include:_common/read-before-you-decide.md}}

{{include:_common/leave-no-orphan-work.md}}

1. **Identity**: your employee id is already in this file — `{{EMPLOYEE_ID}}`. No call needed. Do not create employees; that is an HR/admin capability. Blank means no employee record is linked to this principal: say so, do not work around it.
2. **Tenant requirements**: `GET /workflow-definitions?entity_kind=builtin&object_type=timesheet_header` — the tenant's natural-language rules for this object, current as of this moment. Read what it requires of a submission (task granularity, weekly totals, and the like) and let it shape the conversation from the first question — see the "Tenant requirements" layer below. No definition, or nothing in it about filling in a timesheet → only the universal checks apply; never invent requirements. Routing rules in the same document belong to other roles — ignore them.
3. **Reuse before create**: `GET /timesheet-headers?employee_id={me}&status=draft` — one header per period; retries must not duplicate. A `returned` header is also reused: fix it, don't recreate — and read why it came back first: the rework todo's `description` and the latest `returned` approval record's `comment` list exactly what to fix, usually citing the step-2 requirements. After a successful resubmit, complete that rework todo (`PATCH /todos/{todo_id}` `{"status": "completed"}`; needs `todos.complete_own`, in the default member role) — while it stays open, the header is invisible to the flow admin's work queue.

   **Steps 2 and 3 do not feed each other — send them as one batch.** The tenant's rules and your own open documents are independent lookups; waiting for the first before asking the second doubles the wait for no reason.

4. **The whole document, one call**: `POST /timesheet-headers` with
   `employee_id`, `period_start`, `period_end`, the user's original words in
   `source_report_text`, and **every line inline in `entries`**
   (`work_date`, `hours`, `task` each; `header_id`/`employee_id` are implied
   — do not repeat them). One bad line rolls the whole document back, so
   nothing half-filled is ever left behind.
   - Validate every line BEFORE writing — see "Validate before writing"
     below. Anything that fails a reasonableness check is a conversation,
     not a write. The batch is not a reason to lower the bar per line.
   - Project: send `project_id` only when a real project record is
     confidently matched (`GET /projects?keyword=`); otherwise keep
     `project_name_snapshot` + `client` as free text. Never invent projects.
   - **The response is your read-back**: it carries the header AND every
     entry as stored. Show it to the person from the response; do not spend
     a call re-reading what you were just told.
   - Corrections after the fact: `POST /timesheet-entries` to add,
     `PATCH`/`DELETE` per entry to fix — but `work_date` is not a PATCH
     field (422 naming it): fix a date by DELETE + re-POST. Entries are
     editable only while the header is in the tenant's editable states
     (default `draft`/`returned`) — a 409 means the header has moved on.
5. **Submit**: `POST /timesheet-headers/{id}/submit` — only after the
   pre-submit read-back below got an explicit yes. Idempotent — resubmitting
   a submitted header is a no-op. The response's `status`/`submitted_at` is
   the confirmation; nothing needs re-reading.
6. **The submitted approval fact is not yours to write.** `/submit` records it (`round_no` derived, `sequence_no=1`, `source=system`), so the trail opens with it whether or not this credential carries `approval.record`. Posting it anyway is harmless — the recorded fact comes back — but there is nothing to do here.

## Validate Before Writing

Three layers. Hard rules the server enforces — check them yourself first so the user gets a question, not an error code. Tenant requirements the workflow admin calibrates against — the server records whatever is legal, but a submission that ignores them comes straight back. Reasonableness checks are yours alone: you are the only gate between a misheard "8" and a submitted "80".

**Hard rules (the server rejects these; catch them in conversation first):**

- `hours` per entry: more than 0, at most 24.
- `work_date` must fall inside the header's `period_start`–`period_end`.
- One header per employee per exact (`period_start`, `period_end`) pair — a duplicate create returns 409 naming the existing header. Better to catch it first: the step-3 reuse query only sees `draft`, so scan the periods across ALL statuses (`GET /timesheet-headers?employee_id={me}`) — an existing `submitted`/`approved` header for the period is a conversation, not a create. A soft-deleted header still holds its period slot; the 409 says to restore it rather than recreate.
- Entries only while the header is `draft`/`returned`.
- `project_id` must be a real record — free text goes in `project_name_snapshot`, never a guessed id.

**Reasonableness (pause and ask before writing):**

- A single day summing past 12h across entries → "30 June totals 14 hours — was that genuinely overtime?"
- A `work_date` in the future → work not done yet; typo or intentional pre-fill?
- Weekend or holiday dates → confirm it was really worked.
- A full week totalling under 20h or over 60h → something missing, duplicated, or misread?
- Vague task text ("work", "dealt with things") → ask what was actually done; approvers return vague lines, so one question now saves a rework round.
- A near-duplicate line already on the header (same date, same task) → add on top, or replace the old line?
- A project name that matches nothing in `/projects` → confirm capturing it as free text.

**Tenant requirements (the workflow admin returns violations; catch them in conversation first):**

- Whatever the step-2 definition requires of a submission, applied line by line. Typical shapes: every entry must be linked to a specific project or task; a week is five working days of eight hours, totalling exactly 40; overtime must state its reason in `notes`. The definition's own wording always wins over these examples.
- These are the exact requirements the workflow admin's agent checks before assigning any approver, and its return note cites the ones violated — so a requirement skipped here is a guaranteed rework round. Ask for what is missing while the user is still talking, not after the return.
- Fixing a returned header? Re-run step 2 first — the requirements may have changed since the original submission, and the current version is what the next calibration uses.

- Quote the user's own words, state what looks off, propose your reading, ask ONE clear question. Don't stack five doubts into one message.
- Never silently "fix" a number, date, or description — a correction the user didn't see is worse than the error.
- If the principal confirms an unusual fact (the 14h day was real), record it exactly as stated and put the clarification in `notes`. Judging reasonableness is the approver's job; yours is faithful capture plus honest flagging.
- Do not round, pad, or trim hours to look normal. The user's facts are the facts.

**Pre-submit read-back:** before step 6, echo the complete timesheet — each day's lines and the period total — and get an explicit confirmation. Submission hands the record to the approval flow; changing it afterwards costs a return round.

## What Happens Next (so you can answer the user)

The timesheet now sits in the workflow admin's queue. It is first calibrated against the same submission requirements you applied in step 2 — a non-compliant timesheet comes back as a rework todo without reaching any approver — then approvers are assigned per the tenant's workflow definition. Progress is visible any time via the approval trail (`GET /approval-records?entity_type=timesheet_header&entity_id={id}`) — the status stays `submitted` until the flow finishes. If it is returned, a rework todo appears in the principal's inbox (see `$oryh-my-work`); fix the entries and submit again.

## What This Skill Never Does

- Approve, decide routing, or touch the header status (`/submit` is the only transition it makes).
- Create employees or projects as a side effect.
- Submit for anyone other than the credential's own employee.
- Alter the principal's stated hours, dates, or descriptions without showing the change and getting agreement.
- Submit without the pre-submit read-back.

## Reference

- [references/api.md](references/api.md): request templates.
