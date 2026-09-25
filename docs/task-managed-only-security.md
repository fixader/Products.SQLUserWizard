# Task: Simplify SQLUserWizard and fix security vulnerabilities

This is the living task document. Keep decisions, verification results, current
status and remaining work up to date as implementation progresses.

Created: 2026-09-24
Last updated: 2026-09-25

## Current status for review

The simplified installation model, security changes and runtime upgrade are
implemented locally. All 126 tests pass, including tests from the built source
distribution. The wheel and source distribution pass strict twine validation.
Install / Repair refuses to overwrite differing SQL before database operations.

Fresh installation and scoped upgrades have passed HTTP tests against the lab's
PostgreSQL database, including a real server restart. The original lab installation
has been restored. There has been no general deployment or PyPI publication.

Remaining work: direct Lavaart/Lavaart_pg verification, final review and build
metadata cleanup before final packaging. Documentation is published separately
for review and describes the unreleased candidate, not a published implementation.

All repository content, documentation, code comments and commit messages must be
in English for an international audience.

The product documentation retains the rationale and practical context from
`main`: inspectable PAS setup, adapter independence, recovery access and separation
of security, profiles and application data. Historically verified managed
database/Zope combinations remain expected to work; candidate revalidation is
tracked separately and must not be confused with withdrawal of support.

The original planning checklists and chronological notes below are retained as
history. Later decisions and this current-status section supersede earlier notes.

## Objective and scope

SQLUserWizard must create and manage its own SQL user schema on supported
databases. It must not connect authentication to an existing SQL user database
or migrate/adopt its tables. Users handle any later data import themselves.

Inherited Zope users, synchronization to fallback users and emergency access
remain supported. They are separate from the removed SQL migration features.

## Original work plan and acceptance criteria

### 1. Remove existing SQL user database integration and migration

- [ ] Remove `auth_only` and existing-schema dialects.
- [ ] Remove migration/adoption logic and generated migration methods.
- [ ] Remove associated UI choices and help text.
- [ ] Update tests and documentation to describe the new model.

Acceptance: a new installation offers no connection to old SQL user tables,
no migration action and no generated migration SQL.

### 2. Create product-owned tables

- [ ] Use the same installation model across supported databases.
- [ ] Allow configurable names such as `pas_users` and `pas_roles`.
- [ ] Keep separate user, role catalog, role assignment and profile tables.
- [ ] Validate table names and refuse collisions with unrelated tables.
- [ ] Retain repeatable installation/repair of wizard-owned tables.
- [ ] Handle old settings explicitly without automatically adopting tables.

Acceptance: the wizard creates its schema using the selected names. Repeated
repair preserves its data. Unrelated tables are not modified.

### 3. Preserve inherited users and fallback access

- [ ] Preserve inherited Zope users and local fallback/emergency access.
- [ ] Verify that simplification does not break this access.

### 4. Fix security vulnerabilities

- [ ] Prevent authentication that bypasses enabled 2FA.
- [ ] Distinguish completed 2FA from password-only verification in cookie flows.
- [ ] Complete mandatory 2FA enrollment before granting ordinary access.
- [ ] Require POST and CSRF protection for data/configuration changes.
- [ ] Validate post-login redirect destinations.
- [ ] Add regression tests demonstrating that the vulnerabilities are closed.

Acceptance: missing/invalid 2FA never grants ordinary access; GET requests and
requests without valid CSRF protection cannot make changes; login cannot redirect
to an arbitrary external destination.

### 5. Structure, documentation and verification

- [ ] Refactor where it supports simplification and security fixes.
- [ ] Preserve compatibility with persisted Zope objects when moving code.
- [ ] Update installation instructions, product status and changelog.
- [ ] Run relevant tests and record results here.
- [ ] Verify installation, repair, login, 2FA and fallback in available Zope/database
  environments. Distinguish local tests from live integration verification.

## Starting point

- Repository: https://github.com/fixader/Products.SQLUserWizard
- Local checkout: `C:\Users\rf\Documents\Products.SQLUserWizard`
- Inspected branch/commit: `main`, `8944411`.
- Package version: `0.1.0a2`.
- Before changes: 70 tests passed on Python 3.13.0.
- Previously documented Zope/database lab tests had not yet been repeated.

Initial findings:

- A local reproduction showed the generated authentication script accepting a
  password without OTP for a 2FA-enabled user when form fields were missing.
  Verification of the complete PAS flow was required.
- A local reproduction reached the administrator's deletion operation via GET.
- Inspected mutation methods lacked explicit CSRF checks.
- The login controller used `came_from` directly as a redirect destination.
- Large modules mixed installation, HTML, SQL and authentication.

## Decisions and initial implementation questions

Agreed with the user:

