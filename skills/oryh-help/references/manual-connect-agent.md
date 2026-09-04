<!-- generated from docs/manual/connect-agent.md by the help-references sync (sync_help_references) — edit the source, not this file -->

# Connect your agent

A person does their work through their own AI agent. Before that agent can
touch this workspace, it needs two things: the skills that describe how, and a
credential of its own. Both arrive through one bootstrap.

## Why it is not a copy-pasted API key

`oryh-connect` is the only oryh skill that works before login, and it carries
**no credential** — only this deployment's address, rendered in at the moment
you downloaded it. The agent installs it, opens an approval page, you sign in
and approve there, and only then does the agent receive its own device-bound
key and the skill bundle that key is scoped to.

Nothing is copied between you and the agent, and you never type a password
into an agent. What you approve is a specific device, named on the page,
holding a short code the agent also shows you. The design note is
the device flow.

## 1. Download the bootstrap skill

```bash
curl -O http://127.0.0.1:8080/api/v1/connect-skill
```

That is `oryh-connect.zip`. The same download is served in the browser at
<http://127.0.0.1:8080/web/connect>, which is the easier route for a colleague
who is not going to run `curl`.

## 2. Unzip it where the agent looks for skills

| Agent runtime | Skill directory |
|---|---|
| Claude Code | `~/.claude/skills` |
| Codex (app, CLI, IDE) | `~/.agents/skills` |
| Copilot CLI | `~/.agents/skills` |
| Hermes | `~/.hermes/skills` |
| OpenClaw | `openclaw skills install ./oryh-connect --global` |

`oryh-connect` is installed once per machine, unprefixed. Every other oryh
skill belongs to exactly one employer and is named after it, which is how one
person can work for two companies from the same laptop.

## 3. Ask the agent to connect

`/oryh-connect` in runtimes that take slash commands; plain words in the ones
that do not — "connect me to the company's oryh" works.

The agent shows a link and an eight-character code. Open the link **yourself**,
in your own browser. Sign in with your oryh account, check that the code and
the device name on the page match what the agent showed you, and approve.

The link works even when the agent is running over SSH, in WSL, or inside a
container — the browser is yours, not the agent's.

## 4. What the agent receives

On approval, exactly once: a device credential, and the personal skill bundle
that credential is scoped to. The bundle is generated from what **you** hold —
your role's capabilities and the skills your workspace has aimed at you — so
two colleagues connecting from identical laptops get different bundles. That
is not a bug to report; it is the point. See capabilities and
skills.

Connecting a second device does not invalidate the first. Each device holds
its own key.

## Keeping it current

- **Skills change.** Ask the agent to sync; `oryh-skill-sync` checks whether
  the installed bundle for this company is still current and reinstalls it if
  not. Agents that support session-start hooks do this on their own.
- **A key stops working.** Any oryh skill returning `401 invalid API key`
  means reconnect: run `oryh-connect` again. It is also the skill for adding a
  second employer.
- **The address must not be reused.** A bundle carries the address of the
  deployment that issued it. A copy downloaded from a test server should not be
  pointed at production — download a fresh one from each.

## Next

Set up the workspace — the workspace is still empty.
