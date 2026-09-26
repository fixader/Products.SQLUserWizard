# Application-owned invitation scripts

These examples use the optional core API directly. No separate workflow add-on
is required. Manual delivery works without a mail server; an enabled MailHost
stored directly in the generated folder adds automatic delivery.

First enable invitation storage from **SQL User Admin > Invitations**, allowing
the ordinary `Member` role. SQLUserWizard now creates the `invitations` child
folder, scripts, forms, permissions, proxy roles, local stylesheet, and Manager
notes automatically. The bodies below document the generated wrappers and are
a starting point when an application deliberately takes ownership of one.

## Create an invitation

Script ID: `create_invitation`. Restrict its View permission to Manager, without
acquisition. Do not assign a proxy role. The current manager must have the core
`SQLUserWizard: Administer invitations` permission.

```python
req = context.REQUEST
result = context.sql_user_provisioning.create_invitation(
    email=req.form.get('email', ''),
    roles=['Member'],
    REQUEST=req,
    expires_in=86400,
)
result.update(context.sql_user_provisioning.deliver_invitation_email(
    result['invitation_id'], result['token'], req.form.get('email', ''), req,
))
return result
```

Call it from a manager-only POST form containing the controller's CSRF field.
The result includes a raw token exactly once. Automatic delivery uses only the
local MailHost and fixed Manager configuration. When delivery is unavailable or
fails, present the token only to the authorized Manager for controlled manual
delivery; do not log it or save it in template properties. The example fixes
the role in reviewed code.

## Inspect an invitation

Script ID: `inspect_invitation`. Configure the `InvitationInspector` proxy role
and map only `SQLUserWizard: Inspect invitations` to that role on the controller,
without permission acquisition. The script may have View permission for Anonymous.

```python
req = context.REQUEST
return context.sql_user_provisioning.inspect_invitation(
    token=req.form.get('token', ''), REQUEST=req,
)
```

Use a token-entry POST form for the manual test so the token does not enter access
logs as a URL query parameter. The result contains validity, expiry and proposed
login, not recipient details. Keep response pages uncached and exclude tokens
from application logs and error messages.

## Complete an invitation

Script ID: `complete_invitation`. Give it only the `InvitationCompleter` proxy
role, mapped to `SQLUserWizard: Complete invitations` on the controller without
acquisition. The script may have View permission for Anonymous. Never assign
Manager as a proxy role to either public script.

```python
req = context.REQUEST
return context.sql_user_provisioning.complete_invitation(
    token=req.form.get('token', ''),
    user_id=req.form.get('login_name', ''),
    login_name=req.form.get('login_name', ''),
    password=req.form.get('password', ''),
    profile={
        'first_name': req.form.get('first_name', ''),
        'last_name': req.form.get('last_name', ''),
        'display_name': req.form.get('display_name', ''),
        'mobile': req.form.get('mobile', ''),
    },
    REQUEST=req,
)
```

The completion form must use POST and include the controller-generated CSRF
field, obtained with:

```python
context.sql_user_provisioning.csrf_field(context.REQUEST)
```

Render that trusted field as markup in the form. Escape all other user-controlled
values through the page template's normal escaping. Do not repopulate passwords
after errors. Use the same browser session when rendering and submitting the form.

On success, use the returned `login_url` for the next step. Completion does not
authenticate the browser. The user signs in through the existing login flow and
enrolls TOTP if required. After a lost success response, guide the user to login
or recovery instead of creating another account.

Handle expected validation errors with a generic message. A database failure can
doom the surrounding transaction: let the publisher abort it; do not commit after
catching such a failure. Finish creation/completion requests without further SQL through the same connector.
Explicit transaction boundaries are documented in the
[API reference](invitation-api.md#transaction-boundary-and-remaining-verification).

The generated example provides complete minimal pages, permission setup and
optional local-MailHost delivery. Applications may customize presentation and
wording while preserving the reviewed permission and CSRF boundaries.
