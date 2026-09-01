# Operations

## Back up

The database is the whole state. There is nothing else to capture — no upload
directory, no separate search index, no state hidden in the API container.

```bash
docker compose exec -T db pg_dump -U ofbiz -d oryh > oryh-$(date +%F).sql
```

Restore into an empty database:

```bash
docker compose exec -T db psql -U ofbiz -d oryh < oryh-2026-08-29.sql
```

Take one before every upgrade. Test a restore before you need one.

## Upgrade

```bash
git pull
docker compose up -d --build
```

Migrations run on start and are idempotent, so a restart on the same version
is a no-op. Watch the API log through the first start after an upgrade:

```bash
docker compose logs -f api
```

`ensure_standalone_tenant` runs on every start and will report that the
workspace already exists. That line is expected — it means the bootstrap
correctly refused to touch a live workspace.

## Email

Until you configure SMTP, `ORYH_EMAIL_BACKEND=console` prints outbound mail to
the API log instead of sending it. That is usable for a handful of
invitations:

```bash
docker compose logs api | grep -A6 "\[oryh email\]"
```

Before switching to SMTP, set `ORYH_BASE_URL`. Security links — invitations,
password resets — refuse to send without a declared canonical origin, because
a link built from whatever address a request happened to arrive on is not
something to email to a person.

## Unattended flow driving (optional)

Off by default. It drives queues with **your own** agent runtime and **your
own** model key; nothing is provided for you.

```bash
docker compose --profile flow-runner up -d
```

It needs two files you supply: a credentials file holding the workspace id and
a service key (the bootstrap key works), and a provider file holding your model
credential. Both are mounted read-only and the model key is read fresh per run
and passed only to the agent child process.

Leave `ORYH_RUNNER_PI_BINARY` unset to watch it against the stub adapter
before spending model calls. With no flow skills installed there are no
subscriptions, so it idles until your workspace has one — that is the expected
resting state, not a fault.

## Troubleshooting

**A service is not healthy.**

```bash
docker compose ps
docker compose logs api
docker compose logs gateway
```

The API's own health endpoint is `/healthz`. The gateway's is `/_health`.

**The console loads but nothing works.** Usually the API is still running
migrations, or failed them. `docker compose logs api` says which.

**Links in emails point at the wrong host.** Set `ORYH_BASE_URL` and restart
the API.

**An agent gets `401 invalid API key`.** The credential is gone or disabled.
Reconnect with `oryh-connect`; check the key's state under *Access
credentials*.

**An agent has skills for the wrong deployment.** A bundle carries the address
of the deployment that issued it. Download `oryh-connect` from the deployment
you actually mean and connect again.

**A skill reaches nobody.** The skills screen shows *targeted · nobody* for a
skill aimed at named people with none named. Name someone.

**The port is taken.** Set `ORYH_CONSOLE_PORT` and restart.

## Deleting things

```bash
docker compose down            # stop; the data volume survives
docker compose down -v         # stop AND permanently delete the database
```

The second one is unrecoverable. There is no soft delete and no second copy.

## Reporting a problem

Bugs and security reports go to the public repository — see `SECURITY.md`
there. Include the release you are on and the relevant `docker compose logs`
output; do not paste API keys.
