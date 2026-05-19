from Products.SQLUserWizard.password import encode_password
from Products.SQLUserWizard.password import is_hashed_password
from Products.SQLUserWizard.password import verify_password


def test_encode_password_hashes_by_default():
    stored_password, hash_id = encode_password("secret")

    assert hash_id == "authencoding"
    assert stored_password != "secret"
    assert is_hashed_password(stored_password)
    assert verify_password(stored_password, "secret", hash_id)
    assert not verify_password(stored_password, "wrong", hash_id)


def test_plain_passwords_are_supported_for_legacy_users():
    stored_password, hash_id = encode_password("secret", "plain")

    assert stored_password == "secret"
    assert hash_id == "plain"
    assert verify_password(stored_password, "secret", hash_id)
    assert not verify_password(stored_password, "wrong", hash_id)
