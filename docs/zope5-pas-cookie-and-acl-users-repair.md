# Zope 5 PAS Cookie And Local acl_users Repair

Observed while verifying SQL User Wizard on Zope 5 and Zope 6 labs on
2026-05-26.

## Symptoms

- A valid local PAS exists at `folder/acl_users`, but protected objects still
  challenge with Basic auth from a parent `acl_users`.
- Anonymous access to `secure_test_page` returns `401 Unauthorized` instead of
  redirecting to the SQL User Wizard login form.
- `sql_user_login_submit` accepts valid SQL credentials and sets
  `sql_user_auth`, but the next request is still anonymous.
- Users whose cookie base64 value needs `=` padding fail more visibly because
  the cookie header contains `%253D%253D`.
- A Scriptable Plugin can return success from `authenticateCredentials`, but
  protected pages still challenge or render as anonymous because PAS cannot
  enumerate/build the user principal afterwards.

## Cause 1: local PAS is not bound as the folder user folder

Zope does not use an object as a user folder merely because it is named
`acl_users`. During publication it looks for `__allow_groups__` on the
published object or its parents. PAS normally sets this in `manage_afterAdd`:

```python
container.__allow_groups__ = aq_base(self)
```

Copied/imported folders may contain a valid PAS named `acl_users` without the
folder's `__allow_groups__` pointing to it. In that state Zope continues upward
and asks the parent user folder.

The wizard repair must rebind an existing PAS:

```python
pas.manage_afterAdd(pas, folder)
```

or, if that fails inside product code:

```python
folder.__allow_groups__ = aq_base(pas)
```

This should happen both when the wizard creates a new PAS and when it reuses an
existing PAS during repair. The operation is idempotent: a correctly bound PAS
stays bound, while a copied/imported PAS is repaired.

## Cause 2: Zope response double-encodes quoted CookieAuthHelper values

Products.PluggableAuthService `CookieAuthHelper.updateCredentials` pre-quotes
the cookie value before passing it to `response.setCookie`. In the lab
installations, the response layer quotes the percent signs again. Base64
padding then becomes `%253D%253D` instead of `%3D%3D`.

`CookieAuthHelper.extractCredentials` unquotes once before base64-decoding, so
the double-encoded padded cookie is rejected.

The wizard should still use the PAS Cookie Auth Helper, but the generated
login submit object should set the SQL cookie using the helper's raw base64
value, not the helper's pre-quoted response value:

```python
cookie_value = helper.get_cookie_value(login, password)
if isinstance(cookie_value, bytes):
    cookie_value = cookie_value.decode("ascii")

response.setCookie(
    helper.cookie_name,
    cookie_value,
    path="/",
    same_site=helper.cookie_same_site,
    secure=helper.cookie_same_site == "None" or helper.cookie_secure,
)
```

The important point is that the wizard must call `helper.get_cookie_value(...)`
and pass that raw value to `response.setCookie(...)`. It must not call
`pas.updateCredentials(...)` for the final SQL cookie write on affected
installations.

## Cause 3: SQL auth plugin must enumerate users

PAS does not only need an authentication answer. After credentials are accepted,
it must be able to look up the user as a principal. The SQL Scriptable Plugin
therefore needs:

- `authenticateCredentials`
- `enumerateUsers`
- `getRolesForPrincipal`

and it must be active for all three PAS plugin interfaces:

- `IAuthenticationPlugin`
- `IUserEnumerationPlugin`
- `IRolesPlugin`

If `enumerateUsers` is missing or the plugin is not active as
`IUserEnumerationPlugin`, direct credential checks can succeed while later
requests still behave as anonymous or fall through to a parent user folder.

## Cause 4: local application roles must exist in the SQL role catalog

The wizard can seed generic Zope roles, but application-specific local roles
must also exist in the SQL role catalog used by `getRolesForPrincipal`.
Those role names belong to the local application; they are not product
defaults and should not be seeded globally by SQLUserWizard.

If a role exists in Zope's folder security UI but is missing from the SQL role
catalog, assigning it in the user-role table is not enough. The SQL role lookup
can silently omit it, and the user will authenticate with only the remaining
roles, often just `Authenticated`.

## Wizard implementation checklist

- During install/repair, call the PAS `manage_afterAdd` binding step for
  `acl_users`.
- If `manage_afterAdd` fails, set `folder.__allow_groups__ = aq_base(pas)`.
- Install/update `enumerateUsers` on the SQL Scriptable Plugin.
- Activate the SQL Scriptable Plugin as `IUserEnumerationPlugin`, in addition
  to authentication and roles.
- Ensure any local application roles used by folder security are present and
  enabled in that installation's SQL role catalog before assigning them to
  users. Do not treat project-specific roles as global product roles.
- In the generated login submit object, write the `sql_cookie_auth` cookie
  directly from `get_cookie_value`.
- Keep falling back to `pas.updateCredentials` if the expected SQL cookie helper
  is not present.
- PostgreSQL repair should add/backfill the managed `username` column from an
  older `login_name` column when repairing early managed installs, and loosen
  the old `login_name not null` constraint so new managed writes can use the
  current `username` column.
- Record these repairs in the wizard manifest so the installation can be
  diagnosed later.
- Verify whether each repair is version-specific before documenting it as a
  requirement for every supported Zope/PAS combination.

## Verification

- Anonymous `secure_test_page` should redirect to `sql_user_login_form`.
- Login with a SQL user whose generated cookie contains `=` padding.
- The response cookie should contain `%3D%3D`, not `%253D%253D`.
- The SQL plugin should be listed under active User Enumeration plugins.
- A test user for each application role should show that role from
  `getRolesForPrincipal`.
- A protected folder should return `200 OK` after login.
- A protected folder should still return `401` without the cookie.
