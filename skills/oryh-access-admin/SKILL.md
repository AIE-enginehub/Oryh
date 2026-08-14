---
name: oryh-access-admin
description: Use when an administrator's AI agent needs to change who can do what in oryh — 给某人开某项权限（"让谢婷也能下采购单"）、新建或调整角色（"建一个采购经办角色"）、邀请同事或外部服务商入驻、换岗改角色、停用离职账号、补发技能包或访问凭证。Covers the capability catalog, roles as the unit of grant, user lifecycle, and what each change does to the person's installed skills. Requires users.manage. It never approves, never files documents, and never grants itself more than it already holds.
required_capability: users.manage
---

# Oryh Access Admin

Who can do what is decided in exactly three places, and confusing them is the
most common way this goes wrong:

- **能力（capability）** — 一个动词，如 `purchase_order.manage`。系统能力由服务端强制执行；租户自定义能力**只在 skill 分发与流程路由处生效，服务端核心 API 从不检查它**。
- **角色（role）** — 一组能力。**授权的唯一单位。**
- **用户（user）** — 一个人，**只能挂一个角色**。

所以"给谢婷加一个权限"这句话在系统里没有直接对应的动作。见下方"授权的三条路"——**选哪条是本 skill 最重要的判断**，不是机械操作。

{{include:_common/answer-the-question.md}}

## Trigger Examples

