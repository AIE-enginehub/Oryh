"""Tenant-customizable type vocabularies (OFBiz-style *_TYPE tables).

A type option names a KIND of business fact — a price type, an adjustment
type, an expense category, a work type. The system ships a catalog per
family; tenants add their own entries beside it (dealer price, invoicing service fee…) and may
archive shipped ones they never use. Statuses, approval actions and other
state-machine words are NOT here: those are protocol, not vocabulary.

Validation semantics ("tenants own their tuning", capabilities-style):

- A tenant with NO rows for a family has not customized it — the shipped
  catalog applies verbatim. This is also what keeps a freshly migrated
  deployment working before the per-tenant seed has run.
- Once rows exist (seeded on provision, like capabilities), they are the
  whole truth: active rows are writable values, archived rows are refused.
  The catalog refresh updates system rows' titles/descriptions only — never
  their status, never custom rows.
"""

from __future__ import annotations

from app.locales.zh_CN.type_options import SYSTEM_TYPE_OPTIONS as _SYSTEM_TYPE_OPTIONS_ZH

from app.core.config import settings

TYPE_NAME_PATTERN = r"^[a-z][a-z0-9_]{0,49}$"

# family → (name, title, description); the shipped vocabulary each tenant
# starts from. Order is display order.
SYSTEM_TYPE_OPTIONS: dict[str, tuple[tuple[str, str, str], ...]] = _SYSTEM_TYPE_OPTIONS_ZH

