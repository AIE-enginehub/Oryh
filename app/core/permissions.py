from __future__ import annotations

# Permission grammar: "verb" or "verb:scope". A bare grant of a scopable verb
# or an explicit "verb:*" covers every scope; "verb:<object_type>" covers one.
#
# Three enforcement layers (documented boundary):
#   - system verbs guard the core API (code enforcement points below);
#   - custom capabilities (tenant-defined rows) guard skill-bundle
#     distribution and flow-routing eligibility — never the core API;
#   - the scope dimension extends automatically with the tenant's object
#     types: no code change when a tenant defines a new type.

# (name, scopable, title, description)
SYSTEM_CAPABILITIES: tuple[tuple[str, bool, str, str], ...] = (
    ("timesheet.submit_own", False, "提交自己的工时", "创建、填写、提交、重交自己的工时表"),
    # 请假. `submit_own` like a timesheet, because a leave request is a fact
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
    # 应收会计 and 应付会计 apart — 不相容职务分离 — without a second table. The
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
    # Payroll is the one thing in this system that must not be readable by every
    # credential in the workspace, so it gets a READ capability — the first one.
    # Everything else is tenant-scoped only.
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
    # 规章制度. Reading an INTERNAL policy needs no capability on purpose — an
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
        "按对象类型作用域，门禁汇总类 skill 的分发（如经理汇总日报）——business-objects 读取本身不受此闸控制",
    ),
    ("approval.record", False, "记录审批事实", "写入审批记录（approved/rejected/returned/commented）"),
    (
        "flow_run.record",
        False,
        "记录流程代理运行",
        "写入流程推进代理的运行台账（开始/结束/推进结果）——代理为自己的工作留痕，不推进任何单据",
    ),
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
        "登记库存台账与库存变动（收货、发出、盘点、借用、退回）；不含产品/供应商/客户主数据",
    ),
    # The treasury desk, split from the accounting desk on purpose: 钱账分离.
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
    ("users.manage", False, "用户与角色管理", "邀请用户、分配角色、管理角色与自定义能力"),
    ("keys.manage", False, "访问凭证管理", "签发、查看、停用工作空间与个人访问凭证"),
    ("object_types.manage", False, "对象类型管理", "定义对象字段与状态流程"),
    ("workflows.publish", False, "发布流程定义", "发布新的工作流定义版本"),
    ("skills.manage", False, "Skill 管理", "创建、修订、归档工作空间 skills"),
    ("purchase_order.manage", False, "采购下单与收货", "创建和维护采购订单、记录收货；不是'本人单据'——是采购职能"),
    ("tenant.act_for_any_employee", False, "代表任意员工", "越过'仅本人'限制，代表任何员工操作记录"),
)

SYSTEM_CAPABILITY_NAMES = frozenset(name for name, *_ in SYSTEM_CAPABILITIES)
SCOPABLE_VERBS = frozenset(name for name, scopable, *_ in SYSTEM_CAPABILITIES if scopable)

ALL_PERMISSIONS: tuple[str, ...] = tuple(
    name if not scopable else f"{name}:*" for name, scopable, *_ in SYSTEM_CAPABILITIES
)

# Seeded per tenant; tenants tune from here (e.g. strip approval.record from
# member and grant it via an approver role, or scope a 服务商 role to specific
# object types). todos.assign is deliberately NOT in member: assigning work to
# someone else is routing — the flow/admin side's write — and it also gates
# flow-side skill distribution (approval-notifier), which must not land in
# every member's bundle. Members complete their own todos; they do not mint
# them for colleagues.
DEFAULT_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "admin": ALL_PERMISSIONS,
    "member": (
        "timesheet.submit_own",
        "leave.submit_own",
        "expense.submit_own",
        "purchase.submit_own",
        "quotation.submit_own",
        "order.submit_own",
        "business_object.write:*",
        "approval.record",
        "todos.complete_own",
        "booking.own",
        "crm.own",
    ),
}


