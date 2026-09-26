# Current verification status

## Invitation development checkpoint, 2026-09-26

Branch `feature/invitations` targets an upcoming `0.2.0a2`; it is not published.
169 local tests pass, including executable Script (Python) examples, optional
storage repair and attempt limits that survive transaction aborts. Seven separate
live PostgreSQL tests passed through Z SQL Methods and OpenODBCDA 1.1.1 on a
disposable lab database. See the [living invitation task](task-script-provisioning-and-invitations.md)
for evidence, transaction boundaries and remaining chapter 4/release gates.
Chapter 4 HTTP verification now passes on Plone 6.2.2 / Zope 6.2 with the
0.2.0a2 candidate: setup, invitation acceptance, CSRF rejection, replay rejection,
normal login/TOTP and fallback access. Plone form-protection interoperability and
ZMI permission editing were fixed during this test. The target remains active
after restart; the temporary administrator was removed and test identity disabled.
The existing managed authentication compatibility expectations below remain.

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

The previously tested combinations remain the expected compatibility baseline
for 0.2.0a1. Pending revalidation does not mean support has been withdrawn.
The table distinguishes evidence from the previous release from confirmation of
the new runtime; it does not claim the new security flows were tested everywhere.

| Environment | Previous verification | 0.2.0a1 verification | Compatibility expectation |
| --- | --- | --- | --- |
| Zope 6.1 / PostgreSQL | Managed install, login, roles; TOTP enrollment, QR codes and code rejection | Live HTTP fresh install, scoped upgrade, repair, sessions and 2FA passed | Expected; candidate verified in the recorded lab setups |
| Zope 6.1 / SQLite | Managed install, login and roles via ODBC | In-process installation, repair, upgrade and security tests passed with disposable SQLite adapter | Expected; live ODBC repeat pending |
| Zope 6.1 / MariaDB/MySQL | Managed install, login and roles via ODBC | SQL template tests; live repeat pending | Expected from previous verification |
| Zope 6.1 / Microsoft SQL Server | Managed install, login and roles via ODBC | SQL template tests; live repeat pending | Expected from previous verification |
| Zope 6.1 / Oracle 11g-style SQL | Managed install, login and roles | SQL template tests; live repeat pending | Expected from previous verification |
| Zope 5.8.3 / Python 3.8 / PostgreSQL | Buildout develop install, login, roles and TOTP enrollment/activation via OpenODBCDA | Repeat pending | Expected from previous verification |
| Oracle 12c+ | Templates only; no recorded live test | SQL template tests; live test pending | Intended dialect support, not historically live-verified |
| SQL Server / FreeTDS adapter variant | Not live-verified | Pending | Adapter-specific verification still needed |

Historical TOTP tests also covered return-to-application redirects and QR-code
setup. Historical auth-only PostgreSQL/Oracle tests belong to removed features
and do not expand the current managed-only support boundary.

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

## Release artifacts

- Built wheel and source distribution for 0.2.0a1 using an isolated build.
- Both artifacts pass `twine check --strict`.
- All 126 tests also pass from the unpacked source distribution, including the
  frozen legacy fixture. Wheel product modules match the current source files.
- Source distribution includes upgrade documentation and test fixtures.
- Build reports setuptools deprecation warnings for legacy license metadata.
  The older format is retained for Python 3.8/buildout compatibility; it does
  not prevent building or strict twine validation. Revisit this when changing
  the minimum Python/build backend versions.
- Source modules also parse with Python 3.8 grammar; this does not substitute
  for runtime testing on Python 3.8 / Zope 5.
- Code and documentation are consolidated on `main` for release `v0.2.0a1`.
  PyPI upload is a separate publication step, not implied by the GitHub release.

## TestPyPI publication

Version [0.2.0a1](https://test.pypi.org/project/Products.SQLUserWizard/0.2.0a1/)
was published as an alpha on 2026-09-25 using GitHub Actions trusted publishing.
Both published file hashes match the GitHub release artifacts. The
[publication run](https://github.com/fixader/Products.SQLUserWizard/actions/runs/36183008037)
completed successfully. Production PyPI has not been updated.
