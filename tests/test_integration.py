"""In-process Zope/PAS integration with a disposable SQLite database."""

import re
import sqlite3
import transaction
from types import SimpleNamespace

import pytest
from AccessControl import getSecurityManager
from AccessControl.SecurityManagement import newSecurityManager, noSecurityManager
from AccessControl.users import UnrestrictedUser
from OFS.SimpleItem import SimpleItem
from Testing import ZopeTestCase
from ZPublisher.HTTPRequest import HTTPRequest
from ZPublisher.HTTPResponse import HTTPResponse
from io import BytesIO

from Products.SQLUserWizard.installer import SQLUserWizardInstaller
from Products.SQLUserWizard.security import csrf_field
from Products.SQLUserWizard.totp import totp_code


class SQLiteConnection(SimpleItem):
    id = "test_db"
    title = "Disposable test database"
    meta_type = "Test Database Connection"

    def __init__(self):
        self._v_db = sqlite3.connect(":memory:")

    def __call__(self):
        return self

    def sql_quote__(self, value):
        return "'" + str(value).replace("'", "''") + "'"

    def query(self, sql, max_rows=1000):
        cursor = self._v_db.execute(sql)
        columns = [dict(name=c[0], type="s", width=0, null=True) for c in cursor.description or ()]
        return columns, cursor.fetchmany(max_rows) if columns else []


@pytest.fixture
def app_folder():
    ZopeTestCase.installProduct("PluggableAuthService")
    ZopeTestCase.installProduct("ZSQLMethods")
    ZopeTestCase.installProduct("PythonScripts")
    app = ZopeTestCase.app()
    newSecurityManager(None, UnrestrictedUser("test-manager", "", ["Manager"], []))
    app.manage_addFolder("Lab")
    folder = app.Lab
    folder._setObject("test_db", SQLiteConnection())
    database = folder.test_db._v_db
    yield folder
    database.close()
    noSecurityManager()
    transaction.abort()
    ZopeTestCase.close(app)


@pytest.fixture
def installed(app_folder):
    installer = SQLUserWizardInstaller(app_folder, "test_db", dialect="sqlite", fallback_password="emergency-pass")
    installer.install()
    return app_folder


def request(method="GET", form=None, cookies=None):
    req = HTTPRequest(BytesIO(), dict(REQUEST_METHOD=method, SERVER_NAME="localhost", SERVER_PORT="80",
                                     URL="http://localhost/Lab", SCRIPT_NAME="", PATH_INFO="/Lab"), HTTPResponse())
    req.form.update(form or {})
    req.cookies.update(cookies or {})
    return req


def post(obj, data, cookies=None):
    req = request(form=data, cookies=cookies)
    token = re.search(r'value="([^"]+)"', csrf_field(obj, req))[1]
    req.environ["REQUEST_METHOD"] = "POST"
    req.form["csrf_token"] = token
    return req


def add_user(folder, required=False, enabled=False):
    from Products.SQLUserWizard.sqladmin import save_sql_user
    save_sql_user(folder.acl_users.sql_auth, "alice-id", "alice", password="correct-password",
                  roles=["Member"], totp_required=required, totp_enabled=enabled,
                  totp_secret="JBSWY3DPEHPK3PXP")


def login(folder, **extra):
    controller = folder.sql_user_login_submit
    req = post(controller, dict(__ac_name="alice", __ac_password="correct-password", **extra))
    controller.index_html(req)
    return req


def cookie_from(req, name="sql_user_session"):
    return {name: req.RESPONSE.cookies[name]["value"]}


@pytest.mark.parametrize("field,value", [("src", "select 'custom'"),
                                       ("arguments_src", "custom_argument"),
                                       ("connection_id", "other_database")])
def test_repair_refuses_changed_sql_before_any_database_work(installed, field, value):
    method = installed.acl_users.sql_auth.zsql_pas_fetch_user
    setattr(method, field, value)
    queries = []
    installed.test_db._v_db.set_trace_callback(queries.append)
    with pytest.raises(ValueError, match="overwrite older or customized SQL"):
        SQLUserWizardInstaller(installed, "test_db", dialect="sqlite").install()
    assert getattr(method, field) == value
    assert queries == []


