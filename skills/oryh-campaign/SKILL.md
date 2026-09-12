---
name: oryh-campaign
description: Use when marketing runs a campaign in oryh — 建一场展会/线上活动/邮件营销, 登记触达了谁, 看活动带来了多少线索和商机 — creating, advancing and reading campaigns and their members. Requires campaign.manage. Attribution on leads and deals is the sales desk's ($oryh-crm).
required_capability: campaign.manage
---

# Oryh Campaign

A campaign is a marketing effort — a trade fair, a webinar, a mailing, an ad
run — that leads and deals are attributed to. This skill is marketing's
side of it: the campaign itself, its life, and who it reached. What it
EARNED is never written here: it is the leads and opportunities carrying
`campaign_id`, read live by the detail.

{{include:_common/answer-the-question.md}}

{{include:_common/api-auth-principal.md}}

{{include:_common/confirm-before-you-write.md}}

## Trigger Examples

- "Create an October campaign for the Shanghai medical fair, budget 80,000"
- "Register this list as invitees of the online seminar"
- "How many leads, deals and wins did the fair bring?"
- "The campaign is over, close it" — `completed`, not deleted

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # campaign.manage
  employee_id: "{{EMPLOYEE_ID}}"  # the campaign's owner unless another is named
```

## Running A Campaign

1. **Vocabulary once**: `GET /type-options?family=campaign_type` and
   `family=campaign_member_status` — the workspace's own names; use their
   `name` values.
2. **Dedup**: `GET /campaigns?keyword=` — the same fair entered twice is one
   campaign counted twice.
3. **Create**: `POST /campaigns {"name", "employee_id", "campaign_type",
   "start_date", "end_date", "budget"?, "expected_revenue"?, "parent_campaign_id"?}`.
   A season rolls up its fairs through the parent. It starts `planned`.
4. **Advance as facts happen**: `PATCH /campaigns/{id} {"status": "active"}`
   when it runs, `completed` when it is over (`actual_cost` when known),
   `cancelled` when it does not happen. The machine is the workspace's; read
   `GET /workflow-definitions?entity_kind=builtin&object_type=campaign`
   when a 409 says your assumption was renamed.
5. **Who was reached**: `POST /campaign-members {"campaign_id", "lead_id" |
   "customer_id" (+"contact_id"?), "member_status"}` — one party per row,
   a party once per campaign (a second try answers 409). Update the row as
   they respond, attend, convert or decline.
6. **What it produced**: `GET /campaigns/{id}/detail` — `members_total`,
   `members_by_status`, `leads_total`, `leads_converted`,
   `opportunities_total`, `opportunities_won`, `won_expected_amount`. Say
   out loud that the last is the won deals' ESTIMATES; the money is in
   their orders (`GET /sales-orders?opportunity_id=`).

## What This Skill Never Does

- Write a lead's or a deal's `campaign_id` — attribution is the sales desk's ($oryh-crm), written when they capture the lead.
- Report `won_expected_amount` as revenue, or store any count on the campaign.
- Delete a campaign that ran — `completed` or `cancelled` is its end; deletion is for a campaign entered by mistake.

## Reference

- [references/api.md](references/api.md): request templates.
