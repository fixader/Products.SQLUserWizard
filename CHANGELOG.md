# Changelog

All notable changes to Products.SQLUserWizard are tracked here. The project is
still in alpha, so entries include lab verification notes when they affect
install confidence.

## 0.2.0a2 - 2026-09-26

Release candidate under lab verification; not yet published.

- Added opt-in invitation storage and a permission-checked Script (Python) API.
  Ordinary installation and startup do not create invitation tables.
- Added explicit setup, role restrictions, expiring hashed tokens, rotation,
  revocation, sanitized inspection and normal login/TOTP after completion.
- Invitation creation and completion share a transaction-based SQL workflow.
  Verified OpenODBCDA 1.1.1 explicit begin/commit-request/rollback integration,
  including rollback after a later request abort. Removed the development-only
  PostgreSQL single-statement workaround; other adapters must participate in
  Zope transactions before writing.
- Invitation attempt limits survive aborted requests; limits are per worker.
- Added application-script examples and a separate optional workflow-product design.

## 0.2.0a1 - 2026-09-25

### Changed

- Removed existing-database/auth-only modes and generated migration SQL.
- Every new installation creates its own four-table schema. The default role
  catalog is now `pas_roles`; existing managed mappings are preserved on repair.
- Added table-name validation, catalog collision checks and a manifest ownership
  check before installation changes PAS or database objects.
- Replaced password-bearing cookies with opaque, revocable ZODB sessions.
  SQL users now use form login; inherited ZODB fallback access is preserved.
- Added enrollment-only tokens that cannot authenticate to PAS, expiry,
  authentication throttling and one-time-code replay rejection.
- Added automatic runtime upgrade for recorded older managed installations, including completed migrations, with no SQL execution and isolated failure handling.
- Split request security, sessions, schema checks and trusted PAS adapters into
  separate modules while keeping persisted wizard/admin/controller class paths.

### Fixed

- Password-only PAS authentication can no longer bypass enabled SQL-user 2FA.
- Mutating browser flows require POST and CSRF validation, and login redirects
  are restricted to the same origin.
- Generated SQL methods are no longer anonymously callable; status/manifest
  objects are manager-readable.
- Required 2FA cannot be disabled through self-service. Active secrets are not
  redisplayed on the self-service page, and reset requires a current code.
- Non-PostgreSQL 2FA updates now bind `totp_enabled` instead of the nonexistent
  `enabled` argument.
- Repair preserves existing initial-user passwords, role assignments and 2FA.
- Runtime upgrade preserves locally adapted SQL and older `login_name` schemas.
- Install / Repair refuses to overwrite differing SQL source, arguments or
  connections before executing database operations.
- ZMI constructor CSRF tokens survive recreation of the product factory dispatcher.

### Verification

- Added in-process Zope/PAS/SQLite integration tests and security regressions.
- See `docs/status.md` for actual environment and results. Earlier live database
  verification below belongs to the old authentication flow.

## 0.1.0a2 - 2026-05-26

### Fixed

- Added `enumerateUsers` to the generated SQL Scriptable Plugin and activated
  it as an `IUserEnumerationPlugin`. This prevents PAS from accepting
  credentials but failing to construct the authenticated principal on the next
  request.
- Kept the PAS Cookie Auth Helper as the login mechanism, but changed the
  generated login submit object to write the helper's raw cookie value. PAS
  `CookieAuthHelper.updateCredentials` pre-quotes the base64 cookie value; if
  SQLUserWizard does not read the raw value and writes the pre-quoted value
  through Zope's response layer, `%3D%3D` padding can become double-encoded as
  `%253D%253D`. PAS then unquotes only once during extraction, rejects the
  cookie, and the next request becomes anonymous.
- Rebound existing local `acl_users` objects during install/repair so copied or
  imported folders do not silently keep using a parent user folder.
- Added a narrow PostgreSQL repair for early managed SQLUserWizard tables:
  backfill `username` from older `login_name` columns and loosen the old
  `login_name not null` constraint.

### Verified

- Zope 5 lab, managed PostgreSQL folder: wizard repair created/updated
  `enumerateUsers`, activated user enumeration, produced a non-double-encoded
  `sql_user_auth` cookie, and authenticated a SQL user into a protected page
  with `Manager` and `Authenticated` roles.
- Zope 6 lab, managed PostgreSQL folder: the same cookie/enumeration flow was
  verified with a SQL user reaching the protected test page.
- Local test suite: `70 passed`.

## 0.1.0a1 - 2026-05-26

### Added

- First public alpha package with `pyproject.toml`, `setup.py`, MIT license,
  README installation notes, and Zope 5/Zope 6 dependency metadata.
- Wizard-managed local PAS setup backed by Z SQL Methods.
- Managed PostgreSQL model for security users, editable profiles, role catalog,
  and user-role assignments.
- Auth-only mode for read-only proof against existing Zope-style SQL user and
  role tables.
- Classic `acl_users` migration helper SQL for PostgreSQL and Oracle-style
  sources.
- SQL user admin for create/update/delete, password changes, active/inactive
  status, role assignment, profile editing, and TOTP setup.
- Form login, logout, secure test page, profile edit form, install manifest,
  and status/info objects.
- TOTP authenticator enrollment with QR code support.

### Verified

- Clean managed PostgreSQL lab installation on Zope 6.
- PostgreSQL and Oracle-style auth-only reads against existing Zope-style user
  and role tables.
- Controlled migration workflow from auth-only proof to managed/take-control
  mode.
- Local test suite covered SQL template generation, password handling, TOTP,
  admin behavior, wizard preflight, package metadata, and manifest output.