- Remove existing SQL user database integration and migration.
- Have the wizard create its own user and role tables with configurable names.
- Preserve inherited users.
- Fix the security vulnerabilities.
- Maintain this document throughout the work.

Questions to resolve during implementation:

- Final table defaults; the original role catalog was `pas_roles_catalog`.
- Verification of ownership for existing wizard tables during repair.
- Handling persisted migration objects and old `auth_only` setups without
  unintended database changes.
- Technical design for 2FA proof, cookies and restricted enrollment access.
- Availability of Zope/database environments for integration tests.

## Progress history

| Date | Change | Verification / remaining work |
| --- | --- | --- |
| 2026-09-24 | Initial review and local clone. | 70 tests passed; two security issues reproduced locally. No production changes. |
| 2026-09-24 | Saved the requested task document. | Documentation only; implementation still pending. |

### Initial implementation checkpoint

- Removed migration generators and existing-schema choices.
- Changed the default role catalog to `pas_roles`; recorded table names remain authoritative.
- Added table-name and manifest checks before installation changes.
- Replaced password cookies with server-side sessions and restricted enrollment.
- Connected POST/CSRF and local redirects to browser flows.
- Blocked direct publishing of generated SQL methods; trusted Python calls them internally.
- At this checkpoint, tests and integration verification were still pending.

### Checkpoint requested to limit usage

- Core changes passed 114 tests on Python 3.13 / Zope 6.1 / PAS 4.1 / ZSQLMethods 5.1.
- Tests used real Zope/PAS in process and disposable SQLite. Other live database
  engines and Zope 5 had not been retested.
- Local regressions covered login, restricted 2FA enrollment, POST/CSRF, redirects,
  SQL method permissions, fallback, table collisions and repair.
- The user clarified that completed migrations must upgrade without repeating
  data migration or losing table names, users or roles.
- `upgrade.py` and a startup hook were work in progress, not yet tested against
  actual old objects. Startup error isolation, customized templates and saved
  defaults required review; startup failure handling was incomplete.
- At that time, `docs/upgrade.md` still described the earlier manual-repair plan.
- Nothing had been committed, pushed, published or deployed.

The next block was to isolate startup failures, test actual 0.1.0a2 objects with
completed migrations and custom table names without touching SQL data, and update
the upgrade documentation. The agreed working style was smaller blocks with
frequent progress reports and clear checkpoints.

### Runtime upgrade verified locally

- Froze source from commit `8944411` (0.1.0a2) as test input. Its installer runs in
  a separate process; exported ZODB objects are loaded and upgraded under new code.
- Verified a completed migration using `pas_users_migrated`, `pas_roles_catalog`,
  `pas_user_roles_migrated` and `pas_user_profiles`.
- Upgrade executes no SQL and preserves data. Existing passwords, 2FA, roles and
  fallback work afterward. Missing instance defaults are restored from the manifest.
- Normal product initialization registers the startup hook. Completed runtime
  revisions are skipped on subsequent startup.
- Per-folder failure rolls back partial changes, disables that folder's SQL
  authentication and reports the failure. Traversal continues; ZODB fallback is
  preserved. A corrected installation can retry.
- Ordinary customized DTML login forms receive CSRF fields without replacing
  layout; unrecognized forms require review and trigger upgrade failure.
- Result: 118 tests passed; `git diff --check` was clean.
- Environment: Zope 6.1, Python 3.13 and disposable SQLite. Full server startup,
  Zope 5 and other live database engines were not yet verified.
- No commit, push or running-installation change had occurred at this checkpoint.

### Read-only lab discovery, 2026-09-25

- Confirmed `zopedatest` at `192.168.0.12`, Zope on port 8081.
- Python 3.14.4, Zope 6.1, PAS 4.1, ZSQLMethods 5.1.
- SQLUserWizard reported 0.1.0 and was editable-installed from
  `/home/codex/openodbcda-lab/Products.SQLUserWizard`. Source included cookie
  double-encoding and user enumeration fixes; version alone did not identify its state.
- `/PASProductLab`: managed, local PostgreSQL `openodbc_test`, ordinary `pas_*` tables.
- `/PAS2FALab`: managed, the same local PostgreSQL, separate `pas2fa_*` tables.
- `/PASSmoke_sqlite` and `/PASSmoke_mysql`: separate tables in local databases.
- `/PASSmoke_pg`: PostgreSQL at 192.168.0.11. `/PASSmoke_mssql` pointed to local
  port 11433, absent from the listening-port list; connectivity was not tested.
- `/PASProductLab_existing_pg` and `/PASProductLab_existing_oracle` remained
  `auth_only`, not completed migrations.
- `/PASProductLab_pg_remote` lacked manifest `mode`; the implementation at that
  checkpoint skipped it. Explicit compatibility handling was required.
