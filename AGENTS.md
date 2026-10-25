# AGENT GUIDELINES — theia

Theia is a standalone PySide6 viewer for generated Excel valuation models. It reads local files and optional display metadata.

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

Folder names are display labels. Examples and fixtures use fictional companies and generic model collections.
Keep documentation, code, dependencies, examples, and ignore rules limited to the viewer's own capabilities.

## Simplicity first

Generate the simplest code that satisfies the requirement. Prefer
explicit small functions over clever abstractions. No speculative
features. No hard-coded vendor mapping tables — derive labels from the
filesystem when possible.

## Commits

- Follow PUBLICATION.md: run Argus on the working tree and complete history, and install its local Git hooks in each clone.
- Missing policy, unreadable attachments and unresolved findings block publication. Never bypass hooks or approve exceptions.

- Edit on `main`; do not cut feature branches.
- After any code change, smoke-test before reporting completion.
- Push only when the maintainer explicitly asks to push.
- Keep commit messages short and broker-neutral (see hygiene rule above).
