# Products.SQLUserWizard

A Zope product that creates a local SQL-backed PAS installation, with user
administration, roles, profiles, authenticator 2FA and inherited fallback access.
Version **0.2.0a1** is an alpha release for controlled use and evaluation.
See [verification status](docs/status.md) for tested environments and remaining
confirmation work, and [release notes](docs/release-0.2.0a1.md) before upgrading.

## Why this exists

Zope provides powerful authentication building blocks. Pluggable Auth Service
(PAS) combines authentication and authorization plugins. Z SQL Methods work
through different database adapters, and acquisition lets application folders
reuse connections from their parents. The difficult part is assembling these
pieces into a complete, maintainable application login system.

SQLUserWizard grew out of practical work with Zope 5 and Zope 6 applications.
It bridges the gap between an application folder with a database connection and
a working setup with SQL users, roles, login forms, user administration, profiles,
authenticator enrollment and fallback access. Developers should not have to
reconstruct that setup from scattered examples and undocumented object settings.

The wizard leaves the result inspectable. Managers can see the selected database
connection, the SQL methods for users and roles, the PAS plugins, the fallback
store, editable templates and a manifest describing the installation. These
remain ordinary Zope objects that developers can inspect and maintain.

## Who it is for

- New Zope applications that need SQL-backed users and roles with usable
  administration and recovery access from the start.
- Existing applications adopting a product-owned SQL identity model, with any
  import of old users handled separately by the application's developer.
- Existing managed SQLUserWizard installations, including completed migrations,
  upgrading their authentication runtime while retaining users and table names.

Version 0.2 retains the core product: PAS setup, database adapters, product-owned
tables, roles, profiles, administration and fallback access. The removed features
are the transition path from other SQL-backed `acl_users` implementations:
direct authentication against their existing tables (`auth_only`) and built-in
migration/takeover. This is a focused reduction in scope, not a replacement of
the database integration model. It removes substantial schema-mapping and
migration complexity while preserving the normal managed installation.

The main new runtime changes are the security fixes and server-side sessions.
These need fresh verification independently of the removed transition features.
See [upgrade boundaries](docs/upgrade.md) for
older installations and [release history](CHANGELOG.md) for the earlier design.

## Database and Zope compatibility

Previously verified managed installations establish the compatibility baseline:
PostgreSQL, SQLite, MariaDB/MySQL, Microsoft SQL Server and Oracle 11g-style SQL
on Zope 6.1, plus PostgreSQL on Zope 5.8.3. **These combinations remain expected
to work with 0.2.0a1.** They have not been dropped merely because every live test
has not yet been repeated for this candidate.

The new session and security flows have been verified on Zope 6.1 with SQLite
locally and PostgreSQL over HTTP in the lab. Confirmation on the remaining
historically tested combinations is pending. Oracle 12c+ SQL has templates but
still lacks a recorded live test. See the [compatibility matrix](docs/status.md)
for the distinction between previous verification, expected compatibility and
candidate results.

Z SQL Methods are the database contract. The connection may use OpenODBCDA,
SQLAlchemyDA or another compatible Zope database adapter; the wizard does not
require one particular adapter. Adapter-specific combinations still need their
own verification.

## One installation model

Choose a database connection, dialect and unused table names. The wizard creates
its own schema in that database:

| Purpose | Default table |
| --- | --- |
| Identity, passwords, enabled state and 2FA | `pas_users` |
| Role catalog | `pas_roles` |
| User-role assignments | `pas_user_roles` |
| Editable display profile | `pas_user_profiles` |

Names are configurable. New installations reject existing tables with those
names. Repeated repair is allowed for the installation recorded in its managed
manifest, using the same connection, dialect and table mapping.
Repair stops before database work if existing generated SQL source, arguments
or connection settings differ from the current templates; review such older or
customized installations manually. Runtime upgrade preserves their SQL.

The wizard does not connect authentication to an existing SQL user database and
contains no data migration or takeover feature. Import your own old data into
the new model separately, after installation. Application data stays outside the
user/security model.

Inherited Zope users are different: readable parent-folder users are still copied
to the local ZODB fallback store. An optional emergency manager account remains
available if SQL is unavailable. Use distinct SQL and fallback ids/logins.

## Installation

Use the Zope instance's Python environment. The commands below install the
checked-out source version. For the exact release, select the `v0.2.0a1` tag:

```bash
git clone https://github.com/fixader/Products.SQLUserWizard.git
cd Products.SQLUserWizard
git checkout v0.2.0a1
pip install -e .
```

