<!-- only: bundle -->
That key fetches its own skills: `GET /my/skill-bundle` with the service key
returns the tenant bundle (role `service`), so this agent installs and stays
current without borrowing an administrator's credential — and its writes stay
attributable to `key:<id>` rather than to a person who did not do them.
<!-- /only -->
