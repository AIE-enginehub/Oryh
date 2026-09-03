"""Whole-database integrity audit: cross-table tenant consistency, workflow
invariants, and payload conformance against active object type definitions.

Usage:
    python scripts/data_integrity_audit.py

Runs with the owning connection (ORYH_MIGRATION_DATABASE_URL or
ORYH_DATABASE_URL), which is exempt from RLS, so it audits every tenant.
Exits non-zero if any check fails. Safe to run against a live database:
read-only.
"""

from __future__ import annotations

import os
import sys
from typing import get_args

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jsonschema import Draft202012Validator
from jsonschema.validators import validator_for
from sqlalchemy import text

from app.core.config import settings
from app.core.type_options import TYPE_OPTION_SIGNS
from app.schemas import InventoryMovementReason
from app.db.session import create_ops_sessionmaker

failures: list[str] = []


def movement_reasons() -> str:
    """The API's own movement vocabulary as a SQL list.

    Derived from `InventoryMovementReason`, not restated beside it, for the
    reason `shipped_signs` gives below: a hand-copied list is wrong the first
    time somebody adds a value. It was — the reservations work added `reserved`
    and `reservation_released`, this check kept its old ten, and a correct
    ledger was reported as a violation on v2026.9.1. A check named "in the
    API's vocabulary" has to ask the API.
    """
    values = get_args(InventoryMovementReason)
    assert values, "InventoryMovementReason resolved to no values"
    return ", ".join(f"'{value}'" for value in values)


def shipped_signs(family: str) -> str:
    """The shipped catalog as an inline table, so a sign check works for a
    tenant that never customized the family.

    This is not decoration: a tenant with no rows for a family has not
    customized it, and the shipped catalog applies verbatim — which means a
    check that only joined `type_options` would match nothing at all for those
    tenants and report a clean database forever. Generated from the catalog
    rather than restated, because a hand-copied sign table would be wrong the
    first time somebody added a deduction type.

    `union all` rather than `values (...) as t(a, b)`: the column-alias form is
    Postgres-only, and these checks are run verbatim by the test suite against
    SQLite.
    """
    rows = TYPE_OPTION_SIGNS[family]
    return " union all ".join(
        f"select '{name}' as name, {sign} as sign" if index == 0
        else f"select '{name}', {sign}"
        for index, (name, sign) in enumerate(rows.items())
    )


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'ok' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(f"{name}: {detail}")