# The same vocabulary in English: same families, same names, only the words
# a person reads. `system_type_options()` picks by locale; the open-core
# repository seeds this table, the hosted service the one above.
SYSTEM_TYPE_OPTIONS_EN: dict[str, tuple[tuple[str, str, str], ...]] = {
    "campaign_type": (
        ("trade_fair", "Trade fair", "Exhibitions and industry conferences"),
        ("webinar", "Webinar", "Online seminars and live streams"),
        ("email", "Email campaign", "Mailings"),
        ("advertisement", "Advertising", "Paid search, feed, outdoor and similar placements"),
        ("social", "Social media", "Official accounts, short video, community platforms"),
        ("referral", "Referral", "Customer or partner referral programmes"),
        ("event", "Customer event", "Appreciation events, open days, roadshows"),
        ("other", "Other", "Any other campaign"),
    ),
    "opportunity_lost_reason": (
        ("price", "Price", "Undercut, or the budget was short"),
        ("competitor", "Competitor", "They chose someone else"),
        ("timing", "Timing", "The project slipped or was cancelled"),
        ("no_budget", "No budget", "The budget never materialised"),
        ("no_decision", "No decision", "Went quiet for good"),
        ("other", "Other", "Any other reason"),
    ),
    "deal_party_role": (
        ("end_client", "End client", "Who the work is ultimately for; not necessarily who signs with us"),
        ("referrer", "Referrer", "Who brought the deal; may be owed a share"),
        ("reseller", "Reseller", "Resells our product or service"),
        ("general_contractor", "General contractor", "We serve as their subcontractor"),
        ("consultant", "Consultant", "A third party advising the customer"),
        ("other", "Other", "Any other role"),
    ),
    "customer_relation_type": (
        ("parent_of", "Parent of", "The subject is the object's parent company"),
        ("subsidiary_of", "Subsidiary of", "The subject is the object's subsidiary"),
        ("partner_of", "Partner of", "Partners, either way round"),
        ("referrer_of", "Referrer of", "The subject introduced the object to us"),
        ("referred_by", "Referred by", "The subject came through the object"),
        ("agent_of", "Agent of", "The subject acts for the object"),
        ("principal_of", "Principal of", "The subject is represented by the object"),
        ("end_client_of", "End client of", "The subject is the end client the object serves"),
        ("intermediary_of", "Intermediary of", "The subject stands between the object and us"),
        ("other", "Other", "Any other relation"),
    ),
    "lead_source": (
        ("referral", "Referral", "Introduced by a customer, partner or friend"),
        ("exhibition", "Exhibition", "Met at a trade show or event"),
        ("inbound", "Inbound", "They came to us"),
        ("outbound", "Outbound", "We went to them"),
        ("campaign", "Campaign", "From a marketing campaign"),
        ("other", "Other", "Any other source"),
    ),
    "opportunity_contact_role": (
        ("decision_maker", "Decision maker", "Signs off"),
        ("influencer", "Influencer", "Shapes the decision"),
        ("champion", "Champion", "Pushes for us inside the customer"),
        ("end_user", "End user", "Will use what is bought"),
        ("procurement", "Procurement", "Runs the buying process"),
        ("finance", "Finance", "Approves budget and payment"),
        ("gatekeeper", "Gatekeeper", "Controls access"),
        ("other", "Other", "Any other role"),
    ),
    "geo_type": (
        ("country", "Country", "A country or region"),
        ("province", "Province / state", "First-level division"),
        ("city", "City", "Second-level division"),
        ("district", "District / county", "Third-level division"),
        ("town", "Town", "Fourth-level division"),
        ("postal_code", "Postal code", "A postal code area"),
        ("region", "Custom region", "A region the workspace defines, such as East or South"),
        ("other", "Other", "Any other geographic unit"),
    ),
    "territory_member_role": (
        ("manager", "Manager", "Runs the territory"),
        ("rep", "Rep", "Sells in the territory"),
        ("support", "Support", "Pre-sales, technical support and the like"),
    ),
    "activity_type": (
        ("call", "Call", "A phone call made or taken"),
        ("visit", "Visit", "On site, either way"),
        ("meeting", "Meeting", "Online or in person"),
        ("message", "Message", "WeChat, SMS and other instant messages"),
        ("note", "Note", "A record that is not a contact: an observation, something heard"),
        ("other", "Other", "Any other contact"),
    ),
    "activity_outcome": (
        ("positive", "Positive", "Progress, or clear intent"),
        ("neutral", "Neutral", "No visible progress"),
        ("negative", "Negative", "Refused, postponed or cooling"),
        ("no_answer", "No answer", "Not reached, no reply"),
    ),
    "event_type": (
        ("meeting", "Meeting", "Online or in person"),
        ("visit", "Visit", "At the customer's site"),
        ("demo", "Demo", "Product demonstration or trial"),
        ("call", "Scheduled call", "A call at an agreed time"),
        ("training", "Training", "Customer training"),
        ("other", "Other", "Any other event"),
    ),
    "event_response": (
        ("invited", "Invited", "Invitation sent"),
        ("accepted", "Accepted", "Confirmed attendance"),
        ("declined", "Declined", "Not attending"),
        ("attended", "Attended", "Actually there"),
    ),
    "communication_channel": (
        ("email", "Email", "Electronic mail"),
        ("sms", "SMS", "Text message"),
        ("wechat", "WeChat", "WeChat message"),
        ("phone", "Phone", "A phone call's record"),
        ("other", "Other", "Any other channel"),
    ),
    "campaign_member_status": (
        ("targeted", "Targeted", "On the list, not yet reached"),
        ("sent", "Sent", "Invited or mailed"),
        ("responded", "Responded", "Replied or registered"),
        ("attended", "Attended", "Showed up or took part"),
        ("converted", "Converted", "Became a lead or a deal"),
        ("declined", "Declined", "Refused or unsubscribed"),
    ),
    "facility_type": (
        ("store", "Store", "A shop open to customers"),
        ("warehouse", "Warehouse", "Where stock is held and shipped from"),
        ("office", "Office", "Office premises"),
        ("factory", "Factory", "Production site"),
        ("other", "Other", "Any other facility"),
    ),
    "fin_account_type": (
        ("bank", "Bank account", "Corporate or personal bank account"),
        ("cash", "Cash", "Petty cash or a cash drawer"),
        ("wallet", "Payment platform", "Merchant balance at WeChat Pay, Alipay, PayPal or similar"),
        ("other", "Other", "Any other form of funds"),
    ),
    "product_image_type": (
        ("main", "Main image", "The image shown first, for listings and catalogues"),
        ("detail", "Detail image", "Images for the product detail page"),
        ("design", "Design drawing", "Design sketches, renderings, technical drawings (PDF allowed)"),
        ("packaging", "Packaging", "Packaging and outer carton"),
        ("dimension", "Dimension drawing", "Size and specification markup"),
        ("other", "Other", "Uncategorised images"),
    ),
    "sales_channel_kind": (
        ("marketplace", "Marketplace", "A storefront on a third-party platform such as Tmall, JD or Amazon"),
        ("own_site", "Own online store", "The company's own website, app or mini-program shop"),
        ("live_stream", "Live commerce", "Live-stream selling on Douyin, Kuaishou, video channels and the like"),
        ("offline", "Offline", "Shops, counters, trade fairs: in-person sales"),
        ("wholesale", "Wholesale and distribution", "Dealers and distributors"),
        ("other", "Other", "Any other sales channel"),
    ),
    "product_price_type": (
        ("list", "List price", "The published catalogue price; what quotation discounts are measured against"),
        ("default", "Default selling price", "The price used when nothing else has been agreed"),
        ("promo", "Promotional price", "A time-limited promotion or campaign price"),
        ("wholesale", "Wholesale price", "Volume price for channels and dealers"),
        ("competitive", "Competitor price", "A competitor's price, for reference"),
        ("minimum", "Floor price", "The lowest price a deal may close at"),
        ("maximum", "Ceiling price", "The highest price a deal may close at"),
        ("cost", "Cost price", "Standard cost with no named supplier; a supplier's purchase price lives on the supply relationship"),
    ),
    "contract_type": (
        ("purchase", "Purchase contract", "A contract to buy from a supplier"),
        ("oem", "Contract manufacturing", "Production or processing outsourced to a third-party factory"),
        ("sales", "Sales contract", "A contract to sell to a customer"),
        ("framework", "Framework agreement", "A long-term or annual agreement executed through individual orders"),
        ("service", "Service contract", "A contract for services"),
        ("nda", "Non-disclosure agreement", "Confidentiality, non-compete and similar undertakings"),
        ("other", "Other", "Uncategorised contracts"),
    ),
    "contract_term_type": (
        ("payment_terms", "Payment terms", "Payment schedule, credit period, proportions"),
        ("deposit", "Deposit / advance payment", "The share paid on signing or ordering, and when"),
        ("payment_method", "Payment method", "Wire transfer, acceptance bill, letter of credit and the like"),
        ("delivery_schedule", "Delivery schedule", "Timing of deliveries in instalments"),
        ("delivery_terms", "Delivery terms", "Place, transport, transfer of risk"),
        ("acceptance", "Acceptance", "Acceptance criteria and deadline"),
        ("quality", "Quality", "Quality standards and liability"),
        ("warranty", "Warranty", "Warranty period and scope"),
        ("price", "Price and adjustment", "Pricing and price-adjustment mechanism"),
        ("penalty", "Breach and penalties", "Liquidated damages and compensation"),
        ("term_period", "Term", "Start, end and renewal"),
        ("confidentiality", "Confidentiality", "Confidentiality obligations"),
        ("termination", "Termination", "Grounds and conditions for ending the contract"),
        ("dispute", "Dispute resolution", "Arbitration, litigation and jurisdiction"),
        ("other", "Other", "Uncategorised clauses"),
    ),
    "contract_document_type": (
        ("upstream_reference", "Upstream contract copy", "A copy of the agreement between the counterparty and their client that this contract serves"),
        ("signed", "Signed version", "The executed version signed by both parties"),
        ("draft", "Draft", "A version under negotiation"),
        ("annex", "Annex / schedule", "Attachments, schedules, quotations"),
        ("scan_page", "Scanned page", "The original, scanned page by page"),
        ("amendment", "Amendment", "A supplementary or amending agreement"),
        ("translation", "Translation", "A translated version"),
        ("other", "Other", "Uncategorised documents"),
    ),
    "customer_type": (
        ("retail", "Retail customer", "Individual consumers, walk-in or members"),
        ("wholesale", "Wholesale customer", "Buys in volume at wholesale prices"),
        ("distributor", "Distributor", "An authorised or territory-bound channel partner"),
        ("enterprise", "Enterprise customer", "A company buying directly (B2B)"),
        ("institution", "Institution", "Government, schools, hospitals and similar bodies; usually tenders and credit periods"),
        ("online", "Online customer", "A customer from an e-commerce platform or online store"),
        ("affiliate", "Affiliate", "A group company or related party"),
        ("other", "Other", "Uncategorised customers"),
    ),
    "sales_adjustment_type": (
        ("discount", "Discount", "An allowance on the whole document or on a line"),
        ("promotion", "Promotion", "A reduction from a campaign"),
        ("tax", "Tax", "A tax adjustment"),
        ("shipping", "Shipping", "Freight and logistics charges"),
        ("fee", "Fee", "A service or handling fee"),
        ("surcharge", "Surcharge", "An additional charge"),
        ("rounding", "Rounding", "Rounding the total off"),
        ("other", "Other", "Uncategorised total adjustments"),
    ),
    "expense_category": (
        ("travel", "Travel", "Business-travel spending"),
        ("lodging", "Lodging", "Hotels and accommodation"),
        ("meal", "Meals", "Working meals and catering"),
        ("transport", "Transport", "Local transport, taxis, rail and air tickets"),
        ("office", "Office", "Office supplies and consumables"),
        ("entertainment", "Entertainment", "Business hospitality"),
        ("communication", "Communication", "Phone and internet"),
        ("other", "Other", "Uncategorised expenses"),
    ),
    "invoice_type": (
        ("vat_special", "VAT special invoice", "A VAT invoice whose input tax is deductible"),
        ("vat_general", "VAT general invoice", "A VAT invoice whose input tax is not deductible"),
        ("vat_electronic", "Electronic invoice", "A fully digital invoice"),
        ("proforma", "Pro forma invoice", "A quotation-style document, not a tax document"),
        ("receipt", "Receipt", "Proof of payment that is not an invoice"),
        ("reimbursement", "Expense claim", "An internal payable for money an employee advanced; not a tax document"),
        ("payslip", "Payslip", "A pay document; not a tax document"),
        ("other", "Other", "Uncategorised document types"),
    ),
    "invoice_item_type": (
        ("goods", "Goods", "A goods line"),
        ("service", "Service", "A service or labour line"),
        ("shipping", "Shipping", "A freight or logistics line"),
        ("discount", "Discount", "An allowance line, negative amount"),
        ("tax", "Tax", "A separately stated tax line"),
        ("rounding", "Rounding", "A rounding line"),
        ("other", "Other", "Uncategorised invoice lines"),
    ),
    "billing_account_unit": (
        ("point", "Points", "Loyalty points"),
        ("stored_value", "Stored value", "Prepaid-card or stored-value balance, when it is not the book currency"),
        ("coupon", "Coupon value", "Coupon and voucher balance"),
    ),
    "billing_account_entry_reason": (
        ("deposit", "Deposit", "Money paid in by a customer or employee"),
        ("charge", "Charge", "A document settled from the account balance"),
        ("refund", "Refund", "Money returned from the account"),
        ("earned", "Earned", "Points or coupon value gained through purchases or campaigns"),
        ("redeemed", "Redeemed", "Points or coupon value spent"),
        ("expired", "Expired", "Lapsed on expiry, written by the expiry sweep and naming the entry it expired"),
        ("adjustment", "Adjustment", "A manual correction"),
        ("transfer", "Transfer", "A move between accounts"),
        ("initial", "Opening balance", "The balance the account opened with"),
        ("import_initial", "Imported opening balance", "An opening balance migrated from a previous system"),
        ("other", "Other", "Uncategorised account movements"),
    ),
    "payroll_item_type": (
        ("payroll_salary", "Base salary", "Monthly base salary (OFBiz PAYROL_SALARY)"),
        ("payroll_hourly_rate", "Hourly pay", "Pay by the hour (OFBiz PAYROL_HRLY_RATE)"),
        ("payroll_bonus", "Bonus", "Performance or project bonus (OFBiz PAYROL_BONUS)"),
        ("payroll_commission", "Commission", "Sales commission (OFBiz PAYROL_COMMISSION)"),
        ("payroll_allowance", "Allowance", "Transport, meal, communication and similar allowances"),
        ("payroll_iit", "Income tax withheld", "Individual income tax withheld at source"),
        ("payroll_pension_ee", "Pension (employee share)", "The employee's share of pension contributions"),
        ("payroll_medical_ee", "Medical insurance (employee share)", "The employee's share of medical insurance"),
        ("payroll_unemploy_ee", "Unemployment insurance (employee share)", "The employee's share of unemployment insurance"),
        ("payroll_housing_ee", "Housing fund (employee share)", "The employee's share of the housing fund"),
        ("payroll_other_deduction", "Other deduction", "Uncategorised deductions; a workspace may add its own"),
    ),
    "pay_component_type": (
        ("base_salary", "Base salary", "Fixed pay, per period_type (month, hour, day, year)"),
        ("allowance", "Allowance", "Fixed allowances for role, transport, communication and the like"),
        ("commission", "Commission", "Commission at a rate; must state the basis it is computed on"),
        ("bonus", "Bonus", "A bonus arrangement tied to this person; company-wide rules belong in a workflow definition"),
        ("overtime_rate", "Overtime rate", "The rate overtime is paid at"),
        ("other", "Other", "Uncategorised personal pay terms"),
    ),
    "policy_category": (
        ("hr", "HR", "Employee handbook, attendance, leave, hiring and exit"),
        ("payroll", "Payroll", "Pay policy, bonus and commission schemes, pay-rise rules"),
        ("finance", "Finance", "Financial controls, spending authority, credit periods"),
        ("expense", "Expenses", "Travel and expense standards, receipt requirements"),
        ("procurement", "Procurement", "Purchasing authority, supplier qualification"),
        ("compliance", "Compliance", "Confidentiality, integrity, data and information security"),
        ("external_standard", "External standard", "A figure the company must follow but did not set: social-insurance bases, minimum wage, tax rates"),
        ("other", "Other", "Uncategorised policies"),
    ),
    "pay_period_type": (
        ("month", "Monthly", "The amount is per month"),
        ("hour", "Hourly", "The amount is per hour"),
        ("day", "Daily", "The amount is per day"),
        ("year", "Annual", "The amount is per year"),
    ),
    "payment_method": (
        ("bank_transfer", "Bank transfer", "Corporate or personal bank transfer"),
        ("cash", "Cash", "Cash paid or received"),
        ("cheque", "Cheque", "Settled by cheque"),
        ("bank_acceptance", "Bank acceptance bill", "Settled by a bank acceptance bill"),
        ("commercial_acceptance", "Commercial acceptance bill", "Settled by a commercial acceptance bill"),
        ("wechat", "WeChat Pay", "Paid through WeChat Pay"),
        ("alipay", "Alipay", "Paid through Alipay"),
        ("offset", "Offset", "Netted against another balance; no money moves"),
        ("other", "Other", "Uncategorised settlement methods"),
    ),
    "leave_type": (
        ("annual", "Annual leave", "Paid annual leave"),
        ("sick", "Sick leave", "Absence through illness; whether a certificate is needed is policy"),
        ("personal", "Personal leave", "Absence for personal reasons"),
        ("marriage", "Marriage leave", "Marriage leave"),
        ("maternity", "Maternity leave", "Maternity leave"),
        ("paternity", "Paternity leave", "Leave to accompany a partner giving birth"),
        ("bereavement", "Bereavement leave", "Bereavement leave"),
        ("compensatory", "Time off in lieu", "Leave earned by overtime"),
        ("other", "Other", "Uncategorised leave types"),
    ),
    "work_type": (
        ("regular", "Regular hours", "Ordinary working time"),
        ("overtime", "Overtime", "Overtime hours"),
        ("holiday", "Holiday work", "Work on public holidays"),
        ("travel", "Business travel", "Hours while travelling on business"),
        ("other", "Other", "Uncategorised hours"),
    ),
}


