from Products.SQLUserWizard.totp import normalize_totp_secret
from Products.SQLUserWizard.totp import otpauth_uri
from Products.SQLUserWizard.totp import totp_code
from Products.SQLUserWizard.totp import verify_totp_code


def test_totp_matches_rfc6238_sha1_vector():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

    assert totp_code(secret, for_time=59, digits=8) == "94287082"


def test_totp_verify_accepts_current_code():
    secret = "JBSWY3DPEHPK3PXP"
    code = totp_code(secret, for_time=1_700_000_000)

    assert verify_totp_code(secret, code, for_time=1_700_000_000)
    assert not verify_totp_code(secret, "000000", for_time=1_700_000_000)


def test_otpauth_uri_uses_configured_issuer():
    uri = otpauth_uri("jbsw y3dp ehpk 3pxp", "codex", "SQL_User_Wizard")

    assert "SQL_User_Wizard%3Acodex" in uri
    assert "issuer=SQL_User_Wizard" in uri
    assert "secret=JBSWY3DPEHPK3PXP" in uri


def test_normalize_totp_secret_removes_spaces_and_uppercases():
    assert normalize_totp_secret("jbsw y3dp") == "JBSWY3DP"
