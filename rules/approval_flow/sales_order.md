---
kind: approval_flow
entity_kind: builtin
object_type: sales_order
name: default
title: Sales order approval flow
visibility: internal
---
An order whose total is within 2% of its accepted quotation confirms without a human node: set it to confirmed. An order that drifts from its quotation by more than 2%, or that has no quotation, needs the sales manager. A customer return needs the sales manager. Once confirmed, what happens in the warehouse is the sales_order linkage's sentence.
