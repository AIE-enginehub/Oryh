---
kind: linkage
entity_kind: builtin
object_type: sales_order
name: default
title: Sales order linkage
title_zh: 销售订单单据联动
visibility: internal
---
When an order is confirmed: a shipment draft is raised from its lines for the warehouse, stock is held for it, the warehouse picks before packing — one picklist per order — and then ships. When an order is signed: finance receives an invoicing todo and issues the invoice.

<!-- zh -->
订单 confirmed 后：按订单行生成出货单草稿交给仓库，为其占货，仓库先拣货再打包——每单一张拣货单——然后发货。订单 signed 后：给财务派开票待办，由财务开票。
