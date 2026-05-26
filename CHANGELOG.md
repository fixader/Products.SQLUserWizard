# Changelog

All notable changes to Products.SQLUserWizard are tracked here. The project is
still in alpha, so entries include lab verification notes when they affect
install confidence.

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
