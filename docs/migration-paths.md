# Migration Paths

Products.SQLUserWizard deliberately supports a small number of practical
migration paths. It should make common Zope authentication work predictable,
not become a universal identity migration engine.

`auth_only` mode is available in more than one workflow, but it is not a
general migration promise. Treat it as a safe read-only proof that PAS can talk
to an existing user source through Z SQL Methods. The product's built-in
migration/take-control helper is aimed at old Zope SQL-backed `acl_users`
replacements.

## Path 1: Existing Zope-style SQL user database

Use this when the existing application already has tables that behave like an
old SQL-backed `acl_users`. This is the intended target for the built-in
migration helper:

- one table with username/login and password
- one table with username/user id and Zope role names
- password values that are either plain during testing or compatible with
  `AuthEncoding`
- role names that PAS can use directly, such as `Manager`

Recommended workflow:

1. Install the product in the target application folder.
2. Add or choose a Zope database adapter that can run Z SQL Methods.
3. Run the wizard in `auth_only` mode.
4. Verify login, role lookup, profile display, fallback access, and logout.
5. Only after that proof works, switch deliberately to a managed/take-control
   path if this folder should maintain users and roles going forward.

In `auth_only` mode the wizard must not create, alter, delete, insert, or
update database rows. It is a read-only proof that PAS can authenticate against
the existing user database.

Passing auth-only means "authentication can be proven read-only"; it does not
mean "these tables are safe to let the product maintain." The next step is only
managed/take-control when the source schema is genuinely a classic Zope
user/role model. If the source is a broader application schema, keep the proof
and build an explicit import or sync path into product-owned tables.

Before switching from auth-only to managed mode, classify the existing schema:

- identity/security fields: login name, password/hash, enabled status, 2FA,
  recovery address, and a stable optional link to a person/employee table
- role fields: role names and user-role assignments that PAS should receive
- safe profile fields: display name, first name, last name, email, mobile, or
  similar fields that the application allows users or managers to edit
- application-only fields: internal notes, employment status, business flags,
  dates, addresses, BLOBs/CLOBs, avatar storage, and other domain-specific
  fields

Do not assume that an employee/person table is automatically the PAS profile
table. It may contain manager-only data. A good migration can keep the
employee table as application data, keep the users table narrow, and sync only
approved profile columns between the generated profile layer and the
application table.

## Path 2: New SQL-backed Zope application

Use this when the application is new, or when the old users have already been
converted into a clean target model.

Recommended workflow:

1. Create the application folder.
2. Add or acquire a database adapter.
3. Run the wizard in managed mode.
4. Let the product create the security tables, PAS plugin, login/logout pages,
   user admin, profile layer, secure test page, status page, and fallback
   access.
5. Customize only the generated profile form and profile SQL when the
   application needs more non-security fields.

Managed mode owns the security model. It is the place where the product may
create users, change passwords, assign roles, disable users, and delete users.
Managed users can also enable TOTP authenticator codes for themselves. Managers
may either leave 2FA optional, require enrollment before application access, or
work with already-active 2FA users. The issuer/app name is configured by the
wizard, so a lab can use one shared issuer such as `SQL_User_Wizard` while
production installations choose their own application name.

## Path 3: Arbitrary external application user stores

Use this when the source system is not Zope-like and does not already look like
`users`/`roles` authentication data.

Do not make the wizard map that schema directly, even if auth-only can be made
to read a username and password from it. Auth-only is useful here only as an
experiment or temporary bridge, not as the product-supported migration path.
Instead:

1. Create the target Zope folder with a database connection and this product.
2. Run managed mode and let the product create the target user/role model.
3. Create an import user or import-only script with enough rights to read the
   old source system.
4. Write custom import scripts that convert old users and roles into the
   product model.
5. Migrate the rest of the application after authentication works.

This keeps the security-sensitive tables simple and inspectable. Application
specific data, large profile models, avatar images, BLOBs, CLOBs, and other
domain fields belong in the application layer, not in the core authentication
tables.
