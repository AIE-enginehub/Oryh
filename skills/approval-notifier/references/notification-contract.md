# Approval Notification Contract

This skill is channel-agnostic in principle, but email should be the default channel unless the caller says otherwise.

## Suggested input shape

```yaml
approval_notification:
  channel: email
  event_type: approval_requested
  entity:
    entity_type: business_object
    entity_id: business-object-id
    object_type: warranty_card
    title: Warranty card application JC-WC-APP-0422
    summary: Alpha Repair submitted a warranty card application for Shanghai City Hospital.
    detail_url: '{{ORYH_BASE_URL}}/console/todos'
  approval_context:
    round_no: 1
    mode: sequential
    current_step:
      sequence_no: 1
      approver_id: jc-approver-001
      approver_role: warranty_approver
      approver_name: Manager Chen
  recipients:
    - person_id: jc-approver-001
      name: Manager Chen
      email: manager.chen@example.com
      locale: zh-CN
      timezone: Asia/Shanghai
      channel_preferences:
        primary: email
  notification_policy:
    dedupe_key: business_object:business-object-id:round-1:step-1:approval_requested
    allow_repeat_after_minutes: 1440
    escalate_after_hours: 24
  preview_only: false
```

## Suggested output shape

```json
{
  "status": "sent",
  "channel": "email",
  "event_type": "approval_requested",
  "recipient": {
    "person_id": "jc-approver-001",
    "email": "manager.chen@example.com"
  },
  "subject": "Approval needed: Warranty card application JC-WC-APP-0422",
  "sent_at": "2026-03-30T10:30:00Z",
  "dedupe_key": "business_object:business-object-id:round-1:step-1:approval_requested"
}
```

## Suggested email templates

### approval_requested

Subject:

```text
Approval needed: {entity_title}
```

Body:

```text
{approver_name}，你好：

有一项业务记录需要你审批。
类型：{entity_type}
标题：{entity_title}
摘要：{summary}

请查看并完成审批：
{detail_url}
```

### approval_reminder

Subject:

```text
Reminder: pending approval for {entity_title}
```

Body:

```text
这是对先前审批请求的提醒。以下业务记录仍待处理：
{entity_title}

请查看：
{detail_url}
```

### approval_approved

Subject:

```text
Approval completed: {entity_title}
```

### approval_rejected

Subject:

```text
Approval rejected: {entity_title}
```

### approval_returned

Subject:

```text
Approval returned for update: {entity_title}
```

## Dedupe rules

Suggested behavior:

- same `dedupe_key` within the configured repeat window -> skip sending
- `preview_only: true` -> render but do not send
- no valid recipient email -> fail fast and return the missing field

## Integration notes

- This skill can work with any mail tool the agent already has.
- If no mail tool exists, the skill should still produce a rendered subject and body so the caller can send it another way.
- The caller should persist notification history in memory or another store. This skill should not assume it owns durable notification history.
