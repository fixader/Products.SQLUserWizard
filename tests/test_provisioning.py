import pytest
import transaction
from AccessControl.SecurityManagement import noSecurityManager
from Shared.DC.ZRDB.TM import TM
from zExceptions import Forbidden, Unauthorized

from Products.SQLUserWizard.invitation_install import enable_invitation_storage
from test_integration import app_folder, installed, post, request, SQLiteConnection


@pytest.fixture(autouse=True)
def fresh_attempt_limiter(monkeypatch):
    from Products.SQLUserWizard import provisioning
    monkeypatch.setattr(provisioning, "_attempt_limiter", provisioning._AttemptLimiter())


@pytest.fixture
def provisioning(installed, monkeypatch):
    enable_invitation_storage(installed)
    adapter = installed.test_db
    adapter._v_db.commit()
    resource = TransactionalSQLite(adapter._v_db)
    monkeypatch.setattr(SQLiteConnection, "__call__", lambda self: resource)
    yield installed.sql_user_provisioning
    transaction.abort()


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
    from ZPublisher.interfaces import UseTraversalDefault
    with pytest.raises(UseTraversalDefault):
        provisioning.__bobo_traverse__(request(), "manage_role")
    noSecurityManager()
    with pytest.raises(Unauthorized):
        provisioning.list_invitations(request())


def test_completion_refuses_nontransactional_adapter(provisioning, monkeypatch):
    invitation = create(provisioning)
    monkeypatch.setattr(SQLiteConnection, "__call__", lambda self: self)
    with pytest.raises(ValueError, match="completion failed"):
        provisioning.complete_invitation(invitation["token"], "u", "u", "long-password", {}, post(provisioning, {}))


def test_creation_refuses_nontransactional_adapter_before_writes(provisioning, monkeypatch):
    monkeypatch.setattr(SQLiteConnection, "__call__", lambda self: self)
    with pytest.raises(ValueError, match="creation failed"):
        create(provisioning)
    db = provisioning.aq_parent.test_db._v_db
    assert db.execute("select count(*) from pas_invitations").fetchone()[0] == 0


def test_completion_validates_mobile_before_database_writes(provisioning):
    invitation = create(provisioning)
    with pytest.raises(ValueError, match="mobile"):
        provisioning.complete_invitation(invitation["token"], "u", "u", "long-password",
                                         {"mobile": "1" * 41}, post(provisioning, {}))
    assert provisioning.inspect_invitation(invitation["token"], request())["valid"]


def test_failed_attempts_remain_limited_after_transaction_abort(provisioning):
    for unused in range(30):
        with pytest.raises(ValueError, match="unavailable"):
            provisioning.inspect_invitation("invalid", request())
        transaction.abort()
    with pytest.raises(ValueError, match="Too many"):
        provisioning.inspect_invitation("x" * 43, request())


def test_attempt_limit_expires_and_is_scoped_by_application():
    from Products.SQLUserWizard.provisioning import _AttemptLimiter
    limiter = _AttemptLimiter()
    for unused in range(30):
        limiter.check(("app-one", "ip"), 100)
    with pytest.raises(ValueError, match="Too many"):
        limiter.check(("app-one", "ip"), 399)
    limiter.check(("app-two", "ip"), 399)
    limiter.check(("app-one", "ip"), 400)


@pytest.mark.parametrize("failure", [None, "begin", "commit"])
def test_explicit_transaction_ownership_and_abort(provisioning, monkeypatch, failure):
    calls = []
    def begin(self):
        calls.append("begin")
        if failure == "begin":
            raise RuntimeError("Caller already owns a transaction")
    def commit(self):
        calls.append("commit")
        if failure == "commit":
            raise RuntimeError("Commit request failed")
    def rollback(self):
        calls.append("rollback")
    for name, method in (("begin_transaction", begin), ("commit_transaction", commit),
                         ("rollback_transaction", rollback)):
        monkeypatch.setattr(SQLiteConnection, name, method, raising=False)
    if failure:
        with pytest.raises(ValueError, match="creation failed"):
            create(provisioning)
        assert transaction.isDoomed()
    else:
        create(provisioning)
    assert calls == {None: ["begin", "commit"], "begin": ["begin"],
                     "commit": ["begin", "commit", "rollback"]}[failure]
    transaction.abort()
    assert provisioning.aq_parent.test_db._v_db.execute(
        "select count(*) from pas_invitations").fetchone()[0] == 0


class TransactionalSQLite(TM):
    def __init__(self, db):
        self.db = db

    def query(self, sql, max_rows=1000):
        self._register()
        cursor = self.db.execute(sql)
        columns = [dict(name=c[0], type="s", width=0, null=True) for c in cursor.description or ()]
        return columns, cursor.fetchmany(max_rows) if columns else []


