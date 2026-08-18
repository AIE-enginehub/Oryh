---
name: approval-notifier
description: Use when an AI agent needs to notify approvers, reviewers, submitters, or other participants about approval activity for any oryh entity such as timesheet_header or business_object. This covers email-style approval requests, reminders, escalations, and approval outcome messages using approval step context and contact details stored in agent memory.
required_capability: todos.assign
---

# Approval Notifier

Send approval-related messages (requests, reminders, escalations, outcomes). A flow-side integration skill: it runs alongside `oryh-timesheet-approval-flow` on the workflow admin agent, which is why it is gated like one (`todos.assign` — the routing capability, not in the default member role). It ships only to admins and to roles a tenant explicitly grants `todos.assign`.

Division of labor:

- record skills write business and approval facts; the flow skill assigns todos
- **oryh state is the source of what to notify about**: new assignments = the todos the flow admin just created; overdue reminders = `GET /todos?status=open&due_before=<now>`; outcomes = the final status transition
- this skill only composes and delivers messages; contact data, channel preferences, locale, and anti-spam context come from agent memory
- delivery state (what was already sent) is notifier-side memory — oryh deliberately tracks work state, not message delivery. Worst case after losing that memory is a duplicate reminder, which is acceptable by design

This skill should trigger for user intents like:

- "Tell the manager to approve the timesheet"
- "Notify the JC approver about the warranty card"
- "Email a reminder to the approver"
- "Chase the approval on this application"
- "Tell the filer the outcome"
- "Notify the next approver"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, the links in the message point here
  api_key: "{{ORYH_API_KEY}}"        # tenant service key; the notifier reads queues for the tenant
```

## Required inputs

The caller should provide a parameter block like this:

```yaml
approval_notification:
  channel: "email"
  event_type: "approval_requested"
  entity:
    entity_type: "business_object"
    entity_id: "business-object-id"
    object_type: "warranty_card"
    title: "Warranty card application JC-WC-APP-0422"
    summary: "Alpha Repair submitted a warranty card application for Shanghai City Hospital."
    detail_url: "{{ORYH_BASE_URL}}/console/todos"
  approval_context:
    round_no: 1
    mode: "sequential"
    current_step:
      sequence_no: 1
      approver_id: "5c1c9f6b-6df1-4f6a-b8a2-1b5a52e2c101"
      approver_role: "warranty_approver"
      approver_name: "Manager Chen"
  recipients:
    - person_id: "5c1c9f6b-6df1-4f6a-b8a2-1b5a52e2c101"
      name: "Manager Chen"
      email: "manager.chen@example.com"
      locale: "zh-CN"
      timezone: "Asia/Shanghai"
      channel_preferences:
        primary: "email"
  notification_policy:
    dedupe_key: "business_object:business-object-id:round-1:step-1:approval_requested"
    allow_repeat_after_minutes: 1440
    escalate_after_hours: 24
