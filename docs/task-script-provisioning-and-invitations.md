# Task: Add a safe Script (Python) provisioning and invitation API

Created: 2026-09-25

## Starting state

- Repository: `https://github.com/fixader/Products.SQLUserWizard`
- Starting release: `v0.2.0a1`, commit `b3c0855`
- Package version: `0.2.0a1`
- Baseline: 126 tests pass.
- The release wheel and source archive are attached to the GitHub prerelease and
  the same files have been published to TestPyPI.
- The TestPyPI wheel has been installed successfully on the clean case-study
  server at `192.168.0.74`, using Plone 6.2, Zope 6.2, Python 3.14.4,
  OpenODBCDA 1.0.2 and PostgreSQL 18. The Python package imports and Plone
  restarts, but the wizard has not yet been run there.

Before changing code, fetch the repository and confirm that branch, tag,
package metadata, documentation and tests describe the same implementation. If
they do not, stop and report the inconsistency before installing, publishing or
changing a server.

All repository documentation, code comments and commit messages must be in
English.

## Objective

Add a small, stable provisioning and invitation interface that ordinary Zope
Script (Python) objects can call without receiving direct access to PAS internals
or generated Z SQL Methods.

SQLUserWizard must own:

- the product-owned invitation schema;
- database-dialect-specific invitation Z SQL Methods;
- trusted Python wrappers that validate every operation;
- permissions required by application scripts;
- manifest information, repair behavior and tests; and
- documentation of the supported script-facing API.

An application such as `/ordersystem` must then be able to implement its own
invitation pages and workflow as Zope objects. It should not need another
Python package merely to create and accept invitations.

This task does not make raw SQL methods public and does not turn
RestrictedPython into trusted product code.

## Intended object layout

The target layout for a managed installation is:

```text
/ordersystem
    acl_users
        sql_auth
            zsql_pas_...                  existing protected PAS methods
            zsql_invitation_...           new protected invitation methods

    sql_user_provisioning                 new trusted product controller
    sql_user_login_form                   existing editable login template
    sql_user_login_submit                 existing trusted login controller
    sql_user_admin                        existing administration controller
    MailHost                              optional application delivery object

    invitations                           application-owned example folder
        invite_user                       user-administration script
        list_invitations                  user-administration script
        revoke_invitation                 user-administration script
        accept_invitation                 public token-entry script
        complete_invitation               restricted completion script
        invitation_templates              application presentation objects
```

The example scripts under `invitations` acquire
`sql_user_provisioning`, `MailHost` and branding from the `ordersystem`
application root. Physical placement enables acquisition; permissions remain
the authorization boundary.

## Required design boundary

### Protected database layer

Create invitation SQL templates for every managed dialect currently supported
by SQLUserWizard:

- PostgreSQL;
- SQLite;
- MariaDB/MySQL;
- Microsoft SQL Server;
- Oracle 11g-style SQL; and
- Oracle 12c+ SQL.

The methods should cover only the operations needed by the wrapper, such as:

```text
zsql_invitation_create
zsql_invitation_get_by_hash
zsql_invitation_list
zsql_invitation_rotate_secret
zsql_invitation_revoke
zsql_invitation_consume
zsql_invitation_record_delivery
```

Names are provisional. Choose a consistent final set during implementation and
document it.

The invitation table must be product-owned and collision-checked before any
DDL runs. Keep it separate from `pas_users`, `pas_user_profiles`, `pas_roles`
and `pas_user_roles`. Decide whether approved roles require a normalized child
table rather than a dialect-specific JSON or delimited column. Prefer a design
that preserves constraints and remains portable across all supported engines.

Minimum invitation information:

- stable invitation id;
- hash of a cryptographically random secret;
- recipient email and optional phone;
- optional proposed user id/login and application identity reference;
- approved ordinary roles;
- creator id and creation time;
- expiry time;
- accepted and revoked times;
- resulting user id after successful acceptance; and
- delivery channel and latest delivery result, without message credentials or
  full invitation URLs.

Do not store the raw token. Do not log the token or complete invitation URL.

Generated invitation Z SQL Methods must use typed/quoted parameters, have no
browser-facing permissions and be called only by trusted product code. They are
documented for audit and database-porting purposes, not as the application API.

### Trusted wrapper

Install a persistent product object such as `sql_user_provisioning` in the
managed application root. It locates the local PAS plugin and connection from
the installation manifest. Callers must not be able to supply connection ids,
table names, SQL fragments, password-hash algorithms or PAS plugin paths.

Provide a small script-facing API. Candidate operations are:

```python
create_invitation(...)
inspect_invitation(token)
list_invitations(...)
rotate_invitation_secret(invitation_id)
revoke_invitation(invitation_id)
complete_invitation(token, user_id, login_name, password, profile)
```

The final names may change after reviewing existing SQLUserAdmin helpers. Reuse
or refactor `sqladmin.py` rather than creating a second implementation of user,
password, role and profile rules.

