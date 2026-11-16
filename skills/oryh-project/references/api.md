# Project API

<!-- only: bundle -->
Every path hangs off `api_base_url` exactly as given — no version prefix to add.
<!-- /only -->

{{include:_common/api-conventions.md}}

## Tasks

```text
GET    /project-tasks?project_id=&parent_task_id=&assignee_employee_id=&status=&keyword=
POST   /project-tasks                  → {project_id, name, task_code?, parent_task_id?, assignee_employee_id?, planned_start?, planned_end?, actual_start?, actual_end?, planned_hours?, status?, sort_order?, description?}
PATCH  /project-tasks/{id}             → any of the above but project_id; an assignee holding only project.contribute may send actual_start, actual_end, status
DELETE /project-tasks/{id}             → only with no sub-tasks, dependencies or hours
```

## Dependencies

```text
GET    /project-task-dependencies?project_id=&task_id=
POST   /project-task-dependencies      → {predecessor_task_id, successor_task_id, dependency_type?: FS|SS|FF|SF, lag_days?}
DELETE /project-task-dependencies/{id}
```

## Milestones

```text
GET    /project-milestones?project_id=&status=&due_date_thru=
POST   /project-milestones             → {project_id, name, due_date, contract_term_id?, invoice_id?, description?}
PATCH  /project-milestones/{id}        → name, due_date, contract_term_id, invoice_id, description, status (open | cancelled)
POST   /project-milestones/{id}/reach  → {reached_on, confirmed_by?, evidence_attachment_id?}
POST   /project-milestones/{id}/reopen → back to open; refused while the invoice that billed it stands
```

## Issues

```text
GET    /project-issues?project_id=&task_id=&issue_type=&severity=&owner_employee_id=&status=&unresolved=&keyword=
POST   /project-issues                 → {project_id, title, issue_no?, issue_type?, severity?, task_id?, raised_by_employee_id?, owner_employee_id?, raised_at?, description?, status?, resolved_at?, resolution?}
PATCH  /project-issues/{id}            → any of the above but project_id and issue_no; resolved_at needs resolution
```

## Status reports

```text
GET    /project-reports?project_id=&health=&status=   → latest period first, latest revision first
POST   /project-reports                → {project_id, period_start, period_end, health: green|amber|red, summary, done?, next_steps?, blockers?}
PATCH  /project-reports/{id}           → a draft's words, health, period_end
DELETE /project-reports/{id}           → a draft only
POST   /project-reports/{id}/publish   → copies the figures as of period_end into the report; it never changes after
```

## Where it stands

```text
GET    /projects/{id}/execution?as_of=   → hours {planned, recorded, recorded_on_no_task}, tasks[], milestones[] with standing, milestone_standing, issues {by_status, unresolved_by_type_and_severity, unresolved}, money {expenses, purchase_orders, purchase_invoices, billing, book} per currency, withheld[]
```

Purchase requests and orders take `project_id` (`$oryh-purchase-submit`, `$oryh-purchase-order`); an order does not inherit its request's project.
