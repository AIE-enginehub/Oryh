---
name: oryh-project
description: Use when a project manager plans and follows a project in oryh — break the work into tasks, set who does what and when, record which task waits on which, set milestones and record when each was met, keep the issue log, write the weekly status report, and read where the project stands (hours against plan, milestones on time or late, issues, cost and billing). The server records and derives; you schedule and judge. Requires project.manage (a member updating their own task or raising an issue needs project.contribute).
required_capability: project.manage
---

# Oryh Project

A project's plan is a set of records you keep: tasks in a tree, the
dependencies between them, and milestones. The server keeps them consistent
— a task stays in its project, dependencies never loop, a milestone is
reached only with who confirmed it — and works out the figures on every
read. **It never schedules.** Moving a date when something slips, judging
how far along a task is, deciding whether a milestone is really met: that
is you, with the project manager.

{{include:_common/answer-the-question.md}}

{{include:_common/api-auth-principal.md}}

{{include:_common/confirm-before-you-write.md}}

## Trigger Examples

- "Break the warehouse fit-out into tasks: design, racking, lighting, handover"
- "Racking can't start until design is signed off"
- "Assign racking to Wang from 2 March to 31 March, 40 hours"
- "The customer accepted the racking today — Li Wei signed"
- "Where does the fit-out stand?"
- "Design is a week late — what does that do to the rest?"
- "Log a risk: the anchor bolts may arrive late"
- "Write this week's status report for the fit-out"

## Required Inputs

```yaml
oryh:
<!-- only: bundle -->
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
<!-- /only -->
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
<!-- only: bundle -->
  api_key: "{{ORYH_API_KEY}}"     # project.manage
<!-- /only -->
```

## Planning The Work

1. **Read first**: `GET /projects?keyword=` to find the project, then
   `GET /project-tasks?project_id=<id>` — never plan over a plan that exists.
