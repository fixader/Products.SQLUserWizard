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


def test_login_submit_accepts_explicit_fallback_store():
    fallback = SimpleNamespace(authenticateCredentials=lambda credentials: ("admin", "admin") if credentials == {"login": "admin", "password": "admin"} else None)
    pas = SimpleNamespace(zodb_fallback_users=fallback)
    helper = SQLUserLoginSubmit()
    assert helper._check_credentials(FakePlugin(None), "admin", "admin", "", pas=pas) == "ok"
    assert helper._check_credentials(FakePlugin(None), "admin", "wrong", "", pas=pas) == "credentials"


def test_unrelated_request_identity_does_not_prove_password():
    pas = SimpleNamespace(_extractUserIds=lambda *args: [("admin", "admin")])
    assert SQLUserLoginSubmit()._check_credentials(FakePlugin(None), "admin", "wrong", "", pas=pas, request={}) == "credentials"
