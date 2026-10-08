---
kind: approval_flow
entity_kind: builtin
object_type: sales_order
name: default
title: Sales order approval flow
title_zh: 销售订单审批流程
visibility: internal
---
An order whose total is within 2% of its accepted quotation confirms without a human node: set it to confirmed. An order that drifts from its quotation by more than 2%, or that has no quotation, needs the sales manager. A customer return needs the sales manager. Once confirmed, what happens in the warehouse is the sales_order linkage's sentence.

<!-- zh -->
订单总额与已成交报价相差不超过 2% 的，无需人工节点：直接置为 confirmed。相差超过 2%，或没有报价的订单，需销售经理审批。客户退货需销售经理审批。确认之后仓库做什么，写在销售订单的单据联动里。
