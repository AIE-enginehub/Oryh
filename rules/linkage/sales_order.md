---
kind: linkage
entity_kind: builtin
object_type: sales_order
name: default
title: Sales order linkage
visibility: internal
---
When an order is confirmed: a shipment draft is raised from its lines for the warehouse, stock is held for it, the warehouse picks before packing — one picklist per order — and then ships. When an order is signed: finance receives an invoicing todo and issues the invoice.
