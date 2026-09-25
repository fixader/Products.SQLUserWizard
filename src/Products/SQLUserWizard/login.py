"""Password/2FA verification and restricted enrollment before session issuance."""

import hashlib
from html import escape
from urllib.parse import urlencode

from AccessControl import ClassSecurityInfo
from AccessControl.Permissions import view
from AuthEncoding import pw_validate
from OFS.SimpleItem import SimpleItem
from zExceptions import Unauthorized

from .compat import InitializeClass
from .config import (DEFAULT_LOGIN_FORM_ID, DEFAULT_LOGIN_SUBMIT_ID, DEFAULT_PAS_ID,
                     DEFAULT_PLUGIN_ID, DEFAULT_SECURE_TEST_ID, DEFAULT_COOKIE_AUTH_ID,
                     DEFAULT_FALLBACK_USER_PLUGIN_ID)
from .qrcode import qrcode_svg_data_uri
from .security import csrf_field, require_post, safe_redirect
from .sessions import fingerprint, truthy, SQLSessionHelper
from Acquisition import aq_base
from .totp import verify_totp_code, generate_totp_secret, otpauth_uri


class SQLUserLoginSubmit(SimpleItem):
    meta_type = "SQL User Login Submit"
    security = ClassSecurityInfo()
    security.declareObjectProtected(view)
    pas_id = DEFAULT_PAS_ID
    plugin_id = DEFAULT_PLUGIN_ID

    def __init__(self, id=DEFAULT_LOGIN_SUBMIT_ID):
        self.id = id

    security.declareProtected(view, "csrf_field")

    def csrf_field(self, REQUEST):
        """Render a browser-bound token for the editable login template."""
        return csrf_field(self, REQUEST)

    def _pas(self):
        return getattr(self.aq_parent, self.pas_id)

    def _session_helper(self):
        error = getattr(aq_base(self.aq_parent), "_sqluw_upgrade_error", "")
        helper = getattr(self._pas(), DEFAULT_COOKIE_AUTH_ID)
        if error or not isinstance(helper, SQLSessionHelper):
            raise Unauthorized(error or "SQLUserWizard upgrade is incomplete; use a fallback administrator to repair this folder")
        return helper

    security.declareProtected(view, "index_html")

    def index_html(self, REQUEST=None):
        """Validate a posted login, then create a revocable server session."""
        if REQUEST is None:
            return ""
        require_post(self, REQUEST)
        form = REQUEST.form
        login, password = form.get("__ac_name", ""), form.get("__ac_password", "")
        if not isinstance(login, str) or not isinstance(password, str):
            raise Unauthorized("Invalid credentials")
        came_from = safe_redirect(form.get("came_from", ""), self.aq_parent.absolute_url(),
                                  f"{self.aq_parent.absolute_url()}/{DEFAULT_SECURE_TEST_ID}")
        pas = self._pas()
        plugin = getattr(pas, self.plugin_id)
        helper = self._session_helper()
        status = "credentials"
        users = []
        if helper._allow_attempt(login):
            try:
                users = list(plugin.zsql_pas_fetch_user(login=login))
            except Exception:
                pass
            status = self._check_credentials(plugin, login, password, form.get("otp_code", ""), pas=pas, users=users)
        if status not in ("ok", "enroll"):
            query = urlencode(dict(__ac_name=login, came_from=came_from, login_error=status))
            REQUEST.RESPONSE.redirect(f"{self.aq_parent.absolute_url()}/{DEFAULT_LOGIN_FORM_ID}?{query}")
            return ""
        user = next((u for u in users if u.login_name == login), None)
        if user is not None:
            if status == "enroll" and not getattr(user, "totp_secret", ""):
                plugin.zsql_pas_update_2fa(user_id=user.user_id, totp_required="1", totp_enabled="",
                                         totp_secret=generate_totp_secret())
                user = next(u for u in plugin.zsql_pas_fetch_user(login=login) if u.user_id == user.user_id)
            helper._issue(REQUEST, user.user_id, login, fingerprint(user),
                          scope="enroll" if status == "enroll" else "full")
        else:
            fallback = getattr(pas, DEFAULT_FALLBACK_USER_PLUGIN_ID)
            result = fallback.authenticateCredentials(dict(login=login, password=password))
            if not result:
                raise Unauthorized("Invalid credentials")
            stamp = hashlib.sha256(str(fallback._user_passwords[result[0]]).encode()).hexdigest()
            helper._issue(REQUEST, result[0], result[1], stamp, kind="fallback")
        if status == "enroll":
            came_from = f"{self.absolute_url()}/enroll?{urlencode({'came_from': came_from})}"
        REQUEST.RESPONSE.redirect(came_from)
        return ""

    def _check_credentials(self, plugin, login, password, otp_code, pas=None, request=None, users=None):
        if not login or not password:
            return "credentials"
        if users is None:
            try:
                users = plugin.zsql_pas_fetch_user(login=login)
            except Exception:
                users = []
        for user in users:
            if getattr(user, "login_name", None) != login:
                continue
            if not truthy(getattr(user, "enabled", True)) or not self._password_matches(user, password):
                return "credentials"
            if truthy(getattr(user, "totp_enabled", False)):
                if not otp_code:
                    return "otp_required"
                if not verify_totp_code(getattr(user, "totp_secret", ""), otp_code):
                    return "otp"
                if pas is not None and not getattr(pas, DEFAULT_COOKIE_AUTH_ID)._consume_otp(login, otp_code):
                    return "otp"
            elif truthy(getattr(user, "totp_required", False)):
                return "enroll"
            return "ok"
        # Only the explicit fallback store may authenticate fallback logins.
        # An unrelated identity present in the request is never proof.
        fallback = getattr(pas, DEFAULT_FALLBACK_USER_PLUGIN_ID, None) if pas is not None else None
        if fallback is not None and fallback.authenticateCredentials(dict(login=login, password=password)):
            return "ok"
        return "credentials"

    def _password_matches(self, user, password):
        stored = getattr(user, "password", "")
        if (getattr(user, "password_hash_id", "") or "plain") == "plain":
            return stored == password
        try:
            return pw_validate(stored, password)
        except Exception:
            return False

    security.declareProtected(view, "enroll")

    def enroll(self, REQUEST=None):
        """Enrollment tokens authorize this page only, never a PAS principal."""
        if REQUEST is None:
            raise Unauthorized("Login is required")
        helper = self._session_helper()
        record = helper._record(REQUEST.cookies.get(helper.cookie_name, ""), scope="enroll")
        if record is None:
            raise Unauthorized("Log in again to set up your authenticator")
        plugin = getattr(self._pas(), self.plugin_id)
        user = next(u for u in plugin.zsql_pas_fetch_user(login=record["login"]) if u.user_id == record["user_id"])
        secret = user.totp_secret
        came_from = safe_redirect(REQUEST.get("came_from", ""), self.aq_parent.absolute_url(),
                                  f"{self.aq_parent.absolute_url()}/{DEFAULT_SECURE_TEST_ID}")
        message = ""
        if REQUEST.get("REQUEST_METHOD", "GET").upper() == "POST":
            require_post(self, REQUEST)
            code = REQUEST.form.get("otp_code", "")
            if (helper._allow_attempt(record["login"])
                    and verify_totp_code(secret, code)
                    and helper._consume_otp(record["login"], code)):
                plugin.zsql_pas_update_2fa(user_id=user.user_id,
                                         totp_required="1" if truthy(getattr(user, "totp_required", False)) else "",
                                         totp_enabled="1", totp_secret=secret)
                user = next(u for u in plugin.zsql_pas_fetch_user(login=record["login"]) if u.user_id == record["user_id"])
                helper._issue(REQUEST, user.user_id, user.login_name, fingerprint(user))
                REQUEST.RESPONSE.redirect(came_from)
                return ""
            message = "Authenticator code was not accepted."
        issuer = getattr(self, "totp_issuer", "Zope SQL Users")
        qr = qrcode_svg_data_uri(otpauth_uri(secret, record["login"], issuer))
        REQUEST.RESPONSE.setHeader("Content-Type", "text/html; charset=utf-8")
        REQUEST.RESPONSE.setHeader("Cache-Control", "no-store")
        return f'''<!doctype html><html><head><title>Set up authenticator</title></head>
<body><h1>Set up authenticator</h1><p>Scan the QR code and enter a code to finish logging in.</p>
<img src="{qr}" alt="Authenticator QR code"><p>{escape(message)}</p>
<form method="post">{csrf_field(self, REQUEST)}
<input type="hidden" name="came_from" value="{escape(came_from)}">
<label>Authenticator code <input name="otp_code" autocomplete="one-time-code" required></label>
<button type="submit">Activate and log in</button></form></body></html>'''

    security.declareProtected(view, "logout")

    def logout(self, REQUEST=None):
        """GET displays the wrapper form; POST revokes the current session."""
        if REQUEST is not None and REQUEST.get("REQUEST_METHOD", "GET").upper() == "POST":
            require_post(self, REQUEST)
            self._pas().resetCredentials(REQUEST, REQUEST.RESPONSE)
            REQUEST.RESPONSE.redirect(f"{self.aq_parent.absolute_url()}/{DEFAULT_LOGIN_FORM_ID}")
        return ""


InitializeClass(SQLUserLoginSubmit)
