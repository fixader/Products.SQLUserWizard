# Products.SQLUserWizard

Prototype Zope product for configuring a local PAS user folder backed by SQL
through Z SQL Methods.

## Why this exists

Zope has powerful building blocks for authentication. PAS can be extended,
ordered, combined, and made to talk to many different backends. Z SQL Methods
can sit on top of many database adapters. Acquisition lets a folder reuse
objects and connections from the folders above it. All of that is valuable.

The practical problem is that these pieces have often felt like a large box of
gears with no clear drawing of how they fit together. You can create users and
roles in a standard user folder, and you can build almost anything with PAS,
but the path from "I have an application folder" to "this folder is protected
by SQL users, roles, login, fallback access, and maintainable user tools" is
too cryptic. Too much is left to the developer to discover by reading scattered
objects, old examples, and vague documentation.

This product is meant to remove that black-box feeling. The wizard should not
hide PAS; it should assemble PAS in a known-good way, leave readable objects in
the folder, and document what it did. After running it, a manager/developer
should be able to see:

- which database connection is used
- which SQL methods authenticate users and fetch roles
- where the PAS plugin lives
- how fallback access works
- how to create and maintain users in managed mode
- which objects are safe to customize for the local application
- what remains read-only when using auth-only mode

The goal is not magic. The goal is a working, inspectable starting point that
keeps Zope's flexibility but removes the "good luck, figure out the gears"
part.

## Core data rule

The product deliberately separates the data model into three layers:

- identity and security: user id/login, password hash, enabled status, 2FA,
  recovery address, and the stable link to any local person/employee record
- authorization: role catalog and user-role assignments
- profile display: first name, last name, display name, email, mobile, and
  other fields the application explicitly allows users or managers to edit

Existing Zope applications often blur these layers. A legacy employee table
may look like a profile table because it contains names, phone numbers, and
email addresses, while also containing internal notes, employment status,
business-specific flags, or other manager-only data. The wizard must not turn
that whole table into a self-service profile just because some columns look
human-readable.

For existing databases, first classify each field:

- security fields belong in the SQL user/security methods
- role fields belong in the role lookup and role assignment model
- safe display fields may be copied or synced to the profile table
- application-only fields stay in the application tables unless a local sync
  rule deliberately exposes them

## Product goal

Products.SQLUserWizard is aimed at two practical Zope use cases:

1. Existing Zope applications that already have an `acl_users`-style SQL user
   database and want to move that folder to PAS without losing control of
   users and roles.
2. New Zope applications that want a SQL-backed PAS setup with a usable login
   form, user administration, role assignment, profile fields, and recovery
   access from the start.

It is not intended to be a universal identity migration tool for arbitrary
external applications. For unrelated legacy schemas, create a new product-owned
SQL user model first, then write application-specific import scripts into that
model.

## Supported migration paths

See also:

- [Migration Paths](docs/migration-paths.md)
- [SQL Dialects](docs/dialects.md)
- [Current Status](docs/status.md)

### Existing Zope-style user database

Use auth-only mode first. It maps the local PAS setup to an existing
`users`/`roles`-style database and performs authentication and role lookup
read-only through Z SQL Methods. This proves that the database adapter,
SQL dialect, username/password lookup, password format, and role names work
before the wizard is allowed to write anything.

When the read-only proof is good, switch deliberately to a managed/take-control
path. That path is where the product may create or repair product-owned tables,
install the SQL user admin, and maintain users, roles, passwords, enabled
status, and profile rows.

### New SQL-backed application

Use managed mode. The wizard creates the database tables, PAS objects, cookie
login, user admin, editable profile layer, secure test page, status page, and
fallback access.

### Arbitrary external user stores

Do not make the wizard map every possible legacy schema. Instead:

1. Create the target Zope folder with a database connection and this product.
2. Let managed mode create the target `users`/`roles` model.
3. Add an import user or import-only script with the permissions needed for the
   source system.
4. Write custom import scripts that convert existing users and roles into the
   product model.
5. Migrate the rest of the application after authentication is known to work.

The product intentionally treats Z SQL Methods as the database contract. The
selected `connection_id` may point at OpenODBCDA, SQLAlchemyDA, or any other
Zope Database Adapter that works with Z SQL Methods.

Current scope:

- install or repair a local `acl_users` Pluggable Auth Service
- create a scriptable SQL auth plugin
- create PostgreSQL Z SQL Methods for users and roles
- optionally require per-user TOTP authenticator codes during form login
- read existing Zope-style PostgreSQL and Oracle user tables in
  auth-only mode
- create a manager-only information page and machine-readable manifest
- copy readable parent-folder users into the local fallback user store
- keep repeated wizard runs idempotent
- show a wizard preflight checklist before install/repair so developers must
  think about security fields, profile fields, and application data before
  pointing managed mode at existing tables

Fallback access:

During install/repair the wizard scans parent folders for local `acl_users`
objects. Users whose stored password hash can be read are copied into the
local fallback ZODB user manager with their roles. These fallback users are
active in parallel with SQL users, but after the SQL plugin in the PAS order.

The optional fallback manager field creates or updates one extra local
break-glass user. It is useful for installations that want a dedicated
recovery account, but it is not required when parent admin users can be
synced. User folders that do not expose readable password hashes are reported
as warnings.

This is a first product skeleton extracted from the `/PASLab` prototype.
