from AuthEncoding import is_encrypted
from AuthEncoding import pw_encrypt
from AuthEncoding import pw_validate

from .config import DEFAULT_PASSWORD_HASH_ID


PLAIN_PASSWORD_HASH_ID = "plain"
AUTH_ENCODING_HASH_ID = "authencoding"


def encode_password(password, password_hash_id=DEFAULT_PASSWORD_HASH_ID):
    """Return a stored password value and hash id."""

    hash_id = password_hash_id or DEFAULT_PASSWORD_HASH_ID
    if hash_id == PLAIN_PASSWORD_HASH_ID:
        return password, PLAIN_PASSWORD_HASH_ID

    if hash_id != AUTH_ENCODING_HASH_ID:
        raise ValueError(f"Unsupported password hash id: {hash_id}")

    encrypted = pw_encrypt(password)
    if isinstance(encrypted, bytes):
        encrypted = encrypted.decode("ascii")
    return encrypted, AUTH_ENCODING_HASH_ID


def verify_password(stored_password, supplied_password, password_hash_id):
    """Verify plain legacy or AuthEncoding-hashed passwords."""

    hash_id = password_hash_id or PLAIN_PASSWORD_HASH_ID
    if hash_id == PLAIN_PASSWORD_HASH_ID:
        return stored_password == supplied_password
    if hash_id == AUTH_ENCODING_HASH_ID:
        return pw_validate(stored_password, supplied_password)
    return False


def is_hashed_password(stored_password):
    return bool(is_encrypted(stored_password))
