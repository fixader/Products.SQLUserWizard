from types import SimpleNamespace
from urllib.parse import quote_plus

from Products.SQLUserWizard.config import DEFAULT_PAS_ID
from Products.SQLUserWizard.config import DEFAULT_PLUGIN_ID
from Products.SQLUserWizard.login import SQLUserLoginSubmit
from Products.SQLUserWizard.totp import totp_code


class FakePlugin:
    def __init__(self, user):
        self.user = user

    def zsql_pas_fetch_user(self, login):
        if self.user is None:
            return []
        return [self.user]


def test_login_submit_reports_missing_otp_after_password_is_valid():
    helper = SQLUserLoginSubmit()
    plugin = FakePlugin(
        SimpleNamespace(
            login_name="alice",
            password="secret",
            password_hash_id="plain",
            totp_enabled=True,
            totp_secret="JBSWY3DPEHPK3PXP",
        )
    )

    assert helper._check_credentials(plugin, "alice", "secret", "") == "otp_required"


def test_login_submit_reports_wrong_otp_after_password_is_valid():
    helper = SQLUserLoginSubmit()
    plugin = FakePlugin(
        SimpleNamespace(
            login_name="alice",
            password="secret",
            password_hash_id="plain",
            totp_enabled=True,
            totp_secret="JBSWY3DPEHPK3PXP",
        )
    )

    assert helper._check_credentials(plugin, "alice", "secret", "000000") == "otp"


def test_login_submit_accepts_valid_otp():
    helper = SQLUserLoginSubmit()
    secret = "JBSWY3DPEHPK3PXP"
    plugin = FakePlugin(
        SimpleNamespace(
            login_name="alice",
            password="secret",
            password_hash_id="plain",
            totp_enabled=True,
            totp_secret=secret,
        )
    )

    assert helper._check_credentials(plugin, "alice", "secret", totp_code(secret)) == "ok"


def test_login_submit_redirects_to_enrollment_when_required():
    helper = SQLUserLoginSubmit()
    plugin = FakePlugin(
        SimpleNamespace(
            login_name="alice",
            password="secret",
            password_hash_id="plain",
            totp_required=True,
            totp_enabled=False,
            totp_secret="JBSWY3DPEHPK3PXP",
        )
    )

    assert helper._check_credentials(plugin, "alice", "secret", "") == "enroll"


def test_login_submit_keeps_bad_password_generic():
    helper = SQLUserLoginSubmit()
    plugin = FakePlugin(
        SimpleNamespace(
            login_name="alice",
            password="secret",
            password_hash_id="plain",
            totp_enabled=True,
            totp_secret="JBSWY3DPEHPK3PXP",
        )
    )

    assert helper._check_credentials(plugin, "alice", "wrong", "000000") == "credentials"


def test_login_submit_accepts_pas_fallback_authentication():
    class FallbackPlugin:
        def authenticateCredentials(self, credentials):
            if credentials == {"login": "admin", "password": "admin"}:
                return ("admin", "admin")
            return None

    class PluginRegistry:
        def listPlugins(self, interface):
            return [
                ("sql_auth", sql_plugin),
                ("zodb_fallback_users", fallback_plugin),
            ]

    class FakePas:
        plugins = PluginRegistry()

    helper = SQLUserLoginSubmit()
    sql_plugin = FakePlugin(None)
    fallback_plugin = FallbackPlugin()

    assert (
        helper._check_credentials(
            sql_plugin,
            "admin",
            "admin",
            "",
            pas=FakePas(),
        )
        == "ok"
    )


def test_login_submit_carries_came_from_to_enrollment_page():
    class FakeRequest(dict):
        def __getattr__(self, name):
            return self[name]

    class FakeResponse:
        location = ""

        def redirect(self, location):
            self.location = location

    class FakePas:
        def __init__(self, plugin):
            setattr(self, DEFAULT_PLUGIN_ID, plugin)

        def updateCredentials(self, REQUEST, response, login, password):
            self.credentials = (login, password)

    class FakeFolder:
        def __init__(self, plugin):
            setattr(self, DEFAULT_PAS_ID, FakePas(plugin))
            self.sql_user_admin = SimpleNamespace(meta_type="SQL User Admin")

        def absolute_url(self):
            return "http://zope.local/App"

        def objectIds(self):
            return ["sql_user_admin"]

    helper = SQLUserLoginSubmit()
    plugin = FakePlugin(
        SimpleNamespace(
            login_name="alice",
            password="secret",
            password_hash_id="plain",
            totp_required=True,
            totp_enabled=False,
            totp_secret="JBSWY3DPEHPK3PXP",
        )
    )
    helper.aq_parent = FakeFolder(plugin)
    came_from = "http://zope.local/App/private_page"
    response = FakeResponse()
    request = FakeRequest({
        "RESPONSE": response,
        "__ac_name": "alice",
        "__ac_password": "secret",
        "came_from": came_from,
    })

    helper.index_html(request)

    assert response.location == (
        "http://zope.local/App/sql_user_admin/my_2fa"
        f"?came_from={quote_plus(came_from)}"
    )
