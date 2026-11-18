# Operations

## Back up

The database is the whole state. There is nothing else to capture — no upload
directory, no separate search index, no state hidden in the API container.

```bash
docker compose exec -T db pg_dump -U ofbiz -d oryh > oryh-$(date +%F).sql
```

Restore into an empty database. Start only `db` on a fresh volume: starting
the whole stack would run first boot and create a new workspace before the
restore. Then start the rest, which migrates the restored schema forward if
the backup is older:

```bash
docker compose down -v      # -v DELETES the current database volume
docker compose up -d db
docker compose exec -T db psql -U ofbiz -d oryh < oryh-2026-08-29.sql
docker compose up -d
```

The restore prints `ERROR:  role "oryh_app" does not exist` for every grant
in the backup. That is expected: the restricted runtime role is created by the
API's first start, which grants it again. The `api` log then reports that the
workspace already exists.

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

## Run the Flow Runner

The Flow Runner is the server-side agent for unattended approval routing.
The `flow-runner` Compose profile starts it as a fifth service. Its Docker
image already includes the Pi agent runtime. Start the
[core stack](install.md#get-it-running) first so you have a workspace.

### 1. Configure workspace and model access

Use the workspace service key from [first boot](first-boot.md), or issue a
dedicated service key in **Access credentials**. Call `GET /api/v1/tenant` with
that key in the `X-API-Key` header and use the returned `data.id` as the workspace
ID. Save the following two JSON files in a directory outside the checkout.
The runner container must be able to read the files as UID 10001.

`flow-runner-credentials.json`:

```json
[{"tenant_id": "<workspace id>", "api_key": "<workspace service key>"}]
```

`flow-runner-provider.json`, shown here with an Anthropic provider key:

```json
{"ANTHROPIC_API_KEY": "<your key>"}
```

In the checkout's `.env`, point Compose to those files and select a model
available to your provider account:

```dotenv
ORYH_RUNNER_CREDENTIALS_HOST_FILE=/absolute/path/to/flow-runner-credentials.json
ORYH_RUNNER_PROVIDER_HOST_FILE=/absolute/path/to/flow-runner-provider.json
ORYH_RUNNER_PI_BINARY=pi
ORYH_RUNNER_PI_PROVIDER=anthropic
ORYH_RUNNER_PI_MODEL=<your-model-id>
```

Set the provider, model ID and key variable together if you use another
provider. For a polling-only check, leave `ORYH_RUNNER_PI_BINARY` empty and use
`{}` in the provider file. The stub adapter polls and can record run
information without making model calls or advancing documents.

### 2. Set up one workflow

Pick a document family, such as sales quotations, and set up an approver with
an employee record. Use [business rules](../business-rules.md) to publish an
`approval_flow` rule for that family. The rule must be in force for the date
of the test and name approvers the agent can resolve in the workspace.

The public checkout requires a workspace-authored driver skill. Use
`oryh-skill-author` with an administrator's connected agent, or import a skill
directory that you already maintain. The skill needs the matching advance
capability in its frontmatter, such as `required_capability: quotation.advance`,
and instructions to read the approval rule and route eligible documents through
the ORYH API. Use the workspace's rule for approver selection.

To import a local skill directory, replace the example path and set
`TENANT_ID` to your workspace ID:

```bash
docker compose exec api mkdir -p /tmp/oryh-workflow-skill
docker compose cp ./my-flow-skill/. api:/tmp/oryh-workflow-skill/
docker compose exec api python scripts/import_skill.py /tmp/oryh-workflow-skill --tenant-id "$TENANT_ID"
```

After creating or importing the skill, sync the workspace defaults:

```bash
docker compose exec api python scripts/sync_tenant_defaults.py
```

The sync creates missing subscriptions for built-in document families with a
matching active skill. It preserves existing subscriptions. Check **Flow agent**
in the console, or `GET /api/v1/flow-subscriptions?enabled=true`, for an enabled
subscription with the expected `entity_type` and `driver_skill`.

### 3. Start the service and verify a document advances

```bash
docker compose --profile flow-runner up -d --build --wait
docker compose --profile flow-runner ps
docker compose --profile flow-runner logs --tail=100 flow-runner
```

Look for `adapter=pi` and a message that the workspace is being driven. Submit
a test document that matches the subscription and has no open approval task.
Check the run under **Flow agent**, then verify the expected task, assignment
or state change on the document itself. A running container only confirms that
the process started.

If the runner remains idle, verify the workspace ID and service key, the
subscription and its queue filter, and the effective date and document family
of the published approval rule. If a run fails, inspect its recorded error and
the runner log for a missing skill or provider authentication failure.

Stop automated routing while leaving the core stack running with
`docker compose --profile flow-runner stop flow-runner`.

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
skill aimed at named people with none named. Name someone. *Runner only* is
different: the approval-flow skills ship that way on purpose.

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
