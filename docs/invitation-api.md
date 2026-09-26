# Invitation API

The core API was introduced in `0.2.0a2`. Version `0.2.0b1` adds the generated
forms and optional MailHost-backed delivery described below. Version `0.2.0b2`
also renders and saves configured profile fields during invitation acceptance.

## Explicit setup

Open the application's `sql_user_admin` in the ZMI and select **Invitations**.
Select unused table names, an allowlist of ordinary roles, any additional
application-specific privileged roles to reject, and whether enrollment requires
TOTP. Submit **Enable invitations**. This requires Manage users permission and a
valid POST/CSRF request. It creates two tables and `sql_user_provisioning`.
For invitation use with OpenODBCDA, install version 1.1.1 or later.

Ordinary product installation and startup never enable invitations. Existing
managed identity SQL must match the expected contract before enablement;
customizations require review. Repeated storage repair preserves records and
rejects silently changed policy or SQL.

Enabling invitations also creates a working `invitations` child folder with
creation, inspection and completion wrappers, forms, narrow proxy roles, local
CSS and Manager notes. See [application Script (Python) examples](invitation-script-examples.md).

## Application scripts and permissions

Place application scripts in a child folder such as `/ordersystem/invitations`.
They acquire `/ordersystem/sql_user_provisioning`; the controller resolves storage
from its own physical application's manifest, not the acquired child context.

The API methods cannot be traversed directly through HTTP. Application scripts
must call them. The controller checks permissions even for direct Python calls.
Its internal helpers and configuration are not a RestrictedPython API.

| Operation | Required permission | Request |
| --- | --- | --- |
| `create_invitation`, `rotate_invitation_secret`, `revoke_invitation`, `record_delivery`, `deliver_invitation_email` | SQLUserWizard: Administer invitations | POST with controller CSRF token |
| `list_invitations` | SQLUserWizard: Administer invitations | Request required |
| `inspect_invitation` | SQLUserWizard: Inspect invitations | Request required; throttled |
| `complete_invitation` | SQLUserWizard: Complete invitations | POST with controller CSRF token; throttled |
| `csrf_field` | Public | Request required |

Only Manager receives these custom permissions by default. For public acceptance,
an administrator can define `InvitationInspector` and `InvitationCompleter` roles
in the application and map them only to the corresponding controller permissions,
without acquisition. Grant the inspector proxy role only to the reviewed
inspection script and the completer proxy role only to the reviewed completion
script. Never grant either role to ordinary users or use a Manager proxy role.
These two role names are explicitly forbidden as invitation assignments.

Zope 6.1 integration tests verify acquisition from a child folder, denied access
without a proxy role, inspection and completion with narrow proxy roles, and
absence of controller acquisition from a sibling application. Zope 5 confirmation
is still pending. Template and script installation is automated when invitations
are enabled.

## Current signatures and results

`REQUEST` is the current Zope request. Render
`context.sql_user_provisioning.csrf_field(context.REQUEST)` inside every mutating
form; the token must be generated for the same user as the submitted request.
When Plone protection is installed, the helper also renders its `_authenticator`
field. Submit both fields; validation occurs before database writes.

```python
create_invitation(email, roles, REQUEST, phone="", user_id="", login_name="",
                  identity_reference="", expires_in=86400)
inspect_invitation(token, REQUEST)
list_invitations(REQUEST)
rotate_invitation_secret(invitation_id, REQUEST)
revoke_invitation(invitation_id, REQUEST)
record_delivery(invitation_id, channel, result, REQUEST)
deliver_invitation_email(invitation_id, token, recipient, REQUEST)
complete_invitation(token, user_id, login_name, password, profile, REQUEST)
```

- Creation returns `invitation_id`, a one-time raw `token`, and `expires_at`.
  Rotation returns `invitation_id` and a replacement raw `token`.
- Email is required; `roles` is a list of approved ordinary role names.
  Expiry is an integer from 300 to 604800 seconds. Times are UTC epoch seconds.
- Inspection returns `valid=False` for unavailable invitations, or `valid=True`,
  `expires_at` and `proposed_login`. It does not reveal recipient details or roles.
- Listing returns at most 100 recent sanitized records, without secret hashes
  or internal claim nonces. Pagination/filtering is not yet provided.
- Revocation returns a `revoked` boolean. Delivery status returns `recorded=True`.
  Channels are `manual` or `email`; results are `pending`, `sent` or `failed`.
  Delivery status does not itself send a message or invalidate an invitation.
