# 0.2.0a2 alpha candidate

This candidate is being verified in the chapter 4 lab. It has not yet been
published to TestPyPI or production PyPI.

- Adds optional invitation storage, explicitly enabled from SQL User Admin.
- Provides permission-checked application Script (Python) APIs for creation,
  inspection, rotation, revocation and completion.
- Uses OpenODBCDA 1.1.1 or later for explicit invitation transactions. Other
  adapters must participate in the Zope transaction; unsupported autocommit
  connections are refused before writing.
- Existing managed users, profiles, roles and fallback access remain in place.
  Installing the package does not enable invitations or create invitation tables.
- Completion creates a new identity and then uses normal login/TOTP. It never
  authenticates a browser solely from an invitation token.

See the [API and transaction boundaries](invitation-api.md),
[tested script examples](invitation-script-examples.md), and
[verification status](status.md). The optional workflow/UI add-on is a separate
future product, not a dependency of the core API.

The local suite currently has 165 passing tests. Seven live PostgreSQL tests
passed with OpenODBCDA 1.1.1, including concurrent completion, injected failures
and rollback after a request abort. Chapter 4 HTTP verification is in progress.
