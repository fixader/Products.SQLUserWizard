import pytest
import transaction
from AccessControl.SecurityManagement import noSecurityManager
from Shared.DC.ZRDB.TM import TM
from zExceptions import Forbidden, Unauthorized

from Products.SQLUserWizard.invitation_install import enable_invitation_storage
from test_integration import app_folder, installed, post, request, SQLiteConnection


@pytest.fixture
def provisioning(installed):
    enable_invitation_storage(installed)
    return installed.sql_user_provisioning


def create(controller, **kw):
    return controller.create_invitation("user@example.invalid", ["Member"], post(controller, {}), **kw)


def test_lifecycle_and_sanitized_inspection(provisioning):
    invitation = create(provisioning)
    assert len(invitation["token"]) == 43
    assert provisioning.inspect_invitation(invitation["token"], request())["valid"]
    listed = provisioning.list_invitations(request())
    assert "secret_hash" not in listed[0] and "claim_nonce" not in listed[0]
    rotated = provisioning.rotate_invitation_secret(invitation["invitation_id"], post(provisioning, {}))
    assert not provisioning.inspect_invitation(invitation["token"], request())["valid"]
    provisioning.record_delivery(invitation["invitation_id"], "email", "failed", post(provisioning, {}))
    assert provisioning.inspect_invitation(rotated["token"], request())["valid"]
    assert provisioning.revoke_invitation(invitation["invitation_id"], post(provisioning, {}))["revoked"]
    assert not provisioning.inspect_invitation(rotated["token"], request())["valid"]


@pytest.mark.parametrize("role", ["Manager", "Owner", "Anonymous", "Authenticated", "manager", "Other"])
def test_unapproved_roles_denied(provisioning, role):
    with pytest.raises(ValueError):
        provisioning.create_invitation("user@example.invalid", [role], post(provisioning, {}))


def test_permission_csrf_and_direct_traversal(provisioning):
    with pytest.raises(Forbidden):
        provisioning.create_invitation("user@example.invalid", [], request())
    with pytest.raises(Forbidden):
        provisioning.__bobo_traverse__(request(), "complete_invitation")
    noSecurityManager()
    with pytest.raises(Unauthorized):
        provisioning.list_invitations(request())


def test_completion_refuses_nontransactional_adapter(provisioning):
    invitation = create(provisioning)
    with pytest.raises(ValueError, match="participate"):
        provisioning.complete_invitation(invitation["token"], "u", "u", "long-password", {}, post(provisioning, {}))


class TransactionalSQLite(TM):
    def __init__(self, db):
        self.db = db

    def query(self, sql, max_rows=1000):
        self._register()
        cursor = self.db.execute(sql)
        columns = [dict(name=c[0], type="s", width=0, null=True) for c in cursor.description or ()]
        return columns, cursor.fetchmany(max_rows) if columns else []


@pytest.fixture
def transactional(provisioning, monkeypatch):
    adapter = provisioning.aq_parent.test_db
    adapter._v_db.commit()
    resource = TransactionalSQLite(adapter._v_db)
    monkeypatch.setattr(SQLiteConnection, "__call__", lambda self: resource)
    yield provisioning, resource
    transaction.abort()


def test_transactional_completion_and_replay(transactional):
    controller, resource = transactional
    invitation = create(controller)
    result = controller.complete_invitation(invitation["token"], "new", "new", "long-password", {}, post(controller, {}))
    assert result["user_id"] == "new"
    assert resource.db.execute("select count(*) from pas_users where user_id='new'").fetchone()[0] == 1
    with pytest.raises(ValueError, match="unavailable"):
        controller.complete_invitation(invitation["token"], "new2", "new2", "long-password", {}, post(controller, {}))
    resource.db.rollback()
    resource._registered = 0


def test_failure_dooms_transaction_and_rolls_back_user(transactional, monkeypatch):
    controller, resource = transactional
    invitation = create(controller)
    # Persist the invitation before the simulated completion request.
    resource.db.commit()
    def fail(*args, **kwargs):
        raise RuntimeError("simulated profile failure")
    monkeypatch.setattr("Products.SQLUserWizard.provisioning.save_sql_user", fail)
    with pytest.raises(ValueError, match="completion failed"):
        controller.complete_invitation(invitation["token"], "new", "new", "long-password", {}, post(controller, {}))
    assert transaction.isDoomed()
    # Exercise Zope's transaction manager rather than manually rolling back SQL.
    transaction.abort()
    assert resource.db.execute("select count(*) from pas_users where user_id='new'").fetchone()[0] == 0
    assert resource.db.execute("select claim_nonce from pas_invitations").fetchone()[0] is None
