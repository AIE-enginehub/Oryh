# Oryh Access Admin API Reference

{{include:_common/api-auth-principal.md}}

写操作需要 `users.manage`；补发技能包**额外**需要 `keys.manage`。

## 读：先把现状看清

```text
GET /capabilities        → {capabilities: [{name, kind, title, description, scopable}], object_types: [...]}
                           kind=system 是服务端强制执行的固定词表；kind=custom 是租户自定义
                           scopable=true 的能力才能写成 verb:scope；object_types 是合法作用域取值
GET /roles               → [{id, name, title, description, permissions, is_system, user_count}]
GET /auth/users?size=200 → [{id, email, name, role, employee_id, status, invitation_pending}]
GET /tenant/api-keys?status=active   → 谁持有哪些凭据（需 keys.manage）
```

`GET /roles` 与 `GET /capabilities` 只需登录即可读，写才需要 `users.manage`。

## 角色

```json
POST /roles
{
  "name": "procurement",
  "title": "采购经办",
  "description": "下采购单与收货",
  "permissions": [
    "timesheet.submit_own", "expense.submit_own", "business_object.write:*",
    "todos.complete_own", "booking.own",
    "purchase_order.manage"
  ]
}
```

- `permissions` 是**全量覆盖**，不是增量：`PATCH` 传什么，角色就变成什么。要加一项，先 `GET /roles` 取现有数组，追加后整体发回。
- `name` 租户内唯一（409）；每个能力名必须存在于 `GET /capabilities`（422 会指出是哪一个）。

```json
PATCH /roles/{role_ref}
{"permissions": ["...现有的...", "purchase_order.manage"]}
```

`role_ref` 可以是角色 id，也可以是角色名。`title`/`description` 可单独改，不动 `permissions`。

```text
DELETE /roles/{role_ref}
```

- 系统角色 → 409 `system roles cannot be deleted`
- 仍有用户挂着 → 409 `role is assigned to users`（先把人挪走）

**锁死保护**（422，不要重试，向本人解释）：

```text
the admin role must keep users.manage (lockout guard)
tenant must keep at least one active user with users.manage (lockout guard)
```

第二条在改角色权限、改用户角色、停用用户三处都会触发。

## 自定义能力

```json
POST /capabilities
{"name": "jc.warranty.approve", "title": "保修卡审批资格", "description": "谁可以批保修卡"}
```

**自定义能力只在两处生效**：skill 分发的 `required_capability` 门控，以及流程定义里的路由判断。**服务端核心 API 从不检查它**——不要指望用它去拦某个接口。

- 名字与系统能力冲突 → 409
- `DELETE /capabilities/{name}`：系统能力不可删（409）；被任何角色授予、或被任何 skill 用作门控时不可删（409）

## 用户

```json
POST /auth/invitations
{
  "email": "zhangwei.taian@qq.com",
  "name": "张伟",
  "role": "vendor",
  "employee_id": "employee-id-if-the-record-exists"
}
```

邀请**故意不校验企业邮箱域名**——外部服务商用个人邮箱入驻走的就是这条路。角色必须已存在。邮箱全局唯一、员工档案最多绑一个用户（均 409）。

```text
POST /auth/users/{user_id}/resend-invitation      → 链接过期时重发
POST /auth/users/{user_id}/password-reset-email   → 让本人自己重设，你不要代设
```

```json
PATCH /auth/users/{user_id}
{"role": "procurement", "status": "active", "employee_id": null}
```

- `role` 是**覆盖**：他会失去原角色的全部能力。改之前先把原角色的 `permissions` 念给本人确认。
- `status`: `active` | `disabled`。停用会一并清除未使用的邀请与重置令牌。
- 未接受邀请的账号直接置 `active` → 422（他得先接受邀请）。

## 排查："他为什么没有那个 skill"

```text
GET /users/{user_id}/skills     → 需 users.manage
GET /roles/{role_ref}/skills    → 这个角色的人会收到什么（招人进来之前就能看）
```

```json
{"data": {"subject_label": "谢婷", "role": "member",
  "received": [{"name": "oryh-my-work", "reasons": ["capability"]}],
  "withheld": [
    {"name": "oryh-purchase-submit", "reasons": ["missing_capability"],
     "required_capability": "purchase.submit_own",
     "granted_by_roles": ["procurement", "admin"]},
    {"name": "jc-quote", "reasons": ["missing_capability", "not_in_audience"]}
  ]}}
```

`received` 就是他下次同步会装上的东西，与 bundle 同一份判定，不会不一致。

`granted_by_roles` 是"照着谁授权"的答案。一个能力已经有角色持有，就别再造
一个新能力——那正是 skill 的能力清单越滚越长的来源。

角色视图是按**角色本身**回答的：定向给某个恰好是这个角色的人的 skill，在这里
显示为 `not_in_audience`，因为下一个进这个角色的人拿不到它。

## 技能包与凭据

```text
POST /users/{user_id}/skill-bundle    → 需 users.manage + keys.manage
```

**会轮换该用户的 key，他本地现有的技能包立刻失效、必须重装。** 角色调整后的常规做法**不是**这个，而是让他自己跑一次 `$oryh-skill-sync`——key 不变，其他设备不受影响，新 skill 自动到位。

只有凭据泄露、或他确实拿不到 bundle 时才用这条，**且用前必须先告知他**。

## 审计

角色的建立、修改、删除都会写审计（`role.created` / `role.updated` / `role.deleted`）。
`role.updated` 的 detail 带四样：

```json
{"name": "member", "permissions": [...],
 "added": ["todos.assign"], "removed": ["booking.own"], "is_system": true}
```

`removed` 是"这次拿走了什么"的唯一答案——`permissions` 是覆盖写，光看结果
无法区分"刻意去掉"和"重建数组时漏了"。改完用 `GET /audit-logs?limit=20`
读回来念给本人听，尤其是 `is_system: true` 的那几次。

全量扫描需要 `users.manage`——你有。没有这项能力的人只能按记录或按自己查，
拿不到别人的凭证事件。所以"他说他查不到日志"通常不是故障。
