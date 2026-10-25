---
kind: approval_flow
entity_kind: builtin
object_type: timesheet_header
name: default
title: Timesheet approval flow
visibility: internal
---
The submitter's direct manager approves. A week over 40 hours, or any entry on a project the manager does not own, is countersigned by that project's manager after the direct manager. The last approval is final: set the timesheet to approved. A returned timesheet starts a new round from the direct manager.