STRUCTURAL_CHECKS: tuple[tuple[str, str], ...] = (
    (
        "timesheet_entries tenant matches header",
        "select count(*) from timesheet_entries e join timesheet_headers h on e.header_id=h.id where e.tenant_id<>h.tenant_id",
    ),
    (
        "timesheet_entries employee matches header employee",
        "select count(*) from timesheet_entries e join timesheet_headers h on e.header_id=h.id where e.employee_id<>h.employee_id",
    ),
    (
        "timesheet_headers employee in same tenant",
        "select count(*) from timesheet_headers h join employees emp on h.employee_id=emp.id where h.tenant_id<>emp.tenant_id",
    ),
    (
        "entry work_date inside header period",
        "select count(*) from timesheet_entries e join timesheet_headers h on e.header_id=h.id where e.work_date<h.period_start or e.work_date>h.period_end",
    ),
    # Seeded documents must be filed by someone the tenant's RBAC would let
    # file them. The seeder writes straight to the database and so bypasses
    # every permission check the API enforces — without this, the demo can
    # show work that the product itself forbids, and only an agent holding a
    # real user key ever finds out.
    (
        "purchase requests filed by someone whose role may file them",
        """select count(*) from purchase_requests pr
             join employees e on e.id = pr.employee_id
             join users u on u.employee_id = e.id
             join roles r on r.tenant_id = pr.tenant_id and r.name = u.role
            where not (r.permissions_jsonb::jsonb ? 'purchase.submit_own')""",
    ),
    (
        "sales quotations filed by someone whose role may file them",
        """select count(*) from sales_quotations q
             join employees e on e.id = q.employee_id
             join users u on u.employee_id = e.id
             join roles r on r.tenant_id = q.tenant_id and r.name = u.role
            where not (r.permissions_jsonb::jsonb ? 'quotation.submit_own')""",
    ),
    (
        "purchase orders placed by someone whose role may place them",
        """select count(*) from purchase_orders po
             join employees e on e.id = po.employee_id
             join users u on u.employee_id = e.id
             join roles r on r.tenant_id = po.tenant_id and r.name = u.role
            where not (r.permissions_jsonb::jsonb ? 'purchase_order.manage')""",
    ),
    (
        "approval facts written by someone whose role may write them",
        """select count(*) from approval_records ar
             join users u on ('user:' || u.id::text) = ar.approver_id
             join roles r on r.tenant_id = ar.tenant_id and r.name = u.role
            where ar.action in ('approved','rejected','returned')
              and not (r.permissions_jsonb::jsonb ? 'approval.record')""",
    ),
    (
        "business_object_links tenant matches source object",
        "select count(*) from business_object_links l join business_objects s on l.source_object_id=s.id where l.tenant_id<>s.tenant_id",
    ),
    (
        "business_object_links tenant matches target object",
        "select count(*) from business_object_links l join business_objects t on l.target_object_id=t.id where l.tenant_id<>t.tenant_id",
    ),
    (
        "todos employee in same tenant",
        "select count(*) from todos td join employees emp on td.employee_id=emp.id where td.tenant_id<>emp.tenant_id",
    ),
    (
        "todos business_object entity exists in tenant",
        "select count(*) from todos td where td.entity_type='business_object' and not exists (select 1 from business_objects b where b.id=td.entity_id and b.tenant_id=td.tenant_id)",
    ),
    (
        "todos timesheet entity exists in tenant",
        "select count(*) from todos td where td.entity_type='timesheet_header' and not exists (select 1 from timesheet_headers h where h.id=td.entity_id and h.tenant_id=td.tenant_id)",
    ),
    (
        "approval_records business_object entity exists in tenant",
        "select count(*) from approval_records a where a.entity_type='business_object' and not exists (select 1 from business_objects b where b.id=a.entity_id and b.tenant_id=a.tenant_id)",
    ),
    (
        "approval_records timesheet entity exists in tenant",
        "select count(*) from approval_records a where a.entity_type='timesheet_header' and not exists (select 1 from timesheet_headers h where h.id=a.entity_id and h.tenant_id=a.tenant_id)",
    ),
    (
        "bookings resource in same tenant",
        "select count(*) from resource_bookings rb join resources r on rb.resource_id=r.id where rb.tenant_id<>r.tenant_id",
    ),
    (
        "bookings employee in same tenant",
        "select count(*) from resource_bookings rb join employees emp on rb.booked_by_employee_id=emp.id where rb.tenant_id<>emp.tenant_id",
    ),
    (
        "users employee link in same tenant",
        "select count(*) from users u join employees emp on u.employee_id=emp.id where u.tenant_id<>emp.tenant_id",
    ),
    (
        "api_keys user link in same tenant",
        "select count(*) from api_keys k join users u on k.user_id=u.id where k.tenant_id<>u.tenant_id",
    ),
    (
        "no orphan tenant references (users)",
        "select count(*) from users u where not exists (select 1 from tenants t where t.id=u.tenant_id)",
    ),
    (
        "no orphan tenant references (api_keys)",
        "select count(*) from api_keys k where not exists (select 1 from tenants t where t.id=k.tenant_id)",
    ),
    (
        "completed todos carry completed_at and completed_by",
        "select count(*) from todos where status='completed' and (completed_at is null or completed_by is null)",
    ),
    (
        "open todos carry no completion fields",
        "select count(*) from todos where status='open' and (completed_at is not null or completed_by is not null)",
    ),
    (
        "decided approvals preceded by a submitted record",
        "select count(*) from approval_records d where d.action in ('approved','rejected','returned') and not exists (select 1 from approval_records s where s.entity_id=d.entity_id and s.tenant_id=d.tenant_id and s.action='submitted' and s.sequence_no<d.sequence_no)",
    ),
    (
        "non-draft timesheets have submitted_at",
        "select count(*) from timesheet_headers where status in ('submitted','approved','returned') and submitted_at is null and deleted_at is null",
    ),
    (
        "exclusive resources have no overlapping confirmed bookings",
        """select count(*) from resource_bookings a
           join resource_bookings b on a.resource_id=b.resource_id and a.id<b.id
             and a.status='confirmed' and b.status='confirmed'
             and a.start_at<b.end_at and b.start_at<a.end_at
           join resources r on r.id=a.resource_id where r.booking_mode='exclusive'""",
    ),
    (
        "tenant skills contain SKILL.md",
        "select count(*) from tenant_skills where not (files_jsonb ? 'SKILL.md')",
    ),
    # An inventory item's totals are DERIVED — the item row is a running sum of
    # its append-only detail ledger. That makes `sum(details) = item total` an
    # identity, not a nice-to-have, so it can simply be asserted. It is worth
    # asserting because the way it breaks is silent: a lost update leaves both
    # ledger rows in place and only the total short, with no error anywhere.
    # The seeder writes movements straight to the database, so a reason it
    # invents is never checked against the vocabulary the API shares between
    # its request and response models. `scrapped` got in that way, and the
    # consequence was not a bad label: LISTING the ledger 500s, because the
    # response model rejects a value the row already holds.
    (
        "inventory movement reasons are in the API's vocabulary",
        f"""select count(*) from inventory_item_details
            where reason not in ({movement_reasons()})""",
    ),
    (
        "inventory item totals equal the sum of their ledger",
        """select count(*) from (
             select i.id
               from inventory_items i
               left join inventory_item_details d on d.inventory_item_id = i.id
              group by i.id, i.quantity_on_hand, i.available_to_promise
             having i.quantity_on_hand <> coalesce(sum(d.quantity_on_hand_diff), 0)
                 or i.available_to_promise <> coalesce(sum(d.available_to_promise_diff), 0)
           ) as drifted""",
    ),
    # The settlement ledger is the inventory ledger's twin: applied_amount on a
    # payment and on every document it settles is a running sum of
    # payment_applications. Same identity, same silent failure mode — a lost
    # update leaves the ledger intact and only the total wrong, which nothing
    # else would ever surface.
    (
        "invoice tenant matches its counterparty and employee",
        """select count(*) from invoices i
             join employees e on i.employee_id = e.id
             left join customers c on i.customer_id = c.id
             left join vendors v on i.vendor_id = v.id
            where i.tenant_id <> e.tenant_id
               or (c.id is not null and i.tenant_id <> c.tenant_id)
               or (v.id is not null and i.tenant_id <> v.tenant_id)""",
    ),
    (
        "invoice_items tenant matches invoice",
        "select count(*) from invoice_items it join invoices i on it.invoice_id=i.id where it.tenant_id<>i.tenant_id",
    ),
    (
        # Three-way since payroll: a payslip's counterparty is neither a
        # customer nor a vendor but the employee it pays. The closed-set clause
        # at the end is what makes this check worth running, and it is also what
        # made it wrong the moment a third direction existed — every payslip was
        # reported as a violation. Keep it in step with the CHECK constraint on
        # `invoices`.
        "invoice direction agrees with its counterparty",
        """select count(*) from invoices
            where (direction = 'sales'
                   and (customer_id is null or vendor_id is not null
                        or payee_employee_id is not null))
               or (direction = 'purchase'
                   and (vendor_id is null or customer_id is not null
                        or payee_employee_id is not null))
               or (direction = 'payroll'
                   and (payee_employee_id is null or customer_id is not null
                        or vendor_id is not null))
               or direction not in ('sales', 'purchase', 'payroll')""",
    ),
    (
        "payment names exactly one counterparty",
        """select count(*) from payments
            where (case when customer_id is null then 0 else 1 end)
                + (case when vendor_id is null then 0 else 1 end)
                + (case when payee_employee_id is null then 0 else 1 end) <> 1""",
    ),
    (
        "payment_applications tenant matches payment",
        """select count(*) from payment_applications pa
             join payments p on pa.payment_id = p.id
            where pa.tenant_id <> p.tenant_id""",
    ),
    # A payment's applied_amount counts BOTH sides of the ledger: what it paid
    # out (rows where it is the source) and what was netted against it (rows
    # where a refund names it as to_payment_id). Counting only the source side
    # would have made every netted receipt look drifted.
    (
        "payment applied_amount equals the sum of its applications",
        """select count(*) from payments p
            where p.applied_amount <> (
              coalesce((select sum(amount_applied) from payment_applications
                         where payment_id = p.id), 0)
              + coalesce((select sum(amount_applied) from payment_applications
                           where to_payment_id = p.id), 0)
            )""",
    ),
    (
        "invoice applied_amount equals the sum of its applications",
        """select count(*) from (
             select i.id
               from invoices i
               left join payment_applications pa on pa.invoice_id = i.id
              group by i.id, i.applied_amount
             having i.applied_amount <> coalesce(sum(pa.amount_applied), 0)
           ) as drifted""",
    ),
    (
        "expense claim applied_amount equals the sum of its applications",
        """select count(*) from (
             select c.id
               from expense_claims c
               left join payment_applications pa on pa.expense_claim_id = c.id
              group by c.id, c.applied_amount
             having c.applied_amount <> coalesce(sum(pa.amount_applied), 0)
           ) as drifted""",
    ),
    (
        "nothing is applied beyond what a payment holds",
        "select count(*) from payments where applied_amount < -0.005 or applied_amount > amount + 0.005",
    ),
    (
        "no invoice is settled beyond what it bills",
        """select count(*) from (
             select i.id,
                    i.applied_amount,
                    coalesce(i.total_amount, (
                      select coalesce(sum(it.amount), 0) from invoice_items it
                       where it.invoice_id = i.id and it.deleted_at is null
                    )) as billed
               from invoices i
           ) as settled
            where applied_amount < -0.005 or applied_amount > billed + 0.005""",
    ),
    # Existence is now a foreign key's job, so what is left to check is the
    # part a FK cannot express: direction, currency, and that the document has
    # not since been soft-deleted out from under the money.
    (
        "applications settle a live document of the right direction and currency",
        """select count(*) from payment_applications pa
             join payments p on pa.payment_id = p.id
             left join invoices i on pa.invoice_id = i.id
             left join expense_claims c on pa.expense_claim_id = c.id
             left join payments n on pa.to_payment_id = n.id
            where (pa.invoice_id is not null
                   and (i.deleted_at is not null
                        or (i.direction = 'sales' and p.direction <> 'inbound')
                        or (i.direction = 'purchase' and p.direction <> 'outbound')
                        or i.currency <> p.currency))
               or (pa.expense_claim_id is not null
                   and (c.deleted_at is not null or p.direction <> 'outbound'))
               or (pa.to_payment_id is not null
                   and (n.deleted_at is not null
                        or n.direction = p.direction
                        or n.currency <> p.currency))""",
    ),
    (
        "an invoice line application names a line of that same invoice",
        """select count(*) from payment_applications pa
             join invoice_items it on pa.invoice_item_id = it.id
            where it.invoice_id <> pa.invoice_id""",
    ),
    # A billing account's balance is a running sum of its entries — the third
    # instance of the same identity (stock, settlement, accounts), and it breaks
    # the same silent way.
    (
        "billing account balance equals the sum of its entries",
        """select count(*) from (
             select a.id
               from billing_accounts a
               left join billing_account_entries e on e.billing_account_id = a.id
              group by a.id, a.balance
             having a.balance <> coalesce(sum(e.amount), 0)
           ) as drifted""",
    ),
    (
        "no billing account is drawn past its credit limit",
        "select count(*) from billing_accounts where balance < -credit_limit - 0.005",
    ),
    (
        "billing account names exactly one owner",
        """select count(*) from billing_accounts
            where (case when customer_id is null then 0 else 1 end)
                + (case when vendor_id is null then 0 else 1 end)
                + (case when employee_id is null then 0 else 1 end) <> 1""",
    ),
    (
        "billing account tenant matches its owner",
        """select count(*) from billing_accounts a
             left join customers c on a.customer_id = c.id
             left join vendors v on a.vendor_id = v.id
             left join employees e on a.employee_id = e.id
            where (c.id is not null and a.tenant_id <> c.tenant_id)
               or (v.id is not null and a.tenant_id <> v.tenant_id)
               or (e.id is not null and a.tenant_id <> e.tenant_id)""",
    ),
    (
        "billing_account_entries tenant matches its account",
        """select count(*) from billing_account_entries e
             join billing_accounts a on e.billing_account_id = a.id
            where e.tenant_id <> a.tenant_id""",
    ),
    # `length` rather than `char_length` so this runs on SQLite too — the
    # settlement test executes these very statements against a test database.
    # Nothing is asserted about a POINTS unit's shape: a tenant may legitimately
    # call one "AIR", so a "looks like a currency code" heuristic would only
    # produce false alarms.
    (
        "a currency account counts an actual currency",
        """select count(*) from billing_accounts
            where unit_type not in ('currency', 'points')
               or (unit_type = 'currency' and length(unit) <> 3)""",
    ),
    (
        "no entry belongs to a soft-deleted account",
        """select count(*) from billing_account_entries e
             join billing_accounts a on e.billing_account_id = a.id
            where a.deleted_at is not null""",
    ),
    # Money reaching a points balance is the failure this whole discriminator
    # exists to prevent, so it is asserted rather than assumed.
    (
        "payments settle only currency accounts, in the account's own currency",
        """select count(*) from payment_applications pa
             join payments p on pa.payment_id = p.id
             join billing_accounts a on pa.billing_account_id = a.id
            where a.unit_type <> 'currency' or a.unit <> p.currency""",
    ),
    (
        "every settlement into an account has a matching ledger entry",
        """select count(*) from payment_applications pa
             join payments p on pa.payment_id = p.id
            where pa.billing_account_id is not null
              and not exists (
                select 1 from billing_account_entries e
                 where e.billing_account_id = pa.billing_account_id
                   and e.entity_type = 'payment'
                   and e.entity_id = pa.payment_id
              )""",
    ),
    # ---- payroll ----------------------------------------------------------
    # Paying somebody twice is the most expensive mistake on this path and the
    # least likely to be noticed, so it is asserted three ways: no two terms of
    # the same component in force at once, no two payslips for the same person
    # and period, and a net that is exactly the lines.
    (
        "no employee has two of the same pay term in force at once",
        """select count(*) from pay_histories a
             join pay_histories b
               on b.tenant_id = a.tenant_id
              and b.employee_id = a.employee_id
              and b.component = a.component
              and b.id <> a.id
            where a.effective_from <= coalesce(b.effective_thru, '9999-12-31')
              and b.effective_from <= coalesce(a.effective_thru, '9999-12-31')""",
    ),
    (
        "every pay term states an amount, a rate with its basis, or a formula",
        """select count(*) from pay_histories
            where (amount is null and rate is null and formula is null)
               or (rate is not null and basis is null)""",
    ),
    (
        "no pay term ends before it starts",
        "select count(*) from pay_histories where effective_thru < effective_from",
    ),
    (
        "one payslip per person per period",
        """select count(*) from (
             select tenant_id, payee_employee_id, period_start
               from invoices
              where direction = 'payroll' and deleted_at is null
              group by 1, 2, 3 having count(*) > 1
           ) as duplicated""",
    ),
    (
        "a payslip names the person it pays and the period it covers",
        """select count(*) from invoices
            where direction = 'payroll' and deleted_at is null
              and (payee_employee_id is null or period_start is null or period_end is null
                   or period_end < period_start)""",
    ),
    # A payslip's net IS its lines. A declared total would be a second opinion
    # about what someone earns, and the only thing a second opinion can be here
    # is wrong.
    (
        "a payslip declares no total of its own",
        """select count(*) from invoices
            where direction = 'payroll' and deleted_at is null and total_amount is not null""",
    ),
    (
        "a payslip has lines",
        """select count(*) from invoices i
            where i.direction = 'payroll' and i.deleted_at is null
              and not exists (select 1 from invoice_items it
                               where it.invoice_id = i.id and it.deleted_at is null)""",
    ),
    # The sign check the write path enforces, restated over the whole table:
    # 个税 recorded as +2000 rather than −2000 hands somebody 4000 they are not
    # owed, and nothing downstream would object.
    (
        "every payslip line moves the way its type says it does",
        f"""select count(*) from invoice_items it
             join invoices i on it.invoice_id = i.id
             left join type_options t
               on t.tenant_id = i.tenant_id
              and t.family = 'payroll_item_type'
              and t.name = it.invoice_item_type
             left join ({shipped_signs('payroll_item_type')}) as shipped
               on shipped.name = it.invoice_item_type
            where i.direction = 'payroll' and it.deleted_at is null
              and sign(it.amount) <> 0
              and coalesce(t.sign, shipped.sign) is not null
              and sign(it.amount) <> coalesce(t.sign, shipped.sign)""",
    ),
    # The rates behind these numbers are deliberately not stored anywhere in
    # this database, so the line is the only surviving record of the
    # arithmetic. One that shows no working is a figure nobody can check.
    (
        "every payslip line shows its working",
        """select count(*) from invoice_items it
             join invoices i on it.invoice_id = i.id
            where i.direction = 'payroll' and it.deleted_at is null
              and it.pay_history_id is null
              and coalesce(trim(it.notes), '') = ''""",
    ),
    (
        "a salary line cites only that person's own pay record",
        """select count(*) from invoice_items it
             join invoices i on it.invoice_id = i.id
             join pay_histories ph on it.pay_history_id = ph.id
            where ph.employee_id <> i.payee_employee_id""",
    ),
    (
        "nobody is paid a negative net",
        """select count(*) from (
             select i.id, sum(it.amount) as net
               from invoices i join invoice_items it on it.invoice_id = i.id
              where i.direction = 'payroll' and i.deleted_at is null and it.deleted_at is null
              group by i.id
           ) as slips where net < 0""",
    ),
    # ---- 规章制度 ---------------------------------------------------------
    # A figure an agent applies has to be traceable to a document, a version and
    # a person. These check that the trace has no broken link in it. There is no
    # separate rule table to check — the figures ride `policies.rules_json`,
    # which the server never parses and therefore cannot meaningfully audit
    # beyond the document carrying it.
    (
        "one published version per 制度编号",
        """select count(*) from (
             select tenant_id, code from policies
              where status = 'published' and deleted_at is null
              group by 1, 2 having count(*) > 1
           ) as duplicated""",
    ),
    (
        "a published policy names who published it and when",
        """select count(*) from policies
            where status = 'published'
              and (published_at is null or published_by is null)""",
    ),
    (
        "a restricted policy names the capability that may read it",
        """select count(*) from policies
            where visibility = 'restricted' and coalesce(trim(required_capability), '') = ''""",
    ),
    (
        "no policy stops applying before it starts",
        "select count(*) from policies where effective_thru < effective_from",
    ),
    # Only the newest version of a code may be repealed, and this checks the
    # cause rather than the symptom.
    #
    # Repealing a SUPERSEDED version moves an `effective_thru` that the handover
    # already set, which punches a hole: publish v2 from 2027-07-01 (closing v1
    # at 2027-06-30), repeal v1 as of 2026-12-31, and the first half of 2027 is
    # governed by neither. The gap itself cannot be checked portably — it needs
    # date arithmetic, and SQLite reads `'2026-06-30' + 1` as numeric addition —
    # so this asserts the rule the write path enforces instead, which is both
    # exact and dialect-free.
    (
        "only the newest version of a policy is ever repealed",
        """select count(*) from policies a
             join policies b
               on b.tenant_id = a.tenant_id and b.code = a.code
              and b.version > a.version and b.deleted_at is null
            where a.status = 'repealed' and a.deleted_at is null""",
    ),
    (
        "a version chain points backwards, never at itself",
        """select count(*) from policies p
            left join policies prior on prior.id = p.supersedes_id
           where p.supersedes_id is not null
             and (p.supersedes_id = p.id
                  or prior.id is null
                  or prior.tenant_id <> p.tenant_id
                  or prior.code <> p.code
                  or prior.version >= p.version)""",
    ),
    (
        "a soft-deleted payment carries no applications",
        """select count(*) from payments p
            where p.deleted_at is not null
              and exists (select 1 from payment_applications pa
                           where pa.payment_id = p.id and pa.amount_applied <> 0)
              and p.applied_amount <> 0""",
    ),
    # Charging (billing_account_id on orders/invoices) is guarded at write
    # time; these catch a bypass. An account charged past balance+limit is not
    # a judgment call — the guard exists precisely so this count stays zero.
    (
        "charged sales orders belong to the account's customer",
        """select count(*) from sales_orders o
             join billing_accounts a on a.id = o.billing_account_id
            where o.deleted_at is null
              and (a.customer_id is null or a.customer_id <> o.customer_id)""",
    ),
    (
        "charged purchase orders belong to the account's vendor",
        """select count(*) from purchase_orders o
             join billing_accounts a on a.id = o.billing_account_id
            where o.deleted_at is null
              and (a.vendor_id is null or a.vendor_id <> o.vendor_id)""",
    ),
    (
        "charged invoices match their account's owner",
        """select count(*) from invoices i
             join billing_accounts a on a.id = i.billing_account_id
            where i.deleted_at is null
              and ((i.direction = 'sales' and (a.customer_id is null or a.customer_id <> i.customer_id))
                or (i.direction = 'purchase' and (a.vendor_id is null or a.vendor_id <> i.vendor_id))
                or i.direction = 'payroll')""",
    ),
    (
        "charged documents are in the account's currency",
        """select count(*) from (
             select o.id from sales_orders o join billing_accounts a on a.id = o.billing_account_id
              where o.deleted_at is null and (a.unit_type <> 'currency' or a.unit <> o.currency)
             union all
             select o.id from purchase_orders o join billing_accounts a on a.id = o.billing_account_id
              where o.deleted_at is null and (a.unit_type <> 'currency' or a.unit <> o.currency)
             union all
             select i.id from invoices i join billing_accounts a on a.id = i.billing_account_id
              where i.deleted_at is null and (a.unit_type <> 'currency' or a.unit <> i.currency)
           ) as mismatched""",
    ),
)