2. **Tasks**: `POST /project-tasks {"project_id", "name", "task_code"?,
   "parent_task_id"?, "assignee_employee_id"?, "planned_start"?,
   "planned_end"?, "planned_hours"?}`.
   - A phase is a task with sub-tasks; its hours are theirs, summed by the
     server. Put planned hours on the leaves.
   - `task_code` is the workspace's own (`1.2`), unique within the project.
   - `status` comes from `GET /type-options?family=project_task_status`
     (`not_started`, `in_progress`, `blocked`, `done`, `cancelled`, or the
     workspace's own). Nothing on the server acts on it.
3. **Dependencies**: `POST /project-task-dependencies {"predecessor_task_id",
   "successor_task_id", "dependency_type": "FS", "lag_days": 0}` — `FS`
   (finish to start, the usual), `SS`, `FF`, `SF`. A loop is refused.
4. **Milestones**: `POST /project-milestones {"project_id", "name",
   "due_date", "contract_term_id"?}`. When the contract pays on a
   milestone, link its clause (`GET /contract-terms?contract_id=` of the
   project's contract).

## When Something Slips

The server moves no dates. When a task runs late, read its successors
(`GET /project-task-dependencies?task_id=<id>`), work out what follows from
each dependency and lag, and **propose** the new dates to the project
manager. Write them with `PATCH /project-tasks/{id}` only once agreed. The
audit trail keeps every earlier date.

## Progress

- The person a task is assigned to updates its `actual_start`,
  `actual_end` and `status` through their own agent (`project.contribute`);
  they cannot change the plan.
- Hours come from timesheets that name the task (`$oryh-timesheet-submit`).
- **A milestone met**: `POST /project-milestones/{id}/reach {"reached_on",
  "confirmed_by": "<who confirmed it>", "evidence_attachment_id"?}`. Ask who
  confirmed it and on what evidence; record their name, not yours. Reaching
  it bills nothing: if the contract pays on it, raise the invoice with
  `$oryh-receivables` (naming the project), then link it:
  `PATCH /project-milestones/{id} {"invoice_id"}`. Once that invoice stands,
  the milestone's reached date is fixed.
- A milestone recorded in error: `POST /project-milestones/{id}/reopen`.

## The Issue Log

Issues, risks, change requests and defects are one log per project.

- **Raise**: `POST /project-issues {"project_id", "title", "issue_type"?,
  "severity"?, "task_id"?, "owner_employee_id"?, "description"?}`. The
  number (`PI-`) is allocated. Type, severity and status come from
  `GET /type-options?family=project_issue_type` (and
  `project_issue_severity`, `project_issue_status`). Anyone working on the
  project raises one (`project.contribute`); it is recorded as raised by them.
- **Work it**: `PATCH /project-issues/{id}` — owner, severity, status. A
  contributor changes the issues they raised or own.
- **Resolve**: send `resolved_at` with `resolution` — how it was resolved.
  One without the other is refused. Ask; never write a resolution yourself.
- A change request that changes the contract's scope or price is logged
  here; the contract change itself is a supplement, through `$oryh-contracts`.
- Severity is the person's call, and so is escalating. When you see an
  unresolved high one ageing, say so — do not change it.

## Where It Stands

`GET /projects/{id}/execution?as_of=`:

- **hours** — per task, planned hours against hours recorded on submitted
  timesheets (phases rolled up), and hours with no task;
- **milestones** — each one's standing: `upcoming`, `overdue`,
  `reached_on_time`, `reached_late`;
- **issues** — unresolved by type and severity, and all by status;
- **money**, per currency, each part its own documents' figure:
  `expenses` (approved claim lines naming the project), `purchase_orders`
  (confirmed orders), `purchase_invoices` and `billing` (issued invoices net
  of credit notes; billing also shows the contract's value), and `book`
  (posted journal lines naming the project, debit less credit per account
  type).

The money parts are **never summed for you** — an order becomes an invoice,
so adding them counts twice. Say which you used: "Billed ¥28,000 of the
¥100,000 contract; ¥6,000 invoiced by suppliers against ¥8,000 ordered."
A part the reader may not see is left out and named in `withheld`: say it
was withheld, never read it as zero. Labour cost is not here: hours times a
rate is the workspace's rule, so compute it only from a rate they give you,
and say so.

Answer in the manager's terms: "Racking has used 32 of 40 hours and is due
Friday; the handover milestone is overdue by three days." Percent complete
is a judgement — say how you judged it, never present hours as progress.

## The Status Report

1. Read the figures for the period (`as_of` = its last day), the open
   issues and the last reports (`GET /project-reports?project_id=`) — a
   third amber week running is worth saying.
2. Draft with the manager: `POST /project-reports {"project_id",
   "period_start", "period_end", "health": "green|amber|red", "summary",
   "done"?, "next_steps"?, "blockers"?}`. Health and words are theirs;
   propose, they decide. Edit with `PATCH`; discard with `DELETE`.
3. **Publish** once they agree: `POST /project-reports/{id}/publish`. The
   server copies the figures as of `period_end` into the report, and it
   never changes after. A correction is a new report for the same period
   — it takes the next revision; the earlier one stays.
4. Sending it is a separate act: `POST /notifications` to the people the
   manager names.

## What This Skill Never Does

- Move a date because another task slipped without the manager agreeing.
- Mark a milestone reached on the manager's assumption: someone confirmed it.
- Raise an invoice because a milestone was reached — that is the contract's
  term and the workspace's rule, applied through $oryh-receivables.
- Delete a task with sub-tasks, dependencies or hours; set it `cancelled`.
- Add the money parts into one "cost" or "margin" figure.
- Publish a report, rate its health, or resolve an issue without the person.

## Reference

- [references/api.md](references/api.md): request templates.

Chinese request aliases and original example wording are available in
[locale examples](locales/zh-CN/examples.json); preserve user-provided names and text.
