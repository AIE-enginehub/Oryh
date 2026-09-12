#!/usr/bin/env python3
"""Export the console's data-browser catalogue from the API contract.

The console's generic data browser renders one page per collection: its
filters are the list endpoint's query parameters, its columns the row
model's scalar fields, its sort control the same `order_by` every list
accepts. None of that is hand-written in the frontend — it is read from
`app.openapi()` here, at build time, into a small JSON the page imports.
`tests/test_frontend_contract.py` pins the committed file to the API, the
way `frontend/openapi.json` is pinned.

Deterministic, no database.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from app.main import app

PREFIX = "/api/v1"
SKIP_PARAMS = {"page", "size", "order_by"}

# Where a collection sits in the browser and what a person calls it. Paths
# not named here still appear, under "other", labelled from the path.
GROUPS: dict[str, tuple[str, str]] = {
    "master": ("主数据", "Master data"),
    "sales": ("销售", "Sales"),
    "purchasing": ("采购", "Purchasing"),
    "inventory": ("库存与发运", "Inventory & shipping"),
    "finance": ("财务", "Finance"),
    "people": ("人事", "People"),
    "crm": ("客户关系", "CRM"),
    "contracts": ("合同", "Contracts"),
    "work": ("工作与流程", "Work & flow"),
    "system": ("系统", "System"),
    "other": ("其他", "Other"),
}

RESOURCES: dict[str, tuple[str, str, str]] = {
    "/customers": ("master", "客户", "Customers"),
    "/customer-contacts": ("master", "客户联系人", "Customer contacts"),
    "/customer-products": ("master", "客户产品约定", "Customer product terms"),
    "/vendors": ("master", "供应商", "Vendors"),
    "/supplier-products": ("master", "供应商产品", "Supplier products"),
    "/products": ("master", "产品", "Products"),
    "/product-skus": ("master", "产品 SKU", "Product SKUs"),
    "/product-categories": ("master", "产品分类", "Product categories"),
    "/product-prices": ("master", "价格表", "Price book"),
    "/product-images": ("master", "产品图片", "Product images"),
    "/bills-of-materials": ("master", "物料清单", "Bills of materials"),
    "/projects": ("master", "项目", "Projects"),
    "/resources": ("master", "资源", "Resources"),
    "/stores": ("master", "门店", "Stores"),
    "/store-facilities": ("master", "门店设施", "Store facilities"),
    "/sales-channels": ("master", "销售渠道", "Sales channels"),
    "/facilities": ("master", "设施", "Facilities"),
    "/external-product-maps": ("master", "外部商品映射", "External product maps"),
    "/type-options": ("master", "类型选项", "Type options"),
    "/geos": ("master", "地理区划", "Geos"),
    "/territories": ("master", "销售区域", "Territories"),
    "/territory-geos": ("master", "区域覆盖", "Territory coverage"),
    "/territory-members": ("master", "区域成员", "Territory members"),
    "/sales-quotations": ("sales", "销售报价", "Sales quotations"),
    "/sales-orders": ("sales", "销售订单与退货", "Sales orders & returns"),
    "/campaigns": ("crm", "市场活动", "Campaigns"),
    "/campaign-members": ("crm", "活动成员", "Campaign members"),
    "/activities": ("crm", "跟进记录", "Activities"),
    "/events": ("crm", "日程", "Events"),
    "/event-participants": ("crm", "日程参与人", "Event participants"),
    "/communication-events": ("crm", "往来沟通", "Communications"),
    "/leads": ("crm", "线索", "Leads"),
    "/opportunities": ("crm", "商机", "Opportunities"),
    "/opportunity-items": ("crm", "商机产品行", "Opportunity lines"),
    "/opportunity-contacts": ("crm", "商机联系人", "Opportunity contacts"),
    "/purchase-requests": ("purchasing", "采购申请", "Purchase requests"),
    "/purchase-orders": ("purchasing", "采购订单", "Purchase orders"),
    "/inventory-items": ("inventory", "库存位置", "Inventory positions"),
    "/inventory-movements": ("inventory", "库存移动", "Inventory movements"),
    "/shipments": ("inventory", "发货单", "Shipments"),
    "/picklists": ("inventory", "拣货单", "Picklists"),
    "/invoices": ("finance", "发票与工资条", "Invoices & payslips"),
    "/payments": ("finance", "收付款", "Payments"),
    "/payment-applications": ("finance", "款项核销", "Payment applications"),
    "/billing-accounts": ("finance", "账单账户", "Billing accounts"),
    "/billing-account-entries": ("finance", "账户流水", "Billing account entries"),
    "/fin-accounts": ("finance", "资金账户", "Financial accounts"),
    "/fin-account-transactions": ("finance", "资金流水", "Account transactions"),
    "/expense-claims": ("finance", "报销单", "Expense claims"),
    "/employees": ("people", "员工", "Employees"),
    "/timesheet-headers": ("people", "工时单", "Timesheets"),
    "/employee-leaves": ("people", "请假", "Leave"),
    "/pay-histories": ("people", "薪酬记录", "Pay history"),
    "/contracts": ("contracts", "合同", "Contracts"),
    "/contract-terms": ("contracts", "合同条款", "Contract terms"),
    "/contract-documents": ("contracts", "合同文件", "Contract documents"),
    "/todos": ("work", "待办", "To-dos"),
    "/approval-records": ("work", "审批记录", "Approval records"),
    "/business-objects": ("work", "自定义对象", "Custom objects"),
    "/business-object-links": ("work", "对象关联", "Object links"),
    "/resource-bookings": ("work", "资源预订", "Resource bookings"),
    "/notifications": ("work", "通知", "Notifications"),
    "/external-document-links": ("work", "外部单号链接", "External document links"),
    "/attachments": ("work", "附件", "Attachments"),
    "/policies": ("system", "政策", "Policies"),
    "/workflow-definitions": ("system", "工作流定义", "Workflow definitions"),
    "/object-type-definitions": ("system", "对象类型定义", "Object type definitions"),
    "/audit-logs": ("system", "审计日志", "Audit log"),
    "/flow-runs": ("system", "流程代理运行", "Flow agent runs"),
    "/flow-subscriptions": ("system", "流程代理订阅", "Flow agent subscriptions"),
    "/tenant/api-keys": ("system", "API 密钥", "API keys"),
    "/roles": ("system", "角色", "Roles"),
    "/sales-quotation-items": ("sales", "报价行", "Quotation lines"),
    "/sales-quotation-adjustments": ("sales", "报价调整项", "Quotation adjustments"),
    "/sales-order-items": ("sales", "订单行", "Order lines"),
    "/sales-order-adjustments": ("sales", "订单调整项", "Order adjustments"),
    "/purchase-order-items": ("purchasing", "采购订单行", "Purchase order lines"),
    "/purchase-order-adjustments": ("purchasing", "采购订单调整项", "Purchase order adjustments"),
    "/invoice-items": ("finance", "发票行", "Invoice lines"),
    "/approval-targets": ("work", "可审批对象", "Approval targets"),
    "/bom-items": ("master", "物料清单行", "BOM items"),
    "/contract-items": ("contracts", "合同行", "Contract items"),
    "/inventory-item-details": ("inventory", "库存明细", "Inventory details"),
    "/picklist-items": ("inventory", "拣货单行", "Picklist items"),
    "/shipment-items": ("inventory", "发货单行", "Shipment items"),
}


# A record's own sub-collections: the child collection and the filter that
# names the parent. The detail drawer links "lines", "adjustments", and the
# like straight into the browser, already filtered to this record.
RELATED: dict[str, list[tuple[str, str, str, str]]] = {
    "/campaigns": [
        ("/campaign-members", "campaign_id", "成员", "Members"),
        ("/leads", "campaign_id", "线索", "Leads"),
        ("/opportunities", "campaign_id", "商机", "Opportunities"),
        ("/campaigns", "parent_campaign_id", "子活动", "Child campaigns"),
    ],
    "/leads": [
        ("/activities", "lead_id", "跟进", "Activities"),
        ("/events", "lead_id", "日程", "Events"),
        ("/communication-events", "lead_id", "沟通", "Communications"),
        ("/campaign-members", "lead_id", "活动", "Campaigns"),
        ("/opportunities", "lead_id", "商机", "Opportunities"),
    ],
    "/events": [
        ("/event-participants", "event_id", "参与人", "Participants"),
        ("/activities", "event_id", "记录", "Logged activities"),
    ],
    "/opportunities": [
        ("/activities", "opportunity_id", "跟进", "Activities"),
        ("/events", "opportunity_id", "日程", "Events"),
        ("/communication-events", "opportunity_id", "沟通", "Communications"),
        ("/opportunity-items", "opportunity_id", "产品行", "Lines"),
        ("/opportunity-contacts", "opportunity_id", "联系人", "Contacts"),
        ("/sales-quotations", "opportunity_id", "报价", "Quotations"),
        ("/sales-orders", "opportunity_id", "订单", "Orders"),
    ],
    "/sales-quotations": [
        ("/sales-quotation-items", "quotation_id", "报价行", "Lines"),
        ("/sales-quotation-adjustments", "quotation_id", "调整项", "Adjustments"),
        ("/sales-orders", "quotation_id", "成交订单", "Orders"),
    ],
    "/sales-orders": [
        ("/sales-order-items", "order_id", "订单行", "Lines"),
        ("/sales-order-adjustments", "order_id", "调整项", "Adjustments"),
        ("/invoices", "sales_order_id", "发票", "Invoices"),
        ("/shipments", "sales_order_id", "发货单", "Shipments"),
        ("/purchase-order-items", "sales_order_id", "采购链", "Procurement"),
        ("/sales-orders", "original_order_id", "退货", "Returns"),
        ("/sales-orders", "supersedes_order_id", "替代单", "Replacement"),
    ],
    "/purchase-orders": [
        ("/purchase-order-items", "po_id", "采购行", "Lines"),
        ("/purchase-order-adjustments", "po_id", "调整项", "Adjustments"),
        ("/invoices", "purchase_order_id", "发票", "Invoices"),
    ],
    "/invoices": [
        ("/invoice-items", "invoice_id", "发票行", "Lines"),
        ("/payment-applications", "invoice_id", "核销", "Applications"),
    ],
    "/payments": [("/payment-applications", "payment_id", "核销", "Applications")],
    "/territories": [
        ("/territory-geos", "territory_id", "覆盖的地理", "Coverage"),
        ("/territory-members", "territory_id", "成员", "Members"),
        ("/customers", "territory_id", "客户", "Customers"),
        ("/territories", "parent_territory_id", "子区域", "Child territories"),
    ],
    "/geos": [
        ("/geos", "parent_geo_id", "下级", "Children"),
        ("/customers", "geo_id", "客户", "Customers"),
        ("/leads", "geo_id", "线索", "Leads"),
        ("/territory-geos", "geo_id", "所属区域", "Territories"),
    ],
    "/customers": [
        ("/activities", "customer_id", "跟进", "Activities"),
        ("/events", "customer_id", "日程", "Events"),
        ("/communication-events", "customer_id", "沟通", "Communications"),
        ("/customer-contacts", "customer_id", "联系人", "Contacts"),
        ("/customer-products", "customer_id", "产品约定", "Product terms"),
        ("/sales-orders", "customer_id", "订单", "Orders"),
        ("/sales-quotations", "customer_id", "报价", "Quotations"),
        ("/invoices", "customer_id", "发票", "Invoices"),
        ("/contracts", "customer_id", "合同", "Contracts"),
    ],
    "/vendors": [
        ("/supplier-products", "vendor_id", "供应产品", "Supplied products"),
        ("/purchase-orders", "vendor_id", "采购订单", "Purchase orders"),
        ("/invoices", "vendor_id", "发票", "Invoices"),
    ],
    "/products": [
        ("/product-skus", "product_id", "SKU", "SKUs"),
        ("/product-prices", "product_id", "价格", "Prices"),
        ("/inventory-items", "product_id", "库存", "Stock"),
        ("/external-product-maps", "product_id", "外部映射", "External maps"),
        ("/supplier-products", "product_id", "供应商", "Suppliers"),
    ],
    "/employees": [
        ("/todos", "employee_id", "待办", "To-dos"),
        ("/timesheet-headers", "employee_id", "工时单", "Timesheets"),
        ("/expense-claims", "employee_id", "报销", "Expense claims"),
        ("/employee-leaves", "employee_id", "请假", "Leave"),
        ("/pay-histories", "employee_id", "薪酬", "Pay history"),
    ],
    "/contracts": [
        ("/contract-items", "contract_id", "合同行", "Lines"),
        ("/contract-terms", "contract_id", "条款", "Terms"),
        ("/contract-documents", "contract_id", "文件", "Documents"),
    ],
    "/shipments": [("/shipment-items", "shipment_id", "发货行", "Lines")],
    "/picklists": [("/picklist-items", "picklist_id", "拣货行", "Lines")],
    "/billing-accounts": [("/billing-account-entries", "billing_account_id", "流水", "Entries")],
    "/fin-accounts": [("/fin-account-transactions", "fin_account_id", "流水", "Transactions")],
    "/bills-of-materials": [("/bom-items", "bom_id", "物料行", "Components")],
}


def _deref(spec: dict, schema: dict | None) -> dict:
    while schema and "$ref" in schema:
        name = schema["$ref"].removeprefix("#/components/schemas/")
        schema = spec["components"]["schemas"].get(name, {})
    return schema or {}


def _scalar(spec: dict, schema: dict) -> dict | None:
    """type/format/enum of a schema, seeing through `anyOf: [X, null]`."""
    schema = _deref(spec, schema)
    if "anyOf" in schema:
        options = [_deref(spec, o) for o in schema["anyOf"] if _deref(spec, o).get("type") != "null"]
        if len(options) != 1:
            return None
        schema = options[0]
    kind = schema.get("type")
    if kind not in ("string", "integer", "number", "boolean"):
        return None
    out: dict = {"type": kind}
    if schema.get("format"):
        out["format"] = schema["format"]
    if schema.get("enum"):
        out["enum"] = [v for v in schema["enum"] if v is not None]
    return out


def _row_schema(spec: dict, get: dict) -> dict:
    body = get.get("responses", {}).get("200", {}).get("content", {}).get("application/json", {})
    envelope = _deref(spec, body.get("schema"))
    data = _deref(spec, envelope.get("properties", {}).get("data"))
    if data.get("type") == "array":
        return _deref(spec, data.get("items"))
    return {}


def _humanize(path: str) -> str:
    return path.strip("/").replace("/", " ").replace("-", " ").capitalize()


def _body_fields(spec: dict, operation: dict) -> list[dict] | None:
    """The scalar fields of an operation's JSON request body, in schema
    order, with `required` — the console builds its form from these. None
    when the operation takes no body; [] when the body has no scalar field
    (a verb that takes nothing an admin types)."""
    body = operation.get("requestBody")
    if not body:
        return None
    schema = _deref(spec, body.get("content", {}).get("application/json", {}).get("schema"))
    if not schema:
        return None
    required = set(schema.get("required", []))
    fields = []
    for name, sub in schema.get("properties", {}).items():
        scalar = _scalar(spec, sub)
        if scalar is None:
            continue
        raw = _deref(spec, sub)
        field = {"name": name, "required": name in required, **scalar}
        if raw.get("maxLength"):
            field["maxLength"] = raw["maxLength"]
        if raw.get("description"):
            field["description"] = raw["description"]
        fields.append(field)
    return fields


def _writes(spec: dict, short: str) -> dict:
    """What the API lets a person do to one collection: create (POST on the
    collection), update (PATCH on the record), remove (DELETE on the
    record), and the record's verbs — `POST /{collection}/{id}/<verb>`,
    exactly one segment deep, so `/products/{id}/skus/batch` is not one."""
    paths = spec["paths"]
    collection = PREFIX + short
    record = None
    for path in paths:
        if re.fullmatch(re.escape(collection) + r"/\{[^/}]+\}", path):
            record = path
            break
    out: dict = {}
    post = paths.get(collection, {}).get("post")
    if post:
        out["create"] = _body_fields(spec, post) or []
    if record:
        patch = paths[record].get("patch")
        if patch:
            out["update"] = _body_fields(spec, patch) or []
        if paths[record].get("delete"):
            out["remove"] = True
        actions = []
        for path, item in paths.items():
            match = re.fullmatch(re.escape(record) + r"/([a-z][a-z0-9-]*)", path)
            if not match or "post" not in item:
                continue
            verb = item["post"]
            actions.append({
                "verb": match.group(1),
                "path": path,
                "summary": verb.get("summary") or match.group(1).replace("-", " ").capitalize(),
                "fields": _body_fields(spec, verb) or [],
            })
        actions.sort(key=lambda a: a["verb"])
        out["actions"] = actions
        out["recordPath"] = record
    return out


def console_catalog() -> dict:
    spec = app.openapi()
    resources = []
    for path, item in spec["paths"].items():
        get = item.get("get")
        if not get or not path.startswith(PREFIX) or "{" in path:
            continue  # a per-record sub-list is the record's, not a collection
        params = get.get("parameters", [])
        names = {p["name"] for p in params}
        if "size" not in names or "order_by" not in names:
            continue
        short = path.removeprefix(PREFIX)
        group, zh, en = RESOURCES.get(short, ("other", _humanize(short), _humanize(short)))
        filters = []
        for p in params:
            if p.get("in") != "query" or p["name"] in SKIP_PARAMS:
                continue
            scalar = _scalar(spec, p.get("schema", {})) or {"type": "string"}
            filters.append({
                "name": p["name"],
                "description": p.get("description") or "",
                **scalar,
            })
        columns = []
        for name, schema in _row_schema(spec, get).get("properties", {}).items():
            scalar = _scalar(spec, schema)
            if scalar is None:
                continue
            columns.append({"name": name, **scalar})
        resources.append({
            "key": re.sub(r"[^a-z0-9]+", "-", short.strip("/").lower()),
            "path": path,
            "group": group,
            "label": [zh, en],
            "filters": filters,
            "columns": columns,
            **_writes(spec, short),
            "related": [
                {"resource": re.sub(r"[^a-z0-9]+", "-", child.strip("/").lower()), "param": param, "label": [zh_, en_]}
                for child, param, zh_, en_ in RELATED.get(short, [])
                if PREFIX + child in spec["paths"]
                and param in {p["name"] for p in spec["paths"][PREFIX + child]["get"].get("parameters", [])}
            ],
        })
    resources.sort(key=lambda r: (list(GROUPS).index(r["group"]), r["label"][1]))
    return {
        "groups": [{"key": key, "label": list(label)} for key, label in GROUPS.items()],
        "resources": resources,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", type=Path, default=Path("frontend/src/api/data-catalog.json"))
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(console_catalog(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