# Disagreements worth a human's attention that are NOT integrity violations —
# the flow legitimately lags the ledger for a while. Reported, never fatal.
ADVISORY_CHECKS: tuple[tuple[str, str], ...] = (
    (
        "invoices marked paid with an outstanding balance",
        """select count(*) from (
             select i.id,
                    i.applied_amount,
                    coalesce(i.total_amount, (
                      select coalesce(sum(it.amount), 0) from invoice_items it
                       where it.invoice_id = i.id and it.deleted_at is null
                    )) as billed
               from invoices i
              where i.status = 'paid' and i.deleted_at is null
           ) as marked
            where billed - applied_amount > 0.005""",
    ),
    (
        "expense claims marked paid with nothing applied",
        """select count(*) from expense_claims
            where status = 'paid' and deleted_at is null and applied_amount = 0""",
    ),
    # Not a violation — a policy nobody ever published is somebody's abandoned
    # draft, which is ordinary. Worth a look once it is an old one.
    (
        "policies drafted over 90 days ago and never published",
        """select count(*) from policies
            where status = 'draft' and deleted_at is null
              and created_at < current_date - 90""",
    ),
    # A charge guard bypass: the account is occupied past balance + limit.
    # Structural in spirit; advisory in mechanics only because the exposure
    # expression is long — a non-zero count here is a bug, not a judgment call.
    (
        "accounts occupied past balance plus credit limit",
        """select count(*) from billing_accounts a
            where a.deleted_at is null and a.unit_type = 'currency'
              and (
                coalesce((select sum(greatest(
                    coalesce(o.total_amount, (
                      select coalesce(sum(coalesce(it.amount, it.unit_price * it.quantity, 0)), 0)
                        from sales_order_items it
                       where it.order_id = o.id and it.deleted_at is null
                    ) + (
                      select coalesce(sum(adj.amount), 0) from sales_order_adjustments adj
                       where adj.order_id = o.id and adj.deleted_at is null
                    ))
                    - (select coalesce(sum(coalesce(i.total_amount, (
                          select coalesce(sum(coalesce(ii.amount, ii.unit_price * ii.quantity, 0)), 0)
                            from invoice_items ii where ii.invoice_id = i.id and ii.deleted_at is null
                       ))), 0)
                        from invoices i
                       where i.sales_order_id = o.id
                         and i.billing_account_id = a.id and i.deleted_at is null)
                  , 0)) from sales_orders o
                   where o.billing_account_id = a.id and o.deleted_at is null), 0)
                + coalesce((select sum(greatest(
                    coalesce(o.total_amount, (
                      select coalesce(sum(coalesce(it.amount, it.unit_price * it.quantity, 0)), 0)
                        from purchase_order_items it
                       where it.po_id = o.id and it.deleted_at is null
                    ) + (
                      select coalesce(sum(adj.amount), 0) from purchase_order_adjustments adj
                       where adj.po_id = o.id and adj.deleted_at is null
                    ))
                    - (select coalesce(sum(coalesce(i.total_amount, (
                          select coalesce(sum(coalesce(ii.amount, ii.unit_price * ii.quantity, 0)), 0)
                            from invoice_items ii where ii.invoice_id = i.id and ii.deleted_at is null
                       ))), 0)
                        from invoices i
                       where i.purchase_order_id = o.id
                         and i.billing_account_id = a.id and i.deleted_at is null)
                  , 0)) from purchase_orders o
                   where o.billing_account_id = a.id and o.deleted_at is null), 0)
                + coalesce((select sum(greatest(
                    coalesce(i.total_amount, (
                      select coalesce(sum(coalesce(ii.amount, ii.unit_price * ii.quantity, 0)), 0)
                        from invoice_items ii where ii.invoice_id = i.id and ii.deleted_at is null
                    )) - coalesce(i.applied_amount, 0), 0))
                    from invoices i
                   where i.billing_account_id = a.id and i.deleted_at is null), 0)
              ) > coalesce(a.balance, 0) + coalesce(a.credit_limit, 0) + 0.005""",
    ),
    # 挂账超 30 天仍未开票的订单 — legitimate for as long as delivery takes,
    # worth a look once it is old: the cancel-release is the agent's write and
    # this is the detector for a forgotten one.
    (
        "orders charged to an account for over 30 days with no invoice",
        """select count(*) from sales_orders o
            where o.billing_account_id is not null and o.deleted_at is null
              and o.created_at < current_date - 30
              and not exists (select 1 from invoices i
                               where i.sales_order_id = o.id
                                 and i.billing_account_id = o.billing_account_id
                                 and i.deleted_at is null)""",
    ),
    # HKG-015. A submitted document with nobody assigned is work the flow agent
    # dropped: it advanced the round, or returned and resubmitted, and never
    # raised the next todo. Advisory rather than structural because the gap is
    # legitimate for as long as it takes the runner to poll — an hour is far
    # past that and still short enough to catch the same day.
    #
    # This is the check that would have found HKG-015 without anybody opening
    # the console: a timesheet sat in `submitted`, round 2, with zero todos of
    # any round, while the console showed a superseded round-1 todo that read
    # as an active queue.
    (
        "documents submitted over an hour ago with no open todo",
        """select count(*) from (
             select h.id from timesheet_headers h
              where h.status = 'submitted' and h.deleted_at is null
                and h.submitted_at < now() - interval '1 hour'
                and not exists (select 1 from todos t
                                 where t.entity_type = 'timesheet_header'
                                   and t.entity_id = h.id and t.status = 'open')
             union all
             select c.id from expense_claims c
              where c.status = 'submitted' and c.deleted_at is null
                and c.submitted_at < now() - interval '1 hour'
                and not exists (select 1 from todos t
                                 where t.entity_type = 'expense_claim'
                                   and t.entity_id = c.id and t.status = 'open')
             union all
             select l.id from employee_leaves l
              where l.status = 'submitted' and l.deleted_at is null
                and l.submitted_at < now() - interval '1 hour'
                and not exists (select 1 from todos t
                                 where t.entity_type = 'employee_leave'
                                   and t.entity_id = l.id and t.status = 'open')
           ) as stranded""",
    ),
    # The fact, not a verdict. Whether one actor may submit a round and then
    # decide it is the tenant's workflow definition's business, and a
    # one-person workshop filing and approving is legitimate — so this reports
    # and never fails. It is here because in HKG-015 nobody could see it: the
    # approver returned a timesheet, corrected it himself, resubmitted it under
    # his own credential, and was then the only seat left to sign it off.
    (
        "rounds where the submitter also recorded the decision",
        """select count(*) from approval_records submitted
             join approval_records decided
               on decided.tenant_id = submitted.tenant_id
              and decided.entity_type = submitted.entity_type
              and decided.entity_id = submitted.entity_id
              and decided.round_no = submitted.round_no
            where submitted.action = 'submitted'
              and decided.action in ('approved', 'rejected')
              and decided.approver_id = submitted.approver_id""",
    ),
    # The leftovers of a half-landed transition, from the days when a return
    # was three calls. The server now commits the three together and closes the
    # rework on resubmission, so a fresh one of these means a path that still
    # writes them separately — a skill bundle predating the coupling, an
    # operator working straight against the database, or a bug.
    #
    # Advisory, not structural, for one reason only: every row written before
    # the coupling shipped is legitimately in this shape — no migration moved
    # them, because none could — and a check that fires on history nobody can
    # change is a check people learn to skip.
    (
        "open rework todos on documents that were resubmitted afterwards",
        """select count(*) from todos td
             join timesheet_headers h
               on h.id = td.entity_id and h.tenant_id = td.tenant_id
            where td.entity_type = 'timesheet_header'
              and td.todo_type = 'rework'
              and td.status = 'open'
              and h.status = 'submitted'
              and h.submitted_at > td.created_at""",
    ),
    (
        "open todos on documents whose state their machine cannot leave",
        """select count(*) from todos td
             join timesheet_headers h
               on h.id = td.entity_id and h.tenant_id = td.tenant_id
            where td.entity_type = 'timesheet_header'
              and td.status = 'open'
              and h.status in ('approved', 'rejected')
              and h.deleted_at is null""",
    ),
    # Not a violation — a payslip issued today is legitimately unpaid until
    # payday. Worth a look once it is an old one.
    (
        "payslips issued over 45 days ago and still not paid out",
        """select count(*) from invoices i
            where i.direction = 'payroll' and i.deleted_at is null
              and i.period_end < current_date - 45
              and i.applied_amount < (
                select coalesce(sum(it.amount), 0) from invoice_items it
                 where it.invoice_id = i.id and it.deleted_at is null
              ) - 0.005""",
    ),
)


