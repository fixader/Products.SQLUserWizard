from AccessControl import ClassSecurityInfo
from AuthEncoding import pw_validate
from AccessControl.Permissions import view
from OFS.SimpleItem import SimpleItem
from Products.PluggableAuthService.interfaces.plugins import IAuthenticationPlugin
from urllib.parse import urlencode

from .compat import InitializeClass
from .config import DEFAULT_LOGIN_FORM_ID
from .config import DEFAULT_FALLBACK_USER_PLUGIN_ID
from .config import DEFAULT_LOGIN_SUBMIT_ID
from .config import DEFAULT_PAS_ID
from .config import DEFAULT_PLUGIN_ID
from .config import DEFAULT_SECURE_TEST_ID
from .totp import verify_totp_code


class SQLUserLoginSubmit(SimpleItem):
    """Validate form credentials before allowing PAS to set a login cookie."""

    meta_type = "SQL User Login Submit"
    security = ClassSecurityInfo()
    security.declareObjectProtected(view)

    pas_id = DEFAULT_PAS_ID
    plugin_id = DEFAULT_PLUGIN_ID

    def __init__(self, id=DEFAULT_LOGIN_SUBMIT_ID):
        self.id = id

    security.declareProtected(view, "index_html")

    def index_html(self, REQUEST=None):
        """Handle a posted SQL User Wizard login form."""

        if REQUEST is None:
            return ""

        response = REQUEST.RESPONSE
        login = REQUEST.get("__ac_name", "")
        password = REQUEST.get("__ac_password", "")
        came_from = REQUEST.get(
            "came_from",
            f"{self.aq_parent.absolute_url()}/{DEFAULT_SECURE_TEST_ID}",
        )

        pas = getattr(self.aq_parent, self.pas_id)
        plugin = getattr(pas, self.plugin_id)
        status = self._check_credentials(
            plugin,
            login,
            password,
            REQUEST.get("otp_code", ""),
            pas=pas,
            request=REQUEST,
        )
        if status == "enroll":
            pas.updateCredentials(REQUEST, response, login, password)
            query = urlencode({"came_from": came_from})
            response.redirect(f"{self.aq_parent.absolute_url()}/{self._admin_id()}/my_2fa?{query}")
            return ""
        if status != "ok":
            query = urlencode(
                {
                    "__ac_name": login,
                    "came_from": came_from,
                    "login_error": status,
                }
            )
            response.redirect(f"{self.aq_parent.absolute_url()}/{DEFAULT_LOGIN_FORM_ID}?{query}")
            return ""

        pas.updateCredentials(REQUEST, response, login, password)
        response.redirect(came_from)
        return ""

    def _check_credentials(self, plugin, login, password, otp_code, pas=None, request=None):
        if not login or not password:
            return "credentials"

        try:
            users = plugin.zsql_pas_fetch_user(login=login)
        except Exception:
            return "credentials"

        for user in users:
            if getattr(user, "login_name", None) != login:
                continue
            if not self._password_matches(user, password):
                return "credentials"

            if self._truthy(getattr(user, "totp_enabled", False)):
                if not otp_code:
                    return "otp_required"
                if not verify_totp_code(getattr(user, "totp_secret", ""), otp_code):
                    return "otp"
            if self._truthy(getattr(user, "totp_required", False)):
                return "enroll"
            return "ok"

        if self._check_pas_fallback_credentials(pas, plugin, login, password, request):
            return "ok"

        return "credentials"

    def _check_pas_fallback_credentials(self, pas, sql_plugin, login, password, request=None):
        if pas is None:
            return False

        credentials = {"login": login, "password": password}
        if self._check_direct_pas_authentication_plugins(pas, sql_plugin, credentials):
            return True

        try:
            plugins = pas.plugins.listPlugins(IAuthenticationPlugin)
        except Exception:
            return self._check_pas_extracted_credentials(pas, request)

        sql_plugin_base = getattr(sql_plugin, "aq_base", sql_plugin)
        for _plugin_id, candidate in plugins:
            candidate_base = getattr(candidate, "aq_base", candidate)
            if candidate_base is sql_plugin_base:
                continue
            authenticate = getattr(candidate, "authenticateCredentials", None)
            if authenticate is None:
                continue
            try:
                result = authenticate(credentials)
            except Exception:
                continue
            if result:
                return True
        return self._check_pas_extracted_credentials(pas, request)

    def _check_direct_pas_authentication_plugins(self, pas, sql_plugin, credentials):
        seen = set()
        candidate_ids = [DEFAULT_FALLBACK_USER_PLUGIN_ID]
        try:
            candidate_ids.extend(pas.objectIds())
        except Exception:
            pass

        sql_plugin_base = getattr(sql_plugin, "aq_base", sql_plugin)
        for plugin_id in candidate_ids:
            if plugin_id in seen:
                continue
            seen.add(plugin_id)
            try:
                candidate = pas._getOb(plugin_id)
            except Exception:
                candidate = getattr(pas, plugin_id, None)
            if candidate is None:
                continue
            candidate_base = getattr(candidate, "aq_base", candidate)
            if candidate_base is sql_plugin_base:
                continue
            authenticate = getattr(candidate, "authenticateCredentials", None)
            if authenticate is None:
                continue
            try:
                result = authenticate(credentials)
            except Exception:
                continue
            if result:
                return True
        return False

    def _check_pas_extracted_credentials(self, pas, request):
        if request is None:
            return False
        try:
            user_ids = pas._extractUserIds(request, pas.plugins)
        except Exception:
            return False
        return bool(user_ids)

    def _password_matches(self, user, password):
        password_hash_id = getattr(user, "password_hash_id", "") or "plain"
        stored_password = getattr(user, "password", "")
        if password_hash_id == "plain":
            return stored_password == password
        try:
            return pw_validate(stored_password, password)
        except Exception:
            return False

    def _truthy(self, value):
        return str(value).lower() not in ("", "0", "false", "none")

    def _admin_id(self):
        for object_id in getattr(self.aq_parent, "objectIds", lambda: [])():
            obj = getattr(self.aq_parent, object_id, None)
            if getattr(obj, "meta_type", "") == "SQL User Admin":
                return object_id
        return "sql_user_admin"


InitializeClass(SQLUserLoginSubmit)
