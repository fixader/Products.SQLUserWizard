from html import escape
from types import SimpleNamespace
from urllib.parse import urlencode

from AccessControl import ClassSecurityInfo
from AccessControl import getSecurityManager
from AccessControl.Permissions import manage_users, view
from OFS.SimpleItem import SimpleItem
from zExceptions import Unauthorized

from .compat import InitializeClass
from .config import (
    DEFAULT_ADMIN_ID,
    DEFAULT_TOTP_ISSUER,
    DEFAULT_PASSWORD_HASH_ID,
    DEFAULT_PAS_ID,
    DEFAULT_PLUGIN_ID,
    DEFAULT_PROFILE_FORM_ID,
    DEFAULT_PROFILE_GET_ID,
    DEFAULT_PROFILE_SAVE_ID,
    DEFAULT_LOGOUT_ID,
)
from .sqladmin import (
    delete_sql_user,
    first_row,
    save_sql_profile,
    save_sql_role,
    save_sql_user,
)
from .qrcode import qrcode_svg_data_uri
from .totp import normalize_totp_secret
from .totp import otpauth_uri
from .totp import generate_totp_secret
from .totp import verify_totp_code


class SQLUserAdmin(SimpleItem):
    """Small application-level SQL user administration tool."""

    meta_type = "SQL User Admin"
    security = ClassSecurityInfo()
    security.declareObjectProtected(view)

    pas_id = DEFAULT_PAS_ID
    plugin_id = DEFAULT_PLUGIN_ID
    totp_issuer = DEFAULT_TOTP_ISSUER

    def __init__(self, id=DEFAULT_ADMIN_ID):
        self.id = id

    manage_options = (
        {"label": "Users", "action": "manage_main"},
        {"label": "Security", "action": "manage_access"},
    )

    security.declareProtected(manage_users, "manage_main")

    def manage_main(self, REQUEST=None):
        """Render and process the SQL user admin screen."""

        if REQUEST is not None:
            REQUEST.RESPONSE.setHeader("Content-Type", "text/html; charset=utf-8")

        message = ""
        if REQUEST is not None and REQUEST.get("delete_user"):
            try:
                self._delete_from_request(REQUEST)
            except Exception as exc:
                message = self._message(str(exc), "error")
            else:
                message = self._message("User deleted", "ok")
        elif REQUEST is not None and REQUEST.get("save_user"):
            try:
                self._save_user_from_request(REQUEST)
            except Exception as exc:
                message = self._message(str(exc), "error")
            else:
                message = self._message("User saved", "ok")
        elif REQUEST is not None and REQUEST.get("save_role"):
            try:
                self._save_role_from_request(REQUEST)
            except Exception as exc:
                message = self._message(str(exc), "error")
            else:
                message = self._message("Role saved", "ok")

        selected_user_id = ""
        if REQUEST is not None and not REQUEST.get("delete_user"):
            selected_user_id = REQUEST.get("user_id", "")

        return self._render(message, selected_user_id, REQUEST)

    security.declareProtected(manage_users, "manage_workspace")

    def manage_workspace(self, REQUEST=None):
        """Render the default ZMI workspace for this object."""

        return self.manage_main(REQUEST)

    security.declareProtected(manage_users, "index_html")

    def index_html(self, REQUEST=None):
        """Render the admin screen when opened directly."""

        return self.manage_main(REQUEST)

    security.declareProtected(view, "my_profile")

    def my_profile(self, REQUEST=None):
        """Render and process the current user's own profile screen."""

        if REQUEST is not None:
            REQUEST.RESPONSE.setHeader("Content-Type", "text/html; charset=utf-8")

        user_id = getSecurityManager().getUser().getId()
        if not user_id or user_id == "Anonymous User":
            raise Unauthorized("Login is required")

        message = ""
        if REQUEST is not None and REQUEST.get("save_profile"):
            try:
                self._save_profile_from_request(user_id, REQUEST)
            except Exception as exc:
                message = self._message(str(exc), "error")
            else:
                message = self._message("Profile saved", "ok")

        user = self._get_user_with_profile(user_id)
        return self._render_profile_page(user, message, REQUEST)

    security.declareProtected(view, "my_2fa")

    def my_2fa(self, REQUEST=None):
        """Render and process the current user's authenticator setup."""

        if REQUEST is not None:
            REQUEST.RESPONSE.setHeader("Content-Type", "text/html; charset=utf-8")

        user_id = getSecurityManager().getUser().getId()
        if not user_id or user_id == "Anonymous User":
            raise Unauthorized("Login is required")

        user = self._get_user_with_profile(user_id)
        if user is None:
            raise Unauthorized("Current user is not a SQL user")

        came_from = self._safe_came_from(REQUEST)
        message = ""
        if REQUEST is not None and REQUEST.get("reset_totp"):
            secret = generate_totp_secret()
            self._update_user_totp(user_id, enabled=False, secret=secret)
            message = self._message("New authenticator setup code created", "ok")
            user = self._get_user_with_profile(user_id)
        elif REQUEST is not None and REQUEST.get("confirm_totp"):
            secret = normalize_totp_secret(getattr(user, "totp_secret", ""))
            code = REQUEST.get("otp_code", "")
            if secret and verify_totp_code(secret, code):
                self._update_user_totp(user_id, enabled=True, secret=secret)
                if came_from:
                    REQUEST.RESPONSE.redirect(came_from)
                    return ""
                message = self._message("Two-factor authentication is now active", "ok")
                user = self._get_user_with_profile(user_id)
            else:
                message = self._message("Authenticator code was not accepted", "error")
        elif REQUEST is not None and REQUEST.get("disable_totp"):
            secret = normalize_totp_secret(getattr(user, "totp_secret", ""))
            self._update_user_totp(user_id, enabled=False, secret=secret)
            message = self._message("Two-factor authentication is disabled", "ok")
            user = self._get_user_with_profile(user_id)

        return self._render_2fa_page(user, message, REQUEST)

    def _plugin(self):
        pas = getattr(self.aq_parent, self.pas_id)
        return getattr(pas, self.plugin_id)

    def _save_user_from_request(self, REQUEST):
        user_id = REQUEST.get("edit_user_id") or REQUEST.get("user_id", "")
        login_name = REQUEST.get("login_name", "")
        if not user_id.strip():
            raise ValueError("User id is required")
        if not login_name.strip():
            raise ValueError("Login name is required")

        save_sql_user(
            self._plugin(),
            user_id=user_id.strip(),
            login_name=login_name.strip(),
            password=REQUEST.get("password", ""),
            password_hash_id=REQUEST.get(
                "password_hash_id",
                DEFAULT_PASSWORD_HASH_ID,
            ),
            recovery_email=REQUEST.get("recovery_email", ""),
            first_name=REQUEST.get("first_name", ""),
            last_name=REQUEST.get("last_name", ""),
            display_name=REQUEST.get("display_name", ""),
            email=REQUEST.get("email", ""),
            mobile=REQUEST.get("mobile", ""),
            enabled=bool(REQUEST.get("enabled", "")),
            totp_required=bool(REQUEST.get("totp_required", "")),
            totp_enabled=bool(REQUEST.get("totp_enabled", "")),
            totp_secret=REQUEST.get("totp_secret", ""),
            generate_new_totp_secret=bool(REQUEST.get("generate_totp_secret", "")),
            roles=REQUEST.get("roles", []),
            save_profile=False,
        )
        self._save_profile_from_request(user_id.strip(), REQUEST)

    def _save_role_from_request(self, REQUEST):
        save_sql_role(
            self._plugin(),
            role_id=REQUEST.get("role_id", ""),
            title=REQUEST.get("role_title", ""),
            enabled=bool(REQUEST.get("role_enabled", "")),
        )

    def _save_profile_from_request(self, user_id, REQUEST):
        values = {
            "user_id": user_id,
            "first_name": REQUEST.get("first_name", ""),
            "last_name": REQUEST.get("last_name", ""),
            "display_name": REQUEST.get("display_name", ""),
            "email": REQUEST.get("email", ""),
            "mobile": REQUEST.get("mobile", ""),
        }
        save_method = getattr(self.aq_parent, DEFAULT_PROFILE_SAVE_ID, None)
        if save_method is not None:
            save_method(**values)
            return

        save_sql_profile(self._plugin(), **values)

    def _delete_from_request(self, REQUEST):
        user_id = REQUEST.get("edit_user_id") or REQUEST.get("user_id", "")
        delete_sql_user(self._plugin(), user_id)

    def _update_user_totp(self, user_id, enabled, secret):
        self._plugin().zsql_pas_update_2fa(
            user_id=user_id,
            totp_required="",
            totp_enabled="1" if enabled else "",
            totp_secret=normalize_totp_secret(secret),
        )

    def _render(self, message, selected_user_id, REQUEST=None):
        plugin = self._plugin()
        users = list(plugin.zsql_pas_list_users())
        roles = list(plugin.zsql_pas_list_roles())
        came_from = self._admin_came_from(REQUEST)
        return_link = self._back_to_app_link(came_from)
        selected = None
        selected_roles = []
        if selected_user_id:
            selected = self._get_user_with_profile(selected_user_id)
            selected_roles = [
                row.role for row in plugin.zsql_pas_fetch_roles(user_id=selected_user_id)
            ]

        return f"""<!doctype html>
<html>
<head>
  <title>SQL User Admin</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1.5rem; color: #172033; }}
    a {{ color: #1d5f9f; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
    th, td {{ border-bottom: 1px solid #d6dbe3; padding: .45rem; text-align: left; vertical-align: top; }}
    th {{ background: #f5f7fa; font-size: .9rem; }}
    label {{ display: block; margin: .65rem 0; font-weight: 600; }}
    input {{ box-sizing: border-box; width: min(36rem, 100%); padding: .4rem; }}
    button, .button {{ padding: .45rem .8rem; }}
    fieldset {{ border: 1px solid #c8ced8; margin: 1rem 0; padding: 1rem; }}
    legend {{ font-weight: 700; }}
    .top-layout {{ display: grid; grid-template-columns: minmax(28rem, 1fr) minmax(22rem, .75fr); gap: 1.5rem; align-items: start; }}
    .panel {{ border: 1px solid #c8ced8; padding: 1rem; background: #fff; }}
    .ok {{ border-left: 4px solid #17803a; padding: .6rem; background: #eef8f0; }}
    .error {{ border-left: 4px solid #b42318; padding: .6rem; background: #fff1f0; }}
    .muted {{ color: #667085; }}
    .status {{ display: inline-block; min-width: 4.8rem; padding: .15rem .45rem; border-radius: .25rem; text-align: center; font-size: .85rem; font-weight: 600; }}
    .status-active {{ color: #075e2b; background: #dff6e7; }}
    .status-inactive {{ color: #7a271a; background: #fde6df; }}
    .danger {{ color: #8a1f11; }}
    .form-actions {{ display: flex; flex-wrap: wrap; gap: .6rem; align-items: center; margin-top: .8rem; }}
    .role-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr)); gap: .4rem .8rem; }}
    .role-choice {{ display: flex; align-items: center; gap: .4rem; font-weight: 500; margin: .15rem 0; }}
    .role-choice input {{ width: auto; }}
    .totp-setup {{ display: grid; grid-template-columns: auto minmax(0, 1fr); gap: .8rem; align-items: start; margin-top: .8rem; }}
    .totp-qr {{ width: 11rem; height: 11rem; border: 1px solid #c8ced8; background: #fff; padding: .4rem; box-sizing: border-box; }}
    code.wrap {{ display: block; white-space: normal; overflow-wrap: anywhere; }}
    .split {{ display: grid; grid-template-columns: 1fr 1fr; gap: .75rem; }}
    .toolbar {{ display: flex; justify-content: space-between; gap: 1rem; align-items: center; margin-bottom: 1rem; }}
    @media (max-width: 900px) {{ .top-layout, .split, .totp-setup {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <div class="toolbar">
    <h1>SQL User Admin</h1>
    {return_link}
  </div>
  <p class="muted">Security users, profiles, and roles are stored through the generated Z SQL Methods in <code>{escape(self.pas_id)}/{escape(self.plugin_id)}</code>.</p>
  {message}
  <div class="top-layout">
    <section class="panel">
      <h2>Users</h2>
      {self._render_users_table(users, came_from)}
    </section>
    <section class="panel">
      <h2>Roles</h2>
      {self._render_roles_table(roles)}
      {self._render_role_form(came_from)}
    </section>
  </div>
  <section class="panel">
    <h2>{'Edit user' if selected else 'Create user'}</h2>
    {self._render_user_form(selected, roles, selected_roles, REQUEST, came_from)}
  </section>
</body>
</html>"""

    def _render_users_table(self, users, came_from=""):
        rows = []
        for user in users:
            user_id = escape(str(user.user_id))
            query = {"user_id": str(user.user_id)}
            if came_from:
                query["came_from"] = came_from
            href = "?" + urlencode(query)
            enabled = self._truthy(getattr(user, "enabled", True))
            status_class = "status-active" if enabled else "status-inactive"
            status_text = "Active" if enabled else "Inactive"
            display_name = self._display_name(user)
            rows.append(
                "<tr>"
                f"<td><a href='{escape(href)}'>{user_id}</a></td>"
                f"<td>{escape(str(user.login_name))}</td>"
                f"<td>{display_name}</td>"
                f"<td>{escape(str(getattr(user, 'email', '') or ''))}</td>"
            f"<td>{escape(str(getattr(user, 'roles', '') or ''))}</td>"
            f"<td><span class='status {status_class}'>{status_text}</span></td>"
            f"<td>{'On' if self._truthy(getattr(user, 'totp_enabled', False)) else 'Off'}</td>"
            "</tr>"
        )

        if not rows:
            return "<p>No SQL users found yet.</p>"

        return (
            "<table><thead><tr>"
            "<th>User id</th><th>Login</th><th>Name</th><th>Email</th><th>Roles</th><th>Status</th><th>2FA</th>"
            "</tr></thead><tbody>"
            + "\n".join(rows)
            + "</tbody></table>"
        )

    def _render_roles_table(self, roles):
        if not roles:
            return "<p>No SQL roles found yet.</p>"

        rows = []
        for role in roles:
            enabled = self._truthy(getattr(role, "enabled", True))
            status_class = "status-active" if enabled else "status-inactive"
            status_text = "Active" if enabled else "Inactive"
            rows.append(
                "<tr>"
                f"<td>{escape(str(role.role_id))}</td>"
                f"<td>{escape(str(getattr(role, 'title', '') or ''))}</td>"
                f"<td><span class='status {status_class}'>{status_text}</span></td>"
                "</tr>"
            )
        return (
            "<table><thead><tr><th>Role</th><th>Title</th><th>Status</th></tr></thead><tbody>"
            + "\n".join(rows)
            + "</tbody></table>"
        )

    def _render_role_form(self, came_from=""):
        return f"""<form method="post" class="panel">
  <h3>Create or update role</h3>
  <input type="hidden" name="save_role" value="1">
  {self._came_from_input(came_from)}
  <label>Role id
    <input name="role_id" value="">
  </label>
  <label>Title
    <input name="role_title" value="">
  </label>
  <label class="role-choice">
    <input name="role_enabled" type="checkbox" value="1" checked>
    Active
  </label>
  <button type="submit">Save role</button>
</form>"""

    def _render_user_form(self, user, roles, selected_roles, REQUEST=None, came_from=""):
        value = self._value
        enabled = True if user is None else self._truthy(getattr(user, "enabled", True))
        delete_button = ""
        if user is not None:
            delete_button = """<button class="danger" type="submit" name="delete_user" value="1" onclick="return confirm('Delete this SQL user? This cannot be undone.');">Delete user</button>"""
        new_user_href = "./manage_workspace"
        if came_from:
            new_user_href = "./manage_workspace?" + urlencode({"came_from": came_from})
        return f"""<form method="post">
  <input type="hidden" name="save_user" value="1">
  {self._came_from_input(came_from)}
  <div class="top-layout">
    <fieldset>
      <legend>Security</legend>
      <label>User id
        <input name="edit_user_id" value="{value(user, 'user_id')}" {'readonly' if user else ''}>
      </label>
      <label>Login name
        <input name="login_name" value="{value(user, 'login_name')}">
      </label>
      <label>Password
        <input name="password" type="password" value="">
      </label>
      <label>Password hash id
        <input name="password_hash_id" value="{value(user, 'password_hash_id') or DEFAULT_PASSWORD_HASH_ID}">
      </label>
      <label>Recovery email
        <input name="recovery_email" value="{value(user, 'recovery_email')}">
      </label>
      <label class="role-choice">
        <input name="enabled" type="checkbox" value="1" {'checked' if enabled else ''}>
        Enabled
      </label>
      {self._render_totp_settings(user)}
    </fieldset>
    <fieldset>
      <legend>Roles</legend>
      {self._render_role_choices(roles, selected_roles)}
    </fieldset>
  </div>
  <div class="form-actions">
    <button type="submit">Save security and roles</button>
    {delete_button}
    <a href="{escape(new_user_href)}">New user</a>
  </div>
  {self._render_profile_fields(user, REQUEST)}
</form>"""

    def _render_profile_fields(self, user, REQUEST=None):
        template = getattr(self.aq_parent, DEFAULT_PROFILE_FORM_ID, None)
        if template is not None:
            data = self._profile_template_data(user)
            try:
                return template(client=self, REQUEST=REQUEST or {}, **data)
            except TypeError:
                return template(self, REQUEST or {}, **data)

        return self._render_builtin_profile_fields(user)

    def _render_totp_settings(self, user):
        enabled = self._truthy(getattr(user, "totp_enabled", False)) if user is not None else False
        required = self._truthy(getattr(user, "totp_required", False)) if user is not None else False
        secret = normalize_totp_secret(getattr(user, "totp_secret", "") if user is not None else "")
        account_name = getattr(user, "login_name", "") or getattr(user, "user_id", "") if user is not None else ""
        issuer = getattr(self, "totp_issuer", DEFAULT_TOTP_ISSUER) or DEFAULT_TOTP_ISSUER
        uri = otpauth_uri(secret, account_name or "new-user", issuer) if secret else ""
        uri_html = ""
        if uri:
            try:
                qr = qrcode_svg_data_uri(uri)
                qr_html = f"<img class='totp-qr' src='{qr}' alt='Authenticator QR code'>"
            except Exception:
                qr_html = ""
            uri_html = (
                "<div class='totp-setup'>"
                f"{qr_html}"
                "<p class='muted'>Scan this with an authenticator app. It uses "
                f"issuer <strong>{escape(issuer)}</strong> for folders using "
                f"this config.<br><code class='wrap'>{escape(uri)}</code></p>"
                "</div>"
            )
        return f"""
      <fieldset>
        <legend>Two-factor authentication</legend>
        <label class="role-choice">
          <input name="totp_required" type="checkbox" value="1" {'checked' if required else ''}>
          Require 2FA enrollment before app access
        </label>
        <label class="role-choice">
          <input name="totp_enabled" type="checkbox" value="1" {'checked' if enabled else ''}>
          Require authenticator code at login
        </label>
        <label>TOTP secret
          <input name="totp_secret" value="{escape(secret)}">
        </label>
        <label class="role-choice">
          <input name="generate_totp_secret" type="checkbox" value="1">
          Generate new setup secret when saving
        </label>
        <p class="muted">For normal onboarding, generate a setup secret and
        check enrollment required, but leave active login unchecked. The user
        can then log in with password, scan the QR code, and activate 2FA by
        confirming one code. Users may also open <code>{escape(self.id)}/my_2fa</code>
        themselves and turn 2FA on voluntarily.</p>
        {uri_html}
      </fieldset>"""

    def _render_builtin_profile_fields(self, user):
        value = self._value
        return f"""
  <fieldset>
    <legend>Profile</legend>
    <div class="split">
      <label>First name
        <input name="first_name" value="{value(user, 'first_name')}">
      </label>
      <label>Last name
        <input name="last_name" value="{value(user, 'last_name')}">
      </label>
    </div>
    <label>Display name
      <input name="display_name" value="{value(user, 'display_name')}">
    </label>
    <label>Email
      <input name="email" value="{value(user, 'email')}">
    </label>
    <label>Mobile
      <input name="mobile" value="{value(user, 'mobile')}">
    </label>
  </fieldset>"""

    def _render_profile_page(self, user, message, REQUEST=None):
        came_from = self._safe_came_from(REQUEST)
        user_id = "" if user is None else escape(str(user.user_id))
        display_name = escape(self._display_name(user) or user_id)
        back_link = self._back_to_app_link(came_from)
        twofa_link = self._with_came_from("my_2fa", came_from)
        came_from_input = self._came_from_input(came_from)
        return f"""<!doctype html>
<html>
<head>
  <title>My Profile</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; color: #172033; background: #eef2f6; }}
    main {{ max-width: 860px; margin: 0 auto; padding: 2rem; box-sizing: border-box; }}
    .toolbar {{ display: flex; justify-content: space-between; gap: 1rem; align-items: center; margin-bottom: 1rem; }}
    .toolbar a {{ color: #1f5f8b; text-decoration: none; font-weight: 650; }}
    .panel {{ background: #fff; border: 1px solid #d5dbe3; box-shadow: 0 12px 34px rgba(20, 34, 52, .08); }}
    .hero {{ padding: 1.4rem 1.5rem; border-bottom: 1px solid #d5dbe3; background: #203447; color: #fff; }}
    .hero h1 {{ margin: 0 0 .3rem; font-size: 1.5rem; }}
    .hero p {{ margin: 0; color: #dbe5ee; }}
    .content {{ padding: 1.5rem; }}
    label {{ display: block; margin: .7rem 0; font-weight: 650; }}
    input {{ box-sizing: border-box; width: min(36rem, 100%); padding: .6rem .65rem; border: 1px solid #b8c2cf; font: inherit; }}
    input:focus {{ outline: 2px solid #6797c6; outline-offset: 1px; }}
    button {{ padding: .7rem 1rem; border: 0; background: #20663f; color: #fff; font: inherit; font-weight: 750; cursor: pointer; }}
    button:hover {{ background: #185532; }}
    fieldset {{ border: 1px solid #c8ced8; margin: 0 0 1rem; padding: 1rem; }}
    legend {{ font-weight: 700; }}
    .ok {{ border-left: 4px solid #17803a; padding: .6rem; background: #eef8f0; }}
    .error {{ border-left: 4px solid #b42318; padding: .6rem; background: #fff1f0; }}
    .muted {{ color: #667085; }}
    .split {{ display: grid; grid-template-columns: 1fr 1fr; gap: .75rem; }}
    @media (max-width: 700px) {{
      main {{ padding: 1rem; }}
      .toolbar {{ align-items: flex-start; flex-direction: column; }}
      .split {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="toolbar">
      {back_link}
      <a href="{twofa_link}">Authenticator setup</a>
      <a href="../{DEFAULT_LOGOUT_ID}">Log out</a>
    </div>
    <section class="panel">
      <div class="hero">
        <h1>{display_name}</h1>
        <p>Profile for <code>{user_id}</code>.</p>
      </div>
      <div class="content">
        {message}
        <form method="post">
          <input type="hidden" name="save_profile" value="1">
          {came_from_input}
          {self._render_profile_fields(user, REQUEST)}
          <button type="submit">Save profile</button>
        </form>
      </div>
    </section>
  </main>
</body>
</html>"""

    def _render_2fa_page(self, user, message, REQUEST=None):
        came_from = self._safe_came_from(REQUEST)
        user_id = escape(str(getattr(user, "user_id", "") or ""))
        login_name = escape(str(getattr(user, "login_name", "") or user_id))
        enabled = self._truthy(getattr(user, "totp_enabled", False))
        secret = normalize_totp_secret(getattr(user, "totp_secret", ""))
        issuer = getattr(self, "totp_issuer", DEFAULT_TOTP_ISSUER) or DEFAULT_TOTP_ISSUER
        uri = otpauth_uri(secret, login_name, issuer) if secret else ""
        qr_html = ""
        if uri:
            try:
                qr = qrcode_svg_data_uri(uri)
                qr_html = f"<img class='totp-qr' src='{qr}' alt='Authenticator QR code'>"
            except Exception:
                qr_html = "<p class='error'>QR code could not be rendered.</p>"

        required = self._truthy(getattr(user, "totp_required", False))
        status = "Active" if enabled else "Enrollment required" if required else "Not active yet"
        back_link = self._back_to_app_link(came_from)
        profile_link = self._with_came_from("my_profile", came_from)
        came_from_input = self._came_from_input(came_from)
        setup_block = (
            f"""<div class="totp-setup">{qr_html}
              <div>
                <p>Scan this QR code with your authenticator app.</p>
                <p class="muted">It should appear as <strong>{escape(issuer)}:{login_name}</strong>.</p>
                <code class="wrap">{escape(uri)}</code>
              </div>
            </div>"""
            if uri
            else "<p>No setup secret exists yet. Create one below.</p>"
        )
        return f"""<!doctype html>
<html>
<head>
  <title>Authenticator Setup</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; color: #172033; background: #eef2f6; }}
    main {{ max-width: 760px; margin: 0 auto; padding: 2rem; box-sizing: border-box; }}
    .toolbar {{ display: flex; justify-content: space-between; gap: 1rem; align-items: center; margin-bottom: 1rem; }}
    .toolbar a {{ color: #1f5f8b; text-decoration: none; font-weight: 650; }}
    .panel {{ background: #fff; border: 1px solid #d5dbe3; box-shadow: 0 12px 34px rgba(20, 34, 52, .08); }}
    .hero {{ padding: 1.4rem 1.5rem; border-bottom: 1px solid #d5dbe3; background: #203447; color: #fff; }}
    .hero h1 {{ margin: 0 0 .3rem; font-size: 1.5rem; }}
    .hero p {{ margin: 0; color: #dbe5ee; }}
    .content {{ padding: 1.5rem; }}
    label {{ display: block; margin: .7rem 0; font-weight: 650; }}
    input {{ box-sizing: border-box; width: min(24rem, 100%); padding: .6rem .65rem; border: 1px solid #b8c2cf; font: inherit; }}
    button {{ padding: .7rem 1rem; border: 0; background: #20663f; color: #fff; font: inherit; font-weight: 750; cursor: pointer; margin-right: .5rem; }}
    button.secondary {{ background: #334155; }}
    button.danger {{ background: #9f2a1d; }}
    .totp-setup {{ display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 1rem; align-items: start; margin: 1rem 0; }}
    .totp-qr {{ width: 14rem; height: 14rem; border: 1px solid #c8ced8; background: #fff; padding: .5rem; box-sizing: border-box; }}
    .ok {{ border-left: 4px solid #17803a; padding: .6rem; background: #eef8f0; }}
    .error {{ border-left: 4px solid #b42318; padding: .6rem; background: #fff1f0; }}
    .muted {{ color: #667085; }}
    code.wrap {{ display: block; white-space: normal; overflow-wrap: anywhere; background: #f6f7f9; padding: .45rem; }}
    @media (max-width: 700px) {{
      main {{ padding: 1rem; }}
      .toolbar, .totp-setup {{ align-items: flex-start; grid-template-columns: 1fr; flex-direction: column; }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="toolbar">
      {back_link}
      <a href="{profile_link}">My profile</a>
      <a href="../{DEFAULT_LOGOUT_ID}">Log out</a>
    </div>
    <section class="panel">
      <div class="hero">
        <h1>Authenticator Setup</h1>
        <p>{login_name} - {status}</p>
      </div>
      <div class="content">
        {message}
        {setup_block}
        <form method="post">
          {came_from_input}
          <label>Code from authenticator app
            <input name="otp_code" inputmode="numeric" autocomplete="one-time-code">
          </label>
          <button type="submit" name="confirm_totp" value="1">Activate 2FA</button>
          <button class="secondary" type="submit" name="reset_totp" value="1">Create new QR</button>
          <button class="danger" type="submit" name="disable_totp" value="1">Disable 2FA</button>
        </form>
      </div>
    </section>
  </main>
</body>
</html>"""

    def _profile_template_data(self, user):
        return {
            "user_id": self._raw_value(user, "user_id"),
            "first_name": self._raw_value(user, "first_name"),
            "last_name": self._raw_value(user, "last_name"),
            "display_name": self._raw_value(user, "display_name"),
            "email": self._raw_value(user, "email"),
            "mobile": self._raw_value(user, "mobile"),
        }

    def _get_user_with_profile(self, user_id):
        user = first_row(self._plugin().zsql_pas_get_user(user_id=user_id))
        if user is None:
            return None

        data = {}
        for name in (
            "user_id",
            "login_name",
            "password_hash_id",
            "enabled",
            "totp_required",
            "totp_enabled",
            "totp_secret",
            "recovery_email",
            "first_name",
            "last_name",
            "display_name",
            "email",
            "mobile",
        ):
            data[name] = getattr(user, name, "")

        get_method = getattr(self.aq_parent, DEFAULT_PROFILE_GET_ID, None)
        if get_method is not None:
            profile = first_row(get_method(user_id=user_id))
            if profile is not None:
                for name in (
                    "first_name",
                    "last_name",
                    "display_name",
                    "email",
                    "mobile",
                ):
                    data[name] = getattr(profile, name, "")

        return SimpleNamespace(**data)

    def _render_role_choices(self, roles, selected_roles):
        active_roles = [role for role in roles if self._truthy(getattr(role, "enabled", True))]
        if not active_roles:
            return "<p class='muted'>Create a role first, then assign it here.</p>"

        selected = set(selected_roles)
        choices = []
        for role in active_roles:
            role_id = str(role.role_id)
            title = str(getattr(role, "title", "") or role_id)
            choices.append(
                "<label class='role-choice'>"
                f"<input name='roles:list' type='checkbox' value='{escape(role_id)}' {'checked' if role_id in selected else ''}>"
                f"{escape(role_id)} <span class='muted'>{escape(title) if title != role_id else ''}</span>"
                "</label>"
            )
        return "<div class='role-grid'>" + "\n".join(choices) + "</div>"

    def _display_name(self, user):
        display_name = getattr(user, "display_name", "") or ""
        if display_name:
            return escape(str(display_name))
        return escape(
            " ".join(
                part
                for part in (
                    getattr(user, "first_name", "") or "",
                    getattr(user, "last_name", "") or "",
                )
                if part
            )
        )

    def _value(self, user, name):
        if user is None:
            return ""
        return escape(str(getattr(user, name, "") or ""))

    def _raw_value(self, user, name):
        if user is None:
            return ""
        return str(getattr(user, name, "") or "")

    def _message(self, text, level):
        return f'<p class="{level}">{escape(text)}</p>'

    def _safe_came_from(self, REQUEST):
        if REQUEST is None:
            return ""

        came_from = str(REQUEST.get("came_from", "") or "").strip()
        if not came_from:
            return ""

        folder_url = self.aq_parent.absolute_url()
        folder_path = self.aq_parent.absolute_url_path()
        if came_from == folder_url or came_from.startswith(f"{folder_url}/"):
            return came_from
        if came_from == folder_path or came_from.startswith(f"{folder_path}/"):
            return came_from
        if came_from.startswith("/") and not came_from.startswith("//"):
            return came_from
        return ""

    def _admin_came_from(self, REQUEST):
        if REQUEST is None:
            return ""

        came_from = self._safe_came_from(REQUEST)
        if not came_from:
            came_from = self._safe_local_url(
                str(REQUEST.get("HTTP_REFERER", "") or "").strip()
            )

        if not came_from or self._is_admin_url(came_from):
            return ""
        return came_from

    def _safe_local_url(self, url):
        if not url:
            return ""

        folder_url = self.aq_parent.absolute_url()
        folder_path = self.aq_parent.absolute_url_path()
        if url == folder_url or url.startswith(f"{folder_url}/"):
            return url
        if url == folder_path or url.startswith(f"{folder_path}/"):
            return url
        if url.startswith("/") and not url.startswith("//"):
            return url
        return ""

    def _is_admin_url(self, url):
        try:
            admin_url = self.absolute_url()
            admin_path = self.absolute_url_path()
        except Exception:
            admin_url = ""
            admin_path = ""
        return bool(
            (admin_url and (url == admin_url or url.startswith(f"{admin_url}/")))
            or (admin_path and (url == admin_path or url.startswith(f"{admin_path}/")))
        )

    def _with_came_from(self, path, came_from):
        if not came_from:
            return path
        return f"{path}?{urlencode({'came_from': came_from})}"

    def _back_to_app_link(self, came_from):
        if not came_from:
            return "<span></span>"
        return f'<a href="{escape(came_from)}">Back to app</a>'

    def _came_from_input(self, came_from):
        if not came_from:
            return ""
        return f'<input type="hidden" name="came_from" value="{escape(came_from)}">'

    def _truthy(self, value):
        return str(value).lower() not in ("", "0", "false", "none")


InitializeClass(SQLUserAdmin)


def manage_addSQLUserAdmin(self, id=DEFAULT_ADMIN_ID, title="", REQUEST=None):
    """Add a SQL User Admin to a folder."""

    if REQUEST is not None and REQUEST.get("REQUEST_METHOD", "GET").upper() != "POST":
        from .browser import manage_addSQLUserAdminForm

        return manage_addSQLUserAdminForm(self, REQUEST)

    admin = SQLUserAdmin(id)
    admin.title = title or "SQL User Admin"
    self._setObject(id, admin)
    if REQUEST is not None:
        REQUEST.RESPONSE.redirect(f"{self.absolute_url()}/{id}/manage_main")
    return id
