"""Chinese shipped permissions; codes, order and values are compatibility data."""

SYSTEM_CAPABILITIES: tuple[tuple[str, bool, str, str], ...] = (
    ("timesheet.submit_own", False, "提交自己的工时", "创建、填写、提交、重交自己的工时表"),
    # leave. `submit_own` like a timesheet, because a leave request is a fact
    # about the person filing it. What it deliberately does NOT carry is any
    # notion of entitlement: how many days somebody has is computed from the
    # tenant's policy, never stored, so there is nothing here to grant.
    ("leave.submit_own", False, "提交自己的请假", "创建、填写、提交、撤回、重交自己的请假单"),
    ("leave.advance", False, "推进请假状态", "请假单状态转换（审批终局、退回、销假）——流程推进权"),
    ("timesheet.advance", False, "推进工时状态", "工时表状态转换（审批终局、退回）——流程推进权"),
    ("expense.submit_own", False, "提交自己的报销", "创建、填写、提交、重交自己的报销单，含票据附件上传"),
    ("expense.advance", False, "推进报销状态", "报销单状态转换（审批终局、退回、标记打款）——流程推进权"),
    ("purchase.submit_own", False, "提交自己的采购申请", "创建、填写、提交、重交自己的采购申请"),
    ("purchase.advance", False, "推进采购申请状态", "采购申请状态转换（审批终局、退回、标记下单）——流程推进权"),
    ("quotation.submit_own", False, "提交自己的销售报价", "创建、填写、提交自己的报价单，含发送、成交/流失登记与改版"),
    ("quotation.advance", False, "推进报价单状态", "报价单状态转换（审批终局、退回、过期清扫）——流程推进权"),
    ("order.submit_own", False, "提交自己的销售订单", "创建、填写、提交自己的销售订单，含物流与交付事实维护"),
    ("order.advance", False, "推进销售订单状态", "销售订单状态转换（确认、发货、签收、取消）——流程推进权"),
    # Invoicing is a finance function, not "my own documents", so it follows the
    # purchase_order.manage shape rather than submit_own. It is scopable on the
    # direction (`invoice.manage:sales` / `:purchase`) so a workspace can keep
    # accounts-receivable accountant and accounts-payable accountant apart — segregation of incompatible duties — without a second table. The
    # scope dimension is the same grammar object types use; nothing in
    # permissions_cover needs to know what a scope means.
    (
        "invoice.manage",
        True,
        "开具/登记发票",
        "创建、编辑、提交发票；可按方向作用域（invoice.manage:sales 仅销项，:purchase 仅进项，:payroll 仅工资条，:reimbursement 仅员工报销）",
    ),
    ("invoice.advance", False, "推进发票状态", "发票状态转换（开具、退回、作废、坏账核销）——流程推进权"),
    ("payment.record", False, "登记收付款", "创建、编辑、提交收款与付款单；不含核销"),
    ("payment.advance", False, "推进付款状态", "付款状态转换（批准、拒绝、退回、标记已付）——流程推进权"),
    (
        "payment.apply",
        False,
        "核销",
        "把款项勾对到发票或报销单（含冲正）——与 payment.record 分开，出纳记账与会计核销可分职",
    ),
    # Payroll must not be readable by every credential in the workspace, so it
    # got a READ capability — the first one. Personal documents followed
    # (`*.read_all`, below), then shared paper (`*.read`, further below).
    (
        "payroll.read",
        False,
        "查看薪酬",
        "查看薪资档案与工资条；不持有此权限的凭据看不到任何工资条，但任何人都看得到自己那张",
    ),
    (
        "payroll.manage",
        False,
        "定薪",
        "写入薪资档案（调薪）——与出工资条（invoice.manage:payroll）分开，定薪是另一层的决定",
    ),
    # company policies. Reading an INTERNAL policy needs no capability on purpose — an
    # employee handbook nobody may read is not a handbook. The gate is per-row:
    # a policy marked `restricted` names the capability it wants, reusing the
    # existing scopable grammar rather than inventing a second one.
    (
        "policy.manage",
        False,
        "起草制度",
        "新建与修改制度草稿、维护制度规则；草稿只有持有此权限的凭据看得到——"
        "草稿的裁员方案泄露比发布版更糟",
    ),
    (
        "policy.publish",
        False,
        "发布/废止制度",
        "把草稿发布为生效版本（并关闭上一版），以及废止已发布的制度——"
        "与起草分开，因为发布是一个权威行为，不是一次编辑",
    ),
    (
        "billing_account.manage",
        False,
        "账户管理",
        "为客户/供应商/员工开立往来账户与积分账户，设定授信额度、冻结与销户",
    ),
    (
        "billing_account.post",
        True,
        "记账户流水",
        "写入账户增减流水（充值、扣减、发放积分、兑换、过期）；可按计量类型作用域"
        "（billing_account.post:currency 仅钱，:points 仅积分）——发积分是高欺诈风险动作，与开户分权",
    ),
    ("business_object.write", True, "创建/编辑业务对象", "按对象类型作用域；含链接与软删/恢复"),
    ("business_object.advance", True, "推进业务对象状态", "按对象类型作用域的状态转换——流程推进权"),
    (
        "business_object.summarize",
        True,
        "汇总业务对象",
        "按对象类型作用域，门禁汇总类 skill 的分发（如经理汇总日报）；持有它也读得到该类型的对象",
    ),
    ("approval.record", False, "记录审批事实", "写入审批记录（approved/rejected/returned/commented）"),
    (
        "flow_run.record",
        False,
        "记录流程代理运行",
        "写入流程推进代理的运行台账（开始/结束/推进结果）——代理为自己的工作留痕，不推进任何单据",
    ),
    # Reading a person's documents. Everyone reads their own and whatever was
    # routed to them; reading EVERYONE'S is a grant (app/api/visibility.py).
    # The family's `advance` and the desks downstream of it imply it — nobody
    # approves, ships or pays blind — so these exist for the role that only
    # looks: HR reading leave, a sales director reading the pipeline.
    ("timesheet.read_all", False, "查看全部工时", "查看所有人的工时表；没有此权限只看得到自己的，以及转到自己手上审批的"),
    ("leave.read_all", False, "查看全部请假", "查看所有人的请假单；没有此权限只看得到自己的，以及转到自己手上审批的"),
    ("expense.read_all", False, "查看全部报销", "查看所有人的报销单与票据；没有此权限只看得到自己的，以及转到自己手上审批的"),
    ("purchase.read_all", False, "查看全部采购申请", "查看所有人的采购申请；没有此权限只看得到自己的，以及转到自己手上审批的"),
    ("quotation.read_all", False, "查看全部报价", "查看所有销售的报价单；没有此权限只看得到自己的，以及转到自己手上审批的"),
    ("order.read_all", False, "查看全部销售订单", "查看所有销售的订单与退单；没有此权限只看得到自己的，以及转到自己手上的"),
    ("crm.read_all", False, "查看全部线索与商机", "查看所有人的线索、商机与跟进记录；没有此权限只看得到自己的"),
    # Reading the documents nobody files "as themselves" — invoices, payments,
    # purchase orders, freight, stock, the workspace's own object types,
    # account balances. Until 2026-09-25 belonging to the workspace read all of
    # them, which is right for an employee and wrong for the outside party a
    # workspace lets in: a vendor with warranty-card rights read every other
    # vendor's invoice. Each family now has a read grant, held by `member` by
    # default and implied by the desks that write the family (a scoped grant,
    # `invoice.manage:sales`, implies the read of its scope only). A credential
    # without it reads what names it, what it wrote and what was routed to it
    # — the personal-family rule, applied to shared paper. (app/api/visibility.py)
    (
        "invoice.read",
        True,
        "查看发票",
        "查看发票；可按方向作用域（invoice.read:sales 仅销项，:purchase 仅进项）；工资条另受 payroll.read 约束；"
        "没有此权限只看得到自己经办或收款的，以及转到自己手上的",
    ),
    ("payment.read", False, "查看收付款", "查看收款与付款单及核销记录；没有此权限只看得到自己经办或收款的，以及转到自己手上的"),
    ("purchase_order.read", False, "查看采购订单", "查看采购订单及其行；没有此权限只看得到自己经办的，以及转到自己手上的"),
    ("shipment.read", False, "查看运单", "查看运单及其行；没有此权限只看得到转到自己手上的"),
    ("inventory.read", False, "查看库存", "查看库位、库存流水与拣货单；没有此权限只看得到转到自己手上的拣货单"),
    (
        "business_object.read",
        True,
        "查看业务对象",
        "按对象类型作用域（business_object.read:warranty_card 仅保修卡）；写、推进、汇总某类型的权限都隐含读它；"
        "没有此权限只看得到自己创建的，以及转到自己手上的",
    ),
    ("billing_account.read", False, "查看往来账户", "查看往来账户、积分账户及其流水；没有此权限只看得到自己名下的"),
    ("todos.assign", False, "为他人创建待办", "创建指派给任何员工的待办"),
    (
        "notification.send",
        False,
        "发送工作通知",
        "就待办分配、退回、审批结果向当事员工发送邮件通知——收件地址由服务器"
        "从员工档案解析，调用方不能指定；不能发送任意内容给任意地址",
    ),
    ("todos.complete_own", False, "完成自己的待办", "完成指派给自己的待办"),
    ("booking.own", False, "预订资源", "以自己名义创建/修改/取消资源预订"),
    # The sales pipeline is personal work like a booking, not a routed
    # document: no approval half exists, so the one grant files AND advances
    # your own leads and opportunities — and drives the lead's conversion
    # bridge, which creates the customer it qualified into.
    # A campaign is marketing's, run for everyone: not personal, no approval
    # half — one functional grant files, advances, and curates the members.
    # Attribution (a lead's or a deal's campaign_id) is written by whoever
    # files the lead or deal; reading campaigns needs nothing beyond membership.
    (
        "campaign.manage",
        False,
        "市场活动管理",
        "创建、维护和推进市场活动,登记活动触达的线索与客户;线索与商机的活动归因由填单人写",
    ),
    (
        "crm.own",
        False,
        "维护自己的销售线索与商机",
        "以自己名义创建、推进、转化销售线索,维护自己的商机直至赢单/输单;转化桥会代为建立客户档案",
    ),
    (
        "master_data.manage",
        False,
        "主数据管理",
        "创建、编辑和归档项目、供应商、客户、产品、SKU 与资源等工作空间主数据",
    ),
    # Split out of master_data.manage (plan 2026-10-14): a project is where a
    # deal lands after it is won, and the salesperson or project manager who
    # opens it is not the catalog desk. master_data.manage still implies it.
    (
        "project.manage",
        False,
        "项目管理",
        "创建、编辑、归档项目，并把项目链接到客户、商机、合同与负责人；成交建项目（POST /opportunities/{id}/project）也需要它",
    ),
    # Split out of master_data.manage. The stock ledger is a warehouse's daily
    # work — receiving, issuing, stock-takes, the informal movements nobody has
    # a document for — and a keeper is not a catalog administrator. Under one
    # capability a warehouse role held every product, vendor and customer
    # record or nothing at all. Receiving against a purchase order stays with
    # purchase_order.manage: that is a procurement act, and it posts the
    # movement itself.
    (
        "inventory.manage",
        False,
        "库存管理",
        "登记库位、盘点导入、库存单据过账（报损、调拨、生产入库等）与订单占货；库存流水只由这些业务动作产生。含发货运单的权限",
    ),
    # Split out of inventory.manage. The order desk that ships what it sold
    # files freight legs and posts them — and must NOT be able to touch a
    # stock position or a stock document. An agent that heard "dispatch goods" and
    # wrote a bare ledger row did so because one grant covered both; this
    # is the grant that covers only the shipment. inventory.manage implies
    # it (the keeper who holds the shelf also ships from it).
    (
        "shipment.manage",
        False,
        "发货与运单",
        "建立、推进运单并过账（销售发货、退货收件、采购退货发出）；不含库位、盘点与库存单据",
    ),
    # The treasury desk, split from the accounting desk on purpose: separation of treasury and accounting.
    # Whoever holds the bank register must not need — and does not get — the
    # payment documents' write; whoever files payments cannot touch the
    # register. Deliberately granted to NO shipped role: which person is the
    # cashier is the tenant's first treasury decision, and the setup report
    # names the gap until they make it.
    (
        "fin_account.manage",
        False,
        "资金账户与银行流水",
        "登记资金账户（银行/现金/微信支付宝等第三方支付）与交易流水，导入对账单，链接付款单对账；不含付款单据本身",
    ),
    # Contracts: a natural-language file plus the clauses located inside it.
    # One functional grant files, curates and advances (the purchase-order
    # shape — approval, where a tenant wants one, is todos and approval
    # facts against the contract, driven by the tenant's own agents), and
    # it is scopable on the SIDE derived from the counterparty: a buyer's
    # role holds `contract.manage:purchase` and never sees a sales contract.
    # Reads are gated by the same grant — a contract carries the prices
    # negotiated with a factory, not workspace-wide reading.
    (
        "contract.manage",
        True,
        "合同管理",
        "录入合同与原件、定位条款、推进状态、挂接订单/发票/付款;可按方向作用域"
        "(contract.manage:purchase 仅采购侧,:sales 仅销售侧);读取同样需要此能力",
    ),
    ("employees.manage", False, "员工管理", "创建和维护员工档案"),
    ("users.manage", False, "用户与角色管理", "邀请用户、分配角色、管理角色与自定义能力；只能授出自己持有的权限，不能把人请进 admin 或造出比自己更宽的角色——那是管理员的事"),
    ("keys.manage", False, "访问凭证管理", "签发、查看、停用个人访问凭证；不能为管理员或持有自己没有的用户/凭证/Skill 管理权限的人签发，工作空间凭证只由管理员签发"),
    ("object_types.manage", False, "对象类型管理", "定义对象字段与状态流程"),
    ("workflows.publish", False, "发布流程规则", "起草、发布与废止审批流程、数据要求、单据联动三类业务规则（business_rules）"),
    ("skills.manage", False, "Skill 管理", "创建、修订、归档工作空间 skills"),
    # The narrow write: a workspace's own refinement of one shipped skill —
    # the product-matching rules, the report style — without the registry.
    # An order desk that hits an unmapped listing needs to add a rule, not
    # to publish skills. Scopable by skill name.
    (
        "skills.calibrate",
        True,
        "调整技能校准",
        "只写某个已发布技能的 calibration(本工作区对该技能的补充规则,如商品匹配规则),并读取该技能;"
        "可按技能名作用域(skills.calibrate:oryh-product-matching);不能改技能文件、受众或状态",
    ),
    ("purchase_order.manage", False, "采购下单与收货", "创建和维护采购订单、记录收货；不是'本人单据'——是采购职能"),
    ("tenant.act_for_any_employee", False, "代表任意员工", "越过'仅本人'限制，代表任何员工操作记录"),
)