@pytest.fixture
def transactional(provisioning):
    adapter = provisioning.aq_parent.test_db
    return provisioning, adapter()


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


def application_script(folder, name, body, roles=()):
    from Products.PythonScripts.PythonScript import PythonScript
    folder._setObject(name, PythonScript(name))
    script = folder._getOb(name)
    script.ZPythonScript_edit("token, req", body)
    script.manage_proxy(roles)
    script.manage_permission("View", roles=("Anonymous",), acquire=0)
    return script


def test_real_restricted_script_requires_narrow_proxy_role(provisioning):
    from Products.SQLUserWizard.provisioning import INSPECT
    folder = provisioning.aq_parent
    folder._addRole("InvitationInspector")
    provisioning.manage_permission(INSPECT, roles=("Manager", "InvitationInspector"), acquire=0)
    invitation = create(provisioning)
    folder.manage_addFolder("invitations")
    script = application_script(folder.invitations, "inspect",
        "return context.sql_user_provisioning.inspect_invitation(token, req)")
    noSecurityManager()
    with pytest.raises(Unauthorized):
        script(invitation["token"], request())
    # Configuration is done by a manager, never by the anonymous request.
    from AccessControl.SecurityManagement import newSecurityManager
    from AccessControl.users import UnrestrictedUser
    newSecurityManager(None, UnrestrictedUser("test-manager", "", ["Manager"], []))
    script.manage_proxy(("InvitationInspector",))
    noSecurityManager()
    assert script(invitation["token"], request())["valid"]


def test_restricted_script_cannot_reach_private_helpers(provisioning):
    folder = provisioning.aq_parent
    for index, source in enumerate(("return context.sql_user_provisioning.allowed_roles",
                   "return context.sql_user_provisioning._plugin()")):
        script = application_script(folder, "probe" + str(index), source)
        noSecurityManager()
        if index:
            assert any("_plugin" in error for error in script.errors)
        else:
            with pytest.raises(Unauthorized):
                script("", request())


def test_real_completion_script_uses_proxy_without_manager(transactional):
    from Products.SQLUserWizard.provisioning import COMPLETE
    controller, resource = transactional
    folder = controller.aq_parent
    folder._addRole("InvitationCompleter")
    controller.manage_permission(COMPLETE, roles=("Manager", "InvitationCompleter"), acquire=0)
    invitation = create(controller)
    folder.manage_addFolder("invitations")
    script = application_script(folder.invitations, "complete",
        'return context.sql_user_provisioning.complete_invitation(token, "new", "new", "long-password", {}, req)',
        ("InvitationCompleter",))
    noSecurityManager()
    req = post(controller, {})
    assert script(invitation["token"], req)["user_id"] == "new"
    assert resource.db.execute("select role_id from pas_user_roles where user_id='new'").fetchall() == [("Member",)]
    assert not req.RESPONSE.cookies.get("sql_user_session")


def test_sibling_application_does_not_acquire_controller(provisioning):
    application = provisioning.aq_parent
    application.aq_parent.manage_addFolder("Unrelated")
    script = application_script(application.aq_parent.Unrelated, "inspect",
        "return context.sql_user_provisioning.inspect_invitation(token, req)")
    noSecurityManager()
    with pytest.raises((AttributeError, Unauthorized)):
        script("x" * 43, request())


def test_documented_script_bodies_create_inspect_and_complete(transactional):
    import re
    from pathlib import Path
    from Products.SQLUserWizard.provisioning import COMPLETE, INSPECT
    controller, resource = transactional
    folder = controller.aq_parent
    source = (Path(__file__).parents[1] / "docs/invitation-script-examples.md").read_text()
    bodies = re.findall(r"```python\n(.*?)\n```", source, re.S)[:3]
    assert len(bodies) == 3
    folder._addRole("InvitationInspector")
    folder._addRole("InvitationCompleter")
    controller.manage_permission(INSPECT, roles=("Manager", "InvitationInspector"), acquire=0)
    controller.manage_permission(COMPLETE, roles=("Manager", "InvitationCompleter"), acquire=0)
    scripts = []
    for index, role in enumerate(((), ("InvitationInspector",), ("InvitationCompleter",))):
        script = application_script(folder, "documented" + str(index), bodies[index], role)
        script.ZPythonScript_edit("", bodies[index])
        assert not script.errors
        scripts.append(script)
    folder.REQUEST = post(controller, {"email": "manual@example.invalid"})
    invitation = scripts[0]()
    noSecurityManager()
    folder.REQUEST = request(form={"token": invitation["token"]})
    assert scripts[1]()["valid"]
    folder.REQUEST = post(controller, dict(token=invitation["token"], user_id="manual",
                                           login_name="manual", password="long-password"))
    assert scripts[2]()["user_id"] == "manual"
    assert resource.db.execute("select role_id from pas_user_roles where user_id='manual'").fetchall() == [("Member",)]