def system_type_options() -> dict[str, tuple[tuple[str, str, str], ...]]:
    """The shipped vocabulary in the deployment's content locale."""

    return SYSTEM_TYPE_OPTIONS_EN if settings.resolved_locale == "en" else SYSTEM_TYPE_OPTIONS

TYPE_FAMILIES = frozenset(SYSTEM_TYPE_OPTIONS)

# family → name → which way this kind of value moves money (+1 adds, -1 deducts).
#
# Kept beside the catalog rather than inside its tuples because the sign only
# means anything where it IS the meaning — one family today. A tenant adding its
# own deduction type declares the sign on the type option itself; this map only
# seeds the shipped rows.
TYPE_OPTION_SIGNS: dict[str, dict[str, int]] = {
    "payroll_item_type": {
        "payroll_salary": 1,
        "payroll_hourly_rate": 1,
        "payroll_bonus": 1,
        "payroll_commission": 1,
        "payroll_allowance": 1,
        "payroll_iit": -1,
        "payroll_pension_ee": -1,
        "payroll_medical_ee": -1,
        "payroll_unemploy_ee": -1,
        "payroll_housing_ee": -1,
        "payroll_other_deduction": -1,
    },
}

# Families whose values must declare a sign, and whose sign the write path
# enforces. A tenant adding a value here without one is refused, because an
# unsigned payslip item is exactly the ambiguity this family exists to remove.
SIGNED_TYPE_FAMILIES = frozenset(TYPE_OPTION_SIGNS)

# A customer relation is said from the subject's side; read from the object's
# side it is the reverse. Kept beside the catalog like the signs: it is part
# of a shipped value's meaning. A type with no entry reads the same both ways
# (partners), and so does any type a workspace adds.
CUSTOMER_RELATION_REVERSE: dict[str, str] = {
    "parent_of": "subsidiary_of",
    "subsidiary_of": "parent_of",
    "referrer_of": "referred_by",
    "referred_by": "referrer_of",
    "agent_of": "principal_of",
    "principal_of": "agent_of",
    "end_client_of": "intermediary_of",
    "intermediary_of": "end_client_of",
}


def system_type_names(family: str) -> frozenset[str]:
    return frozenset(name for name, *_ in SYSTEM_TYPE_OPTIONS.get(family, ()))


def system_type_sign(family: str, name: str) -> int | None:
    return TYPE_OPTION_SIGNS.get(family, {}).get(name)
