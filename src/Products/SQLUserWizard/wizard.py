from html import escape

from AccessControl import ClassSecurityInfo
from AccessControl.Permissions import manage_users
from OFS.SimpleItem import SimpleItem

from .config import (
    DEFAULT_FALLBACK_LOGIN,
    DEFAULT_TABLES,
    DEFAULT_TOTP_ISSUER,
    DEFAULT_WIZARD_ID,
    MODE_AUTH_ONLY,
    MODE_MANAGED,
)
from .compat import InitializeClass
from .installer import SQLUserWizardInstaller


class SQLUserWizard(SimpleItem):
    """ZMI helper that installs and repairs a SQL-backed PAS setup."""

    meta_type = "SQL User Wizard"
    security = ClassSecurityInfo()
    security.declareObjectProtected(manage_users)

    connection_id = "pg_odbc"
    dialect = "postgresql"
    mode = MODE_MANAGED
    users_table = DEFAULT_TABLES["users"]
    profiles_table = DEFAULT_TABLES["profiles"]
    roles_table = DEFAULT_TABLES["roles"]
    user_roles_table = DEFAULT_TABLES["user_roles"]
    fallback_login = DEFAULT_FALLBACK_LOGIN
    initial_user_id = ""
    initial_login_name = ""
    initial_roles = "Manager"
    seed_standard_roles = True
    totp_issuer = DEFAULT_TOTP_ISSUER

    def __init__(self, id=DEFAULT_WIZARD_ID):
        self.id = id

    manage_options = (
        {"label": "Wizard", "action": "manage_main"},
        {"label": "Security", "action": "manage_access"},
    )

    security.declareProtected(manage_users, "manage_main")

    def manage_main(self, REQUEST=None):
        """Render and run the SQL User Wizard management screen."""

        if REQUEST is not None:
            REQUEST.RESPONSE.setHeader("Content-Type", "text/html; charset=utf-8")

        message = ""
        if REQUEST is not None and REQUEST.get("run_wizard"):
            self.connection_id = REQUEST.get("connection_id", self.connection_id)
            self.dialect = REQUEST.get("dialect", self.dialect)
            self.mode = REQUEST.get("mode", self.mode)
            self.users_table = REQUEST.get("users_table", self.users_table)
            self.profiles_table = REQUEST.get("profiles_table", self.profiles_table)
            self.roles_table = REQUEST.get("roles_table", self.roles_table)
            self.user_roles_table = REQUEST.get(
                "user_roles_table", self.user_roles_table
            )
            self.fallback_login = REQUEST.get("fallback_login", self.fallback_login)
            fallback_password = REQUEST.get("fallback_password", "")
            self.initial_user_id = REQUEST.get("initial_user_id", self.initial_user_id)
            self.initial_login_name = REQUEST.get(
                "initial_login_name", self.initial_login_name
            )
            self.initial_roles = REQUEST.get("initial_roles", self.initial_roles)
            self.seed_standard_roles = bool(REQUEST.get("seed_standard_roles", ""))
            self.totp_issuer = REQUEST.get("totp_issuer", self.totp_issuer)
            result = self.install_or_repair(
                fallback_password=fallback_password,
                initial_password=REQUEST.get("initial_password", ""),
            )
            message = self._format_result(result)

        return self._render_form(message)

    security.declareProtected(manage_users, "manage_workspace")

    def manage_workspace(self, REQUEST=None):
        """Render the default ZMI workspace for this object."""

        return self.manage_main(REQUEST)

    security.declareProtected(manage_users, "index_html")

    def index_html(self, REQUEST=None):
        """Render the wizard when opened directly."""

        return self.manage_main(REQUEST)

    security.declareProtected(manage_users, "install_or_repair")

    def install_or_repair(self, fallback_password="", initial_password=""):
        """Install or repair the SQL-backed PAS setup in the parent folder."""

        tables = {
            "users": self.users_table,
            "profiles": self.profiles_table,
            "roles": self.roles_table,
            "user_roles": self.user_roles_table,
        }
        initial_user = {}
        if self.mode != MODE_AUTH_ONLY and self.initial_user_id.strip():
            initial_user = {
                "user_id": self.initial_user_id.strip(),
                "login_name": (
                    self.initial_login_name.strip() or self.initial_user_id.strip()
                ),
                "password": initial_password,
                "password_hash_id": "authencoding",
                "recovery_email": "",
                "first_name": "",
                "last_name": "",
                "display_name": "",
                "email": "",
                "mobile": "",
                "enabled": True,
                "roles_text": self.initial_roles,
            }
        installer = SQLUserWizardInstaller(
            folder=self.aq_parent,
            connection_id=self.connection_id,
            dialect=self.dialect,
            tables=tables,
            fallback_login=self.fallback_login,
            fallback_password=fallback_password,
            initial_user=initial_user,
            seed_roles=self.seed_standard_roles,
            mode=self.mode,
            totp_issuer=self.totp_issuer,
        )
        return installer.install()

    def _format_result(self, result):
        lines = ["<section class='result'><h2>Install / Repair Result</h2>"]
        if result.actions:
            lines.append("<h3>Actions</h3><ul class='clean-list'>")
            lines.extend(f"<li>{escape(line)}</li>" for line in result.actions)
            lines.append("</ul>")
        if result.warnings:
            lines.append("<h3>Warnings</h3><ul class='clean-list warnings'>")
            lines.extend(f"<li>{escape(line)}</li>" for line in result.warnings)
            lines.append("</ul>")
        lines.append("</section>")
        return "\n".join(lines)

    def _render_form(self, message):
        connection_id = escape(self.connection_id)
        mode = escape(self.mode)
        dialect = escape(self.dialect)
        users_table = escape(self.users_table)
        profiles_table = escape(self.profiles_table)
        roles_table = escape(self.roles_table)
        user_roles_table = escape(self.user_roles_table)
        seed_checked = "checked" if self.seed_standard_roles else ""
        fallback_login = escape(self.fallback_login)
        initial_user_id = escape(self.initial_user_id)
        initial_login_name = escape(self.initial_login_name)
        initial_roles = escape(self.initial_roles)
        totp_issuer = escape(self.totp_issuer)
        preflight = self._render_preflight()
        return f"""<!doctype html>
<html>
<head>
  <title>SQL User Wizard</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; color: #172033; background: #eef2f6; }}
    main {{ max-width: 1040px; margin: 0 auto; padding: 2rem; box-sizing: border-box; }}
    header {{ margin-bottom: 1.25rem; }}
    h1 {{ margin: 0 0 .35rem; font-size: 1.8rem; }}
    h2 {{ margin: 0 0 .75rem; font-size: 1.15rem; }}
    h3 {{ margin: 1rem 0 .4rem; font-size: 1rem; }}
    p {{ line-height: 1.5; }}
    label {{ display: block; margin: .75rem 0; font-weight: 650; }}
    input, select {{ box-sizing: border-box; display: block; width: 100%; margin-top: .3rem; padding: .55rem .65rem; border: 1px solid #b8c2cf; font: inherit; background: #fff; }}
    input:focus, select:focus {{ outline: 2px solid #6797c6; outline-offset: 1px; }}
    .checkbox-label {{ display: flex; align-items: center; gap: .5rem; }}
    .checkbox-label input {{ width: auto; margin-top: 0; }}
    button {{ padding: .75rem 1rem; border: 0; background: #20663f; color: #fff; font: inherit; font-weight: 750; cursor: pointer; }}
    button:hover {{ background: #185532; }}
    fieldset {{ border: 1px solid #d5dbe3; margin: 0; padding: 1rem; }}
    legend {{ padding: 0 .35rem; font-weight: 750; }}
    .note {{ color: #596579; }}
    .panel, .result {{ background: #fff; border: 1px solid #d5dbe3; padding: 1.25rem; margin: 1rem 0; box-shadow: 0 12px 34px rgba(20, 34, 52, .07); }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }}
    .wide {{ grid-column: 1 / -1; }}
    .help {{ margin: .35rem 0 0; color: #667085; font-size: .93rem; }}
    .clean-list {{ margin: .5rem 0 0; padding: 0; list-style: none; display: grid; gap: .35rem; }}
    .clean-list li {{ padding: .45rem .6rem; background: #eef8f0; border-left: 4px solid #17803a; }}
    .clean-list.warnings li {{ background: #fff7e8; border-left-color: #d29528; }}
    .clean-list.danger li {{ background: #fff1f0; border-left-color: #b42318; }}
    .preflight strong {{ display: inline-block; min-width: 7.5rem; }}
    .preflight code {{ background: #f6f7f9; padding: .1rem .25rem; }}
    .summary {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; margin-top: 1rem; }}
    .summary div {{ background: #fff; border: 1px solid #d5dbe3; padding: .85rem; }}
    .summary strong {{ display: block; margin-bottom: .25rem; }}
    @media (max-width: 760px) {{
      main {{ padding: 1rem; }}
      .grid, .summary {{ grid-template-columns: 1fr; }}
      .wide {{ grid-column: auto; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>SQL User Wizard</h1>
      <p class="note">Install or repair a local PAS setup backed by Z SQL
      Methods. Use auth-only as a read-only proof against an existing
      Zope-style user database, or managed mode when this product should own
      the user and role tables.</p>
    </header>
    {message}
    {preflight}
    <form method="post" class="panel">
      <input type="hidden" name="run_wizard" value="1">
      <div class="grid">
        <fieldset>
          <legend>Database</legend>
          <label>Connection id
            <input name="connection_id" value="{connection_id}">
          </label>
          <label>Install mode
            <select name="mode">
              <option value="{MODE_MANAGED}" {'selected' if self.mode == MODE_MANAGED else ''}>Managed tables</option>
              <option value="{MODE_AUTH_ONLY}" {'selected' if self.mode == MODE_AUTH_ONLY else ''}>Existing schema / auth-only</option>
            </select>
          </label>
          <label>SQL dialect
            <select name="dialect">
              <option value="postgresql" {'selected' if self.dialect == 'postgresql' else ''}>PostgreSQL managed</option>
              <option value="sqlite" {'selected' if self.dialect == 'sqlite' else ''}>SQLite managed</option>
              <option value="mysql" {'selected' if self.dialect == 'mysql' else ''}>MySQL / MariaDB managed</option>
              <option value="mssql" {'selected' if self.dialect == 'mssql' else ''}>Microsoft SQL Server managed</option>
              <option value="oracle11g" {'selected' if self.dialect in ('oracle', 'oracle11g') else ''}>Oracle 11g managed</option>
              <option value="oracle12c" {'selected' if self.dialect == 'oracle12c' else ''}>Oracle 12c+ managed</option>
              <option value="existing_postgresql" {'selected' if self.dialect == 'existing_postgresql' else ''}>Existing PostgreSQL auth-only</option>
              <option value="existing_oracle" {'selected' if self.dialect == 'existing_oracle' else ''}>Existing Oracle auth-only</option>
            </select>
          </label>
          <p class="help">Managed mode creates product-owned tables. Auth-only
          mode only reads an existing Zope-style user schema and is the safe
          first step before taking control.</p>
        </fieldset>
        <fieldset>
          <legend>Fallback Access</legend>
          <label>Extra fallback manager login
            <input name="fallback_login" value="{fallback_login}">
          </label>
          <label>Extra fallback manager password
            <input name="fallback_password" type="password" value="">
          </label>
          <p class="help">Parent-folder users are synced automatically. These
          fields only create one additional local recovery user.</p>
        </fieldset>
        <fieldset class="wide">
          <legend>SQL Tables</legend>
          <div class="grid">
            <label>Users table
              <input name="users_table" value="{users_table}">
            </label>
            <label>Profiles table
              <input name="profiles_table" value="{profiles_table}">
            </label>
            <label>Roles catalog table
              <input name="roles_table" value="{roles_table}">
            </label>
            <label class="checkbox-label">
              <input name="seed_standard_roles" type="checkbox" value="1" {seed_checked}>
              Seed standard Zope roles
            </label>
            <label>User roles table
              <input name="user_roles_table" value="{user_roles_table}">
            </label>
          </div>
          <p class="help">For existing-schema auth-only, use <code>users</code> and
          <code>roles</code>. Profile/user-role tables are ignored. Standard
          role seeding creates missing <code>Manager</code>, <code>Owner</code>,
          <code>Authenticated</code>, and <code>Anonymous</code> role catalog
          rows without assigning them to users.</p>
        </fieldset>
        <fieldset class="wide">
          <legend>Authenticator</legend>
          <label>Issuer / app name
            <input name="totp_issuer" value="{totp_issuer}">
          </label>
          <p class="help">This is the app name shown by Authenticator apps.
          Use one shared issuer for all lab folders, for example
          <code>SQL_User_Wizard</code>. Production installations should choose
          their own application name.</p>
        </fieldset>
        <fieldset class="wide">
          <legend>First SQL User</legend>
          <div class="grid">
            <label>User id
              <input name="initial_user_id" value="{initial_user_id}">
            </label>
            <label>Login name
              <input name="initial_login_name" value="{initial_login_name}">
            </label>
            <label>Password
              <input name="initial_password" type="password" value="">
            </label>
            <label>Roles
              <input name="initial_roles" value="{initial_roles}">
            </label>
          </div>
          <p class="help">Ignored in auth-only mode. Existing database users
          are authenticated read-only. For unrelated legacy schemas, import
          users into the managed model with custom scripts.</p>
        </fieldset>
      </div>
      <button type="submit">Install / Repair SQL PAS</button>
    </form>
    <section class="summary">
      <div><strong>Local PAS</strong><code>acl_users</code> with SQL auth and cookie login.</div>
      <div><strong>User Tools</strong>Managed mode installs admin/profile tools; auth-only installs read-only login and diagnostics.</div>
      <div><strong>Mode</strong>{mode} / {dialect}</div>
    </section>
  </main>
</body>
</html>"""

    def _render_preflight(self):
        groups = self._preflight_groups()
        sections = []
        for css_class, title, items in groups:
            if not items:
                continue
            sections.append(
                f"<h3>{escape(title)}</h3><ul class='clean-list {css_class}'>"
            )
            sections.extend(f"<li>{item}</li>" for item in items)
            sections.append("</ul>")
        return f"""
    <section class="panel preflight">
      <h2>Preflight</h2>
      <p class="note">Read this before running install/repair. Existing
      databases may mix authentication fields, profile fields, and application
      data in the same tables.</p>
      {''.join(sections)}
    </section>
"""

    def _preflight_groups(self):
        table_values = {
            "Users": self.users_table,
            "Profiles": self.profiles_table,
            "Roles catalog": self.roles_table,
            "User roles": self.user_roles_table,
        }
        errors = []
        warnings = []
        checks = []

        normalized = {}
        for label, value in table_values.items():
            key = (value or "").strip().lower()
            if not key:
                errors.append(
                    f"<strong>{escape(label)}</strong> Table name is empty."
                )
                continue
            if key in normalized:
                errors.append(
                    f"<strong>{escape(label)}</strong> Reuses "
                    f"<code>{escape(value)}</code> from "
                    f"{escape(normalized[key])}. Use distinct tables."
                )
            normalized[key] = label

        if self.mode == MODE_AUTH_ONLY:
            checks.append(
                "<strong>Auth-only</strong> Installs read-only Z SQL Methods "
                "for authentication, role lookup, and profile display."
            )
            checks.append(
                "<strong>No writes</strong> Auth-only mode must not create, "
                "alter, update, delete, or insert database rows."
            )
            if not self.dialect.startswith("existing_"):
                warnings.append(
                    "<strong>Dialect</strong> Auth-only is meant for "
                    "<code>existing_postgresql</code> or "
                    "<code>existing_oracle</code>. Managed dialects are for "
                    "product-owned tables."
                )
        else:
            checks.append(
                "<strong>Managed</strong> Install/repair may create or alter "
                "security tables and may update users, roles, profiles, and "
                "2FA fields."
            )
            if self.dialect.startswith("existing_"):
                warnings.append(
                    "<strong>Mode mismatch</strong> Existing-schema dialects "
                    "are read-only proofs. Use a managed dialect only when the "
                    "product should own or repair the target tables."
                )

        application_named = [
            value
            for value in table_values.values()
            if value and not value.strip().lower().startswith("pas_")
        ]
        if self.mode != MODE_AUTH_ONLY and application_named:
            warnings.append(
                "<strong>Existing names</strong> These table names do not look "
                f"product-owned: <code>{escape(', '.join(application_named))}</code>. "
                "Before repair, separate identity/security fields from editable "
                "profile fields and application-only data."
            )

        if self.mode != MODE_AUTH_ONLY:
            checks.append(
                "<strong>Profile split</strong> Keep passwords, enabled status, "
                "2FA, and recovery data in the users table. Put first name, "
                "last name, display name, email, and mobile in the profiles "
                "table unless the application deliberately syncs selected "
                "fields elsewhere."
            )
            checks.append(
                "<strong>App data</strong> Internal notes, employment status, "
                "business roles, addresses, dates, avatar blobs, and other "
                "domain fields belong to application tables. Do not expose them "
                "through self-service profile forms without an explicit sync rule."
            )

        return (
            ("danger", "Stop First", errors),
            ("warnings", "Review", warnings),
            ("", "Expected Behavior", checks),
        )


InitializeClass(SQLUserWizard)


def manage_addSQLUserWizard(self, id=DEFAULT_WIZARD_ID, title="", REQUEST=None):
    """Add a SQL User Wizard to a folder."""

    if REQUEST is not None and REQUEST.get("REQUEST_METHOD", "GET").upper() != "POST":
        from .browser import manage_addSQLUserWizardForm

        return manage_addSQLUserWizardForm(self, REQUEST)

    wizard = SQLUserWizard(id)
    wizard.title = title or "SQL User Wizard"
    self._setObject(id, wizard)
    if REQUEST is not None:
        REQUEST.RESPONSE.redirect(f"{self.absolute_url()}/{id}/manage_main")
    return id
