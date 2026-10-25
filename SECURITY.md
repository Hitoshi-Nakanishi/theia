# Security

Security fixes target the current `main` branch. Older snapshots do not have a separate support commitment.

Theia reads local workbooks and optional sidecars. It does not execute Excel macros or recalculate formulas. Cached values
can be stale or absent. Files still pass through native parsers; use current dependencies and share synthetic reproductions
rather than confidential input files. Very large or malformed files can consume substantial resources.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting from the repository's Security tab when available. Otherwise, open an issue
requesting a confidential contact channel, without exploit details, confidential files or credentials. Wait for a private
channel before sharing sensitive material. Do not post real account information, access tokens or proprietary examples.