def test_install_repair_and_pas_cookie_authentication(installed):
    add_user(installed)
    req = login(installed, came_from="https://evil.example/")
    assert req.RESPONSE.getHeader("Location").endswith("/Lab/secure_test_page")
    cookie = cookie_from(req)
    assert "correct-password" not in str(cookie)
    assert req.RESPONSE.cookies["sql_user_session"]["HttpOnly"]
    next_request = request(cookies=cookie)
    pas = installed.acl_users
    assert pas._extractUserIds(next_request, pas.plugins) == [("alice-id", "alice")]
    assert pas.sql_auth.enumerateUsers(id="alice-id", exact_match=True)[0]["login"] == "alice"
    assert pas.sql_auth.getRolesForPrincipal(SimpleNamespace(getId=lambda: "alice-id")) == ("Member",)
    SQLUserWizardInstaller(installed, "test_db", dialect="sqlite").install()
    assert pas._extractUserIds(next_request, pas.plugins) == [("alice-id", "alice")]
    assert len(pas.sql_auth.zsql_pas_list_users()) == 1


def test_2fa_rejects_password_only_and_accepts_verified_session(installed):
    add_user(installed, enabled=True)
    pas = installed.acl_users
    assert pas.sql_auth.authenticateCredentials({"login": "alice", "password": "correct-password"}) is None
    bad = login(installed)
    assert "sql_user_session" not in bad.RESPONSE.cookies
    assert "otp_required" in bad.RESPONSE.getHeader("Location")
    req = login(installed, otp_code=totp_code("JBSWY3DPEHPK3PXP"))
    assert pas._extractUserIds(request(cookies=cookie_from(req)), pas.plugins) == [("alice-id", "alice")]
    replay = login(installed, otp_code=totp_code("JBSWY3DPEHPK3PXP"))
    assert "sql_user_session" not in replay.RESPONSE.cookies


def test_enrollment_cannot_authenticate_until_otp_confirmation(installed):
    add_user(installed, required=True)
    req = login(installed, came_from="/Lab/private")
    assert "/enroll?" in req.RESPONSE.getHeader("Location")
    cookies = cookie_from(req)
    pas = installed.acl_users
    assert pas._extractUserIds(request(cookies=cookies), pas.plugins) == []
    controller = installed.sql_user_login_submit
    assert "Authenticator QR code" in controller.enroll(request(cookies=cookies))
    confirmed = post(controller, dict(otp_code=totp_code("JBSWY3DPEHPK3PXP"), came_from="/Lab/private"), cookies)
    controller.enroll(confirmed)
    assert confirmed.RESPONSE.getHeader("Location") == "/Lab/private"
    assert pas._extractUserIds(request(cookies=cookie_from(confirmed)), pas.plugins) == [("alice-id", "alice")]
    assert pas.sql_cookie_auth._record(cookies["sql_user_session"], scope="enroll") is None


def test_session_revoked_on_logout_and_password_change(installed):
    add_user(installed)
    controller = installed.sql_user_login_submit
    cookies = cookie_from(login(installed))
    controller.logout(post(controller, {}, cookies))
    pas = installed.acl_users
    assert pas._extractUserIds(request(cookies=cookies), pas.plugins) == []
    cookies = cookie_from(login(installed))
    pas.sql_auth.zsql_pas_update_password(user_id="alice-id", password="new-password", password_hash_id="plain")
    assert pas._extractUserIds(request(cookies=cookies), pas.plugins) == []


def test_fallback_login_works_during_database_failure(installed):
    installed.test_db._v_db.execute("drop table pas_users")
    controller = installed.sql_user_login_submit
    req = post(controller, dict(__ac_name="pas_fallback_manager", __ac_password="emergency-pass"))
    controller.index_html(req)
    pas = installed.acl_users
    assert pas._extractUserIds(request(cookies=cookie_from(req)), pas.plugins) == [("pas_fallback_manager", "pas_fallback_manager")]


