## 假期余额是算出来的，不是查出来的

There is no balance field, no allowance table and no entitlement endpoint, and
looking for one is the first wrong turn. **A leave balance is not a fact
anybody recorded** — it is what the workspace's rules imply about this person
today, and the rules change. A company that revises 年假 in June, or backdates
a 调休 ratio to January, changes every balance in the company retroactively;
a stored number would be a pile of figures that were true under text nobody
follows any more.

So you compute it, every time, from two things the server does keep:

```text
GET /policies?category=hr&status=published&in_force_on=2026-06-15   ← the rules
GET /employee-leaves?employee_id={id}&overlapping_from=…&overlapping_thru=…  ← the facts
GET /employees/{id}                                                 ← hire_date, for 工龄
```

`in_force_on` is why this is better than a stored balance rather than merely
different: asked "how many days did I have in March", you pass the March date
and get the rule that applied **in March**. A ledger could not answer that
without rewriting itself.

### The formula

```text
可用 = 应得(policy, 工龄, 期间) − 已批准 − 在途
```

- **应得** comes from the policy. Read `rules_json` if the document carries one
  — a tier table is easier to apply than a paragraph — and fall back to the
  prose. The policy also says what to do about a partial year, whether unused
  days carry over, and whether the balance may go negative.
- **已批准** is the sum of `duration_days` over rows in the tenant's approved
  states, of the leave type in question, overlapping the period.
- **在途** is the same sum over `submitted` rows. **Do not leave this out.** It
  is what stops somebody spending the same three days twice by filing two
  requests before either is decided — there is no server-side hold, and this
  subtraction is the whole of the protection.

`overlapping_from`/`overlapping_thru` returns a request that straddles the
period boundary. The policy says how to split it; do not silently count it as
belonging to whichever year it started in.

### 报数的规矩

**Show the arithmetic, every time — in one line, answer first.** Not a bare
"你还有 4 天", and not a paragraph either:

> **可用 4 天** = 应得 10（工龄 7 年，《员工请假管理制度》v3）− 已批 5 − 在途 1

Expand the derivation — hire date, the tier table, how a straddling request
was split — only when the person asks or disputes the number.

Three reasons this matters more here than elsewhere. The number came from a
document that can be revised, so the person should see which version produced
it. Two agents that disagree can be compared line by line, and the argument
lands on the policy text — **which is the thing to fix**, not the data. And a
person who is told a bare number cannot tell a rule change from a mistake.

Cite the policy's `code` and `version`. If no leave policy is published, say so
and stop — do not fall back to statutory defaults you happen to know. The
workspace's rule being unwritten is a fact worth surfacing, and guessing it
puts an answer in somebody's mouth that nobody in the company agreed to.

### 边界

- **不要为了记住余额去写任何东西** —— 不建自定义对象、不动 billing account、不在
  `custom_fields` 里存一个数。那正是这套设计要避免的：把一个推论固化成伪事实。
- Over-entitlement is not yours to refuse. Filing a request for more days than
  the balance allows is legal — it is a request. Say clearly that it exceeds
  the balance and by how much, then let the person decide whether to file and
  the approver decide whether to grant.
- 调休 is the same computation with a different source for 应得: approved
  overtime on the timesheets, converted by whatever ratio the policy states.
  Same rule — read the ratio, do not assume 1:1.
