"""Load real 0.1.0a2 ZODB objects under the current package, then upgrade."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import zipfile
import transaction

import pytest
from AccessControl.SecurityManagement import noSecurityManager
from Products.PluggableAuthService.interfaces.plugins import IAuthenticationPlugin
from Products.SQLUserWizard.sessions import SQLSessionHelper
from Products.SQLUserWizard.totp import totp_code
from Products.SQLUserWizard.upgrade import upgrade_folder, upgrade_tree
from test_integration import app_folder, post, request, cookie_from


@pytest.fixture(scope="session")
def legacy_export(tmp_path_factory):
    target = tmp_path_factory.mktemp("old-sqluserwizard")
    tests = Path(__file__).parent
    with zipfile.ZipFile(tests / "fixtures/sqluserwizard-0.1.0a2.zip") as archive:
        archive.extractall(target)
    env = dict(os.environ, PYTHONPATH=str(target / "src"))
    result = subprocess.run([sys.executable, str(tests / "build_legacy_installation.py"), str(target)],
                            env=env, cwd=target, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    return target


@pytest.fixture
def legacy(app_folder, legacy_export):
    transaction.savepoint(optimistic=True)
    obj = app_folder._p_jar.importFile(str(legacy_export / "legacy.zexp"))
    app_folder._setObject("Legacy", obj)
    folder = app_folder.Legacy
    db = sqlite3.connect(":memory:")
    db.executescript((legacy_export / "database.sql").read_text(encoding="utf-8"))
    folder.test_db._v_db = db
    yield folder
    db.close()


def test_actual_old_installation_preserves_data_defaults_and_authenticates(legacy):
    before = list(legacy.test_db._v_db.iterdump())
    methods = {obj.getId(): obj.src for obj in legacy.acl_users.sql_auth.objectValues()
               if obj.meta_type == "Z SQL Method"}
    queries = []
    legacy.test_db._v_db.set_trace_callback(queries.append)
    assert not isinstance(legacy.acl_users.sql_cookie_auth, SQLSessionHelper)
    assert upgrade_folder(legacy)
    assert queries == []  # Not even a read is needed during runtime upgrade.
    assert methods == {obj.getId(): obj.src for obj in legacy.acl_users.sql_auth.objectValues()
                       if obj.meta_type == "Z SQL Method"}
    assert list(legacy.test_db._v_db.iterdump()) == before
    assert legacy.sql_user_wizard.roles_table == "pas_roles_catalog"
    assert legacy.sql_user_wizard.users_table == "pas_users_migrated"
    assert not upgrade_folder(legacy)
    noSecurityManager()
    controller = legacy.sql_user_login_submit
    req = post(controller, dict(__ac_name="alice", __ac_password="correct-password",
                               otp_code=totp_code("JBSWY3DPEHPK3PXP")))
    controller.index_html(req)
    pas = legacy.acl_users
    assert pas._extractUserIds(request(cookies=cookie_from(req)), pas.plugins) == [("alice-id", "alice")]
    assert pas.zodb_fallback_users.authenticateCredentials(dict(login="pas_fallback_manager", password="emergency-pass"))


def test_custom_login_form_is_preserved_with_csrf_added(legacy):
    form = legacy.sql_user_login_form
    form.manage_edit(data='<h1>My company</h1><form method="post" action="sql_user_login_submit"></form>', title="Custom")
    upgrade_folder(legacy)
    assert "My company" in form.raw
    assert "csrf_field(REQUEST)" in form.raw


def test_broken_upgrade_rolls_back_only_that_folder_and_keeps_fallback(legacy, monkeypatch):
    import Products.SQLUserWizard.upgrade as module
    original = module.upgrade_folder
    seen = []

    def fail_one(folder):
        seen.append(folder.getId())
        if folder.getId() == "Legacy":
            folder.partial_change = True
            raise ValueError("Simulated failure")
        return original(folder)

    monkeypatch.setattr(module, "upgrade_folder", fail_one)
    upgrade_tree(legacy.aq_parent)
    assert not hasattr(legacy.aq_base, "partial_change")
    assert "SQL login is disabled" in legacy._sqluw_upgrade_error
    pas = legacy.acl_users
    assert "sql_auth" not in pas.plugins.listPluginIds(IAuthenticationPlugin)
    assert "zodb_fallback_users" in pas.plugins.listPluginIds(IAuthenticationPlugin)
    assert "acl_users" in seen  # Traversal continues past the failed folder.
    monkeypatch.setattr(module, "upgrade_folder", original)
    assert upgrade_folder(legacy)
    assert "_sqluw_upgrade_error" not in legacy.aq_base.__dict__
    assert "sql_auth" in pas.plugins.listPluginIds(IAuthenticationPlugin)


def test_package_initialization_registers_startup_upgrade(monkeypatch):
    from types import SimpleNamespace
    from Products.SQLUserWizard import initialize
    from Products.SQLUserWizard.upgrade import upgrade_database
    from zope.processlifetime import IDatabaseOpenedWithRoot
    handlers = []
    monkeypatch.setattr("zope.component.provideHandler", lambda *args: handlers.append(args))
    initialize(SimpleNamespace(registerClass=lambda **kw: None))
    assert (upgrade_database, (IDatabaseOpenedWithRoot,)) in handlers


def test_scoped_upgrade_leaves_other_folders_unchanged(legacy, monkeypatch):
    monkeypatch.setenv("SQLUSERWIZARD_UPGRADE_PATHS", "/DifferentFolder")
    upgrade_tree(legacy.aq_parent)
    assert not isinstance(legacy.acl_users.sql_cookie_auth, SQLSessionHelper)
    monkeypatch.setenv("SQLUSERWIZARD_UPGRADE_PATHS", "/Lab/Legacy")
    upgrade_tree(legacy.aq_parent)
    assert isinstance(legacy.acl_users.sql_cookie_auth, SQLSessionHelper)


def test_missing_mode_is_reported_and_old_sql_auth_is_disabled(legacy):
    manifest = legacy.acl_users.sql_user_wizard_manifest
    data = json.loads(manifest.read())
    del data["mode"]
    manifest.manage_edit(title=manifest.title, data=json.dumps(data))
    upgrade_tree(legacy)
    assert "_sqluw_upgrade_error" in legacy.aq_base.__dict__
    assert "sql_auth" not in legacy.acl_users.plugins.listPluginIds(IAuthenticationPlugin)
    assert "zodb_fallback_users" in legacy.acl_users.plugins.listPluginIds(IAuthenticationPlugin)
    assert "mode" not in json.loads(manifest.read())


def test_missing_2fa_method_cannot_report_successful_upgrade(legacy):
    legacy.acl_users.sql_auth._delObject("zsql_pas_update_2fa")
    with pytest.raises(ValueError, match="zsql_pas_update_2fa"):
        upgrade_folder(legacy)
    assert not isinstance(legacy.acl_users.sql_cookie_auth, SQLSessionHelper)


def test_stale_dialect_does_not_rewrite_custom_sql(legacy):
    manifest = legacy.acl_users.sql_user_wizard_manifest
    data = json.loads(manifest.read())
    data["sql_dialect"] = "oracle11g"  # The actual adapter/schema remains SQLite.
    manifest.manage_edit(title=manifest.title, data=json.dumps(data))
    plugin = legacy.acl_users.sql_auth
    method = plugin.zsql_pas_fetch_user
    method.manage_edit(title=method.title, connection_id=method.connection_id,
                       arguments=method.arguments_src, template=method.src + "\n-- local customization")
    before = (method.src, method.connection_id, method.arguments_src)
    assert upgrade_folder(legacy)
    assert (method.src, method.connection_id, method.arguments_src) == before
    noSecurityManager()
    req = post(legacy.sql_user_login_submit,
               dict(__ac_name="alice", __ac_password="correct-password",
                    otp_code=totp_code("JBSWY3DPEHPK3PXP")))
    legacy.sql_user_login_submit.index_html(req)
    assert legacy.acl_users._extractUserIds(request(cookies=cookie_from(req)),
                                           legacy.acl_users.plugins) == [("alice-id", "alice")]