def test_new_install_refuses_foreign_table_before_pas_creation(app_folder):
    app_folder.test_db._v_db.execute("create table pas_users (legacy text)")
    with pytest.raises(ValueError, match="already exist"):
        SQLUserWizardInstaller(app_folder, "test_db", dialect="sqlite").install()
    assert "acl_users" not in app_folder.objectIds()
    assert app_folder.test_db._v_db.execute("pragma table_info(pas_users)").fetchone()[1] == "legacy"


def test_anonymous_pas_auth_and_sql_methods_not_public(installed):
    add_user(installed)
    noSecurityManager()
    req = login(installed)
    pas = installed.acl_users
    assert pas._extractUserIds(request(cookies=cookie_from(req)), pas.plugins) == [("alice-id", "alice")]
    for container in (pas.sql_auth, installed):
        for obj in container.objectValues():
            if obj.meta_type == "Z SQL Method":
                assert not getSecurityManager().checkPermission("Use Database Methods", obj)
    assert not getSecurityManager().checkPermission("View", pas.sql_user_wizard_manifest)


def test_manager_can_manage_generated_zsql_methods(installed):
    for container in (installed.acl_users.sql_auth, installed):
        for obj in container.objectValues():
            if obj.meta_type == "Z SQL Method":
                assert getSecurityManager().checkPermission(
                    "Use Database Methods", obj
                )


def test_profile_and_2fa_require_post_and_csrf(installed):
    from zExceptions import Forbidden, Unauthorized
    add_user(installed, required=True, enabled=True)
    pas = installed.acl_users
    newSecurityManager(None, pas.getUserById("alice-id").__of__(pas))
    admin = installed.sql_user_admin
    for method, action in ((admin.my_profile, "save_profile"), (admin.my_2fa, "reset_totp"),
                           (admin.my_2fa, "disable_totp"), (admin.my_2fa, "confirm_totp")):
        for verb in ("GET", "POST"):
            with pytest.raises(Forbidden):
                method(request(verb, {action: "1"}))
    with pytest.raises(Unauthorized):
        admin.my_2fa(post(admin, dict(disable_totp="1", otp_code=totp_code("JBSWY3DPEHPK3PXP"))))
    assert "JBSWY3DPEHPK3PXP" not in admin.my_2fa(request())
    assert "Authenticator QR code" not in admin.my_2fa(request())


def test_optional_self_service_setup_rotates_to_enrollment_session(installed):
    add_user(installed)
    pas = installed.acl_users
    cookies = cookie_from(login(installed))
    newSecurityManager(None, pas.getUserById("alice-id").__of__(pas))
    admin = installed.sql_user_admin
    reset = post(admin, dict(reset_totp="1"), cookies)
    admin.my_2fa(reset)
    assert "/enroll" in reset.RESPONSE.getHeader("Location")
    pending = cookie_from(reset)
    assert pas._extractUserIds(request(cookies=pending), pas.plugins) == []
    noSecurityManager()
    user = pas.sql_auth.zsql_pas_fetch_user(login="alice")[0]
    confirmed = post(installed.sql_user_login_submit, dict(otp_code=totp_code(user.totp_secret)), pending)
    installed.sql_user_login_submit.enroll(confirmed)
    assert pas._extractUserIds(request(cookies=cookie_from(confirmed)), pas.plugins) == [("alice-id", "alice")]


def test_inherited_zodb_user_still_imported(app_folder):
    app_folder.aq_parent.acl_users._doAddUser("inherited-manager", "inherited-password", ["Manager"], [])
    SQLUserWizardInstaller(app_folder, "test_db", dialect="sqlite").install()
    store = app_folder.acl_users.zodb_fallback_users
    assert store.authenticateCredentials(dict(login="inherited-manager", password="inherited-password")) == ("inherited-manager", "inherited-manager")


