"""Browser request checks shared by the wizard, login and user administration."""

import hashlib
import hmac
import re
import secrets
import time
from html import escape
from urllib.parse import unquote, urlsplit

from AccessControl import getSecurityManager
from Acquisition import aq_base, aq_parent
from Persistence import Persistent
from zExceptions import Forbidden


def safe_redirect(url, base_url, default=""):
    if not isinstance(url, str) or not url:
        return default
    decoded = unquote(url)
    if any(ord(c) < 32 or ord(c) == 127 for c in decoded) or "\\" in decoded:
        return default
    if decoded.startswith("//") or url != url.strip():
        return default
    try:
        target, base = urlsplit(url), urlsplit(base_url)
        if target.username or target.password:
            return default
        if target.scheme or target.netloc:
            if (target.scheme, target.hostname, target.port) != (base.scheme, base.hostname, base.port):
                return default
        elif not url.startswith("/"):
            return default
    except ValueError:
        return default
    return url


def _key(obj):
    # ZMI product constructors receive an ephemeral factory dispatcher. Bind
    # their token to its persistent folder, shared by the GET and POST factory.
    while not isinstance(aq_base(obj), Persistent):
        parent = aq_parent(obj)
        if parent is None:
            raise ValueError("A persistent CSRF owner is required")
        obj = parent
    key = getattr(aq_base(obj), "_csrf_key", None)
    if key is None:
        obj._csrf_key = key = secrets.token_bytes(32)
        # Plone can abort writes made while rendering a GET form. Persist only
        # this controller's initial CSRF key so the following POST can validate
        # it. Plone's own form authenticator remains enabled and required.
        try:
            from plone.protect.utils import safeWrite
        except ImportError:
            pass
        else:
            safeWrite(obj)
    return key


def _cookie_name(obj):
    # A unique cookie per controller also prevents sibling applications from
    # accidentally sharing CSRF state.
    return "sqluw_csrf_" + hashlib.sha256(_key(obj)).hexdigest()[:16]


def _signature(obj, nonce, timestamp):
    user_id = getSecurityManager().getUser().getId() or "anonymous"
    body = f"{nonce}:{timestamp}:{user_id}".encode()
    return hmac.new(_key(obj), body, hashlib.sha256).hexdigest()


def _plone_authenticator(obj, request, verify=False):
    """Honor optional Plone protection before writes, not at response time."""
    try:
        from plone.protect.authenticator import check, createToken
        from plone.protect.auto import getRoot, getRootKeyManager
        from plone.keyring.interfaces import IKeyManager
        from zope.component import queryUtility
    except ImportError:
        return ""
    manager = queryUtility(IKeyManager)
    if manager is None:
        manager = getRootKeyManager(getRoot(obj))
    if manager is None:
        return ""
    if verify:
        check(request, manager=manager)
        return ""
    return '<input type="hidden" name="_authenticator" value="%s">' % escape(createToken(manager=manager))


def csrf_field(obj, request):
    if request is None:
        return ""
    name = _cookie_name(obj)
    nonce = getattr(request, "cookies", {}).get(name, "")
    if not isinstance(nonce, str) or not re.fullmatch(r"[a-f0-9]{64}", nonce):
        nonce = secrets.token_hex(32)
        request.RESPONSE.setCookie(name, nonce, path="/", http_only=True,
                                   secure=request.get("URL", "").startswith("https:"), same_site="Strict")
        # Rendering several forms in one request must issue the same nonce.
        request.cookies[name] = nonce
    timestamp = str(int(time.time()))
    token = timestamp + "." + _signature(obj, nonce, timestamp)
    request.RESPONSE.setHeader("Cache-Control", "no-store")
    return (f'<input type="hidden" name="csrf_token" value="{escape(token)}">'
            + _plone_authenticator(obj, request))


def require_post(obj, request):
    if request.get("REQUEST_METHOD", "GET").upper() != "POST":
        raise Forbidden("This action requires POST")
    token = getattr(request, "form", {}).get("csrf_token", "")
    nonce = getattr(request, "cookies", {}).get(_cookie_name(obj), "")
    try:
        timestamp, signature = token.split(".", 1)
        age = time.time() - int(timestamp)
        valid = nonce and 0 <= age <= 3600 and hmac.compare_digest(signature, _signature(obj, nonce, timestamp))
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise Forbidden("Invalid or expired form token; reload the form")
    _plone_authenticator(obj, request, verify=True)


def protect_forms(obj, request, html):
    if request is None:
        return html
    field = csrf_field(obj, request)
    return re.sub(r'(<form\b[^>]*\bmethod=["\']post["\'][^>]*>)',
                  lambda match: match[0] + field, html, flags=re.I)
