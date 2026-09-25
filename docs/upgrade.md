# Upgrade and repair

Version 0.2.0a1 removes existing-database authentication and migration. It also
changes authentication from password-bearing PAS cookies to server-side sessions.

## Existing managed installations

### Supported upgrade baseline

The oldest verified source release is **0.1.0a2**, using the actual installer
from commit `8944411`. Its manifest records `version: "0.1.0"`, so the manifest
version alone cannot distinguish it from earlier experimental installations.
Version is diagnostic information, not sufficient proof of compatibility.

Automatic runtime upgrade requires a SQLUserWizard manifest with explicit
`mode: "managed"`, a valid four-table mapping, the recorded local SQL plugin,
and all runtime SQL methods checked by `upgrade_folder`, including
`zsql_pas_update_2fa`. These are necessary compatibility checks, not a guarantee
that arbitrary local SQL modifications are compatible. Completed migrations
meeting this contract are supported; migration history itself is not a barrier.

Earlier experimental setups without that contract are **outside automatic
upgrade support**. The lab folder `PASProductLab_pg_remote` is one such example.
Missing mode or required methods causes upgrade refusal, a logged diagnostic,
and disabled SQL authentication in that folder; ZODB fallback remains available.
This is an intentional support boundary, not an outstanding requirement to
automatically convert those test installations.

For disposable old test setups, the normal remedy is to retire/remove the old
wizard installation and create a fresh managed installation with unused table
names. Merely uninstalling and reinstalling the Python package does not remove
its persisted ZODB objects or SQL tables. Remove obsolete folder/PAS objects
explicitly after ensuring administrator access from outside that installation;
delete old SQL tables only if their data is no longer needed.

If data must be retained, transfer it separately outside the wizard, or prepare
a separately tested manual upgrade after reviewing the actual schema and method
contracts. A custom upgrade path for these experimental setups is not part of
this release. Changing only the version or adding `mode` does not establish
compatibility. SQL data is not modified by the refused runtime upgrade.

1. Back up the ZODB and SQL database and test the upgrade on a copy.
2. Install the new package and restart Zope. A startup handler finds managed
   manifests and updates the generated authentication objects automatically.
3. The recorded connection, dialect and all four table names are preserved.
   Older names such as `pas_roles_catalog`, `pas_users_migrated` and
   `pas_user_roles_migrated` are not renamed. Completed migrations are ordinary
   managed installations and do not run their migration again.
4. This runtime upgrade executes no SQL: no schema repair, user creation,
   role seeding or synchronization. It replaces the cookie helper and generated
   PAS scripts, protects existing SQL methods and updates standard login/logout pages.
   Existing SQL source is preserved: older schemas may use `login_name` and local
   methods may have been adapted independently of the manifest.
   Existing cookies expire in effect; users log in again with their existing
   password and authenticator.
5. Verify login, roles, profiles and fallback access. Install / Repair refuses
   to replace existing generated SQL when its source, arguments or connection
   differ from the current templates. Older or customized SQL requires manual
   review; runtime upgrade preserves it without running schema repair.

Each installation is upgraded within a rollback checkpoint. A failure rolls back
that folder's partial changes, logs the error and disables its SQL authentication
plugin. Other folders continue upgrading and Zope can start. ZODB fallback Basic
Auth remains available, and the wizard displays an upgrade-needs-attention notice.
After correcting the cause, restart to retry, or run repair as a fallback manager.
An unrecognized customized login form requires manual review; it is not silently
overwritten or accepted without CSRF protection.

Early manifests without `mode`, and managed installations missing required SQL
methods (including the 2FA update method), require manual compatibility review.
Startup reports these through the same failure isolation and fallback mechanism;
it does not guess ownership or claim their runtime upgrade succeeded. Those
early installations are outside the automatic upgrade support boundary above.

The startup handler is registered by normal Zope product initialization. Programs
that load ZODB outside normal Zope startup must explicitly call the upgrade routine
before using the new controllers. Repeated startup skips the completed revision.

Customized templates are preserved and reported. Ordinary customized DTML POST forms get a token field added while preserving their layout. Other custom login forms must render
`sql_user_login_submit.csrf_field(REQUEST)` inside their POST form. Logout must
POST a token to `sql_user_login_submit.logout`; GET only renders confirmation.
Custom profile displays should call `sql_user_admin.my_profile_data()` for the
current user's profile; direct Z SQL Method access is no longer public.

Repair preserves existing initial-user credentials, roles and 2FA settings.
Use user administration to change them. It does not silently switch a managed
installation to another connection or table mapping. If the manifest is absent
but tables exist, installation stops rather than guessing who owns the tables.
The manifest is a local ownership record; administrators must not repoint its
database adapter to an unrelated database and then run repair.

## Retired existing-database installations

Saved `auth_only` settings and existing-schema dialects are rejected. They are
not automatically converted to managed mode. Create a new folder and wizard
using unused names; the wizard creates its own schema. Any transfer of old users
is a separate, user-managed import after installation.

An old retired folder still contains its old persisted objects until explicitly
retired by its administrator. Do not leave its old authentication endpoints in
service as though a package upgrade had secured them. This release does not
delete that folder or modify its source database.

## Database failure during setup

Some database adapters/engines commit DDL independently of ZODB transactions.
If setup fails after creating some tables, retry can stop on those names because
there is no completed ownership manifest. Inspect the failed installation and
use new unused names or explicitly clean up its partial tables. The wizard does
not adopt tables merely because their columns resemble its schema.

## Session behavior

- Full sessions expire after eight hours; enrollment-only sessions after ten
  minutes. Logout revokes the current session on the server.
- Cookies contain a random token, with HttpOnly, SameSite=Lax, an application
  path and Secure on HTTPS requests. Configure the deployment to report its
  external HTTPS URL correctly.
- Password, enabled-state and 2FA changes invalidate SQL sessions. Fallback
  sessions are checked against the current local fallback password hash.
- SQL HTTP Basic authentication is intentionally disabled; SQL users must use
  the protected login form. ZODB fallback authentication remains available.
- Login and enrollment allow ten attempts per login per five minutes. Reuse of
  an accepted authenticator code is rejected for two minutes.
- The helper stores session state in ZODB. PAS authentication caching is disabled
  for this folder so expiration/revocation checks cannot be bypassed by a cache.
- Keep SQL and fallback ids/logins distinct: PAS combines identities and roles
  across its plugins.

## Scoped lab testing

Set `SQLUSERWIZARD_UPGRADE_PATHS=/PASProductLab,/PAS2FALab` to restrict automatic
runtime upgrades to those exact physical folder paths. An empty value selects no
folders; an unset variable retains automatic discovery. The setting limits ZODB
object upgrades, not the shared Python code loaded by the process. During partial
lab testing, other old controllers may therefore still need the old package.

On 2026-09-25 the candidate was temporarily installed on zopedatest, restarted
through systemd with that scope, and tested over HTTP against local PostgreSQL.
Original SQL table checksums were unchanged after cleanup. The original product
and ZODB were restored after the test, and the normal service was verified up.