def main() -> int:
    SessionLocal = create_ops_sessionmaker()
    schema = settings.database_schema.replace('"', '""')
    with SessionLocal() as db:
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text(f'set search_path to "{schema}", public'))

        print("== structural and workflow invariants (all tenants) ==")
        for name, sql in STRUCTURAL_CHECKS:
            bad = db.execute(text(sql)).scalar()
            check(name, bad == 0, f"{bad} offending rows")

        # Advisory: the flow's marker legitimately lags the ledger (an invoice
        # is set `paid` moments before the receipt is applied), so a
        # disagreement is worth reporting and never worth failing on.
        print("== advisory: flow markers vs the settlement ledger ==")
        for name, sql in ADVISORY_CHECKS:
            lagging = db.execute(text(sql)).scalar()
            print(f"  [{'ok' if lagging == 0 else 'note'}] {name}" + (f" — {lagging} rows" if lagging else ""))

        print("== payload conformance against active definitions ==")
        rows = db.execute(
            text(
                """select b.id, b.object_type, b.payload_jsonb, d.json_schema, t.name
                   from business_objects b
                   join object_type_definitions d
                     on d.tenant_id=b.tenant_id and d.object_type=b.object_type and d.status='active'
                   join tenants t on t.id=b.tenant_id
                   where b.deleted_at is null"""
            )
        ).all()
        bad = 0
        for object_id, object_type, payload, json_schema, tenant_name in rows:
            validator_cls = validator_for(json_schema, default=Draft202012Validator)
            errors = list(validator_cls(json_schema).iter_errors(payload))
            if errors:
                bad += 1
                failures.append(
                    f"payload violates schema: {tenant_name}/{object_type}/{object_id}: {errors[0].message}"
                )
        check(f"all {len(rows)} schema-governed objects conform", bad == 0, f"{bad} violations")

    if failures:
        print(f"\nDATA AUDIT FAILED ({len(failures)}):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nDATA AUDIT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
