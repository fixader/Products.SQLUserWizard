# SQLUserWizard 0.2.0a1

Release date: 2026-09-25. Git tag: `v0.2.0a1`. This is an alpha release.

## What changes

The core product remains: an inspectable PAS installation backed by Z SQL
Methods, configurable product-owned tables, roles, profiles, user administration,
authenticator enrollment and inherited ZODB fallback access.

The removed features are direct auth-only mapping and built-in migration from
other SQL-backed `acl_users` implementations. New installations always create
their own schema; import any old data separately. Completed managed migrations
remain within the documented upgrade boundary.

Security changes replace password-bearing cookies with revocable server-side
sessions, enforce 2FA before ordinary access, restrict enrollment tokens, add
POST/CSRF enforcement and same-origin redirects, and protect direct SQL endpoints.
SQL HTTP Basic login is disabled; explicit ZODB fallback access remains available.

## Before upgrading

Read [Upgrade and repair](upgrade.md). Startup upgrades supported managed
installations without executing SQL or changing recorded table names. Existing
cookies no longer authenticate; users must log in again. Existing SQL source is
preserved. Install / Repair refuses to overwrite differing SQL source, arguments
or connection settings and requires manual review in those cases.

The oldest verified source is 0.1.0a2. Early experimental manifests without mode
or required SQL methods are refused; failures disable SQL login for that folder
while preserving ZODB fallback. Retired auth-only installations are not converted
or secured automatically. Administrators must retire those endpoints separately.

Customized login forms must support CSRF tokens; unrecognized forms need review.
Custom profile code must use the protected product interfaces rather than public
SQL endpoints. See the upgrade guide for details and recovery steps.

## Verification and limits

- 126 automated tests pass on Python 3.13 / Zope 6.1, including actual 0.1.0a2
  object upgrades and disposable SQLite integration.
- Fresh PostgreSQL installation and two scoped upgrades passed live HTTP tests
  and a real Zope restart. Original SQL checksums were unchanged after cleanup.
- Wheel and source distribution pass strict twine validation; tests pass from
  the unpacked source distribution.
- Previously tested PostgreSQL, SQLite, MariaDB/MySQL, SQL Server, Oracle 11g
  and Zope 5 combinations remain expected to work. Full revalidation is pending.
- Direct Lavaart/Lavaart_pg upgrade verification remains pending; these locally
  customized installations are not represented as live-verified by this release.

See [verification status](status.md) for the complete environment matrix.

## Installation and distribution

Install the wheel attached to the GitHub release in the Zope environment, or use:

```bash
pip install "Products.SQLUserWizard @ git+https://github.com/fixader/Products.SQLUserWizard.git@v0.2.0a1"
```

Restart Zope after installation. Review the upgrade guide first when replacing
an existing version. PyPI publication is separate from this GitHub release.
