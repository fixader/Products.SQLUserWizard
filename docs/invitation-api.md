# Invitation API (development branch)

This API is under development on `feature/invitations`, not part of the published
0.2.0a1 package. The optional workflow product is described
[separately](task-optional-invitation-product.md).

## Explicit setup

Open the application's `sql_user_admin` in the ZMI and select **Invitations**.
Select unused table names, an allowlist of ordinary roles, any additional
application-specific privileged roles to reject, and whether enrollment requires
TOTP. Submit **Enable invitations**. This requires Manage users permission and a
valid POST/CSRF request. It creates two tables and `sql_user_provisioning`.

Ordinary product installation and startup never enable invitations. Existing
managed identity SQL must match the expected contract before enablement;
customizations require review. Repeated storage repair preserves records and
rejects silently changed policy or SQL.

## Application scripts and permissions

Place application scripts in a child folder such as `/ordersystem/invitations`.
They acquire `/ordersystem/sql_user_provisioning`; the controller resolves storage
from its own physical application's manifest, not the acquired child context.

The API methods cannot be traversed directly through HTTP. Application scripts
must call them. The controller checks permissions even for direct Python calls.
Its internal helpers and configuration are not a RestrictedPython API.

| Operation | Required permission | Request |
| --- | --- | --- |
| `create_invitation`, `rotate_invitation_secret`, `revoke_invitation`, `record_delivery` | SQLUserWizard: Administer invitations | POST with controller CSRF token |
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
is still pending. Template and script installation is not yet automated.

## Current signatures and results

`REQUEST` is the current Zope request. Render
`context.sql_user_provisioning.csrf_field(context.REQUEST)` inside every mutating
form; the token must be generated for the same user as the submitted request.

```python
create_invitation(email, roles, REQUEST, phone="", user_id="", login_name="",
                  identity_reference="", expires_in=86400)
inspect_invitation(token, REQUEST)
list_invitations(REQUEST)
rotate_invitation_secret(invitation_id, REQUEST)
revoke_invitation(invitation_id, REQUEST)
record_delivery(invitation_id, channel, result, REQUEST)
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

Completion requires the actual database connection to join Zope's current
transaction. It conditionally claims the invitation, performs a strict identity
insert, reuses core profile/role helpers and records acceptance. The request's
transaction manager owns commit/rollback. Adapters with a different registration
model require explicit compatibility work; they are not automatically accepted.

Transactional SQLite tests verify the failure path through Zope's transaction
manager. Live PostgreSQL, broader concurrency/failure cases and the complete
application/MailHost examples remain pending. This document is a development
contract, not a claim that the feature is ready for deployment.
