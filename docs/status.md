# Current verification status

## 0.2.0a1 local verification

- 126 tests pass on Python 3.13.0, Zope 6.1, PAS 4.1 and ZSQLMethods 5.1.
- Integration tests use real Zope objects, PAS scripts and Z SQL Methods with a
  disposable SQLite adapter: install/repair, authentication, 2FA, enrollment,
  revocation, fallback, permissions and collision handling are covered.
- Upgrade tests run the actual 0.1.0a2 installer in a separate process and load
  its exported ZODB objects under the new package. A completed migration with
  older/custom table names retains its data and authenticates after upgrade.
- The runtime upgrade performs no SQL calls. Failure rollback, SQL-login
  isolation, fallback preservation, retry and ordinary customized login forms
  are tested. Startup-handler registration is tested.
- No production installation has been changed. Zope 5 and live MySQL/SQL Server/Oracle
  upgrades have not been retested. Live PostgreSQL and server restart results follow below.

## Historical verification

The 0.1.0a2 lab results in the changelog belong to the old cookie/authentication
flow. They are not evidence that the new session and upgrade flow has passed on
all those environments. Template tests cover all supported SQL dialects, while
current local database execution tests use SQLite; live PostgreSQL results follow below.

See [upgrade behavior](upgrade.md) and the [living task document](task-managed-only-security.md).

## Live lab verification, 2026-09-25

Host: `zopedatest` / `192.168.0.12:8081`, Python 3.14.4, Zope 6.1, PAS 4.1,
ZSQLMethods 5.1, OpenODBCDA and local PostgreSQL `openodbc_test`.

Passed through the actual HTTP publisher and a real systemd restart:

- Scoped automatic upgrade of `/PASProductLab` and `/PAS2FALab`; other inspected
  manifests were not upgraded. All eight original SQL tables retained their data.
- Password login, roles, OTP-required rejection, 2FA login, restricted enrollment
  followed by activation, logout and denied GET/missing-CSRF mutations.
- Direct protected SQL endpoint denied (HTTP 404).
- Fresh wizard creation through ZMI, new PostgreSQL tables, first-user login,
  profile saving with valid CSRF, and repeated install/repair.

Two live findings were fixed and regression-covered:

1. Runtime upgrades now preserve SQL method source instead of regenerating it.
   The older PAS2FALab schema uses `login_name`, not `username`.
2. Constructor CSRF tokens now bind to the persistent containing folder, not
   Zope's transient product factory dispatcher.

Temporary users and tables were removed. Original table hashes were checked after
cleanup; original product code and ZODB were restored and the service returned
HTTP 200. Backup and detailed result files are on the lab host at:
`/home/codex/openodbcda-lab/backups/sqluw-upgrade-20260925T052203Z`.

Outside automatic upgrade support: experimental manifests lacking `mode` or
required runtime SQL methods, and retired auth-only setups. The oldest verified
source release is 0.1.0a2; its manifest writes 0.1.0, so structural checks enforce
the support boundary (see upgrade.md). These experimental setups do not block
completion of the supported upgrade path.

Still requiring validation: a direct upgrade of Lavaart/Lavaart_pg. Install /
Repair now refuses differing SQL source, arguments and connection settings before
any database calls; three regression cases cover this guard.

## Distribution candidate

- Built wheel and source distribution for 0.2.0a1 using an isolated build.
- Both artifacts pass `twine check --strict`.
- All 126 tests also pass from the unpacked source distribution, including the
  frozen legacy fixture. Wheel product modules match the current source files.
- Source distribution includes upgrade documentation and test fixtures.
- Build reports setuptools deprecation warnings for legacy license metadata;
  these still need cleanup before the final build.
- Nothing has been uploaded to PyPI. Documentation may be published for review
  ahead of the implementation; it describes the unreleased candidate.
