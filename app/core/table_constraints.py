"""Every CHECK the shipped schema carries, declared where the models can see it.

Eighty-one exist in the shipped DDL. Before this module the models declared
twenty-two, and a constraint the model does not declare does not exist on
SQLite, which is what the test suite builds. So the suite ran against a
database materially more permissive than the one the product runs on, and
stayed green over values Postgres refuses.

They are split in two because they answer different questions. A VOCABULARY is
a closed list of values a column may hold — thirty of those, and where every
piece of drift found so far has been. An INVARIANT is any other rule the schema
enforces: non-negative money, ordered dates, "a rate needs a basis". Fifty-one
of those, and declaring them turned up nothing, which is itself worth knowing.

That is not hypothetical. `todos.status` allowed `cancelled` in
`schemas.TodoStatus`, `cancel_todos_for` wrote it, and the baseline migration's
CHECK never listed it. Cancelling a todo was a 500 for the life of the product,
and because deleting a document cancels its todos in the same transaction,
**deleting any document with an open todo was a 500 too** — in production, with
879 tests passing over it.

Declaring them here rather than on each class is deliberate:

- one place to read the answer to "what may this column hold", instead of
  hunting through eighteen model classes and a DDL dump;
- `tests/test_table_constraints.py` compares this registry against
  `sql/schema.sql` in both directions, so a constraint added to the database
  without being added here fails the build, and vice versa;
- the same tuples can back the API's `Literal`s, which is the other half of the
  drift: three copies of the todo status list existed and one disagreed.

**Not everything with quoted values belongs here.** Five CHECKs in the schema
are conditional rules that happen to mention literals —
`invoices_direction_counterparty_ck`, `policies_published_attribution_ck` and
friends. A rule like "a restricted policy must name a capability" is logic, not
a vocabulary, and flattening it into a value list would lose it.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, MetaData

# (table, column) -> the values that column may hold.
#
# Sorted as the DDL sorts them so a diff against `sql/schema.sql` reads
# cleanly. The list is the constraint; the order is not.
COLUMN_VOCABULARIES: dict[tuple[str, str], tuple[str, ...]] = {
    ("approval_records", "action"): (
        "approved", "commented", "rejected", "returned", "submitted",
    ),
    ("approval_records", "entity_type"): (
        "approval_target", "business_object", "employee_leave", "expense_claim",
        "invoice", "payment", "purchase_order", "purchase_request", "sales_order",
        "sales_quotation", "timesheet_header",
    ),
    ("billing_accounts", "unit_type"): ("currency", "points"),
    ("capabilities", "kind"): ("custom", "system"),
    ("customers", "status"): ("active", "archived"),
    ("device_authorizations", "status"): ("approved", "consumed", "denied", "pending"),
    ("employees", "status"): ("active", "inactive"),
    ("enterprise_pilot_applications", "status"): (
        "accepted", "contacted", "rejected", "submitted",
    ),
    ("object_type_definitions", "entity_kind"): ("builtin", "business_object"),
    ("object_type_definitions", "status"): ("active", "archived"),
    ("pending_registrations", "status"): (
        "approved", "pending_email", "pending_review", "rejected",
    ),
    ("platform_admins", "status"): ("active", "disabled"),
    ("policies", "status"): ("draft", "published", "repealed", "superseded"),
    ("policies", "visibility"): ("internal", "public", "restricted"),
    ("product_skus", "status"): ("active", "archived"),
    ("products", "status"): ("active", "archived"),
    ("projects", "status"): ("active", "archived"),
    ("resource_bookings", "status"): ("cancelled", "confirmed"),
    ("resources", "booking_mode"): ("exclusive", "shared"),
    ("resources", "status"): ("active", "archived", "inactive"),
    ("tenant_skills", "kind"): ("custom", "product"),
    ("tenant_skills", "status"): ("active", "archived"),
    ("tenants", "status"): ("active", "inactive"),
    # `timesheet_entries.work_type` is deliberately absent. It is a
    # tenant-extensible vocabulary — `TYPE_FAMILIES` carries it, a workspace
    # defines its own values through `POST /type-options`, and the write path
    # validates against the tenant's active options. The database also carried
    # a fixed five-value CHECK, left over from before type options existed, so
    # defining a custom work type returned 201 and using it returned 500.
    # `20260813_0054` drops it; `tests/test_table_constraints.py` keeps any
    # extensible family from acquiring one again.
    ("todos", "entity_type"): (
        "approval_target", "business_object", "employee_leave", "expense_claim",
        "invoice", "payment", "project", "purchase_order", "purchase_request",
        "sales_order", "sales_quotation", "timesheet_header",
    ),
    ("todos", "status"): ("cancelled", "completed", "open"),
    ("users", "status"): ("active", "disabled", "invited"),
    ("vendors", "status"): ("active", "archived"),
    ("workflow_definitions", "entity_kind"): ("builtin", "business_object"),
    ("workflow_definitions", "status"): ("active", "superseded"),
}

# Three constraints predate the `_chk` convention and are named `_ck` in the
# database. The name is what a Postgres error message prints, so it is matched
# rather than corrected — renaming a live constraint buys nothing and costs a
# migration on every environment.
CONSTRAINT_NAME_OVERRIDES: dict[tuple[str, str], str] = {
    ("billing_accounts", "unit_type"): "billing_accounts_unit_type_ck",
    ("policies", "status"): "policies_status_ck",
    ("policies", "visibility"): "policies_visibility_ck",
}


def constraint_name(table: str, column: str) -> str:
    return CONSTRAINT_NAME_OVERRIDES.get((table, column), f"{table}_{column}_chk")


def check_expression(table: str, column: str) -> str:
    values = ", ".join(f"'{value}'" for value in COLUMN_VOCABULARIES[(table, column)])
    return f"{column} in ({values})"


# Everything else the schema enforces: non-negative money, ordered date
# ranges, "a rate needs a basis", "a published policy names its publisher".
# Not vocabularies, so they carry an expression rather than a value list — but
# invisible to SQLite for exactly the same reason, which is what matters here.
#
# The text is the shipped DDL's, with Postgres casts stripped so both dialects
# accept it. `tests/test_table_constraints.py` checks the set against
# `sql/schema.sql`; it deliberately does not compare expression text, because
# `(0)::numeric` and `0` mean the same thing and pinning the spelling would
# turn every dump-format change into a failure.
TABLE_INVARIANTS: dict[str, tuple[str, str]] = {
    "approval_records_round_no_chk": ("approval_records", "round_no >= 1"),
    "approval_records_sequence_no_chk": ("approval_records", "sequence_no >= 1"),
    "approval_records_source_chk": ("approval_records", "(source in ('web', 'api', 'ai', 'system')) OR (source IS NULL)"),
    "attachments_size_chk": ("attachments", "size_bytes >= 0"),
    "billing_accounts_credit_limit_ck": ("billing_accounts", "credit_limit >= 0"),
    "business_object_links_distinct_objects_chk": ("business_object_links", "source_object_id <> target_object_id"),
    "customers_kind_ck": ("customers", "(customer_kind IS NULL) OR (customer_kind in ('person', 'company'))"),
    "employee_leaves_duration_ck": ("employee_leaves", "duration_days > 0"),
    "employee_leaves_period_ck": ("employee_leaves", "thru_date >= from_date"),
    "enterprise_pilot_applications_weekly_users_chk": ("enterprise_pilot_applications", "(weekly_active_agent_users IS NULL) OR ((weekly_active_agent_users >= 0) AND (weekly_active_agent_users <= 1000000))"),
    "expense_items_amount_chk": ("expense_items", "amount > 0"),
    "expense_items_tax_amount_chk": ("expense_items", "(tax_amount IS NULL) OR (tax_amount >= 0)"),
    "invoices_direction_counterparty_ck": ("invoices", "((direction = 'sales') AND (customer_id IS NOT NULL) AND (vendor_id IS NULL) AND (payee_employee_id IS NULL)) OR ((direction = 'purchase') AND (vendor_id IS NOT NULL) AND (customer_id IS NULL) AND (payee_employee_id IS NULL)) OR ((direction = 'payroll') AND (payee_employee_id IS NOT NULL) AND (customer_id IS NULL) AND (vendor_id IS NULL)) OR ((direction = 'reimbursement') AND (payee_employee_id IS NOT NULL) AND (customer_id IS NULL) AND (vendor_id IS NULL))"),
    "object_type_definitions_version_chk": ("object_type_definitions", "version >= 1"),
    "pay_histories_amount_ck": ("pay_histories", "(amount IS NULL) OR (amount >= 0)"),
    "pay_histories_period_ck": ("pay_histories", "(effective_thru IS NULL) OR (effective_thru >= effective_from)"),
    "pay_histories_rate_basis_ck": ("pay_histories", "(rate IS NULL) OR (basis IS NOT NULL)"),
    "pay_histories_rate_ck": ("pay_histories", "(rate IS NULL) OR (rate >= 0)"),
    "pay_histories_states_something_ck": ("pay_histories", "(amount IS NOT NULL) OR (rate IS NOT NULL) OR (formula IS NOT NULL)"),
    "payment_applications_item_needs_invoice_ck": ("payment_applications", "(invoice_item_id IS NULL) OR (invoice_id IS NOT NULL)"),
    "payments_amount_positive_ck": ("payments", "amount > 0"),
    "policies_effective_period_ck": ("policies", "(effective_thru IS NULL) OR (effective_from IS NULL) OR (effective_thru >= effective_from)"),
    "policies_published_attribution_ck": ("policies", "(status <> 'published') OR ((published_at IS NOT NULL) AND (published_by IS NOT NULL))"),
    "policies_restricted_needs_capability_ck": ("policies", "(visibility <> 'restricted') OR (required_capability IS NOT NULL)"),
    "product_skus_list_price_chk": ("product_skus", "(list_price IS NULL) OR (list_price >= 0)"),
    "products_list_price_chk": ("products", "(list_price IS NULL) OR (list_price >= 0)"),
    "projects_date_chk": ("projects", "(end_date IS NULL) OR (start_date IS NULL) OR (end_date >= start_date)"),
    "purchase_request_items_amount_chk": ("purchase_request_items", "(amount IS NULL) OR (amount >= 0)"),
    "purchase_request_items_quantity_chk": ("purchase_request_items", "quantity > 0"),
    "purchase_request_items_unit_price_chk": ("purchase_request_items", "(unit_price IS NULL) OR (unit_price >= 0)"),
    "resource_bookings_period_chk": ("resource_bookings", "end_at > start_at"),
    "resource_bookings_quantity_chk": ("resource_bookings", "quantity >= 1"),
    "resources_capacity_chk": ("resources", "(capacity IS NULL) OR (capacity >= 1)"),
    "resources_max_quantity_chk": ("resources", "(max_quantity IS NULL) OR (max_quantity >= 1)"),
    "sales_order_items_amount_chk": ("sales_order_items", "(amount IS NULL) OR (amount >= 0)"),
    "sales_order_items_list_price_chk": ("sales_order_items", "(list_price_snapshot IS NULL) OR (list_price_snapshot >= 0)"),
    "sales_order_items_quantity_chk": ("sales_order_items", "quantity > 0"),
    "sales_order_items_tax_rate_chk": ("sales_order_items", "(tax_rate IS NULL) OR ((tax_rate >= 0) AND (tax_rate <= 100))"),
    "sales_order_items_unit_price_chk": ("sales_order_items", "(unit_price IS NULL) OR (unit_price >= 0)"),
    "sales_orders_total_amount_chk": ("sales_orders", "(total_amount IS NULL) OR (total_amount >= 0)"),
    "sales_quotation_items_amount_chk": ("sales_quotation_items", "(amount IS NULL) OR (amount >= 0)"),
    "sales_quotation_items_list_price_chk": ("sales_quotation_items", "(list_price_snapshot IS NULL) OR (list_price_snapshot >= 0)"),
    "sales_quotation_items_quantity_chk": ("sales_quotation_items", "quantity > 0"),
    "sales_quotation_items_tax_rate_chk": ("sales_quotation_items", "(tax_rate IS NULL) OR ((tax_rate >= 0) AND (tax_rate <= 100))"),
    "sales_quotation_items_unit_price_chk": ("sales_quotation_items", "(unit_price IS NULL) OR (unit_price >= 0)"),
    "sales_quotations_revision_no_chk": ("sales_quotations", "revision_no >= 1"),
    "sales_quotations_total_amount_chk": ("sales_quotations", "(total_amount IS NULL) OR (total_amount >= 0)"),
    "tenant_skills_version_chk": ("tenant_skills", "version >= 1"),
    "timesheet_entries_hours_chk": ("timesheet_entries", "(hours > 0) AND (hours <= 24)"),
    "timesheet_headers_period_chk": ("timesheet_headers", "period_end >= period_start"),
    "workflow_definitions_version_chk": ("workflow_definitions", "version >= 1"),
}


def apply_table_constraints(metadata: MetaData) -> int:
    """Attach the registered CHECKs to whichever of these tables `metadata` has.

    Called once per model module, and tolerant of tables it does not own — the
    platform tables live in a separate module and the standalone edition does
    not carry them at all.

    A constraint already declared on the class is left alone, so this can be
    adopted table by table rather than in one sweep. Where both exist the
    class's wins, which is why `tests/test_table_constraints.py` also checks
    that no table declares one of these by hand.
    """
    wanted: list[tuple[str, str, str]] = [
        (table_name, constraint_name(table_name, column), check_expression(table_name, column))
        for (table_name, column) in COLUMN_VOCABULARIES
    ]
    wanted += [
        (table_name, name, expression)
        for name, (table_name, expression) in TABLE_INVARIANTS.items()
    ]

    attached = 0
    for table_name, name, expression in wanted:
        table = metadata.tables.get(table_name)
        if table is None:
            continue
        if any(getattr(existing, "name", None) == name for existing in table.constraints):
            continue
        table.append_constraint(CheckConstraint(expression, name=name))
        attached += 1
    return attached
