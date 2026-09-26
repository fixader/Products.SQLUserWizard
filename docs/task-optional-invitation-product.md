# Task: Optional invitation workflow product

Created: 2026-09-25
Status: Design only. Implement the SQLUserWizard invitation API first.

This is a living design document. Update it as the core API and application
examples establish concrete requirements. The add-on has not been implemented;
its package name and release version have not been selected.

## Purpose

Offer a complete invitation workflow that a Zope application can install and
customize, following SQLUserWizard's model of assembling inspectable Zope objects.
Applications may instead use the core API directly with their own Script (Python)
objects. Installing this add-on must never be a requirement for invitation API use.

## Ownership boundary

SQLUserWizard owns invitation tables, SQL dialect support, ownership/collision
checks, secret generation and hashing, expiry, revocation, single-use enforcement,
permissions, ordinary-role restrictions and transactional user provisioning.
These operations are exposed through its documented, protected controller API.

The optional product owns ready-to-use forms, application scripts, presentation,
delivery orchestration and setup guidance. It must call the same public wrapper
API available to application authors. It must not access private controller
helpers, raw SQL methods, database connections or PAS internals.

Application configuration owns branding, the canonical HTTPS origin, support
information, mail wording and selection of approved ordinary roles. A configured
MailHost owns SMTP transport and credentials. SQLUserWizard does not send email.

## Optional activation

- Ordinary SQLUserWizard installation and startup create no invitation tables.
- Direct API users explicitly enable invitation storage through core setup.
- Add-on setup offers that same explicit enablement step when storage is absent.
- Installing the Python add-on package alone must execute no application DDL.
- Existing enabled storage is reused through the core ownership checks.
- Disabling/removing the add-on leaves core invitations and SQL users intact.
  Revoking pending invitations is a separate administrator operation.
- Removing tables or deleting user data is never an uninstall side effect.

## Intended installed experience

An administrator selects the application folder and installs the workflow.
Setup validates core API compatibility, explicit invitation enablement and
permissions before installing application objects. It provides:

1. An invitation form selecting recipients and approved ordinary roles.
2. A list with status, expiry and delivery result.
3. Explicit revoke and rotate/reissue operations. Reissue invalidates old links.
4. A public invitation-entry page showing only the core API's sanitized data.
5. Registration forms for the permitted identity, password and profile fields.
6. A completion page directing users into existing SQLUserWizard login and,
   where required, its existing TOTP enrollment flow.

Pages and wording should be editable without modifying security code. Default
templates must work without branding. Managers can configure organization name,
logo, support address and explanatory text at the application level.

## Delivery

Use the application's acquired MailHost and a configured canonical HTTPS origin.
Manual controlled delivery must remain available, including installations without
MailHost. Do not construct invitation origins from an untrusted request Host.

Only create/rotate returns a raw token. It must not be persisted in template
properties, diagnostics, logs or delivery history. Do not send during the SQL
provisioning transaction. Design post-commit delivery so an SMTP failure leaves
a valid invitation; record only sanitized delivery status through the core API.
Because raw tokens cannot be recovered, a later retry may require explicit
rotation and a newly generated link. Do not promise transparent resend of an
existing secret.

Core creation and completion own an explicit transaction with OpenODBCDA 1.1.1
or later. After either returns, the add-on must finish the request without more
SQL through that connector: the database commit is requested and deferred until
Zope completes the request. Send mail after successful commit and record delivery
in a separate request/transaction. Do not nest a caller-owned transaction around
the core operation. See the core [transaction boundary](invitation-api.md#transaction-boundary-and-remaining-verification).

## Permissions and security

The add-on must install only narrowly authorized scripts, using the final core
permission/proxy-role contract. Public completion must not run with Manager
proxy roles. Placement under an application folder enables acquisition, but
does not replace permission checks.

Every mutating form must use POST and the core CSRF mechanism. Token pages must
prevent caching and referrer leakage and avoid third-party assets. The product
must not grant privileged roles, bypass token validation, or create a logged-in
session merely because the user possesses an invitation.

## Compatibility and lifecycle

Declare a minimum SQLUserWizard version once its API is released. Refuse setup
against an incompatible API with a clear diagnostic. Do not duplicate core schema
upgrades or silently change its policy. Preserve application-customized templates
on add-on repair and report conflicts for review.

## Required tests

- Both custom-script-only and add-on workflows use the same core API.
- Package installation and ordinary Zope startup do not create invitation tables.
- Fresh setup, existing enabled storage and repeat setup preserve data.
- Create, inspect, revoke, rotate and complete work through actual Zope scripts.
- Permissions, acquisition and proxy roles enforce application isolation.
- POST/CSRF, token leakage, expiry and replay behavior remain enforced.
- Manual delivery, successful MailHost delivery and SMTP failure behave as documented.
- Custom templates survive repair; disabling the add-on preserves normal login.
- Upgrade incompatibility fails before changing application objects or SQL data.

## Open decisions

- Package name, supported core API version and ZMI installation entry point.
- Exact generated folder/object names and configurable presentation fields.
- Post-commit MailHost delivery and safe failure reporting without token persistence.
- Whether administrator pages use editable DTML or another supported template type.

## Relationship to current implementation

Track core implementation in
[the invitation API task](task-script-provisioning-and-invitations.md).
Implement and verify that API before developing or publishing this add-on.
