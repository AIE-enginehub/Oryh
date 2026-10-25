"""Chinese shipped type options; codes, order and values are compatibility data."""

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
    "deal_party_role": (
        ("end_client", "末端客户", "最终使用或受益的一方；我们未必与其签约"),
        ("referrer", "转介人", "把这笔交易介绍给我们的一方，可能有分成"),
        ("reseller", "分销商", "转售我们产品或服务的一方"),
        ("general_contractor", "总包方", "我们作为分包为其服务的一方"),
        ("consultant", "顾问", "为客户把关或提供建议的第三方"),
        ("other", "其他", "其余角色"),
    ),
    "customer_relation_type": (
        ("parent_of", "母公司", "主体是客体的母公司"),
        ("subsidiary_of", "子公司", "主体是客体的子公司"),
        ("partner_of", "合作伙伴", "双方互为合作伙伴"),
        ("referrer_of", "转介人", "主体把客体介绍给我们"),
        ("referred_by", "经其转介", "主体由客体介绍而来"),
        ("agent_of", "代理", "主体是客体的代理或中间人"),
        ("principal_of", "被代理方", "主体由客体代理"),
        ("end_client_of", "末端客户", "主体是客体所服务的末端客户"),
        ("intermediary_of", "中间方", "主体是客体与我们之间的中间方"),
        ("other", "其他", "其余关系"),
    ),
    "lead_source": (
        ("referral", "转介绍", "客户、伙伴或朋友介绍"),
        ("exhibition", "展会", "展会或活动上结识"),
        ("inbound", "主动联系", "对方主动找上门"),
        ("outbound", "主动开发", "我们主动联系"),
        ("campaign", "营销活动", "来自某次营销活动"),
        ("other", "其他", "其余来源"),
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
    # sales-channel types — what KIND of channel a sales channel is; the channel
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
    # customer category — the OPEN axis of customer master data. The closed one (person vs
    # organization) is `customers.customer_kind`, a constrained column rather than a
    # value here: that distinction is universal, not the tenant's to extend,
    # and keeping it closed is what would let a constraint branch on it later.
    #
    # Nothing branches on these names. They are how a workspace segments its own
    # book; what a segment IMPLIES — pricing, payment terms, whether a member prepays —
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
        ("upstream_reference", "上游合同副本", "对方与其客户之间、管着这份合同的那份协议的副本"),
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
    # The tax document's own kind. Direction (sales-side/purchase-side) is NOT here — it is a
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
        # Expense claims and payslips are not tax instruments, but they are documents.
        # This table already holds non-tax documents: pro forma invoices and receipts.
        # Using `other` would incorrectly classify both as uncategorized tax instruments
        # and distort future input-tax reporting.
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
    # payslip items (OFBiz InvoiceItemType's PAYROL_* family). Additions are
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
    # workflow definition, and national policy (social-insurance and housing-fund rates) in neither.
    "pay_component_type": (
        ("base_salary", "基本工资", "固定薪资；按 period_type 计（月/时/日/年）"),
        ("allowance", "补贴", "岗位/交通/通讯等固定补贴"),
        ("commission", "提成", "按比例计的销售提成——须同时说明 basis（按什么算）"),
        ("bonus", "奖金", "与这个人绑定的奖金安排；全员统一的规则属于工作流定义"),
        ("overtime_rate", "加班费率", "加班计薪标准"),
        ("other", "其他", "未归类的个人薪酬条款"),
    ),
    # Policy categories. `external_standard` also records external requirements:
    # Shanghai contribution-base standards are not company policies, but correct
    # payroll needs a published source with an issuer, date and provenance.
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
    # leave types. A vocabulary rather than a constrained column because the list
    # is genuinely local: paternity leave and bereavement leave exist in some workspaces and not
    # others, and their length is set by provincial regulation. Nothing in the
    # server branches on the value — how many days a type is worth, whether it
    # is paid, whether it needs a certificate, all of that is in the tenant's
    # leave policy and read by an agent. This list only keeps the spelling
    # consistent so "annual leave" and "annual leave" are not two different things.
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
