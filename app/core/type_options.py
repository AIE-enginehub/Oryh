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
    "campaign_type": (
        ("trade_fair", "展会", "线下展会、行业会议"),
        ("webinar", "线上活动", "网络研讨会、直播"),
        ("email", "邮件营销", "邮件群发"),
        ("advertisement", "广告投放", "搜索、信息流、户外等付费投放"),
        ("social", "社交媒体", "公众号、抖音、小红书等"),
        ("referral", "转介绍", "老客户或伙伴推荐计划"),
        ("event", "客户活动", "客户答谢、开放日、路演"),
        ("other", "其他", "其余市场活动"),
    ),
    "opportunity_lost_reason": (
        ("price", "价格", "对方报价更低或预算不够"),
        ("competitor", "竞争对手", "选了别家"),
        ("timing", "时机", "项目推迟或取消"),
        ("no_budget", "无预算", "预算未落实"),
        ("no_decision", "未决策", "长期无决定"),
        ("other", "其他", "其余原因"),
    ),
    "opportunity_contact_role": (
        ("decision_maker", "决策者", "拍板的人"),
        ("influencer", "影响者", "意见影响决策的人"),
        ("champion", "内部支持者", "在客户内部推动我们的人"),
        ("end_user", "使用者", "实际使用产品的人"),
        ("procurement", "采购", "走采购流程的人"),
        ("finance", "财务", "审预算与付款的人"),
        ("gatekeeper", "把关人", "控制接触渠道的人"),
        ("other", "其他", "其余角色"),
    ),
    "geo_type": (
        ("country", "国家", "国家或地区"),
        ("province", "省", "省、直辖市、自治区、特别行政区"),
        ("city", "市", "地级市、地区、自治州"),
        ("district", "区县", "市辖区、县、县级市"),
        ("town", "乡镇街道", "乡、镇、街道"),
        ("postal_code", "邮编", "邮政编码区"),
        ("region", "自定义区域", "本工作区自己划的片区,如华东、华南"),
        ("other", "其他", "其余地理单位"),
    ),
    "territory_member_role": (
        ("manager", "负责人", "区域负责人"),
        ("rep", "销售", "区域内的销售"),
        ("support", "支持", "售前、技术支持等"),
    ),
    "activity_type": (
        ("call", "电话", "打过或接到的电话"),
        ("visit", "拜访", "上门或到访"),
        ("meeting", "会议", "线上或线下会议"),
        ("message", "消息", "微信、短信等即时消息"),
        ("note", "备注", "非沟通的记录:内部观察、听说"),
        ("other", "其他", "其余接触"),
    ),
    "activity_outcome": (
        ("positive", "积极", "有进展或意向明确"),
        ("neutral", "中性", "无明显进展"),
        ("negative", "消极", "拒绝、推迟或降温"),
        ("no_answer", "未联系上", "没有接通或没有回复"),
    ),
    "event_type": (
        ("meeting", "会议", "线上或线下会议"),
        ("visit", "拜访", "客户现场"),
        ("demo", "演示", "产品演示或试用"),
        ("call", "电话约谈", "约定时间的电话"),
        ("training", "培训", "客户培训"),
        ("other", "其他", "其余日程"),
    ),
    "event_response": (
        ("invited", "已邀请", "已发出邀请"),
        ("accepted", "已接受", "确认参加"),
        ("declined", "已拒绝", "不参加"),
        ("attended", "已参加", "实际到场"),
    ),
    "communication_channel": (
        ("email", "邮件", "电子邮件"),
        ("sms", "短信", "手机短信"),
        ("wechat", "微信", "微信消息"),
        ("phone", "电话", "电话通话记录"),
        ("other", "其他", "其余渠道"),
    ),
    "campaign_member_status": (
        ("targeted", "目标", "列入名单,尚未触达"),
        ("sent", "已触达", "已发送、已邀请"),
        ("responded", "已回应", "有回复或报名"),
        ("attended", "已参加", "到场或参与"),
        ("converted", "已转化", "成为线索/商机的成员"),
        ("declined", "已拒绝", "明确拒绝或退订"),
    ),
    "facility_type": (
        ("store", "店铺", "对外营业的门店"),
        ("warehouse", "仓库", "存货与发货场所"),
        ("office", "办公室", "办公场所"),
        ("factory", "工厂", "生产场所"),
        ("other", "其他", "其余设施"),
    ),
    "fin_account_type": (
        ("bank", "银行账户", "对公/对私银行户"),
        ("cash", "现金", "备用金/现金柜"),
        ("wallet", "第三方支付", "微信支付/支付宝/PayPal 等商户账户余额"),
        ("other", "其他", "其余资金形态"),
    ),
    "product_image_type": (
        ("main", "展示图", "对外展示/主图类图片"),
        ("detail", "详情图", "商品详情页用图"),
        ("design", "设计图稿", "设计稿/效果图/图纸(可为 PDF)"),
        ("packaging", "包装图", "包装与外箱"),
        ("dimension", "尺寸图", "尺寸/规格标注图"),
        ("other", "其他", "未归类的图片"),
    ),
    # 销售渠道类型 — what KIND of channel a sales channel is; the channel
    # itself (its code, its stores) is master data, this is only its label
    "sales_channel_kind": (
        ("marketplace", "平台商城", "天猫/京东/亚马逊等第三方平台店铺"),
        ("own_site", "自营线上", "官网/小程序/自建商城"),
        ("live_stream", "直播带货", "抖音/快手/视频号等直播渠道"),
        ("offline", "线下", "门店/专柜/展会等线下销售"),
        ("wholesale", "批发分销", "经销商/分销商渠道"),
        ("other", "其他", "其余销售渠道"),
    ),
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
    "contract_type": (
        ("purchase", "采购合同", "向供应商采购的合同"),
        ("oem", "委托加工合同", "委托第三方工厂生产/加工"),
        ("sales", "销售合同", "向客户销售的合同"),
        ("framework", "框架协议", "长期框架/年度协议,具体以订单执行"),
        ("service", "服务合同", "服务类合同"),
        ("nda", "保密协议", "保密/竞业等约定"),
        ("other", "其他", "未归类的合同"),
    ),
    "contract_term_type": (
        ("payment_terms", "付款条件", "付款节奏/账期/比例"),
        ("deposit", "首付款/预付款", "签约或下单时预付的比例与时点"),
        ("payment_method", "付款方式", "电汇/承兑/信用证等"),
        ("delivery_schedule", "交货节奏", "分批交付的时间安排"),
        ("delivery_terms", "交货条件", "地点、运输、风险转移"),
        ("acceptance", "验收", "验收标准与期限"),
        ("quality", "质量", "质量标准与责任"),
        ("warranty", "质保", "质保期与范围"),
        ("price", "价格与调价", "定价、调价机制"),
        ("penalty", "违约责任", "违约金与赔偿"),
        ("term_period", "合同期限", "起止与续约"),
        ("confidentiality", "保密", "保密义务"),
        ("termination", "终止", "解除与终止条件"),
        ("dispute", "争议解决", "仲裁/诉讼与管辖"),
        ("other", "其他", "未归类条款"),
    ),
    "contract_document_type": (
        ("signed", "签署版", "双方签署的正式版本"),
        ("draft", "草稿", "谈判中的版本"),
        ("annex", "附件/附表", "合同附件、附表、报价单"),
        ("scan_page", "扫描页", "按页扫描的原件"),
        ("amendment", "补充协议", "补充/变更协议"),
        ("translation", "译文", "翻译版本"),
        ("other", "其他", "未归类文件"),
    ),
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
        # 报销与工资条不是税务票据，但它们仍是单据，而这张表本来就装着
        # 非税务凭证——形式发票"非税务凭证"，收据"非发票的收付款凭证"。
        # 归进 `other` 会更糟：那是"是票据但未归类"，而这两者根本不是票据，
        # 混进去会污染将来的进项税额统计。
        ("reimbursement", "报销单", "员工垫付后由公司偿付的内部应付凭证，非税务票据"),
        ("payslip", "工资条", "发薪凭证，非税务票据"),
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
    # 请假类型. A vocabulary rather than a constrained column because the list
    # is genuinely local: 陪产假 and 丧假 exist in some workspaces and not
    # others, and their length is set by provincial regulation. Nothing in the
    # server branches on the value — how many days a type is worth, whether it
    # is paid, whether it needs a certificate, all of that is in the tenant's
    # leave policy and read by an agent. This list only keeps the spelling
    # consistent so "年假" and "年休假" are not two different things.
    "leave_type": (
        ("annual", "年假", "带薪年休假"),
        ("sick", "病假", "因病缺勤；是否需要证明由制度规定"),
        ("personal", "事假", "因私缺勤"),
        ("marriage", "婚假", "婚假"),
        ("maternity", "产假", "产假"),
        ("paternity", "陪产假", "配偶生育陪护假"),
        ("bereavement", "丧假", "丧假"),
        ("compensatory", "调休", "以加班折抵的休假"),
        ("other", "其他", "未归类的假别"),
    ),
    "work_type": (
        ("regular", "正常工时", "常规工作时间"),
        ("overtime", "加班", "加班工时"),
        ("holiday", "节假日", "节假日工作"),
        ("travel", "出差", "出差期间工时"),
        ("other", "其他", "未归类工时"),
    ),
}

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
    from app.core.config import settings  # noqa: PLC0415 - config imports nothing from here

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


def system_type_names(family: str) -> frozenset[str]:
    return frozenset(name for name, *_ in SYSTEM_TYPE_OPTIONS.get(family, ()))


def system_type_sign(family: str, name: str) -> int | None:
    return TYPE_OPTION_SIGNS.get(family, {}).get(name)