```

Minimum required values:

- `channel`
- `event_type`
- at least one `recipient`
- enough entity context to compose a useful message

## Parameter Semantics

- `entity.entity_type` and `entity.entity_id` identify the oryh record being discussed, such as `timesheet_header` plus `timesheet_headers.id` or `business_object` plus `business_objects.id`.
- `entity.object_type` is only present for business objects, such as `warranty_card`.
- `approval_context.current_step.approver_id` should align with `employees.id` when the approver is represented in oryh.
- `approval_context.current_step.approver_role` is a role snapshot for message context. It mirrors what record-writing skills may store in `approval_records.approver_role`.
- `notification_policy.dedupe_key` is notifier-side memory context. Oryh does not own notification dedupe state.

## What belongs in agent memory

Agent memory should hold:

- approver email addresses
- preferred language and timezone
- fallback contacts
- anti-spam history, such as when the last reminder was sent
- tenant-specific subject or tone preferences

Do not hardcode recipient contact data inside the skill itself.

## What this skill is responsible for

1. Turn approval context into a clean notification
2. Choose the right recipients from the passed input
3. Apply simple dedupe and reminder rules from the provided policy
4. Produce or send a message through the available mail or messaging tool
5. Return a structured result the agent can store or use for follow-up

## What this skill is not responsible for

- deciding the approval workflow
- deciding final business status
- recording approval facts in `oryh`
- storing long-term recipient memory

Those responsibilities stay with the orchestration layer and the relevant oryh skills.

## Recommended workflow

### 1. Gather context

From the caller and memory, collect:

- approver identities
- contact channels
- entity summary
- approval step information
- any prior notification history for dedupe

If required contact data is missing, stop and report exactly what is missing.

### 2. Check notification policy

Before sending:

- compare `notification_policy.dedupe_key` against recent notifications
- skip if the same event was already sent too recently
- send a reminder only when the repeat window has elapsed

### 3. Compose the message

Keep messages short and action-oriented. Include:

- who submitted the timesheet
- the relevant business object or period
- why the recipient is being notified
- the requested action
- a direct link or reference ID

### 4. Send the notification

Prefer the recipient's primary channel. For now, email is the default.

Return structured output with:

- recipient
- channel
- event_type
- sent_at
- dedupe_key
- delivery status
- subject

### 5. Hand control back to the agent

The agent should then:

- wait for approval activity
- use the relevant oryh record skill to write approval facts
- decide whether to notify the next approver or the original submitter

## Event types

Supported event types should be treated as intent labels:

- `approval_requested`
- `approval_reminder`
- `approval_escalated`
- `approval_approved`
- `approval_rejected`
- `approval_returned`

## Email content guidance

For `approval_requested`, prefer:

- clear subject line
- one-paragraph summary
- explicit next action
- relevant business context

For `approval_reminder`, mention:

- prior request exists
- what is still pending
- whether the message is a reminder or escalation

For outcome notifications, clearly state:

- approved / rejected / returned
- who acted
- any approver comment if supplied

### Returns, specifically

A return is the one outcome whose message has a job beyond informing: the
person has to act on it. Three rules, learned from a customer who wrote their
own return-notification skill because this one was not reaching them:

- **Quote the approver's `comment` verbatim.** Do not summarise it, tidy its
  grammar, or drop the parts that look redundant. It is the instruction for
  what to fix, written by the person who will judge the fix; a paraphrase is a
  different instruction. If it is empty, say that it is empty rather than
  inventing a reason.
- **Only notify while it still needs doing.** Check the document's current
  status first — a return that has already been reworked and resubmitted, or
  one on a document since approved, is history. Notifying about it sends
  someone to look at a queue where nothing is waiting.
- **Never guess an address.** No email on the employee record means say so and
  name the person, so somebody can fix the record. A message sent to a guessed
  address is worse than one not sent: it looks delivered.

Point the person at their queue (`{base_url}/console/todos`) rather than
describing what to do — the rework todo the flow agent opened is already there,
and it carries the same text.

## Pairing With Oryh Record Skills

Typical sequence for a timesheet approval:

1. Use `oryh-timesheet-submit` to create and submit the header
2. Use `oryh-timesheet-approval-flow` to open the current approval step
3. Use `approval-notifier` to notify the current approver
4. When the approver acts, use `oryh-timesheet-approve` to write the approval event and complete the current todo
5. Use `oryh-timesheet-approval-flow` to decide whether to open the next step or finish the flow
6. When the flow ends, optionally notify the submitter of the result

Typical sequence for a generic business object approval:

1. Use `oryh-business-object` to create the business record
2. Write a `submitted` approval record for the current approver
3. Create the approver todo explicitly with `POST /todos`
4. Use `approval-notifier` to notify the current approver
5. When the approver acts, record the approval event. The approver's own todo is
   completed by that same call — the server closes it in the transaction that
   records the decision, so there is no second call and nothing to notify about
   a todo that was left open.

## References

Load [references/notification-contract.md](./references/notification-contract.md) for suggested payload shapes, email templates, and returned result format.