- `/Lavaart` used migrated table names and an Oracle connection.
- `/Lavaart_pg` recorded `oracle11g` in both manifest and wizard, but its active
  `VolumOrdre` adapter pointed to PostgreSQL database `lavaart` at 192.168.0.11.
  The manifest could not safely drive SQL regeneration.
- ZODB was opened with `FileStorage(read_only=True)`. No service changes, package
  installs or SQL queries were performed during discovery.
- The initial recommendation was an isolated copy of PASProductLab/PAS2FALab and
  a fresh folder. Before shared-instance updates, compatibility handling or an
  explicit folder scope was needed. Later authorization allowed direct lab testing.

These findings added cases beyond the successful 0.1.0a2 test. No deployment was
approved or performed during the discovery block.

### Direct lab test completed, 2026-09-25

- The user authorized direct lab testing with backup and selected folders.
- Backup: `/home/codex/openodbcda-lab/backups/sqluw-upgrade-20260925T052203Z`.
- Service: `zopedatest-zope61.service` (systemd, Restart=always).
- Added `SQLUSERWIZARD_UPGRADE_PATHS` to select exact physical folder paths;
  the test selected PASProductLab and PAS2FALab.
- Real startup upgraded both folders. Row counts and checksums for eight original
  SQL tables were unchanged after upgrade and after test cleanup.
- HTTP tests passed for login/roles, missing-OTP rejection, valid 2FA, restricted
  enrollment, activation, logout, CSRF and GET rejection.
- Fresh PostgreSQL installation through HTTP/ZMI passed: wizard creation,
  tables, first user, profile write and repair.
- Fixed a compatibility issue: PAS2FALab still uses `login_name`. Runtime upgrade
  now preserves actual SQL source instead of regenerating it from current templates.
- Fixed constructor CSRF: tokens bind to the persistent parent rather than the
  transient ZMI product factory. Added a regression test.
- Result: 120 tests passed; `git diff --check` was clean.
- Removed temporary SQL users and four fresh test tables. Restored original code
  and ZODB, removing temporary administrator/folders and the systemd scope setting.
  The service was active and returned HTTP 200 after restoration.
- Preserved tested candidate source in the backup's `candidate-tested` directory.
  No Git commit or push had occurred at this checkpoint.

At that time, open cases were missing-mode manifests, retired auth-only folders
and direct Lavaart/Lavaart_pg tests. Zope 5 and other live database engines had not
been retested. The later support-boundary decision below supersedes the need to
add automatic conversion for experimental setups.

### Compatibility block: older manifests and local SQL

- Missing manifest mode now produces an upgrade diagnostic; existing failure
  isolation disables old SQL authentication while retaining ZODB fallback.
- Managed installations must contain the SQL methods required by the new
  controllers, including `update_2fa`, before runtime upgrade starts.
- A regression test confirms login with a stale manifest dialect and customized
  SQL; source, arguments and connection ID are preserved.
- At this checkpoint, protecting Install / Repair from overwriting customized SQL
  remained the next task. Runtime upgrade already preserved it.
- No lab changes. Result: 123 tests passed; `git diff --check` was clean.

### Agreed support boundary

- Automatic conversion of the earliest experimental lab setups is outside scope.
  Refuse their upgrade and require separate manual handling.
- The oldest verified source is 0.1.0a2, commit `8944411`. It writes `version=0.1.0`
  in the manifest, so a numeric version cutoff alone is unreliable.
- The technical boundary requires an explicit managed manifest, valid table mapping
  and required SQL methods, including `update_2fa`. Missing mode/methods are rejected;
  fallback is preserved through upgrade failure handling.
- `docs/upgrade.md` documents the boundary and manual options. Completed managed
  migrations remain in scope. Earlier plans for automatic support of experimental
  setups are superseded.
- Removal and fresh installation are acceptable remedies for disposable test
  setups; dedicated conversion code is not required. Reinstalling the Python
  package alone does not remove persisted ZODB objects or SQL tables.
- No uninstall or new lab changes were performed in this documentation block.

### Repair protection and distribution checks

- Install / Repair now refuses differing generated SQL source, arguments or
  connection settings before any database calls. Three regression cases cover it.
- Result: 126 tests passed, including from the unpacked source distribution.
- Built wheel and source distribution; both passed `twine check --strict`.
  Wheel product modules match current source; the source package includes the
  legacy fixture, tests and documentation.
- Remaining build warnings concern legacy license metadata; final packaging is pending.
- Published review documentation on `docs/0.2.0a1-review`, commit `f63331a`.
  Product implementation remains uncommitted; nothing has been uploaded to PyPI.
- Corrected this task document to English after the user clarified the repository
  language requirement. Future repository content and commits must use English.
