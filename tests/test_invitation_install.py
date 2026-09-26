import json

import pytest
from AccessControl.SecurityManagement import noSecurityManager
from zExceptions import Unauthorized

from Products.SQLUserWizard.installer import SQLUserWizardInstaller
from Products.SQLUserWizard.invitation_install import enable_invitation_storage
from test_integration import app_folder, installed, request, post


def test_storage_is_explicit_and_repair_preserves_ownership(installed):
    db = installed.test_db._v_db
    assert not db.execute("select name from sqlite_master where name like 'pas_invitation%'").fetchall()
    enable_invitation_storage(installed)
    invitations = installed.invitations
    assert set(("create_invitation", "inspect_invitation", "complete_invitation", "form",
                "create_form", "sql_wizard.css", "README-invitations.html")) <= set(invitations.objectIds())
    assert invitations.create_invitation._proxy_roles == ()
    assert invitations.inspect_invitation._proxy_roles == ("InvitationInspector",)
    assert invitations.form._proxy_roles == ("InvitationInspector",)
    assert invitations.complete_invitation._proxy_roles == ("InvitationCompleter",)
    db.execute("insert into pas_invitations (invitation_id, secret_hash, email, creator_id, created_at, expires_at) values ('i','h','u@example.invalid','m',1,100)")
    before = list(db.iterdump())
    enable_invitation_storage(installed)
    assert list(db.iterdump()) == before
    SQLUserWizardInstaller(installed, "test_db", dialect="sqlite").install()
    manifest = json.loads(installed.acl_users.sql_user_wizard_manifest.read())
    assert manifest["invitations"]["schema_revision"] == 1
    assert len(manifest["tables"]) == 4
    assert db.execute("select count(*) from pas_invitations").fetchone()[0] == 1


def test_storage_refuses_collisions_before_creating_objects(installed):
    installed.test_db._v_db.execute("create table pas_invitations (foreign_data text)")
    with pytest.raises(ValueError, match="without ownership"):
        enable_invitation_storage(installed)
    assert "zsql_invitation_setup" not in installed.acl_users.sql_auth.objectIds()


def test_storage_requires_manager_permission(installed):
    noSecurityManager()
    with pytest.raises(Unauthorized):
        enable_invitation_storage(installed)


def test_storage_repair_refuses_customized_sql(installed):
    enable_invitation_storage(installed)
    method = installed.acl_users.sql_auth.zsql_invitation_get
    method.src += " -- customized"
    with pytest.raises(ValueError, match="Customized invitation SQL"):
        enable_invitation_storage(installed)


def test_storage_repair_restores_missing_method_without_ddl_or_data_loss(installed):
    enable_invitation_storage(installed, allowed_roles=("Member",), totp_required=True)
    plugin = installed.acl_users.sql_auth
    plugin._delObject("zsql_invitation_get")
    db = installed.test_db._v_db
    before = list(db.iterdump())
    queries = []
    db.set_trace_callback(queries.append)
    enable_invitation_storage(installed, allowed_roles=("Member",), totp_required=True)
    db.set_trace_callback(None)
    assert "zsql_invitation_get" in plugin.objectIds()
    assert list(db.iterdump()) == before
    assert not any(sql.lstrip().lower().startswith(("create", "alter", "drop")) for sql in queries)
    assert installed.sql_user_provisioning.totp_required


def test_storage_repair_refuses_changed_policy_without_mutation(installed):
    enable_invitation_storage(installed, totp_required=True)
    manifest = installed.acl_users.sql_user_wizard_manifest.read()
    before = list(installed.test_db._v_db.iterdump())
    with pytest.raises(ValueError, match="policy"):
        enable_invitation_storage(installed, totp_required=False)
    assert installed.acl_users.sql_user_wizard_manifest.read() == manifest
    assert list(installed.test_db._v_db.iterdump()) == before


def test_setup_page_only_enables_after_protected_post(installed):
    from zExceptions import Forbidden
    admin = installed.sql_user_admin
    assert "Enable invitations" in admin.manage_invitations(request())
    assert "sql_user_provisioning" not in installed.objectIds()
    data = dict(enable_invitations="1", invitations_table="test_invites",
                invitation_roles_table="test_invite_roles", allowed_roles="Member",
                privileged_roles="SiteAdmin", totp_required="1")
    with pytest.raises(Forbidden):
        admin.manage_invitations(request(form=data))
    assert "enabled" in admin.manage_invitations(post(admin, data))
    assert installed.sql_user_provisioning.totp_required
    assert installed.sql_user_provisioning.privileged_roles == ("SiteAdmin",)
    policy = post(admin, {"save_invitation_policy": "1"})
    assert "policy was saved" in admin.manage_invitations(policy)
    assert not installed.sql_user_provisioning.totp_required


def test_plone_rejection_precedes_invitation_ddl(installed, monkeypatch):
    from Products.SQLUserWizard import security
    from zExceptions import Forbidden
    admin = installed.sql_user_admin
    req = post(admin, dict(enable_invitations="1", invitations_table="pas_invitations",
                           invitation_roles_table="pas_invitation_roles", allowed_roles="Member"))
    def reject(obj, request, verify=False):
        if verify:
            raise Forbidden("Invalid Plone authenticator")
        return ""
    monkeypatch.setattr(security, "_plone_authenticator", reject)
    with pytest.raises(Forbidden, match="Plone"):
        admin.manage_invitations(req)
    assert "sql_user_provisioning" not in installed.objectIds()
    assert not installed.test_db._v_db.execute(
        "select name from sqlite_master where name like 'pas_invitation%'").fetchall()
