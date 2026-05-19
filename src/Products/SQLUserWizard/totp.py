import base64
import hashlib
import hmac
import os
import struct
import time
from urllib.parse import quote


DEFAULT_TOTP_ISSUER = "Zope SQL Users"


def generate_totp_secret(length=20):
    """Return a base32 TOTP secret without padding."""

    return base64.b32encode(os.urandom(length)).decode("ascii").rstrip("=")


def normalize_totp_secret(secret):
    return "".join(str(secret or "").upper().split())


def totp_code(secret, for_time=None, period=30, digits=6):
    """Return the TOTP code for ``secret`` at ``for_time``."""

    clean_secret = normalize_totp_secret(secret)
    if not clean_secret:
        return ""

    padding = "=" * ((8 - len(clean_secret) % 8) % 8)
    key = base64.b32decode(clean_secret + padding, casefold=True)
    counter = int((time.time() if for_time is None else for_time) // period)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**digits)).zfill(digits)


def verify_totp_code(secret, code, for_time=None, period=30, digits=6, window=1):
    """Accept a current TOTP code, allowing one step of clock drift by default."""

    clean_code = "".join(str(code or "").split())
    if not clean_code:
        return False

    now = time.time() if for_time is None else for_time
    for offset in range(-window, window + 1):
        expected = totp_code(secret, now + (offset * period), period, digits)
        if hmac.compare_digest(expected, clean_code):
            return True
    return False


def otpauth_uri(secret, account_name, issuer=DEFAULT_TOTP_ISSUER):
    """Return an Authenticator-compatible otpauth URI."""

    clean_secret = normalize_totp_secret(secret)
    clean_issuer = issuer or DEFAULT_TOTP_ISSUER
    label = f"{clean_issuer}:{account_name}"
    return (
        "otpauth://totp/"
        + quote(label)
        + "?secret="
        + quote(clean_secret)
        + "&issuer="
        + quote(clean_issuer)
        + "&algorithm=SHA1&digits=6&period=30"
    )
