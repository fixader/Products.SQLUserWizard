import re
from types import SimpleNamespace

import pytest
from zExceptions import Forbidden

from Products.SQLUserWizard.admin import SQLUserAdmin
from Products.SQLUserWizard.login import SQLUserLoginSubmit
from Products.SQLUserWizard.security import csrf_field, protect_forms, require_post, safe_redirect
from Products.SQLUserWizard.schema import validate_tables
from Products.SQLUserWizard.config import DEFAULT_TABLES
from Products.SQLUserWizard.wizard import SQLUserWizard
from Products.SQLUserWizard.totp import verify_totp_code


class Request(dict):
    def __init__(self, method="GET", **form):
        super().__init__(REQUEST_METHOD=method, **form)
        self.cookies = {}
        self.form = form
        self.RESPONSE = SimpleNamespace(setCookie=lambda *a, **kw: None, setHeader=lambda *a: None)


def authorized(obj, **form):
    req = Request("POST", **form)
    req.form["csrf_token"] = re.search(r'value="([^"]+)"', csrf_field(obj, req))[1]
    return req


@pytest.mark.parametrize("url", ["https://evil.example/", "//evil.example/", "/\\evil.example/", "/%5cevil.example/",
                                  "/%2fevil.example/", "javascript:alert(1)", "/ok%0d%0aLocation:evil", " /ok",
                                  "http://site.local@evil.example/", "http://site.local:81/x", ["/x"]])
def test_redirect_rejects_external_and_ambiguous_targets(url):
    assert safe_redirect(url, "http://site.local/App", "/safe") == "/safe"


@pytest.mark.parametrize("url", ["/App/page", "http://site.local/App/page", "/other-local-app?q=1"])
def test_redirect_accepts_local_targets(url):
    assert safe_redirect(url, "http://site.local/App") == url


def test_csrf_is_bound_to_browser_and_controller(monkeypatch):
    obj = SQLUserAdmin()
    req = authorized(obj)
    require_post(obj, req)
    with pytest.raises(Forbidden):
        require_post(SQLUserAdmin(), req)
    copied = Request("POST", csrf_token=req.form["csrf_token"])
    with pytest.raises(Forbidden):
        require_post(obj, copied)
    req["REQUEST_METHOD"] = "GET"
    with pytest.raises(Forbidden):
        require_post(obj, req)
    req["REQUEST_METHOD"] = "POST"
    monkeypatch.setattr("Products.SQLUserWizard.security.time.time", lambda: 9999999999)
    with pytest.raises(Forbidden):
        require_post(obj, req)


def test_protect_forms_includes_every_post_form():
    html = protect_forms(SQLUserAdmin(), Request(), '<form method="post"></form><form action="x" method="post"></form>')
    assert html.count('name="csrf_token"') == 2


def test_plone_marks_only_initial_csrf_key_write_safe(monkeypatch):
    import sys
    from types import ModuleType
    calls = []
    utils = ModuleType("plone.protect.utils")
    utils.safeWrite = calls.append
    monkeypatch.setitem(sys.modules, "plone.protect.utils", utils)
    obj = SQLUserAdmin()
    req = authorized(obj)
    assert calls == [obj]
    require_post(obj, req)
    csrf_field(obj, req)
    assert calls == [obj]
    with pytest.raises(Forbidden):
        require_post(obj, Request("POST", csrf_token="invalid"))


def test_optional_plone_authenticator_is_rendered_and_checked(monkeypatch):
    import sys
    from types import ModuleType
    import zope.component
    auth = ModuleType("plone.protect.authenticator")
    auth.createToken = lambda manager: "plone-test-token"
    def check(request, manager):
        if request.form.get("_authenticator") != "plone-test-token":
            raise Forbidden("Invalid Plone authenticator")
    auth.check = check
    auto = ModuleType("plone.protect.auto")
    auto.getRoot = lambda obj: obj
    auto.getRootKeyManager = lambda root: object()
    interfaces = ModuleType("plone.keyring.interfaces")
    interfaces.IKeyManager = object()
    for module in (auth, auto, interfaces):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(zope.component, "queryUtility", lambda interface: object())
    obj = SQLUserAdmin()
    req = authorized(obj)
    assert 'name="_authenticator"' in csrf_field(obj, req)
    with pytest.raises(Forbidden, match="Plone"):
        require_post(obj, req)
    req.form["_authenticator"] = "plone-test-token"
    require_post(obj, req)


@pytest.mark.parametrize("action", ["delete_user", "save_user", "save_role"])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_admin_rejects_unprotected_changes_before_sql(action, method):
    with pytest.raises(Forbidden):
        SQLUserAdmin().manage_main(Request(method, **{action: "1"}))


def test_valid_post_reaches_admin_mutation():
    admin = SQLUserAdmin()
    calls = []
    admin._delete_from_request = lambda request: calls.append(request["user_id"])
    admin._render = lambda *args: "done"
    admin.manage_main(authorized(admin, delete_user="1", user_id="alice"))
    assert calls == ["alice"]


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_wizard_and_direct_install_endpoint_reject_unprotected_changes(method):
    wizard = SQLUserWizard()
    with pytest.raises(Forbidden):
        wizard.manage_main(Request(method, run_wizard="1"))
    with pytest.raises(Forbidden):
        wizard.install_or_repair(REQUEST=Request(method))
    with pytest.raises(Forbidden):
        SQLUserLoginSubmit().index_html(Request(method))


@pytest.mark.parametrize("name", ["users; drop table users", "schema.users", "a'", "", "a b", "a" * 31])
def test_invalid_table_names_are_rejected(name):
    with pytest.raises(ValueError):
        validate_tables({**DEFAULT_TABLES, "users": name})


def test_duplicate_table_names_are_rejected_case_insensitively():
    with pytest.raises(ValueError):
        validate_tables({**DEFAULT_TABLES, "profiles": "PAS_USERS"})


def test_malformed_totp_secret_and_code_fail_closed():
    assert not verify_totp_code("invalid-secret!", "123456")
    assert not verify_totp_code("JBSWY3DPEHPK3PXP", "１２３４５６")


def test_product_factory_csrf_survives_new_dispatcher_on_post():
    from Acquisition import Implicit
    from OFS.Folder import Folder
    class Factory(Implicit):
        pass
    folder = Folder("target")
    req = authorized(Factory().__of__(folder))
    require_post(Factory().__of__(folder), req)
    with pytest.raises(Forbidden):
        require_post(Factory().__of__(Folder("other")), req)
