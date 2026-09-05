"""Tell a person that work reached them — sent by the server, decided by the agent.

The flow agent is the side that assigns work, so it is the side that should say
so. It cannot: the pi child's environment is a six-variable whitelist built
from an allowlist on purpose ("a deny-list misses the secret nobody thought to
name"), and there is no mail transport in it. Widening that whitelist to carry
SMTP credentials would hand a model process the mail server, which is a worse
trade than this endpoint.

So the decision stays with the agent — whether to notify is the tenant's
workflow definition's call, read at routing time — and the delivery happens
here, on the same SMTP the invitations and password resets already use.

Two things are deliberately NOT parameters:

* **The address.** It is resolved from the employee record. An agent cannot
  send to an address it chose, which is the structural version of the rule a
  tenant's own notification skill had to state in prose ("绝不猜邮箱"): a
  message to a guessed address is worse than none, because it looks delivered.
* **The body.** The caller supplies a title, an optional verbatim detail, and
  an event kind; the wording is assembled here. An endpoint that accepted
  arbitrary text would be an open mail relay wearing a business API's clothes.

Found because production had none of this: for one live tenant the notifier
skill was invoked in 0 of 60 flow runs, and when a customer wrote their own to
fill the gap, it sent through a mail tool their own agent happened to have —
which the flow runner does not.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Actor, get_actor, require_permission
from app.core.request_context import resolved_base_url
from app.db.session import get_db
from app.models import Employee, Todo
from app.schemas import SendNotificationRequest
from app.services.audit import record_audit
from app.services.emails import send_work_notification

router = APIRouter()

# What the console can show the person when they follow the link. Every event
# lands them in the same place — their queue — because that is where the work
# is; the mail says which item and why, not what to click through to.
NOTIFIABLE_EVENTS = ("assigned", "returned", "approved", "rejected")


@router.post("/notifications", status_code=status.HTTP_202_ACCEPTED)
def send_notification(
    payload: SendNotificationRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Email one employee about one work event — or about everything one run
    assigned to them, as one message.

    202, not 201: nothing is stored, and SMTP acceptance is not delivery. The
    response says what was attempted and to whom, so a flow agent can report
    "told 张三" or "李四 has no address on file" rather than guessing.
    """
    require_permission(actor, "notification.send")

    if payload.event not in NOTIFIABLE_EVENTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"event must be one of {', '.join(NOTIFIABLE_EVENTS)}",
        )

    employee = db.scalar(
        select(Employee).where(
            Employee.tenant_id == actor.tenant_id, Employee.id == payload.employee_id
        )
    )
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="employee not found")

    if not employee.email:
        # Not an error: the flow agent did its part, and the workspace has a
        # gap only a person can close. Saying which person is the useful half.
        return {
            "data": {
                "delivered": False,
                "reason": "no email address on the employee record",
                "employee_id": employee.id,
                "employee_name": employee.name,
            },
            "meta": {},
        }

    todos: list[Todo] = []
    if payload.todo_ids:
        # A link to a todo that is gone, or that belongs to somebody else, sends
        # the reader somewhere confusing. Cheap to check, and it keeps the
        # endpoint from being a way to probe other tenants' ids. All-or-nothing:
        # a list with one stranger's item in it is refused whole, so the message
        # never quietly names fewer items than the caller believes it does.
        wanted = list(dict.fromkeys(payload.todo_ids))
        found = {
            todo.id: todo
            for todo in db.scalars(
                select(Todo).where(
                    Todo.tenant_id == actor.tenant_id,
                    Todo.employee_id == employee.id,
                    Todo.id.in_(wanted),
                )
            )
        }
        if len(found) != len(wanted):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="todo not found for this employee",
            )
        todos = [found[todo_id] for todo_id in wanted]

    # the todos are the message: their titles, in the order the caller named
    # them, with `title` as the one-line summary only when the caller gave one
    items = [todo.title for todo in todos]
    title = payload.title or (items[0] if len(items) == 1 else f"{len(items)} 项工作")
    send_work_notification(
        to=employee.email,
        recipient_name=employee.name,
        event=payload.event,
        title=title,
        items=items if len(items) > 1 else None,
        detail=payload.detail,
        actor_name=payload.actor_name,
        link=f"{resolved_base_url()}/console/todos",
    )
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="notification.sent",
        entity_type=payload.entity_type or "employee",
        entity_id=payload.entity_id or employee.id,
        actor=actor.label,
        # The address is not recorded: the employee id resolves it, and a trail
        # that repeats every address becomes its own contact-data export.
        detail={
            "event": payload.event,
            "employee_id": employee.id,
            "title": title,
            "todo_ids": [todo.id for todo in todos],
        },
    )
    db.commit()
    return {
        "data": {
            "delivered": True,
            "employee_id": employee.id,
            "employee_name": employee.name,
        },
        "meta": {},
    }