- Generated creation wrappers call `deliver_invitation_email`. It considers
  only a MailHost stored directly in the generated `invitations` folder and
  only when a Manager has enabled delivery and supplied a fixed sender, subject
  and canonical invitation URL. It returns `manual`, `sent` or `failed`.
  Delivery events go to the Zope server log without the token, full link,
  message body or SMTP password.
- Completion requires a password of 12-1024 characters. Allowed profile keys
  are `first_name`, `last_name`, `display_name` and `mobile`; email comes from the
  invitation. Approved roles also come exclusively from stored invitation state.
- Completion returns `user_id`, `login_name` and the application's `login_url`.
  It issues no session; use the existing login and required TOTP enrollment flow.

Permission failures raise `Unauthorized`; invalid POST/CSRF or direct traversal
raises `Forbidden`; validation/unavailable invitations raise `ValueError`.
Applications should catch expected input errors and show generic messages without
echoing tokens or passwords. Do not catch errors to commit partial provisioning:
completion failures after claiming doom the transaction, preventing commit.

## Transaction boundary and remaining verification

Invitation creation and completion use the same multi-statement workflow on all
supported SQL dialects. For OpenODBCDA, use **1.1.1 or later**, the verified release
with the explicit transaction API. SQLUserWizard begins the transaction, executes
its Z SQL Methods through the reserved connection and requests commit after all
checks succeed. The adapter performs the database commit when Zope finishes the
request; a normal request abort after the commit request still rolls back the SQL.

Failures roll back the owned transaction and doom the surrounding Zope
transaction, even if application code catches the error. A failed begin does not
commit or roll back a caller-owned transaction. Nested explicit transactions are
not supported: let the controller own the creation/completion transaction.

After creation or completion, **finish the request without executing more SQL
through that connector**. OpenODBCDA rejects SQL after commit has been requested.
Render the returned information or redirect to login; perform further inspection,
delivery-status updates or other database operations in a separate request.

Other adapters must join Zope's transaction directly; the controller checks the
actual connection before writing. Non-participating adapters are refused. There
is no autocommit fallback or PostgreSQL-specific atomic statement implementation.
This requirement concerns invitations, not existing managed authentication.

On 2026-09-26, seven live tests passed against a disposable PostgreSQL database
using the published OpenODBCDA 1.1.1 wheel, its real Zope connector and pool, actual
Z SQL Methods, and the controller's production creation/completion workflow:

- completion, required TOTP state and rejected replay;
- four concurrent attempts producing exactly one identity;
- duplicate user ID/login rejection, preserving the existing identity;
- injected failures at user, profile, catalog, assignment and acceptance writes,
  with no partial changes and a usable connection afterward;
- rejected unapproved roles, expired invitations and revoked invitations;
- failed invitation-role creation rolling back the invitation itself;
- request abort after commit was requested rolling back user creation and
  invitation consumption, followed by a successful retry.

The reproducible harness is `tests/live_invitation_postgresql.py`. Run it directly
with candidate `src` on `PYTHONPATH`, OpenODBCDA 1.1.1 or later installed, and
`SQLUW_TEST_DSN` pointing **only to an empty, disposable PostgreSQL database**.
It creates and truncates test tables. Permission/CSRF checks and PAS fallback
lookup are isolated in this harness; the local integration suite tests those
boundaries separately. It is not part of the default test suite. Test databases
and roles were removed afterward; no application database was modified.

The adapter's commit coordination is not a distributed two-phase commit guarantee
across ZODB and multiple databases, nor a guarantee against an ambiguous result
if the connection fails during physical commit. Do not blindly retry account
creation after such a failure; inspect state in a new request first.

Chapter 4 HTTP invitation/login/optional-TOTP/fallback verification passed on
Plone 6.2.2 and Zope 6.2. The same lab sent a real invitation using a local
MailHost configured for authenticated SMTP with STARTTLS. Live invitation
verification on other database families and Zope 5 wrapper confirmation remain
pending. The SQL workflow is shared;
that alone does not establish live compatibility on every driver or storage engine.

## Attempt limits

Inspection and completion share a limit of 30 attempts per five minutes per
application and caller address in each worker process. The bounded in-memory
counter survives aborted requests, but resets on process restart and is not shared
between workers. Configure trusted proxy handling and a shared ingress limit for
public multi-worker deployments. Invalid token formats also count as attempts.