Return plain, sanitized mappings suitable for Script (Python). Never return
password hashes, authenticator secrets, stored token hashes, raw database rows
with security fields, or internal objects that let RestrictedPython reach the
PAS plugin.

### Token rules

- Generate at least 256 bits of entropy with Python's `secrets` module.
- Return the raw token only when it is created or rotated.
- Store only a one-way hash.
- Compare secrets safely and avoid timing-sensitive string comparisons where
  comparison occurs in Python.
- Make tokens single-use and time-limited.
- Rotating a token invalidates the previous token.
- Rate-limit inspection and completion attempts.
- A failed SMTP attempt must not destroy a valid pending invitation.

### User and role rules

- Creating an invitation must not create an active user.
- Completion provisions the managed SQL identity through existing, centralized
  SQLUserWizard password/profile/role logic.
- A user may choose their password and explicitly editable profile fields.
- Roles come only from the stored, pre-approved invitation state. Ignore role
  names supplied by the public completion request.
- Invitations and script-facing provisioning must always reject `Manager`,
  `Owner`, fallback/recovery access and any configured privileged equivalent.
- Decide explicitly how pseudo-roles such as `Anonymous` and `Authenticated`
  are treated; do not silently assign them as ordinary managed roles.
- Users cannot promote themselves.
- Privileged promotion remains a separate action performed by a different
  existing manager after ordinary enrollment and login have succeeded.
- Security changes must invalidate affected sessions through the existing
  session model.

### Atomic completion

Invitation completion must be replay-safe and transactional:

1. Resolve the stored hash and verify pending, unexpired state.
2. Prevent concurrent completion of the same invitation.
3. Create the user, profile and ordinary role assignments through the trusted
   SQLUserWizard service.
4. Mark the invitation accepted and store the resulting user id.
5. Commit only if every step succeeds; otherwise roll back.

Use a conditional state change or equivalent database locking and require an
unambiguous successful result. Verify behavior through the actual Zope database
transaction path. Document any adapter-specific transaction limit rather than
claiming unsupported atomicity.

Do not automatically issue a full authenticated session after acceptance in
the first implementation. Redirect the person to the existing, tested PAS login
flow. Accounts that require TOTP then use SQLUserWizard's current restricted
enrollment behavior.

## Permissions and Script (Python)

Physical location is not permission. Implement and test a narrow permission and
proxy-role design.

Suggested separation:

- invitation administration: create, list, resend/rotate and revoke;
- invitation completion: validate a token and provision only its stored
  identity and ordinary roles; and
- privileged user/role management: remains outside the invitation API.

Do not use a `Manager` proxy role for public completion scripts. Add the minimum
custom permission and role required for the reviewed completion script, for
example `SQLUserWizard: Provision invited users` and a narrowly mapped proxy
role. Prove the exact Zope 5 and Zope 6 behavior instead of assuming that a
custom proxy role works identically.

The wrapper must still enforce all validation when the caller has permission.
A proxy role authorizes a request for a specific operation; it does not bypass
role restrictions, token validation, table ownership or password handling.

Add integration tests showing that:

- the documented script in the documented child context can acquire and call
  the controller;
- the same script without its proxy role is denied;
- an unrelated script elsewhere cannot acquire or call it accidentally;
- direct browser traversal to protected provisioning operations is denied;
- raw invitation and PAS Z SQL Methods remain non-publishable;
- a public caller cannot choose roles or invoke generic user creation; and
- a Manager can still inspect and maintain the installation through documented
  management paths.

Do not rely on checking a caller's physical path as the primary authorization
mechanism. Acquisition determines lookup; permissions and the wrapper contract
determine authority.

## Installation, manifest and upgrade requirements

- Preserve the existing four-table identity mapping and all `v0.2.0a1`
  installations.
- Do not silently add an invitation table to `DEFAULT_TABLES` if doing so would
  invalidate existing manifests or repairs. Model invitation ownership and
  table naming separately and version the manifest deliberately.
- New installations may create the reviewed invitation schema once collision
  checks pass.
- Upgrading the Python package and starting Zope must not execute invitation
  DDL against existing databases.
- Existing managed installations need an explicit, documented enable/install
  action for the invitation schema and controller.
- Startup upgrade must keep its current per-folder rollback and fallback-access
  guarantees.
- Install/Repair must not overwrite customized SQL source, arguments,
  connection settings or templates without explicit review.
- Repeated invitation enable/repair must be idempotent and preserve invitation
  and user data.
- A partial DDL failure must not make the wizard adopt unrelated tables on the
  next run.
- Uninstalling or disabling the application invitation examples must not break
  normal PAS login or existing managed users.

Choose the next package version only after reviewing compatibility and release
scope. Do not rewrite or replace `v0.2.0a1` artifacts.

## MailHost boundary

Mail delivery is intentionally outside the core database transaction and
outside PAS authentication.

The wrapper returns the one-time raw token to the authorized invitation-creation
script. The application builds a link from a configured canonical HTTPS origin
and sends it through its acquired Zope MailHost. SQLUserWizard must not require
SMTP, IMAP or POP3 and must not store mailbox credentials.

