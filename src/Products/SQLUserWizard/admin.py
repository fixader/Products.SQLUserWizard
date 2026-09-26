from html import escape
from types import SimpleNamespace
from urllib.parse import urlencode, urlsplit

from AccessControl import ClassSecurityInfo
from AccessControl import getSecurityManager
from AccessControl.Permissions import manage_users, view
from OFS.SimpleItem import SimpleItem
from zExceptions import Unauthorized

from .compat import InitializeClass
from .security import require_post, protect_forms, safe_redirect
from .sessions import fingerprint
from .config import (
    DEFAULT_ADMIN_ID,
    DEFAULT_TOTP_ISSUER,
    DEFAULT_PASSWORD_HASH_ID,
    DEFAULT_PAS_ID,
    DEFAULT_PLUGIN_ID,
    DEFAULT_PROFILE_FORM_ID,
    DEFAULT_PROFILE_GET_ID,
    DEFAULT_PROFILE_SAVE_ID,
    DEFAULT_PROFILE_DATA_GET_ID,
    DEFAULT_PROFILE_DATA_SAVE_ID,
    DEFAULT_LOGOUT_ID,
    DEFAULT_COOKIE_AUTH_ID,
    DEFAULT_LOGIN_SUBMIT_ID,
)
from .profile_fields import FIELD_TYPES
from .profile_fields import collect_values
from .profile_fields import dump_values
from .profile_fields import load_values
from .profile_fields import normalize_definition
from .profile_fields import ordered
from .profile_fields import render_fields
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
    profile_fields = ()

    def __init__(self, id=DEFAULT_ADMIN_ID):
        self.id = id

    manage_options = (
        {"label": "Users", "action": "manage_main"},
        {"label": "Profile fields", "action": "manage_profile_fields"},
        {"label": "Invitations", "action": "manage_invitations"},
        {"label": "Security", "action": "manage_access"},
    )

    security.declareProtected(manage_users, "manage_profile_fields")

    def manage_profile_fields(self, REQUEST=None):
        """Configure validated application-specific profile fields."""
        if REQUEST is not None:
            REQUEST.RESPONSE.setHeader("Content-Type", "text/html; charset=utf-8")
        message = ""
        if REQUEST is not None and (REQUEST.form.get("save_field") or REQUEST.form.get("delete_field")):
            require_post(self, REQUEST)
            try:
                field_id = str(REQUEST.form.get("field_id", "")).strip().lower()
                definitions = [dict(item) for item in self.profile_fields if item.get("id") != field_id]
                if REQUEST.form.get("save_field"):
                    definitions.append(normalize_definition(
                        field_id=field_id,
                        label=REQUEST.form.get("label", ""),
                        field_type=REQUEST.form.get("field_type", "text"),
                        required=bool(REQUEST.form.get("required")),
                        active=bool(REQUEST.form.get("active")),
                        sort_order=REQUEST.form.get("sort_order", 100),
                        options=REQUEST.form.get("options", ""),
                        default=REQUEST.form.get("default", ""),
                    ))
                    message = self._message("Profile field saved", "ok")
                else:
                    message = self._message("Profile field removed from the profile forms. Existing user profiles were not rewritten.", "ok")
                self.profile_fields = tuple(ordered(definitions))
            except Exception as exc:
                message = self._message(str(exc), "error")
        selected_id = "" if REQUEST is None else str(REQUEST.get("field_id", ""))
        selected = next((item for item in self.profile_fields if item.get("id") == selected_id), {})
        return protect_forms(self, REQUEST, self._render_profile_field_editor(message, selected))

    def _render_profile_field_editor(self, message, selected):
        rows = []
        for item in ordered(self.profile_fields):
            field_id = escape(item["id"])
            rows.append(
                "<tr>"
                f"<td><a href='?field_id={field_id}#profile-field-editor'>{field_id}</a></td>"
                f"<td>{escape(item['label'])}</td><td>{escape(item['type'])}</td>"
                f"<td>{'Required' if item.get('required') else 'Optional'}</td>"
                f"<td>{'Active' if item.get('active', True) else 'Inactive'}</td>"
                f"<td>{int(item.get('sort_order', 100))}</td></tr>"
            )
        options_text = "\n".join("|".join(pair) for pair in selected.get("options", ()))
        type_options = "".join(
            f'<option value="{kind}"{" selected" if selected.get("type", "text") == kind else ""}>{kind}</option>'
            for kind in FIELD_TYPES
        )
        table = ("<p>No custom profile fields yet.</p>" if not rows else
                 "<p class='muted'>Select a field ID to edit or remove that definition.</p>"
                 "<div class='table-scroll'><table><thead><tr><th>Field id</th><th>Label</th><th>Type</th><th>Requirement</th><th>Status</th><th>Order</th></tr></thead><tbody>"
                 + "".join(rows) + "</tbody></table></div>")
        checked_required = " checked" if selected.get("required") else ""
        checked_active = " checked" if selected.get("active", True) else ""
        return f"""<!doctype html><html><head><title>Profile field editor</title>
<link rel="stylesheet" href="../sql_wizard.css"></head><body class="sqluw-page">
<main class="sqluw-editor-shell"><h1>Profile field editor</h1>
<p class="muted">Add application-specific descriptive fields. Roles remain the authorization mechanism.</p>
{message}<section class="panel"><h2>Configured fields</h2>{table}</section>
<section class="panel" id="profile-field-editor"><h2>{'Edit field' if selected else 'Add field'}</h2>
{'<p class="muted">The field ID is permanent. Change the label or other settings below, then select Save field. Remove definition takes effect immediately.</p>' if selected else '<p class="muted">Create a stable field ID. You can edit its label and settings after saving.</p>'}
<form method="post">
<label class="form-field"><span>Field id</span><input name="field_id" value="{escape(selected.get('id', ''))}"{' readonly' if selected else ''} required></label>
<label class="form-field"><span>Label</span><input name="label" value="{escape(selected.get('label', ''))}" required></label>
<label class="form-field"><span>Type</span><select name="field_type">{type_options}</select></label>
<label class="form-field"><span>Default value</span><input name="default" value="{escape(selected.get('default', ''))}"></label>
<label class="form-field"><span>Sort order</span><input name="sort_order" type="number" value="{int(selected.get('sort_order', 100))}"></label>
<label class="form-field"><span>Select options</span><textarea name="options" rows="6" placeholder="value|Visible label">{escape(options_text)}</textarea></label>
<label class="check-row"><input name="required" type="checkbox" value="1"{checked_required}><span>Required</span></label>
<label class="check-row"><input name="active" type="checkbox" value="1"{checked_active}><span>Active</span></label>
<div class="form-actions"><button name="save_field" value="1">Save field</button>
{'<button class="danger" name="delete_field" value="1">Remove definition</button>' if selected else ''}
<a class="button" href="manage_profile_fields">New field</a></div></form></section>
<section class="panel"><h2>Address example</h2><p>Add fields such as <code>address_line_1</code>, <code>address_line_2</code>, <code>postal_code</code>, <code>city</code>, <code>region</code> and a country select. A <code>user_type</code> select is descriptive; use roles for access.</p></section>
</main></body></html>"""

    security.declareProtected(manage_users, "manage_invitations")

    def manage_invitations(self, REQUEST=None):
        """Explicitly enable invitation storage and its script-facing controller."""
        if REQUEST is not None:
            REQUEST.RESPONSE.setHeader("Content-Type", "text/html; charset=utf-8")
        from .invitation_install import enable_invitation_storage
        from .sqladmin import normalize_roles
        from .invitation_sql import DEFAULT_INVITATION_TABLES
        from .provisioning import CONTROLLER_ID
        if not getSecurityManager().checkPermission(manage_users, self):
            raise Unauthorized("Manage users permission is required")
        folder = self.aq_parent
        message = ""
        if REQUEST is not None and REQUEST.form.get("enable_invitations"):
            require_post(self, REQUEST)
            # Errors propagate so the publisher aborts the ZODB transaction.
            enable_invitation_storage(folder, tables={
                "invitations": REQUEST.form.get("invitations_table", ""),
                "roles": REQUEST.form.get("invitation_roles_table", ""),
            }, allowed_roles=normalize_roles(REQUEST.form.get("allowed_roles", "")),
                privileged_roles=normalize_roles(REQUEST.form.get("privileged_roles", "")),
                totp_required=REQUEST.form.get("totp_required") == "1")
            message = "Invitation storage and API are enabled."
        controller = folder._getOb(CONTROLLER_ID, None)
        invitations = folder._getOb("invitations", None)
        if (controller is not None and invitations is not None and REQUEST is not None
                and REQUEST.form.get("save_invitation_mail")):
            require_post(self, REQUEST)
            enabled = REQUEST.form.get("mail_enabled") == "1"
            sender = REQUEST.form.get("mail_from", "").strip()
            subject = REQUEST.form.get("mail_subject", "").strip()
            invitation_url = REQUEST.form.get("invitation_url", "").strip().rstrip("/")
            if enabled:
                if (not sender or "@" not in sender or "\r" in sender or "\n" in sender):
                    raise ValueError("A valid invitation sender address is required")
                if not subject or "\r" in subject or "\n" in subject:
                    raise ValueError("A valid invitation subject is required")
                parsed = urlsplit(invitation_url)
                if parsed.scheme not in ("http", "https") or not parsed.netloc:
                    raise ValueError("An absolute HTTP(S) invitation form URL is required")
            properties = {
                "sqluw_mail_enabled": enabled,
                "sqluw_mail_from": sender,
                "sqluw_mail_subject": subject,
                "sqluw_invitation_url": invitation_url,
            }
            for name, value in properties.items():
                if invitations.hasProperty(name):
                    invitations._updateProperty(name, value)
                else:
                    invitations._setProperty(name, value, "boolean" if isinstance(value, bool) else "string")
            message = "Invitation email settings were saved."
        if (controller is not None and REQUEST is not None
                and REQUEST.form.get("save_invitation_policy")):
            require_post(self, REQUEST)
            controller.totp_required = REQUEST.form.get("totp_required") == "1"
            message = "Invitation enrollment policy was saved."
        if (controller is not None and REQUEST is not None
                and REQUEST.form.get("repair_invitation_examples")):
            require_post(self, REQUEST)
            from .invitation_examples import install_invitation_examples
            install_invitation_examples(folder, controller.allowed_roles)
            message = "Invitation forms and scripts were repaired. Customized managed objects were preserved."
        if controller is not None:
            mailhosts = invitations.objectValues("Mail Host") if invitations is not None else ()
            mail_enabled = bool(invitations and invitations.getProperty("sqluw_mail_enabled", False))
            mail_status = ("Automatic invitation email is active."
                           if mailhosts and mail_enabled else
                           "A local MailHost exists, but automatic invitation email is disabled."
                           if mailhosts else
                           "No local MailHost is configured; invitations use manual delivery.")
            checked = " checked" if mail_enabled else ""
            mail_from = escape(invitations.getProperty("sqluw_mail_from", "") if invitations else "")
            mail_subject = escape(invitations.getProperty(
                "sqluw_mail_subject", "Your account invitation") if invitations else "")
            invitation_url = escape(invitations.getProperty(
                "sqluw_invitation_url", "") if invitations else "")
            totp_checked = " checked" if controller.totp_required else ""
            html = ("<h1>Invitations</h1><p>" + escape(message or "Invitation storage and API are enabled.")
                    + "</p><p>" + escape(mail_status) + "</p>"
                    '<form method="post"><h2>Enrollment policy</h2>'
                    '<label><input name="totp_required" type="checkbox" value="1"' + totp_checked
                    + "> Require invited users to enroll in two-factor authentication</label><br>"
                    '<button name="save_invitation_policy" value="1">Save enrollment policy</button></form>'
                    '<form method="post"><h2>Email delivery</h2>'
                    '<label><input name="mail_enabled" type="checkbox" value="1"' + checked
                    + "> Send new invitations automatically</label><br>"
                    '<label>Sender address <input name="mail_from" type="email" value="' + mail_from
                    + '"></label><br><label>Subject <input name="mail_subject" value="' + mail_subject
                    + '"></label><br><label>Public invitation form URL <input name="invitation_url" type="url" value="'
                    + invitation_url + '"></label><br><button name="save_invitation_mail" value="1">Save email settings</button></form>'
                    '<form method="post"><button name="repair_invitation_examples" value="1">'
                    "Repair invitation forms and scripts</button></form>")
            return protect_forms(self, REQUEST, html)
        html = '''<h1>Enable invitations</h1>
<p>This optional action creates two invitation tables and a protected API controller.
Ordinary installation and startup do not create invitation storage.</p>
<form method="post">
<label>Invitation table <input name="invitations_table" value="%s"></label><br>
<label>Invitation roles table <input name="invitation_roles_table" value="%s"></label><br>
<label>Allowed ordinary roles <input name="allowed_roles" value="Member"></label><br>
<label>Additional privileged roles to reject <input name="privileged_roles" value=""></label><br>
<label><input type="checkbox" name="totp_required" value="1">Require TOTP enrollment</label><br>
<p>Include application-specific privileged roles in the rejection list.
SMTP and ready-made invitation pages are optional application concerns.</p>
<button name="enable_invitations" value="1">Enable invitations</button>
</form>''' % (DEFAULT_INVITATION_TABLES["invitations"], DEFAULT_INVITATION_TABLES["roles"])
        return protect_forms(self, REQUEST, html)

    security.declareProtected(manage_users, "manage_main")

    def manage_main(self, REQUEST=None):
        """Render and process the SQL user admin screen."""

        if REQUEST is not None:
            REQUEST.RESPONSE.setHeader("Content-Type", "text/html; charset=utf-8")

        message = ""
        if REQUEST is not None and any(REQUEST.get(key) for key in ("delete_user", "save_user", "save_role")):
            require_post(self, REQUEST)
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

        return protect_forms(self, REQUEST, self._render(message, selected_user_id, REQUEST))

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
            require_post(self, REQUEST)
            try:
                self._save_profile_from_request(user_id, REQUEST)
            except Exception as exc:
                message = self._message(str(exc), "error")
            else:
                message = self._message("Profile saved", "ok")

        user = self._get_user_with_profile(user_id)
        return protect_forms(self, REQUEST, self._render_profile_page(user, message, REQUEST))

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
        if REQUEST is not None and any(REQUEST.get(key) for key in ("reset_totp", "confirm_totp", "disable_totp")):
            require_post(self, REQUEST)
            if self._truthy(getattr(user, "totp_enabled", False)):
                if not verify_totp_code(user.totp_secret, REQUEST.form.get("otp_code", "")):
                    raise Unauthorized("A current authenticator code is required")
            if REQUEST.get("disable_totp") and self._truthy(getattr(user, "totp_required", False)):
                raise Unauthorized("Two-factor authentication is required for this account")
        if REQUEST is not None and REQUEST.get("reset_totp"):
            secret = generate_totp_secret()
            self._update_user_totp(user_id, enabled=False, secret=secret)
            message = self._message("New authenticator setup code created", "ok")
            user = self._get_user_with_profile(user_id)
            self._refresh_session(REQUEST, user, scope="enroll")
            target = f"{self.aq_parent.absolute_url()}/{DEFAULT_LOGIN_SUBMIT_ID}/enroll"
            REQUEST.RESPONSE.redirect(self._with_came_from(target, came_from))
            return ""
        elif REQUEST is not None and REQUEST.get("confirm_totp"):
            secret = normalize_totp_secret(getattr(user, "totp_secret", ""))
            code = REQUEST.get("otp_code", "")
            if secret and verify_totp_code(secret, code):
                self._update_user_totp(user_id, enabled=True, secret=secret)
                self._refresh_session(REQUEST, self._get_user_with_profile(user_id))
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
            self._refresh_session(REQUEST, user)

        return protect_forms(self, REQUEST, self._render_2fa_page(user, message, REQUEST))

    security.declareProtected(view, "my_profile_data")

    def my_profile_data(self):
        """Return only the current user's display profile to templates."""
        user_id = getSecurityManager().getUser().getId()
        if not user_id or user_id == "Anonymous User":
            raise Unauthorized("Login is required")
        return getattr(self.aq_parent, DEFAULT_PROFILE_GET_ID)(user_id=user_id)

    def _plugin(self):
        pas = getattr(self.aq_parent, self.pas_id)
        return getattr(pas, self.plugin_id)

    def _refresh_session(self, request, user, scope="full"):
        # Use the auth row (not the joined display profile) for a stable stamp.
        login = user.login_name
        row = next(u for u in self._plugin().zsql_pas_fetch_user(login=login) if u.user_id == user.user_id)
        helper = getattr(getattr(self.aq_parent, self.pas_id), DEFAULT_COOKIE_AUTH_ID)
        helper._issue(request, row.user_id, login, fingerprint(row), scope=scope)

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
        else:
            save_sql_profile(self._plugin(), **values)
        existing = self._profile_extra_values(user_id)
        extra = collect_values(self.profile_fields, REQUEST, existing)
        data_save = getattr(self.aq_parent, DEFAULT_PROFILE_DATA_SAVE_ID, None)
        if data_save is not None:
            data_save(user_id=user_id, profile_data=dump_values(extra))

    def _delete_from_request(self, REQUEST):
        user_id = REQUEST.get("edit_user_id") or REQUEST.get("user_id", "")
        delete_sql_user(self._plugin(), user_id)

    def _update_user_totp(self, user_id, enabled, secret):
        self._plugin().zsql_pas_update_2fa(
            user_id=user_id,
            totp_required="1" if self._truthy(getattr(self._get_user_with_profile(user_id), "totp_required", False)) else "",
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
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, sans-serif; max-width: 1540px; margin: 0 auto; padding: 2rem clamp(1rem, 3vw, 2.5rem); color: #172033; background: #f6f8fb; line-height: 1.45; }}
    a {{ color: #1d5f9f; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    h1, h2, h3 {{ line-height: 1.2; }}
    h2 {{ margin: 0 0 1rem; font-size: 1.2rem; }}
    h3 {{ margin: 0 0 .85rem; font-size: 1rem; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: .5rem; }}
    .table-scroll {{ max-width: 100%; overflow: auto; border: 1px solid #e1e5eb; border-radius: .35rem; }}
    .table-scroll table {{ margin-top: 0; }}
    .users-scroll {{ max-height: 24rem; }}
    .users-scroll thead {{ position: sticky; top: 0; z-index: 1; }}
    th, td {{ border-bottom: 1px solid #d6dbe3; padding: .55rem .6rem; text-align: left; vertical-align: top; }}
    th {{ background: #f1f4f8; font-size: .84rem; }}
    label {{ font-weight: 600; }}
    input {{ width: 100%; min-width: 0; padding: .5rem .6rem; border: 1px solid #aeb8c6; border-radius: .3rem; background: #fff; color: #172033; }}
    input:focus {{ border-color: #3979b7; outline: 2px solid #cfe3f6; outline-offset: 1px; }}
    button, .button {{ padding: .55rem .9rem; border: 1px solid #8f9baa; border-radius: .35rem; background: #fff; color: #172033; cursor: pointer; font-weight: 600; }}
    button:hover, .button:hover {{ background: #f1f4f8; text-decoration: none; }}
    fieldset {{ min-width: 0; border: 1px solid #c8ced8; border-radius: .45rem; margin: 0; padding: 1rem; background: #fff; }}
    legend {{ padding: 0 .35rem; font-weight: 700; }}
    .top-layout {{ display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(22rem, .85fr); gap: 1.25rem; align-items: start; margin-bottom: 1.25rem; }}
    .panel {{ min-width: 0; border: 1px solid #c8ced8; border-radius: .5rem; padding: 1.1rem; background: #fff; box-shadow: 0 1px 2px rgba(23, 32, 51, .06); }}
    .ok {{ border-left: 4px solid #17803a; padding: .7rem; background: #eef8f0; }}
    .error {{ border-left: 4px solid #b42318; padding: .7rem; background: #fff1f0; }}
    .muted {{ color: #667085; font-weight: 400; }}
    .status {{ display: inline-block; min-width: 4.8rem; padding: .15rem .45rem; border-radius: .25rem; text-align: center; font-size: .82rem; font-weight: 600; }}
    .status-active {{ color: #075e2b; background: #dff6e7; }}
    .status-inactive {{ color: #7a271a; background: #fde6df; }}
    .danger {{ color: #8a1f11; border-color: #d6a29a; }}
    .form-actions {{ display: flex; flex-wrap: wrap; gap: .7rem; align-items: center; padding-top: 1rem; }}
    .form-actions button:first-child {{ color: #fff; border-color: #1d5f9f; background: #1d5f9f; }}
    .user-editor-grid {{ display: grid; grid-template-columns: minmax(30rem, 1.35fr) minmax(22rem, .8fr); gap: 1.25rem; align-items: start; }}
    .editor-column {{ display: grid; gap: 1.25rem; align-content: start; min-width: 0; }}
    .form-field {{ display: grid; grid-template-columns: 10.5rem minmax(0, 1fr); gap: .75rem; align-items: center; margin: .65rem 0; }}
    .check-row {{ display: flex; gap: .55rem; align-items: flex-start; margin: .65rem 0; font-weight: 500; }}
    .check-row input, .role-choice input {{ width: auto; margin-top: .18rem; flex: 0 0 auto; }}
    .role-grid {{ display: grid; grid-template-columns: 1fr; gap: .5rem; }}
    .role-choice {{ font-weight: 500; }}
    .role-card {{ display: flex; gap: .65rem; align-items: flex-start; margin: 0; padding: .65rem .7rem; border: 1px solid #d6dbe3; border-radius: .35rem; background: #f9fafc; }}
    .role-copy {{ display: grid; gap: .08rem; min-width: 0; }}
    .role-copy small {{ color: #667085; font-weight: 400; }}
    .role-editor {{ margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #d6dbe3; }}
    .role-editor .form-field {{ grid-template-columns: 5.5rem minmax(0, 1fr); }}
    .totp-setup {{ display: grid; grid-template-columns: auto minmax(0, 1fr); gap: .8rem; align-items: start; margin-top: .8rem; }}
    .totp-qr {{ width: 11rem; height: 11rem; border: 1px solid #c8ced8; background: #fff; padding: .4rem; }}
    code.wrap {{ display: block; white-space: normal; overflow-wrap: anywhere; }}
    .toolbar {{ display: flex; flex-direction: column; gap: .35rem; align-items: flex-start; margin-bottom: 1rem; }}
    .toolbar h1 {{ margin: 0; }}
    .profile-editor-link {{ margin: .15rem 0 .55rem; text-align: right; }}
    @media (max-width: 1000px) {{ .top-layout, .user-editor-grid, .totp-setup {{ grid-template-columns: 1fr; }} }}
    @media (max-width: 620px) {{ body {{ padding: 1rem; }} .form-field, .role-editor .form-field {{ grid-template-columns: 1fr; gap: .25rem; }} th, td {{ padding: .4rem; }} }}
  </style>
  <link rel="stylesheet" href="../sql_wizard.css">
</head>
<body class="sqluw-page">
  <div class="toolbar">
    {return_link}
    <h1>SQL User Admin</h1>
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
            "<div class='table-scroll users-scroll'><table><thead><tr>"
            "<th>User id</th><th>Login</th><th>Name</th><th>Email</th><th>Roles</th><th>Status</th><th>2FA</th>"
            "</tr></thead><tbody>"
            + "\n".join(rows)
            + "</tbody></table></div>"
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
        return f"""<form method="post" class="role-editor">
  <h3>Create or update role</h3>
  <input type="hidden" name="save_role" value="1">
  {self._came_from_input(came_from)}
  <label class="form-field">Role id
    <input name="role_id" value="">
  </label>
  <label class="form-field">Title
    <input name="role_title" value="">
  </label>
  <label class="check-row">
    <input name="role_enabled" type="checkbox" value="1" checked>
    <span>Active</span>
  </label>
  <div class="form-actions"><button type="submit">Save role</button></div>
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
  <div class="user-editor-grid">
    <div class="editor-column">
      <fieldset>
        <legend>Security</legend>
        <label class="form-field">User id
          <input name="edit_user_id" value="{value(user, 'user_id')}" {'readonly' if user else ''}>
        </label>
        <label class="form-field">Login name
          <input name="login_name" value="{value(user, 'login_name')}">
        </label>
        <label class="form-field">Password
          <input name="password" type="password" value="">
        </label>
        <label class="form-field">Password hash id
          <input name="password_hash_id" value="{value(user, 'password_hash_id') or DEFAULT_PASSWORD_HASH_ID}">
        </label>
        <label class="form-field">Recovery email
          <input name="recovery_email" value="{value(user, 'recovery_email')}">
        </label>
        <label class="check-row">
          <input name="enabled" type="checkbox" value="1" {'checked' if enabled else ''}>
          <span>Enabled</span>
        </label>
      </fieldset>
      {self._render_profile_fields(user, REQUEST)}
    </div>
    <div class="editor-column">
      <fieldset>
        <legend>Roles</legend>
        {self._render_role_choices(roles, selected_roles)}
      </fieldset>
      {self._render_totp_settings(user)}
    </div>
  </div>
  <div class="form-actions">
    <button type="submit">Save user</button>
    {delete_button}
    <a class="button" href="{escape(new_user_href)}">New user</a>
  </div>
</form>"""

    def _render_profile_fields(self, user, REQUEST=None):
        editor_link = '<p class="profile-editor-link"><a href="manage_profile_fields">Edit profile fields</a></p>'
        custom_controls = render_fields(
            self.profile_fields,
            self._profile_extra_values(self._raw_value(user, "user_id")),
        )
        template = getattr(self.aq_parent, DEFAULT_PROFILE_FORM_ID, None)
        if template is not None:
            data = self._profile_template_data(user)
            try:
                rendered = template(client=self, REQUEST=REQUEST or {}, **data)
            except TypeError:
                rendered = template(self, REQUEST or {}, **data)
            return editor_link + self._merge_profile_controls(rendered, custom_controls)

        return editor_link + self._render_builtin_profile_fields(user, custom_controls)

    @staticmethod
    def _merge_profile_controls(rendered, custom_controls):
        """Place configured controls inside the existing Profile fieldset."""
        if not custom_controls:
            return rendered
        marker = "</fieldset>"
        position = rendered.rfind(marker)
        if position < 0:
            return f"<fieldset><legend>Profile</legend>{rendered}{custom_controls}</fieldset>"
        return rendered[:position] + custom_controls + rendered[position:]

    def _profile_extra_values(self, user_id):
        if not user_id:
            return {}
        method = getattr(self.aq_parent, DEFAULT_PROFILE_DATA_GET_ID, None)
        if method is None:
            return {}
        row = first_row(method(user_id=user_id))
        return load_values(getattr(row, "profile_data", "") if row is not None else "")

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
        <label class="check-row">
          <input name="totp_required" type="checkbox" value="1" {'checked' if required else ''}>
          Require 2FA enrollment before app access
        </label>
        <label class="check-row">
          <input name="totp_enabled" type="checkbox" value="1" {'checked' if enabled else ''}>
          Require authenticator code at login
        </label>
        <label class="form-field">TOTP secret
          <input name="totp_secret" value="{escape(secret)}">
        </label>
        <label class="check-row">
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

    def _render_builtin_profile_fields(self, user, custom_controls=""):
        value = self._value
        return f"""
  <fieldset>
    <legend>Profile</legend>
    <label class="form-field">First name
      <input name="first_name" value="{value(user, 'first_name')}">
    </label>
    <label class="form-field">Last name
      <input name="last_name" value="{value(user, 'last_name')}">
    </label>
    <label class="form-field">Display name
      <input name="display_name" value="{value(user, 'display_name')}">
    </label>
    <label class="form-field">Email
      <input name="email" value="{value(user, 'email')}">
    </label>
    <label class="form-field">Mobile
      <input name="mobile" value="{value(user, 'mobile')}">
    </label>
    {custom_controls}
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
  <link rel="stylesheet" href="../sql_wizard.css">
</head>
<body class="sqluw-page">
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
        uri = otpauth_uri(secret, login_name, issuer) if secret and not enabled else ""
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
        if enabled:
            setup_block = "<p>Authenticator is active. Enter a current code to change its setup.</p>"
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
  <link rel="stylesheet" href="../sql_wizard.css">
</head>
<body class="sqluw-page">
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
                "<label class='role-choice role-card'>"
                f"<input name='roles:list' type='checkbox' value='{escape(role_id)}' {'checked' if role_id in selected else ''}>"
                "<span class='role-copy'>"
                f"<strong>{escape(role_id)}</strong>"
                f"<small>{escape(title) if title != role_id else 'Application role'}</small>"
                "</span></label>"
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

        return safe_redirect(REQUEST.get("came_from", ""), self.aq_parent.absolute_url())

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
        return safe_redirect(url, self.aq_parent.absolute_url())

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

    if REQUEST is not None:
        require_post(self, REQUEST)
    admin = SQLUserAdmin(id)
    admin.title = title or "SQL User Admin"
    self._setObject(id, admin)
    if REQUEST is not None:
        REQUEST.RESPONSE.redirect(f"{self.absolute_url()}/{id}/manage_main")
    return id
