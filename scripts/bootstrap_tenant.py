from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy.exc import SQLAlchemyError

from app.db.session import create_ops_sessionmaker

SessionLocal = create_ops_sessionmaker()
from app.schemas import ApiKeyRead, TenantRead
from app.services.tenants import create_tenant_with_api_key


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a tenant and bootstrap API key.")
    parser.add_argument("--name", required=True, help="Tenant display name.")
    parser.add_argument(
        "--api-key-label",
        default="bootstrap",
        help="Label to store with the initial API key.",
    )
    parser.add_argument(
        "--status",
        default="active",
        choices=["active", "inactive"],
        help="Initial tenant status.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db = SessionLocal()
    try:
        tenant, api_key, plain_text_api_key = create_tenant_with_api_key(
            db,
            tenant_name=args.name,
            tenant_status=args.status,
            api_key_label=args.api_key_label,
        )
    except SQLAlchemyError as exc:
        db.rollback()
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    finally:
        db.close()

    payload = {
        "tenant": TenantRead.model_validate(tenant).model_dump(),
        "api_key": ApiKeyRead.model_validate(api_key).model_dump(),
        "plain_text_api_key": plain_text_api_key,
    }
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