def test_retired_manifest_and_changed_table_names_cannot_take_over(installed):
    import json
    pas = installed.acl_users
    manifest = pas.sql_user_wizard_manifest
    data = json.loads(manifest.raw)
    with pytest.raises(ValueError, match="recorded"):
        SQLUserWizardInstaller(installed, "test_db", dialect="sqlite", tables={**data["tables"], "users": "other_users"}).install()
    data["mode"] = "auth_only"
    manifest.manage_edit(data=json.dumps(data), title="Old manifest")
    with pytest.raises(ValueError, match="retired"):
        SQLUserWizardInstaller(installed, "test_db", dialect="sqlite").install()


def test_repair_removes_old_migration_methods(installed):
    from Products.ZSQLMethods.SQL import SQL
    plugin = installed.acl_users.sql_auth
    old = "zsql_pas_classic_acl_users_migration"
    plugin._setObject(old, SQL(old, "Old migration", "test_db", "", "select 1"))
    SQLUserWizardInstaller(installed, "test_db", dialect="sqlite").install()
    assert old not in plugin.objectIds()


def test_session_expiry_tampering_and_enrollment_forgery(installed, monkeypatch):
    add_user(installed, required=True)
    req = login(installed)
    helper = installed.acl_users.sql_cookie_auth
    token = cookie_from(req)["sql_user_session"]
    assert helper._record(token) is None
    assert helper._record(token + "tampered", scope="enroll") is None
    monkeypatch.setattr("Products.SQLUserWizard.sessions.time.time", lambda: 9999999999)
    assert helper._record(token, scope="enroll") is None


def test_login_template_renders_csrf_field(installed):
    noSecurityManager()
    html = installed.sql_user_login_form(installed, installed.REQUEST)
    assert 'name="csrf_token"' in html


def test_repair_keeps_initial_user_security_settings(installed):
    add_user(installed, required=True, enabled=True)
    plugin = installed.acl_users.sql_auth
    before = plugin.zsql_pas_fetch_user(login="alice")[0]
    SQLUserWizardInstaller(installed, "test_db", dialect="sqlite", initial_user={
        "user_id": "alice-id", "login_name": "alice", "password": "replacement", "roles": ["Manager"]
    }).install()
    after = plugin.zsql_pas_fetch_user(login="alice")[0]
    assert before.password == after.password
    assert after.totp_enabled and after.totp_required
    assert [row.role for row in plugin.zsql_pas_fetch_roles(user_id="alice-id")] == ["Member"]


@pytest.mark.parametrize("dialect", ["postgresql", "sqlite", "mysql", "mssql", "oracle11g", "oracle12c"])
def test_totp_update_renders_declared_arguments_for_every_dialect(app_folder, dialect):
    from Products.SQLUserWizard.dialects import managed_templates
    from Products.ZSQLMethods.SQL import SQL
    spec = managed_templates(dialect)["update_2fa"]
    method = SQL(spec["id"], spec["title"], "test_db", spec["arguments"], spec["template"]).__of__(app_folder)
    rendered = method(src__=True, user_id="alice-id", totp_required="1", totp_enabled="1", totp_secret="SECRET")
    assert "totp_enabled = case" in rendered.lower()
    assert "SECRET" in rendered


def test_session_is_invalidated_when_user_disabled(installed):
    add_user(installed)
    cookies = cookie_from(login(installed))
    installed.test_db._v_db.execute("update pas_users set enabled = 0")
    pas = installed.acl_users
    assert pas._extractUserIds(request(cookies=cookies), pas.plugins) == []


def test_login_throttles_repeated_password_guesses(installed):
    add_user(installed)
    controller = installed.sql_user_login_submit
    for _ in range(10):
        req = post(controller, dict(__ac_name="alice", __ac_password="wrong"))
        controller.index_html(req)
    assert "sql_user_session" not in login(installed).RESPONSE.cookies


def test_sql_session_rejects_legacy_password_cookie(installed):
    from Products.PluggableAuthService.plugins.CookieAuthHelper import CookieAuthHelper
    add_user(installed, enabled=True)
    value = CookieAuthHelper("old").get_cookie_value("alice", "correct-password")
    pas = installed.acl_users
    assert pas._extractUserIds(request(cookies={"sql_user_auth": value}), pas.plugins) == []