# Principal kinds for tenant-level (service) API keys.
#
# `Actor.kind` answers "is there a person behind this credential". Principal
# kind answers "whose machine holds it". A tenant's own service key is the
# tenant's root credential for automation — it issued the key to itself, so
# bypassing the permission layer is not a hole, it is the point. A hosted flow
# agent key is held by ORYH inside someone else's tenant, so it carries an
# enumerable grant set instead, reported on the key itself (`ApiKeyRead
# .permissions`) so the customer's answer to "what can your agent do in my
# company" is a list they can read, not a promise they have to take.
PRINCIPAL_TENANT_SERVICE = "tenant_service"
PRINCIPAL_HOSTED_FLOW_AGENT = "hosted_flow_agent"
PRINCIPAL_KINDS: tuple[str, ...] = (PRINCIPAL_TENANT_SERVICE, PRINCIPAL_HOSTED_FLOW_AGENT)

# Rendered wherever the hosted agent's writes are attributed. It comes from
# this constant, never from the key's label, so a tenant cannot mint a key that
# reads as ORYH's agent in its own audit trail.
HOSTED_FLOW_AGENT_DISPLAY_NAME = "ORYH 托管流程代理"

# Advancement, assignment, and a record of its own work — nothing else. The
# hosted agent moves flows and hands out todos. It cannot reshape identity or
# access (users/roles/keys), cannot file documents in someone's name
# (`*.submit_own`), cannot edit business object payloads, and cannot publish the
# tenant's own definitions or skills.
#
# `flow_run.record` is here so the runner needs no second, wider credential: the
# principal that did the work is the one that writes down having done it, in the
# tenant it did it in, signed as itself.
HOSTED_FLOW_AGENT_PERMISSIONS: tuple[str, ...] = (
    "timesheet.advance",
    "leave.advance",
    "expense.advance",
    "purchase.advance",
    "quotation.advance",
    "order.advance",
    "invoice.advance",
    "payment.advance",
    # the hosted agent runs the points-expiry sweep, which is a ledger write
    "billing_account.post:*",
    "business_object.advance:*",
    "approval.record",
    "todos.assign",
    # The flow agent is the side that assigns work, so it is the side that
    # tells people work arrived. Its own runtime has no mail transport — the
    # pi child's environment is a six-variable whitelist on purpose — so the
    # server sends on its behalf. See app/api/notifications.py.
    "notification.send",
    "flow_run.record",
)


def permissions_cover(permissions: frozenset[str], verb: str, scope: str | None = None) -> bool:
    if verb in permissions or f"{verb}:*" in permissions:
        return True
    return scope is not None and f"{verb}:{scope}" in permissions


def permissions_cover_any_scope(permissions: frozenset[str], verb: str) -> bool:
    """Does this actor hold `verb` under ANY scope?

    `permissions_cover(perms, "invoice.manage")` is False for someone holding
    only `invoice.manage:sales`, and that is right wherever the caller knows
    which scope it needs — the settlement path always does.

    The attachment gate does not. It asks a different question: "does this
    actor file attachment-backed records at all", and an 应收会计 scoped to
    销项 files exactly as many as one scoped to both. Asking the scoped
    question there produced a 403 on the upload for someone fully entitled to
    the record the upload was for.
    """
    if verb in permissions:
        return True
    prefix = verb + ":"
    return any(grant.startswith(prefix) for grant in permissions)


def validate_permission_grammar(grant: str, known_custom: frozenset[str]) -> str | None:
    """Return an error string if the grant is not a system verb (optionally
    scoped), not a custom capability, and therefore meaningless."""
    verb, _, scope = grant.partition(":")
    if verb in SYSTEM_CAPABILITY_NAMES:
        if scope and verb not in SCOPABLE_VERBS:
            return f"{verb!r} does not accept a scope"
        return None
    if grant in known_custom:
        return None
    return f"unknown capability {grant!r}"
