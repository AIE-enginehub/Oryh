# Security

## Reporting a vulnerability

Please report privately through GitHub's **Report a vulnerability** button on
this repository's Security tab, which opens a private advisory only the
maintainers can read. Do not open a public issue for a suspected
vulnerability, and please do not include real credentials or customer data in
a report — a redacted reproduction is enough.

We aim to acknowledge within a few working days and to keep you informed while
we work. When a fix ships we will credit you unless you would rather we did
not.

## What is in scope

The code in this repository, deployed as documented in the README: the API,
the console, the flow runner, the skills, and the Compose deployment.

Out of scope: our hosted service (report those the same way; they are simply
not this repository's issue tracker), and findings that require an attacker to
already hold a tenant's administrator credential or database access.

## What a self-hosted deployment should know

- **The bootstrap credentials print once**, to the `api` service log on first
  boot. Change the administrator password after the first sign-in and treat
  the service key as you would any credential.
- **Row-level security is on** and the runtime connects as a restricted role;
  migrations and ops scripts use the owning role. Keep that split — it is what
  makes a mistake in application code a failed query rather than a data leak.
- **Set `ORYH_BASE_URL`** and terminate TLS in front of the gateway for any
  deployment reachable off localhost. Left unset, links and origin checks
  follow the address each request arrives on and cookies skip the `Secure`
  flag, which is right for a laptop and wrong for a server.
- **Agent credentials are tenant data.** A skill bundle carries a rendered API
  key; anyone who can download a bundle holds that key.
