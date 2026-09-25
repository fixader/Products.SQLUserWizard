# Products.SQLUserWizard

A Zope product that creates a local SQL-backed PAS installation, with user
administration, roles, profiles, authenticator 2FA and inherited fallback access.
Version **0.2.0a1** is an unreleased alpha candidate. This documentation describes
the candidate under development; see [release status](docs/status.md).

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

```bash
git clone https://github.com/fixader/Products.SQLUserWizard.git
cd Products.SQLUserWizard
pip install -e .
```

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

[Current task and progress](docs/task-managed-only-security.md) Â·
[Changelog](CHANGELOG.md)
