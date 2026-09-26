# Application-owned invitation scripts

These examples use the optional core API directly. No invitation workflow add-on
or mail server is required. They are a starting point for a controlled manual
test, not a complete enrollment user interface.

First enable invitation storage from **SQL User Admin > Invitations**, allowing
the ordinary `Member` role. Create an `invitations` child folder in the application.
Install the following bodies as Zope **Script (Python)** objects with an empty
parameter list. Inputs come from `context.REQUEST.form`.

## Create an invitation

Script ID: `create_invitation`. Restrict its View permission to Manager, without
acquisition. Do not assign a proxy role. The current manager must have the core
`SQLUserWizard: Administer invitations` permission.

```python
req = context.REQUEST
return context.sql_user_provisioning.create_invitation(
    email=req.form.get('email', ''),
    roles=['Member'],
    REQUEST=req,
    expires_in=86400,
)
```

Call it from a manager-only POST form containing the controller's CSRF field.
The result includes a raw token exactly once. Present it only to the authorized
manager for controlled delivery; do not log it or save it in template properties.
The example deliberately fixes the role in reviewed code.

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
    user_id=req.form.get('user_id', ''),
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

The future optional product will provide complete pages, permission setup and
delivery orchestration using these same controller methods.
