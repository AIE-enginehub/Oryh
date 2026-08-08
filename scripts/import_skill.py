"""Import a skill directory into a tenant as data.

Usage:
    python scripts/import_skill.py <skill_dir> --tenant-id <uuid> [--update]

Reads every file under <skill_dir> (SKILL.md required), extracts name,
description, and required_capability from the SKILL.md frontmatter (the same
fields app/services/provisioning.py reads for the shipped product catalog),
and creates the tenant skill. With --update, an existing skill of the same
name is replaced (version bump on file changes; required_capability always
refreshed from frontmatter, matching product-skill provisioning behavior).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import create_ops_sessionmaker

SessionLocal = create_ops_sessionmaker()
from app.models import TenantSkill


def read_skill_dir(skill_dir: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(skill_dir.rglob("*")):
        if path.is_file():
            files[str(path.relative_to(skill_dir))] = path.read_text(encoding="utf-8")
    if "SKILL.md" not in files:
        raise SystemExit(f"{skill_dir} does not contain SKILL.md")
    return files


def parse_frontmatter(skill_md: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    lines = skill_md.splitlines()
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if ":" in line:
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()
    return meta


def import_skill(db: Session, tenant_id: str, skill_dir: Path, update: bool = False) -> TenantSkill:
    files = read_skill_dir(skill_dir)
    meta = parse_frontmatter(files["SKILL.md"])
    name = meta.get("name") or skill_dir.name
    description = meta.get("description")
    required_capability = meta.get("required_capability") or None
    title = name.replace("-", " ").title()

    skill = db.scalar(
        select(TenantSkill).where(TenantSkill.tenant_id == tenant_id, TenantSkill.name == name)
    )
    if skill is not None:
        if not update:
            raise SystemExit(f"skill {name!r} already exists for tenant; rerun with --update")
        if files != skill.files_jsonb:
            skill.version += 1
        skill.files_jsonb = files
        skill.description = description
        skill.required_capability = required_capability
        skill.status = "active"
    else:
        skill = TenantSkill(
            tenant_id=tenant_id,
            name=name,
            title=title,
            description=description,
            required_capability=required_capability,
            files_jsonb=files,
            created_by="import-script",
        )
        db.add(skill)
    return skill


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a skill directory as tenant data")
    parser.add_argument("skill_dir", type=Path)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()

    with SessionLocal() as db:
        skill = import_skill(db, args.tenant_id, args.skill_dir, update=args.update)
        db.commit()
        db.refresh(skill)
        print(f"imported skill {skill.name!r} v{skill.version} ({len(skill.files_jsonb)} files) for tenant {skill.tenant_id}")


if __name__ == "__main__":
    main()