- "让谢婷也能下采购单和收货"
- "建一个采购经办的角色"
- "小李换到销售部了，权限改一下"
- "邀请泰安的张伟进来，他只做保修卡"
- "王工离职了，把账号停掉"
- "谁能审批报销？把权限矩阵给我看看"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # 管理员的用户绑定 key（需 users.manage）
```

补发技能包（`POST /users/{id}/skill-bundle`）**额外需要 `keys.manage`**；没有就会 403，那是角色配置问题，不要重试。

## Steps

1. **先看清现状，再谈改法。** 三个只读调用：
   `GET /capabilities`（系统 + 自定义能力，及可作用域的对象类型）、
   `GET /roles`（每个角色持有哪些能力、是不是系统角色）、
   `GET /auth/users`（谁挂着哪个角色）。
   把"谁现在能做这件事"数出来告诉本人——常常一数就发现问题不是缺权限，而是权限过于集中。

2. **判断走哪条路**（下一节），**并把代价讲清楚再动手**。授权是影响面大的改动：先说清方案与影响，得到本人明确同意，再写。

3. **执行**，一次只改一件事，改完读回确认。

4. **告诉本人后续会发生什么**：角色一改，那个人的 agent 在下次 `$oryh-skill-sync` 就会自动拿到新增的 skill——**不需要你补发技能包，也不该补发**（见"技能包与凭据"）。

## 授权的三条路

用户只能有一个角色，所以"让谢婷也能下采购单"有三种实现，代价各不相同：

| 路 | 做法 | 代价 | 什么时候选 |
|---|---|---|---|
| **A 拓宽她现有的角色** | `PATCH /roles/{role_ref}` 给她当前的角色加上该能力 | **现在和将来**每个挂这个角色的人都会得到它 | 这项权限确实属于这个岗位 |
| **B 换到已有的另一个角色** | `PATCH /auth/users/{id}` 改 `role` | 她**失去**原角色的全部能力 | 是换岗，不是兼任 |
| **C 新建一个角色** | `POST /roles` 后再把人挂过去 | 多一个角色要维护 | 这是一份新职责，且不该顺带给出别的东西 |

**默认倾向 C**，除非这项权限本就属于那个岗位。理由：A 是会悄悄扩大的口子——今天只有一个人挂 `finance_reviewer`，明天新来的财务也自动获得了采购下单权。

**把 B 当成陷阱来防**：改 `role` 是覆盖不是追加。改之前先把她当前角色的能力读出来念给本人听，确认这些是可以丢的。

**但先算一次包含关系**：如果目标角色的能力**完全包含**她当前角色的（常见于 `member` → 某个"member 基线 + 一项"的角色），那 B 就是纯增量、零损失，此时**不要**为它新建一个几乎一样的角色——那只是多一个要维护的角色。两个角色的 `permissions` 做一次集合比较就能判断，把结果念给本人听。

**"兼任"在当前模型里做不到**——一人一角色。真要兼任，只能新建一个把两边能力并起来的角色（路 C）。这是模型限制，如实说，别假装能做到。

## 写之前必须说出口的三件事

- **最小授权**：只给要办的事所需的那一项。要开采购下单，就只加 `purchase_order.manage`，不要顺手给 admin。
- **不相容职责**：某些能力放在一起会让同一个人既做承诺又做确认。典型的是 `purchase_order.manage` ——它**同时**包含下单与收货，等于"自己订货、自己确认到货"。这是采购内控的经典缺口：**要指出来**，让本人决定是接受还是把收货分给别人（注意：当前该能力无法拆分，只能靠分派不同的人来缓解）。
- **谁会因此获得权限**：走路 A 时，把现在挂着这个角色的人全部列出来。
  `GET /roles` 的 `user_count` 直接给出人数——先说数字，再说名字。

## 收权：另外三件必须说出口的事

上面三条是授权形状的。**收权不是它们的镜像**，有自己的坑：

- **谁会因此失去权限**——`GET /roles` 的 `user_count` 就是人数，说出数字和角色名
  （要点名到人再 `GET /auth/users?role=<name>`）。没有人会来报告"我悄悄少了一个
  权限"；他们只会在下次要用的时候发现做不了。
- **在途的活会不会断**：这项能力是不是正卡在某个人手上的半截流程里。
  例如取消 `booking.own` 的同时，那些人也失去了**改期和取消**——`booking.own`
  是"订/改/取消"打包的一项，拆不开。收权前先看有没有未来的预订、未完的待办。
- **这一项是不是捆着别的**：能力不是都能按你想的粒度切。`booking.own` 不分资源
  类型，收掉会议室就等于收掉全部可预订资源。**做不到的事如实说**，别让本人
  以为拿到了一个更精细的结果。

**`PATCH /roles/{role_ref}` 是整体覆盖。** 先 `GET /roles` 读出 `permissions`，
在它的基础上删掉那一项再写回去——凭记忆重建这个数组，漏掉的那一项和你刻意
去掉的那一项在服务端和审计里长得一模一样。改完再读一次，确认只少了该少的。

**改系统角色（`is_system: true`，尤其是 `member`）要单独说一句。** 服务端不会拦
你——它是管理员的正当操作——但 `member` 是绝大多数人的角色，也是**每一个未来
新人**的默认角色。改它等于改公司的默认值。审计里 `role.updated` 的 detail 现在
带 `added`/`removed`/`is_system`，改完读回去念给本人听。

## 服务端会拦你的地方（先解释，别重试）

- **锁死保护**：`admin` 角色不能移除 `users.manage`；任何改动都不能让租户失去最后一个持有 `users.manage` 的活跃用户（改角色权限、改用户角色、停用用户三条路都会撞上）→ **422**。这不是 bug，是防止把自己锁在门外；如实说明并给替代方案。
- **系统角色不能删**（409）；**有人在用的角色不能删**（409）——先把人挪走。
- **自定义能力**：被任何角色授予、或被任何 skill 用作 `required_capability` 时不能删（409）；名字与系统能力冲突时不能建（409）。
- **能力名必须存在**：角色里写一个不存在的能力 → 422，报文会指出是哪一个。别猜名字，从 `GET /capabilities` 里取。
- **作用域语法**：只有 `scopable: true` 的能力能写成 `verb:scope`（如 `business_object.write:warranty_card`）；给不可作用域的能力加冒号 → 422。作用域取值来自 `GET /capabilities` 返回的 `object_types`。
- **用户激活**：未接受邀请的账号不能直接置为 `active`（422）——他得先接受邀请。

## 用户生命周期

- **邀请**：`POST /auth/invitations`（邮箱 + 角色，可选 `employee_id` 绑定员工档案）。**邀请故意不校验企业邮箱域名**——外部服务商用个人邮箱入驻走的就是这条路。链接过期了用 `POST /auth/users/{id}/resend-invitation`。
- **换岗/停用**：`PATCH /auth/users/{id}`（`role` / `status` / `employee_id`）。停用会**同时清掉未使用的邀请与重置令牌**，避免账号日后重新启用时旧链接复活。
- **忘记密码**：`POST /auth/users/{id}/password-reset-email`。**不要**替人设密码——这个 skill 不碰密码。

## 留痕：哪些动作有审计，哪些没有

改完之后本人常会问"以后怎么查"。**如实回答，别含糊**：

| 动作 | 有审计吗 |
|---|---|
| 建/改/删角色（含改 `description`） | **有** —— `role.created` / `role.updated` / `role.deleted`；`role.updated` 的 detail 带 `added` / `removed` / `is_system` |
| **改某个人挂哪个角色**、改状态、改邮箱 | **有** —— `user.updated`，detail 里每个变化的字段都带 `{"from": …, "to": …}` |
| 签发技能包 | **有** —— `skill_bundle.issued` |
| 邀请 | **没有** —— `POST /auth/invitations` 目前不写审计 |

所以"谁在什么时候把谁从 member 改成了 partner"是**查得到的**：

```text
GET /audit-logs?action=user.updated&entity_id={user_id}
→ detail: {"role": {"from": "member", "to": "partner"}, "email": "…"}
```

**没有写审计的接口**——`GET /audit-logs` 是只读的，不要编造一个写入口。也**不要**把说明文字写进角色的 `description` 来"补留痕"：权限变更和角色变更本来就有审计，那么做只是往租户配置里塞进一段以后会被当成事实读的话，而且没人要求你写。

## 技能包与凭据

角色一改，那个人**能拿到的 skill 集合**随即改变。但两条路的代价天差地别：

- **让他自己同步**（默认，几乎总是对的）：他的 agent 跑一次 `$oryh-skill-sync`，新 skill 自动到位，**key 不变，其他设备不受影响**。
- **管理员补发** `POST /users/{id}/skill-bundle`：**会轮换他的 key**，他本地现有的技能包**立刻失效、必须重装**。只在凭据泄露或他确实拿不到 bundle 时才用，**用之前必须先告诉他**。

**能力不是唯一的一根轴**：skill 还可以被**定向**到指定的角色或个人（`distribution_mode: "targeted"`）。两者是 AND——定向只能在能力允许的范围内收窄，永远不能越权。所以"他有能力却收不到某个 skill"是**受众**问题不是权限问题，归 `$oryh-skill-author` 管；反过来"他在受众里却收不到"才是这里的问题：他缺那份 skill 要求的能力。

**别靠推理判断是哪一种，问服务端**：

```text
GET /users/{id}/skills     → received[] + withheld[]，每条都带 reason
```

`reasons` 会把**所有**拦住他的原因都列出来，不是只列第一个。两条轴同时挡住
时两样都得改：只补能力，他再同步一次照样收不到。

`missing_capability` 归你管，响应里的 `granted_by_roles` 是哪些角色**目前**
持有这项能力——照着授权，别新造一个能力，也别把它当成"让他转成那个角色"，
那通常是提权而不是修复。

**收权之后再读这个字段要格外小心**：你刚把某项能力收窄到两三个角色，
`granted_by_roles` 就正好列出那两三个——它长得像"把人挪进去就好了"，
而那恰恰是你这次改动要防的事。它回答的是"现在谁有"，不是"该让谁有"。`not_in_audience` 不归你管，改权限也解决不了，转给
`$oryh-skill-author`。人肉推能力矩阵推错的代价是给人开了一项他本不需要的
权限，而且没人会发现。

**收权同样要走这一步**：改完再读一次，确认你没有连带摘掉别的东西。
`PATCH /roles/{role_ref}` 是整体覆盖，漏写一项和刻意去掉一项在服务端和审计里长得一模一样。

## What This Skill Never Does

- 给自己或自己的角色增加当前没有的能力。要提权，让另一个管理员来做。
- 批准任何单据、代写审批事实、派工作待办——那些是各自角色的 agent 的事。
- 删除系统角色，或把租户改成没有管理员。
- 编造能力名或作用域取值：一律从 `GET /capabilities` 取。
- 替人设置密码，或在未告知的情况下轮换别人的 key。
- 在没讲清影响面、没得到明确同意之前动手改权限。

## Reference

- [references/api.md](references/api.md): 能力目录、角色与用户的读写模板，以及每个拦截的报文。