Provide an example using MailHost, but keep these responsibilities separate:

- SQLUserWizard: invitation state, token security and provisioning;
- application script: wording, canonical URL and delivery request;
- MailHost/mail service: authenticated SMTP delivery;
- human mailbox owner: replies received through IMAP or POP3.

Manual controlled delivery must remain possible during testing.

## Branding boundary

Do not move application branding into PAS security records. Existing editable
login templates may use folder-local configuration for organisation name, logo,
introductory text and support address while retaining the existing protected
login controller, CSRF field, POST behavior, redirect validation, sessions and
TOTP flow.

Invitation provisioning and login branding are related examples but separate
security concerns. The provisioning API must work with the default templates.

## Documentation deliverables

Document the supported wrapper API as a real compatibility contract:

- method purpose;
- required permission;
- expected acquisition context;
- recommended physical script location;
- proxy-role requirement;
- arguments and accepted types;
- sanitized return shape;
- expected exceptions and failure behavior; and
- security and transaction effects.

Add complete, copyable examples for an `/ordersystem/invitations` folder:

- create and send an invitation through an acquired MailHost;
- list pending invitations;
- revoke and rotate an invitation;
- render token acceptance;
- complete registration; and
- redirect to the standard SQLUserWizard login and TOTP enrollment flow.

Examples must not contain real domains, credentials, people or production data.
The Plone Order System case study may separately substitute its fictional Acme
Inc. presentation and `admin@omnitree.no` laboratory sender.

Update README, status, changelog, dialect documentation, upgrade/repair
documentation and the living task status as implementation proceeds.

## Test requirements

Add focused unit and real-object integration coverage for:

- all supported dialect templates;
- schema collision and ownership checks;
- fresh installation and explicit invitation enablement;
- repair and repeated enablement;
- creation, inspection, expiry, rotation, revocation and completion;
- token replay and concurrent completion;
- transaction rollback after failures at each completion stage;
- duplicate email, login and user id behavior;
- ordinary role allowlists and privileged-role rejection;
- password hashing and safe profile fields;
- session invalidation after security changes;
- permission, acquisition, proxy-role and direct-publishing boundaries;
- absence of secrets in returned values, logs and rendered errors;
- existing `0.2.0a1` managed-installation upgrade behavior;
- fallback access when SQL or invitation processing fails; and
- installation from built wheel and source distribution.

Run the complete existing suite throughout the work. Preserve the frozen
`0.1.0a2` upgrade fixture and the `v0.2.0a1` behavior it currently verifies.

After local tests pass, use an isolated or disposable PostgreSQL installation
before touching a shared lab. For the case-study server, back up ZODB and record
database state before running the wizard. Do not publish to main PyPI or modify
another live installation without an explicit release/deployment decision.

## Out of scope

- Sending or receiving email inside SQLUserWizard.
- SMTP account management, IMAP/POP3 processing, SPF, DKIM or DMARC setup.
- SMS provider integration.
- Open public self-registration without an invitation.
- Assigning `Manager`, `Owner` or fallback access from an invitation.
- User self-promotion.
- Arbitrary legacy identity-schema import or takeover.
- Exposing generic SQL execution or unrestricted PAS objects to
  RestrictedPython.
- Replacing the existing session, CSRF, redirect or TOTP security model.
- Automatically starting a full session solely from possession of an email
  invitation token.

## Acceptance criteria

The task is complete when:

1. A clean managed installation can explicitly enable product-owned invitation
   storage on every documented SQL dialect.
2. An existing `v0.2.0a1` managed installation upgrades without SQL changes and
   can enable invitations later through an explicit action.
3. Raw Z SQL Methods and PAS internals remain protected.
4. Documented Script (Python) examples can create, inspect, revoke, rotate and
   complete invitations only through the wrapper.
5. Tokens are hashed, expiring, single-use and replay-safe.
6. Completion creates a normal managed SQL user, profile and approved ordinary
   roles in one verified transaction, then uses the existing login/TOTP flow.
7. Invitations cannot grant privileged roles or fallback access, even when a
   caller tampers with request values.
8. Permission, acquisition and proxy-role tests demonstrate the documented
   script-placement rules.
9. Existing login, session, 2FA, profile, repair, upgrade and fallback tests
   continue to pass.
10. Full documentation, distributions and verification results accurately
    distinguish implemented behavior from pending live database tests.

## Working method

Maintain a current-status section at the top of this file once implementation
begins. Work in reviewable checkpoints:

1. inspect and agree the API and schema;
2. implement schema/templates and collision checks;
3. implement the trusted controller and permissions;
4. add Script (Python) integration tests and examples;
5. verify upgrade/repair behavior;
6. run live isolated PostgreSQL tests;
7. build and inspect distributions; and
8. review release/version/publication separately.

Stop at any newly discovered inconsistency between code, metadata,
documentation, artifacts or deployed state. Report it before continuing with
installation, publication or server changes.