Alternatively, install the tagged source directly:

```bash
pip install "Products.SQLUserWizard @ git+https://github.com/fixader/Products.SQLUserWizard.git@v0.2.0a1"
```

The GitHub release includes a wheel and source distribution. PyPI publication
is separate; these instructions do not depend on a PyPI upload. For ongoing
development, use `main` instead of the release tag.

Install into the Zope instance environment, restart Zope, then add SQL User Wizard
to the application folder. Select its database connection and dialect, set unused
table names, optionally supply the first SQL user and fallback manager, and run
Install / Repair. The database adapter must be available in that folder or through
acquisition and support Z SQL Methods.

Runtime dependencies: Zope 5+, Products.PluggableAuthService,
Products.ZSQLMethods and segno. `setup.py` remains for older buildout workflows.
SQL templates cover PostgreSQL, SQLite, MySQL/MariaDB, SQL Server and Oracle
11g/12c+. See [dialects](docs/dialects.md) and [verification status](docs/status.md)
for the distinction between template support and live verification.

For older buildout installations, use a `develop` checkout or install the
checkout with `pip install -e /path/to/Products.SQLUserWizard` in the instance
environment. Runtime dependencies are `Zope>=5.0`,
`Products.PluggableAuthService>=2.0`, `Products.ZSQLMethods` and `segno` for QR codes.

For an existing installation, read [upgrade and repair](docs/upgrade.md) first.
Normal Zope startup upgrades recorded managed installations without running SQL or changing their table mapping. Existing users must log in again.

## Authentication and user tools

- SQL users log in through the form, with an authenticator code when enabled.
- A random browser cookie refers to a revocable server-side session in ZODB;
  it contains no password. Full sessions last eight hours.
- Users who must enroll in 2FA receive a ten-minute token that authorizes only
  enrollment. It cannot authenticate to PAS until a code is confirmed.
- Password, enabled-state and 2FA changes invalidate existing SQL sessions.
- Login, logout, installation and user/profile/2FA changes use POST with a
  browser-bound CSRF token. Redirects stay on the same origin.
- Generated Z SQL Methods are called internally by product code; they are not
  public browser endpoints. The status page and manifest are manager-readable.
- User administration controls users, roles and security settings. Self-service
  profiles expose display fields only; application data is not automatically
  exposed to users.
- SQL HTTP Basic login is disabled. ZODB fallback recovery is retained.

The installation remains inspectable through its generated PAS objects, status
page and manifest. Editable templates may be customized; repair preserves
customized templates and reports them for review.

## Keep security, profiles and application data separate

The generated model separates identity/security, authorization and editable
profile data. Passwords, enabled status and 2FA belong to the security layer;
roles and assignments determine authorization; names and contact details belong
to the explicitly editable profile layer.

An employee or person table may also contain internal notes, employment status,
business flags or other restricted information. Those fields remain application
data. Having a name and email column does not make the whole table suitable for
self-service access. If an application needs synchronization, its developer
must explicitly select which fields may enter the profile model.

## Fallback and recovery access

During installation/repair, the wizard scans parent folders for local `acl_users`
objects. Where password hashes are readable, users and their roles are copied
into the local ZODB fallback store. These are local copies, not a live connection
to an external SQL user database. User folders without readable password hashes
are reported as warnings.

An optional fallback manager provides a dedicated recovery account. It is not
required when suitable parent administrators can be copied. Fallback access
remains available when SQL is unavailable; use distinct SQL and fallback
identities to avoid combining permissions across PAS plugins.

## Development

```bash
pip install -e ".[test]"
python -m pytest -q
```

The integration tests run Zope/PAS in process with a disposable SQLite adapter.
They exercise real Z SQL Methods, restricted PAS scripts, session authentication,
2FA enrollment, fallback access and repair. They never connect to a production
database. Tests against other live database engines remain a separate step.

Implementation responsibilities:

- `wizard.py`: setup form and orchestration.
- `installer.py`: create/repair local Zope objects.
- `schema.py`: identifiers, catalog checks and ownership boundary.
- `config.py` / `dialects.py`: schema and query templates.
- `login.py` / `sessions.py`: password/2FA verification and server sessions.
- `security.py`: POST/CSRF and redirect validation.
- `pas.py`: trusted PAS adapters around protected SQL methods.
- `admin.py` / `sqladmin.py`: user/profile management and SQL operations.

[Current task and progress](docs/task-managed-only-security.md) ·
[Invitation provisioning task](docs/task-script-provisioning-and-invitations.md) ·
[Changelog](CHANGELOG.md)
