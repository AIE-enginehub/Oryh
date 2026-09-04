<!-- generated from docs/manual/first-boot.md by the help-references sync (sync_help_references) — edit the source, not this file -->

# First boot

## What happens on the first start

Before the API serves anything, its container runs a fixed chain:

```text
alembic upgrade head          # create or update the schema
bootstrap_db_roles.py         # create/refresh the restricted runtime role
sync_tenant_defaults.py       # install the provisioned defaults
ensure_standalone_tenant.py   # create THE workspace — only if none exists
```

The last step is the one that matters to you. A standalone deployment has
exactly one workspace, so there is no registration flow to complete: the first
boot creates the company, its first administrator and a service key for
connecting agents, and prints all three.

It prints them **once**, on the boot that created them, and never again. The
check is deliberately blunt — if any workspace already exists, the script says
so and exits without touching it. It will not "fix" a live workspace on
restart.

## Get the credentials

They land in the `api` service log, after a hundred lines of migration output:

```bash
docker compose logs api | grep -A6 "standalone workspace created"
```

```text
================================================================
  oryh standalone workspace created
  company:   Acme Ltd
  console:   sign in as admin@acme.example.com
  password:  8Kd2mQ-xR4vT9wL   (generated — change it after first sign-in)
  agent key: oryh_sk_...       (service key for connecting agents)
  This is printed ONCE. Store it now.
================================================================
```

The `password:` line appears only when the password was generated here. If you
set `ORYH_STANDALONE_ADMIN_PASSWORD` yourself, it is presumed you already know
it and it is not echoed.

**Store both lines now**, in whatever your team uses for secrets. The agent key
is a service credential for the workspace; the console password is your
administrator sign-in.

## Sign in

Open <http://127.0.0.1:8080/> (or your `ORYH_BASE_URL`) and sign in as the
administrator. Change the password immediately if it was generated.

You are looking at an empty workspace: no employees, no customers, no
documents. That is correct. The console is for administering the workspace —
the work itself happens through agents, which is the next
step.

## If you lost the credentials

There is no second printing, and re-running the script will not help: the
workspace exists, so it exits without doing anything. Recovery depends on what
you still have.

**You know the administrator's email address.** Use the console's password
reset. With the default `ORYH_EMAIL_BACKEND=console`, the reset email is not
sent anywhere — it is printed to the API log, link and all:

```bash
docker compose logs api | grep -A6 "\[oryh email\]"
```

Open the link it contains and set a new password.

**You need another agent key.** Issue one from the console under **Access
credentials**; you do not need the bootstrap key back. See
administration.

**You have nothing and the workspace is empty anyway.** Starting over is
cheap while there is no real data in it — but understand exactly what it
destroys:

```bash
docker compose down -v      # -v DELETES the database volume, permanently
docker compose up -d
```

Never run that against a deployment that holds records you care about.

## Next

Connect your agent.
