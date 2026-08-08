"""Tenant-customizable type vocabularies (OFBiz-style *_TYPE tables).

A type option names a KIND of business fact — a price type, an adjustment
type, an expense category, a work type. The system ships a catalog per
family; tenants add their own entries beside it (经销价、开票服务费…) and may
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

TYPE_NAME_PATTERN = r"^[a-z][a-z0-9_]{0,49}$"

# family → (name, title, description); the shipped vocabulary each tenant
# starts from. Order is display order.
SYSTEM_TYPE_OPTIONS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "product_price_type": (
        ("list", "目录价", "对外目录/牌价，报价折扣的比较基准"),
        ("default", "默认售价", "无特殊约定时的默认成交价"),
        ("promo", "促销价", "限时促销/活动价"),
        ("wholesale", "批发价", "渠道/经销批量价"),
        ("competitive", "竞品价", "竞争对手参考价"),
        ("minimum", "最低限价", "允许成交的下限"),
        ("maximum", "最高限价", "允许成交的上限"),
        ("cost", "成本价", "无具名供应商的标准成本；供应商进价记在供应关系上"),
    ),
    # 客户分类 — the OPEN axis of customer master data. The closed one (自然人 vs
    # 组织) is `customers.customer_kind`, a constrained column rather than a
    # value here: that distinction is universal, not the tenant's to extend,
    # and keeping it closed is what would let a constraint branch on it later.
    #
    # Nothing branches on these names. They are how a workspace segments its own
    # book; what a segment IMPLIES — pricing, 账期, whether a member prepays —
    # is a judgment for an agent or a workflow definition, never for the server.
    "customer_type": (
        ("retail", "零售客户", "面向个人消费者的散客或会员"),
        ("wholesale", "批发客户", "批量采购、按批发价成交的客户"),
        ("distributor", "经销商", "有授权或区域约定的渠道商"),
        ("enterprise", "企业客户", "直接采购的企业客户（B2B 直客）"),
        ("institution", "政企机构", "政府、学校、医院等机构客户，通常有招标与账期要求"),
        ("online", "电商客户", "来自电商平台或线上店铺的客户"),
        ("affiliate", "关联方", "集团内部或有关联关系的往来单位"),
        ("other", "其他", "未归类的客户"),
    ),
    "sales_adjustment_type": (
        ("discount", "折扣", "整单或行级金额折让"),
        ("promotion", "促销", "促销活动带来的减免"),
        ("tax", "税", "税额调整"),
        ("shipping", "运费", "运输/物流费用"),
        ("fee", "手续费", "服务费/手续费"),
        ("surcharge", "附加费", "附加收费"),
        ("rounding", "抹零", "凑整抹零"),
        ("other", "其他", "未归类的总价调整"),
    ),
    "expense_category": (
        ("travel", "差旅", "差旅相关支出"),
        ("lodging", "住宿", "酒店/住宿"),
        ("meal", "餐费", "工作餐/餐饮"),
        ("transport", "交通", "市内交通/打车/高铁机票"),
        ("office", "办公", "办公用品与耗材"),
        ("entertainment", "招待", "业务招待"),
        ("communication", "通讯", "话费/网络"),
        ("other", "其他", "未归类的报销支出"),
    ),
    # The tax document's own kind. Direction (销项/进项) is NOT here — it is a
    # constrained column on the invoice, because every settlement guard branches
    # on it and a tenant-extensible vocabulary would leave those undecidable.
    # Names deliberately match the `InvoiceType` literal that expense items
    # already use, so the two vocabularies can be unified later without a data
    # rewrite.
    "invoice_type": (
        ("vat_special", "增值税专用发票", "可抵扣进项税的专用发票"),
        ("vat_general", "增值税普通发票", "不可抵扣的普通发票"),
        ("vat_electronic", "电子发票", "全电/电子发票"),
        ("proforma", "形式发票", "对外报价性质的形式发票，非税务凭证"),
        ("receipt", "收据", "非发票的收付款凭证"),
        ("other", "其他", "未归类的票据类型"),
    ),
    # OFBiz invoiceItemTypeId: charges and allowances are LINE types here, which
    # is why this family needs no separate invoice-adjustment table.
    "invoice_item_type": (
        ("goods", "货物", "商品/货物行"),
        ("service", "服务", "服务/劳务行"),
        ("shipping", "运费", "运输/物流费用行"),
        ("discount", "折扣", "折让行，金额为负"),
        ("tax", "税", "单列税额行"),
        ("rounding", "抹零", "凑整抹零行"),
        ("other", "其他", "未归类的开票行"),
    ),
    # What a non-money account counts. Money accounts carry a currency code in
    # the same column instead, so this family is only consulted for points.
    "billing_account_unit": (
        ("point", "积分", "通用积分单位"),
        ("stored_value", "储值", "预付卡/储值余额（非记账本位币时使用）"),
        ("coupon", "券额", "优惠券/代金券额度"),
    ),
    # Why an account moved. Mirrors the inventory ledger's reason vocabulary;
    # `expired` is load-bearing — the expiry sweep both writes and excludes on it.
    "billing_account_entry_reason": (
        ("deposit", "充值", "客户/员工存入款项"),
        ("charge", "扣款", "以账户余额支付单据"),
        ("refund", "退款", "从账户退还款项"),
        ("earned", "获得", "消费或活动获得的积分/券额"),
        ("redeemed", "兑换", "使用积分/券额抵扣"),
        ("expired", "过期", "到期失效——由过期扫描写入，指向被它过期的那笔入账"),
        ("adjustment", "调整", "人工更正"),
        ("transfer", "转移", "账户之间的划转"),
        ("initial", "期初", "开户时的起始余额"),
        ("import_initial", "导入期初", "从旧系统迁入的起始余额"),
        ("other", "其他", "未归类的账户变动"),
    ),
    # 工资条项目 (OFBiz InvoiceItemType's PAYROL_* family). Additions are
    # positive, deductions negative — the direction is declared in
    # TYPE_OPTION_SIGNS below and checked on write, because a mis-signed
    # deduction pays someone twice what they are owed.
    "payroll_item_type": (
        ("payroll_salary", "基本工资", "月度基本工资（OFBiz PAYROL_SALARY）"),
        ("payroll_hourly_rate", "计时工资", "按小时计的工资（OFBiz PAYROL_HRLY_RATE）"),
        ("payroll_bonus", "奖金", "绩效/项目奖金（OFBiz PAYROL_BONUS）"),
        ("payroll_commission", "佣金", "销售提成（OFBiz PAYROL_COMMISSION）"),
        ("payroll_allowance", "补贴", "交通/餐补/通讯等补贴（OFBiz 自定义 CN_PAYROL_ALLOWANCE）"),
        ("payroll_iit", "个人所得税", "代扣个人所得税（OFBiz 自定义 CN_PAYROL_IIT）"),
        ("payroll_pension_ee", "养老保险（个人）", "个人承担的基本养老保险（CN_PAYROL_PENSION_EE）"),
        ("payroll_medical_ee", "医疗保险（个人）", "个人承担的基本医疗保险（CN_PAYROL_MEDICAL_EE）"),
        ("payroll_unemploy_ee", "失业保险（个人）", "个人承担的失业保险（CN_PAYROL_UNEMPLOY_EE）"),
        ("payroll_housing_ee", "住房公积金（个人）", "个人承担的住房公积金（CN_PAYROL_HOUSING_EE）"),
        ("payroll_other_deduction", "其他扣款", "未归类的扣款；租户可另建自己的扣款类型"),
    ),
    # What kind of compensation term a pay_histories row states. Only terms that
    # are facts about THIS PERSON belong there — company-wide policy lives in a
    # workflow definition, and national policy (五险一金 rates) in neither.
    "pay_component_type": (
        ("base_salary", "基本工资", "固定薪资；按 period_type 计（月/时/日/年）"),
        ("allowance", "补贴", "岗位/交通/通讯等固定补贴"),
        ("commission", "提成", "按比例计的销售提成——须同时说明 basis（按什么算）"),
        ("bonus", "奖金", "与这个人绑定的奖金安排；全员统一的规则属于工作流定义"),
        ("overtime_rate", "加班费率", "加班计薪标准"),
        ("other", "其他", "未归类的个人薪酬条款"),
    ),
    # 规章制度的门类。`external_standard` 是那个不显然但必要的一类：上海市当年度
    # 社保缴费基数标准不属于公司的任何一份制度，但工资算得对不对取决于它，所以它
    # 需要一个有发布人、有日期、有出处的落脚点。
    "policy_category": (
        ("hr", "人事", "员工手册、考勤、休假、招聘与离职"),
        ("payroll", "薪酬", "薪酬管理办法、奖金与提成制度、调薪规则"),
        ("finance", "财务", "财务管理制度、资金审批权限、账期"),
        ("expense", "报销", "差旅与报销标准、发票要求"),
        ("procurement", "采购", "采购审批权限、供应商准入"),
        ("compliance", "合规", "保密、廉洁、数据与信息安全"),
        ("external_standard", "外部标准", "政府或行业发布的、公司必须照办的口径——社保基数、最低工资、税率通知"),
        ("other", "其他", "未归类的制度"),
    ),
    "pay_period_type": (
        ("month", "月薪", "金额是每月的"),
        ("hour", "时薪", "金额是每小时的"),
        ("day", "日薪", "金额是每天的"),
        ("year", "年薪", "金额是每年的"),
    ),
    "payment_method": (
        ("bank_transfer", "银行转账", "对公/对私银行转账"),
        ("cash", "现金", "现金收付"),
        ("cheque", "支票", "支票结算"),
        ("bank_acceptance", "银行承兑汇票", "银行承兑汇票结算"),
        ("commercial_acceptance", "商业承兑汇票", "商业承兑汇票结算"),
        ("wechat", "微信", "微信支付"),
        ("alipay", "支付宝", "支付宝支付"),
        ("offset", "抵账", "以款抵款/往来冲抵，不产生实际资金流"),
        ("other", "其他", "未归类的结算方式"),
    ),
    "work_type": (
        ("regular", "正常工时", "常规工作时间"),
        ("overtime", "加班", "加班工时"),
        ("holiday", "节假日", "节假日工作"),
        ("travel", "出差", "出差期间工时"),
        ("other", "其他", "未归类工时"),
    ),
}

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


def system_type_names(family: str) -> frozenset[str]:
    return frozenset(name for name, *_ in SYSTEM_TYPE_OPTIONS.get(family, ()))


def system_type_sign(family: str, name: str) -> int | None:
    return TYPE_OPTION_SIGNS.get(family, {}).get(name)
