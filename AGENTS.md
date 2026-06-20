# AGENT GUIDELINES — theia

This is a standalone PySide6 viewer. Private cleanup/preprocess code belongs in
the ignored `private_models/` workspace, not in tracked files. This is its own
repository, separate from the parent-project repository.

## Vendor identifiers and personal data — git hygiene

The following MUST NEVER appear in tracked files, including commit
messages, code constants, README examples, sample fixtures, or test data:

- **Specific broker / vendor names** — in any form, in any tracked file,
  whenever the same fact can be expressed generically as `<broker>` /
  `the broker` / `vendor`. This rule applies recursively: even this rule
  must not enumerate the vendor names it is forbidding.
- **Personal names** of analysts, employees, or clients.
- **Email addresses** (other than the maintainer's git commit author
  identity), phone numbers, real account names, or 1Password vault
  paths beyond the documented `op://VAULT/ITEM/field` placeholder shape.
- **Real ticker positions, fund names, portfolio-identifying data,
  client codes,** or anything that could leak holdings.

This project deliberately uses the *folder-name-as-label* convention
(`<DATA_PATH>/broker_models/<broker>/...`). The actual broker label only ever
lives in directory names on the local filesystem and in runtime arguments.
Tracked code and commit messages refer to it as `<broker>`.

If a fact about a specific vendor is genuinely required to explain
behaviour (e.g. handling that vendor's quirky export format), name the
vendor only inline in a one-line example body — never in commit titles,
never in top-level constants, never in mapping tables.

## Simplicity first

Generate the simplest code that satisfies the requirement. Prefer
explicit small functions over clever abstractions. No speculative
features. No hard-coded vendor mapping tables — derive labels from the
filesystem when possible.

## Commits

- Edit on `main`; do not cut feature branches.
- After any code change, smoke-test before reporting completion.
- Push only when the maintainer explicitly asks to push.
- Keep commit messages short and broker-neutral (see hygiene rule above).
