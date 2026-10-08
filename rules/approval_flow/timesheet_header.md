---
kind: approval_flow
entity_kind: builtin
object_type: timesheet_header
name: default
title: Timesheet approval flow
title_zh: 工时单审批流程
visibility: internal
---
The submitter's direct manager approves. A week over 40 hours, or any entry on a project the manager does not own, is countersigned by that project's manager after the direct manager. The last approval is final: set the timesheet to approved. A returned timesheet starts a new round from the direct manager.

<!-- zh -->
直属经理审批。一周超过 40 小时，或任一行记在经理不负责的项目上的，经理通过后再由该项目经理会签。最后一个通过即为最终：工时单置为 approved。被退回的工时单重提后从直属经理重新开始一轮。
