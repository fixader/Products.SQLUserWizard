"""Compatibility helpers for supported Zope generations."""

try:
    from AccessControl.class_init import InitializeClass
except ImportError:  # pragma: no cover - older Zope fallback
    from App.class_init import InitializeClass

from Products.PluggableAuthService.interfaces.plugins import IAuthenticationPlugin
from Products.PluggableAuthService.interfaces.plugins import IChallengePlugin
from Products.PluggableAuthService.interfaces.plugins import ICredentialsResetPlugin
from Products.PluggableAuthService.interfaces.plugins import ICredentialsUpdatePlugin
from Products.PluggableAuthService.interfaces.plugins import IExtractionPlugin
from Products.PluggableAuthService.interfaces.plugins import IRoleAssignerPlugin
from Products.PluggableAuthService.interfaces.plugins import IRoleEnumerationPlugin
from Products.PluggableAuthService.interfaces.plugins import IRolesPlugin
from Products.PluggableAuthService.interfaces.plugins import IUserAdderPlugin
from Products.PluggableAuthService.interfaces.plugins import IUserEnumerationPlugin


PAS_PLUGIN_INTERFACES = (
    ("IAuthenticationPlugin", IAuthenticationPlugin),
    ("IUserEnumerationPlugin", IUserEnumerationPlugin),
    ("IRolesPlugin", IRolesPlugin),
)

PAS_FALLBACK_USER_INTERFACES = (
    IUserAdderPlugin,
    IAuthenticationPlugin,
    IUserEnumerationPlugin,
)

PAS_FALLBACK_ROLE_INTERFACES = (
    IRolesPlugin,
    IRoleEnumerationPlugin,
    IRoleAssignerPlugin,
)

PAS_COOKIE_AUTH_INTERFACES = (
    IExtractionPlugin,
    IChallengePlugin,
    ICredentialsUpdatePlugin,
    ICredentialsResetPlugin,
)


def zmi_workspace(method):
    """Expose the same callable under old/new ZMI workspace names."""

    return method
