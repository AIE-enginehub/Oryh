# Contributing

## How this repository is produced

This is an **export**. Development happens in a private trunk, and each
release regenerates this repository from an allowlist — the SaaS platform
layer that runs our hosted service, our operations directory, and our
marketing site are not part of it. Two consequences worth knowing before you
spend an evening:

- The git history here starts fresh at each release rather than continuing.
  Long-lived forks should track releases rather than individual commits.
- A pull request cannot be merged here mechanically. We apply accepted changes
  to the private trunk, and they return in the next export with attribution.
  It is not the most elegant arrangement; it is an honest description of one.

So: **open an issue before writing anything substantial.** A patch we cannot
take is worse than a conversation we can.

## Sign your work (DCO)

We use the [Developer Certificate of Origin](https://developercertificate.org/)
rather than a contributor licence agreement. Add a `Signed-off-by` line to
each commit — `git commit -s` does it — certifying that you wrote the change
or otherwise have the right to submit it under Apache-2.0.

## What a good change looks like here

The codebase has opinions, and matching them matters more than matching a
style guide:

- **Comments explain WHY.** Most non-obvious code here carries a note about
  the decision behind it, often naming the failure that motivated it. If your
  change encodes a judgement, write down the judgement.
- **Derive, do not restate.** A hand-maintained list beside the registry it
  shadows is the defect this codebase has fixed most often. Generate it, and
  pin the generation with a test.
- **Tests are the argument.** New behaviour comes with a test that fails
  without it. Run the whole suite:

  ```bash
  uv run --extra dev pytest
  ```

- **The record layer stores facts and state; agents drive the flow.** Business
  policy — what a discount may be, who must approve what — belongs in a
  workflow definition or a skill, not in a server-side rule. A pull request
  that teaches the API a company's policy will get this paragraph back.

## Running it

See the README. `docker compose up -d --build`, then read the `api` log for
the credentials printed on first boot.
