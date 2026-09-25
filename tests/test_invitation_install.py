import json

import pytest
from AccessControl.SecurityManagement import noSecurityManager
from zExceptions import Unauthorized

from Products.SQLUserWizard.installer import SQLUserWizardInstaller
from Products.SQLUserWizard.invitation_install import enable_invitation_storage
from test_integration import app_folder, installed


def test_storage_is_explicit_and_repair_preserves_ownership(installed):
    db = installed.test_db._v_db
    assert not db.execute("select name from sqlite_master where name like 'pas_invitation%'").fetchall()
    enable_invitation_storage(installed)
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
