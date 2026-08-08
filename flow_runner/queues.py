"""Where a subscription's work queue is — read from the subscription, not here.

This module used to hold the answer: an `entity_type → REST path` table, in a
process that by design imports nothing from `app`. Two copies of one mapping,
and the one over here had no way to notice the other had grown. It went stale
the moment invoices and payments shipped, and the failure was silent in the
worst way — an unlisted type fell through to `/business-objects`, which answers
nothing for a builtin family, which reads as an empty queue. A subscription that
could never work looked exactly like one with nothing to do.

The server now sends `queue_path` and `entity_kind` with each subscription, from
the same declaration the API validates against. What is left here is the reading
of those fields, and a fallback for a server too old to send them.
"""

from __future__ import annotations

from typing import Any

# Only for a control plane that predates `queue_path`. A builtin family named
# here would be a third copy of the table, so nothing is named here: an old
# server plus a builtin subscription is a case the caller must not paper over.
BUSINESS_OBJECT_QUEUE_PATH = "/business-objects"


def queue_location(
    subscription: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """The path and query that find this subscription's unattended records.

    `object_type` is injected for tenant-defined types so the caller never has
    to know which shape it is dealing with — that distinction is the server's
    `entity_kind`, not a guess made from the name.
    """
    entity_type = subscription["entity_type"]
    query = dict(subscription.get("queue_filter") or {})
    path = subscription.get("queue_path") or BUSINESS_OBJECT_QUEUE_PATH
    if workflow_entity_kind(subscription) == "business_object":
        return path, {"object_type": entity_type, **query}
    return path, query


def workflow_entity_kind(subscription: dict[str, Any]) -> str:
    """The workflow-definition namespace for this queue's document family.

    Defaults to `business_object` only when the server did not say — which is
    the pre-`queue_path` control plane, where every subscription the runner
    could poll at all was a tenant-defined one anyway.
    """
    return subscription.get("entity_kind") or "business_object"
