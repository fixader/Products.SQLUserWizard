"""Opaque, revocable browser sessions; passwords never go into cookies."""

import hashlib
import json
import secrets
import time

from AccessControl import ClassSecurityInfo
from Acquisition import aq_parent
from BTrees.OOBTree import OOBTree
from Products.PluggableAuthService.plugins.CookieAuthHelper import CookieAuthHelper

from .compat import InitializeClass
from .config import DEFAULT_COOKIE_AUTH_ID, DEFAULT_PLUGIN_ID, DEFAULT_FALLBACK_USER_PLUGIN_ID


def truthy(value):
    return str(value).lower() not in ("", "0", "false", "none")


def fingerprint(user):
    fields = ("user_id", "login_name", "password", "password_hash_id", "enabled",
              "totp_required", "totp_enabled", "totp_secret")
    return hashlib.sha256(json.dumps([str(getattr(user, field, "")) for field in fields]).encode()).hexdigest()


class SQLSessionHelper(CookieAuthHelper):
    """Retain PAS challenge/reset interfaces, replacing credential cookies."""

    security = ClassSecurityInfo()
    sql_plugin_id = DEFAULT_PLUGIN_ID
    fallback_plugin_id = DEFAULT_FALLBACK_USER_PLUGIN_ID
    cookie_name = "sql_user_session"
    session_seconds = 8 * 3600

    def __init__(self, id):
        super().__init__(id, "SQL User Sessions", cookie_name=self.cookie_name)
        self._sessions = OOBTree()
        self._attempts = OOBTree()
        self._used_codes = OOBTree()

    def _allow_attempt(self, login):
        now = time.time()
        key = hashlib.sha256(str(login).encode()).hexdigest()
        for old, (until, count) in list(self._attempts.items()):
            if until <= now:
                del self._attempts[old]
        until, count = self._attempts.get(key, (now + 300, 0))
        if count >= 10 or len(self._attempts) >= 10000 and key not in self._attempts:
            return False
        self._attempts[key] = (until, count + 1)
        return True

    def _consume_otp(self, login, code):
        now = time.time()
        clean_code = "".join(str(code).split())
        key = hashlib.sha256(f"{login}:{clean_code}".encode()).hexdigest()
        for old, until in list(self._used_codes.items()):
            if until <= now:
                del self._used_codes[old]
        if key in self._used_codes:
            return False
        self._used_codes[key] = now + 120
        return True

    def _path(self):
        return aq_parent(aq_parent(self)).absolute_url_path() or "/"

    def _issue(self, request, user_id, login, stamp, kind="sql", scope="full"):
        now = time.time()
        for token, record in list(self._sessions.items()):
            if record["expires"] <= now:
                del self._sessions[token]
        self._revoke(request)
        if len(self._sessions) >= 10000:
            raise ValueError("Session capacity reached")
        token = secrets.token_urlsafe(32)
        self._sessions[token] = dict(user_id=user_id, login=login, stamp=stamp,
                                     kind=kind, scope=scope,
                                     expires=now + (600 if scope == "enroll" else self.session_seconds))
        request.RESPONSE.setCookie(self.cookie_name, token, path=self._path(),
                                   http_only=True, secure=request.get("URL", "").startswith("https:"), same_site="Lax")
        request.RESPONSE.setHeader("Cache-Control", "no-store")
        return token

    def _revoke(self, request):
        token = getattr(request, "cookies", {}).get(self.cookie_name, "")
        if isinstance(token, str) and token in self._sessions:
            del self._sessions[token]

    def _record(self, token, scope="full"):
        if not isinstance(token, str):
            return None
        record = self._sessions.get(token)
        if not record or record["expires"] <= time.time() or record["scope"] != scope:
            return None
        pas = aq_parent(self)
        if record["kind"] == "sql":
            try:
                rows = getattr(pas, self.sql_plugin_id).zsql_pas_fetch_user(login=record["login"])
                user = next((u for u in rows if u.user_id == record["user_id"]), None)
                if user is None or not truthy(getattr(user, "enabled", True)) or fingerprint(user) != record["stamp"]:
                    return None
                if scope == "full" and truthy(getattr(user, "totp_required", False)) and not truthy(getattr(user, "totp_enabled", False)):
                    return None
            except Exception:
                return None
        else:
            fallback = getattr(pas, self.fallback_plugin_id, None)
            current = getattr(fallback, "_user_passwords", {}).get(record["user_id"])
            if current is None or hashlib.sha256(str(current).encode()).hexdigest() != record["stamp"]:
                return None
            if getattr(fallback, "_login_to_userid", {}).get(record["login"]) != record["user_id"]:
                return None
        return record

    @security.private
    def extractCredentials(self, request):
        token = getattr(request, "cookies", {}).get(self.cookie_name, "")
        record = self._record(token)
        return {"sqluw_session": token, "login": record["login"]} if record else {}

    @security.private
    def updateCredentials(self, request, response, login, password):
        # Only the login controller may create a session, after password/2FA.
        return None

    @security.private
    def resetCredentials(self, request, response):
        self._revoke(request)
        response.expireCookie(self.cookie_name, path=self._path())
        response.expireCookie("sql_user_auth", path="/")


InitializeClass(SQLSessionHelper)


def authenticate_session(plugin, credentials):
    helper = getattr(aq_parent(plugin), DEFAULT_COOKIE_AUTH_ID, None)
    if not isinstance(helper, SQLSessionHelper):
        return None
    record = helper._record(credentials.get("sqluw_session"))
    return (record["user_id"], record["login"]) if record else None
