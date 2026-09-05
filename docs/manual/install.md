# Install

## What you need

- **Docker** with Compose v2 (`docker compose`, not `docker-compose`).
- **About 2 GB of RAM** for the four services.
- A machine you can reach on a port — `8080` by default.

Nothing else. Postgres, the API, the console and the gateway all come from the
compose file; there is no separate database to provision, no application
server to configure, and no Node or Python toolchain to install.

## Get it running

```bash
git clone https://github.com/AIE-enginehub/Oryh.git
cd Oryh
docker compose up -d --build
```

The first build takes a few minutes because the API and console images are
built from source. Migrations then run on start.

When the stack is up:

```bash
docker compose ps
```

Four services should report healthy.

| Service | What it is |
|---|---|
| `db` | Postgres 16. The whole state of the system lives here. |
| `api` | The FastAPI application. Runs migrations on start. |
| `console` | The static browser console. |
| `gateway` | nginx. The only service that publishes a port. |

Then open <http://127.0.0.1:8080/> — but do not sign in yet. First read
[first boot](first-boot.md), because the credentials you need were printed
into the log while the stack was starting.

## Configuration

Configuration lives in a `.env` file next to the compose file. Every setting
has a working default, so an evaluation deployment needs no `.env` at all.
`.env.example` documents the full set; these are the ones that matter for a
real deployment.

### The address it answers on

```bash
ORYH_CONSOLE_PORT=8080          # the port the gateway publishes
ORYH_BASE_URL=https://oryh.example.com
```

`ORYH_BASE_URL` is the canonical browser origin. Leave it unset on a box you
reach over plain HTTP by IP — links and origin checks then follow the address
each request came in on, which is what you want while evaluating. Set it as
soon as the deployment is reachable by more than you: it is what gets rendered
into skill bundles, invitation links and password-reset links, and **SMTP
delivery refuses to send security links without it**.

### The first workspace

Read only on the boot that creates the workspace, and inert forever after.

```bash
ORYH_STANDALONE_COMPANY_NAME=Acme Ltd
ORYH_STANDALONE_ADMIN_EMAIL=admin@acme.example.com
ORYH_STANDALONE_ADMIN_PASSWORD=            # leave empty to have one generated
```

Leaving the password empty is the better default: a generated password is
printed once and cannot have been committed to anything. See
[first boot](first-boot.md).

### Email

```bash
ORYH_EMAIL_BACKEND=console      # the standalone default
```

`console` prints every outbound message — invitations, password resets — to
the `api` service log instead of sending it. That is deliberate: a fresh
standalone box has no mail relay, and invitations must still be usable from
`docker compose logs`. Switch to real delivery when you have a relay:

```bash
ORYH_EMAIL_BACKEND=smtp
ORYH_SMTP_HOST=smtp.example.com
ORYH_SMTP_PORT=465
ORYH_SMTP_SECURITY=tls
ORYH_SMTP_USER=service@example.com
ORYH_SMTP_PASSWORD=...
ORYH_SMTP_FROM=service@example.com
```

`ORYH_SMTP_USER` and `ORYH_SMTP_PASSWORD` can stay unset with a relay that
authenticates by your egress IP. `ORYH_BASE_URL` cannot — see above.

### The database password

```bash
ORYH_APP_DB_PASSWORD=change-me
```

The API connects at runtime as a restricted `oryh_app` role so row-level
security applies; migrations use the owning role. Set this to something of
your own before the deployment holds real data.

## Next

[First boot](first-boot.md) — the credentials, and what to do with them.
