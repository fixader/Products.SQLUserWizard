"""Upgrade generated runtime objects without touching SQL data or schema."""

import json
import logging
import os
import re

import transaction
from AccessControl import getSecurityManager
from AccessControl.SecurityManagement import newSecurityManager, setSecurityManager
from AccessControl.users import system
from Acquisition import aq_base

from .config import (DEFAULT_MANIFEST_ID, DEFAULT_PAS_ID, DEFAULT_LOGIN_FORM_ID,
                     DEFAULT_PROFILE_GET_ID, DEFAULT_PROFILE_SAVE_ID)
from .installer import SQLUserWizardInstaller
from .schema import validate_tables
from .compat import PAS_PLUGIN_INTERFACES
from Products.PluggableAuthService.interfaces.plugins import IAuthenticationPlugin


logger = logging.getLogger("Products.SQLUserWizard.upgrade")
RUNTIME_REVISION = 2


def upgrade_folder(folder):
    """Return True when a recorded managed installation was upgraded.

    Completed old migrations are already managed installations. Their exact
    table mapping is authoritative; defaults never rename their tables.
    """
    reader = SQLUserWizardInstaller(folder, "unused")
    pas = reader._local_object(folder, DEFAULT_PAS_ID)
    if pas is None:
        return False
    manifest = reader._local_object(pas, DEFAULT_MANIFEST_ID)
    if manifest is None:
        return False
    data = json.loads(reader._object_source(manifest))
    if data.get("product") != "Products.SQLUserWizard":
        return False
    if "mode" not in data:
        # Early releases did not record ownership mode. Do not infer it from
        # current class defaults, or silently leave old authentication active.
        raise ValueError("Legacy manifest has no mode; review schema and SQL capabilities before upgrade")
    if data.get("mode") != "managed":
        return False
    if data.get("runtime_revision", 0) >= RUNTIME_REVISION:
        return False
    validate_tables(data["tables"])
    installer = SQLUserWizardInstaller(
        folder, data["connection_id"], dialect=data["sql_dialect"],
        tables=data["tables"], plugin_id=data.get("plugin_id", "sql_auth"),
        fallback_login=data.get("fallback", {}).get("login", "pas_fallback_manager"),
        fallback_user_plugin_id=data.get("fallback", {}).get("user_plugin_id", "zodb_fallback_users"),
        fallback_role_plugin_id=data.get("fallback", {}).get("role_plugin_id", "zodb_fallback_roles"),
        admin_id=(data.get("admin_path") or "/sql_user_admin").rsplit("/", 1)[-1],
        totp_issuer=data.get("totp_issuer", "Zope SQL Users"),
    )
    plugin = installer._local_object(pas, installer.plugin_id)
    if plugin is None:
        raise ValueError("Recorded SQL authentication plugin is missing")
    required = ("fetch_user", "fetch_roles", "get_user", "list_users", "list_roles",
                "upsert_user", "update_user", "update_password", "update_2fa",
                "upsert_profile", "upsert_role", "assign_role", "clear_roles",
                "delete_profile", "delete_user")
    missing = ["zsql_pas_" + name for name in required
               if installer._local_object(plugin, "zsql_pas_" + name) is None]
    if missing:
        raise ValueError("Legacy SQL methods need review before upgrade: " + ", ".join(missing))
    # All calls below edit ZODB objects only. Never install(), schema setup,
    # initial-user creation, role seeding or inherited-user synchronization.
    installer._bind_pas_to_folder(pas)
    _protect_existing_sql(installer, plugin)
    installer._ensure_plugin_scripts(plugin)
    installer._activate_plugin_interfaces(plugin)
    for _name, interface in PAS_PLUGIN_INTERFACES:
        installer._activate_if_missing(pas.plugins, interface, installer.plugin_id)
    installer._ensure_cookie_auth_helper(pas)
    installer._ensure_login_submit()
    installer._ensure_admin_tool()
    installer._ensure_login_template()
    installer._ensure_logout_template()
    installer._ensure_secure_test_page()
    _patch_custom_login_form(installer)
    _restore_saved_defaults(folder, data)
    installer._ensure_manifest(pas)
    installer._ensure_info_page(pas)
    if "_sqluw_upgrade_error" in aq_base(folder).__dict__:
        del folder._sqluw_upgrade_error
    logger.info("Upgraded SQLUserWizard runtime at %s without changing SQL data", folder.absolute_url_path())
    return True


def _protect_existing_sql(installer, plugin):
    # Runtime upgrade must preserve the actual database contract. Old schemas
    # and locally adapted SQL can differ from today's templates or manifest.
    for method in plugin.objectValues():
        if getattr(method, "meta_type", "") == "Z SQL Method":
            method.manage_permission("Use Database Methods", roles=(), acquire=0)
    for object_id in (DEFAULT_PROFILE_GET_ID, DEFAULT_PROFILE_SAVE_ID):
        method = installer._local_object(installer.folder, object_id)
        if method is not None:
            method.manage_permission("Use Database Methods", roles=(), acquire=0)
    for old_id in ("zsql_pas_classic_acl_users_migration", "zsql_pas_classic_migration_tables"):
        if old_id in plugin.objectIds():
            plugin._delObject(old_id)


def _patch_custom_login_form(installer):
    template = installer._local_object(installer.folder, DEFAULT_LOGIN_FORM_ID)
    source = installer._object_source(template)
    if "csrf_field(" in source:
        return
    # Preserve ordinary customized DTML login forms and their styling.
    patched, count = re.subn(
        r'(<form\b[^>]*\bmethod=["\']post["\'][^>]*>)',
        lambda match: match[0] + '\n<dtml-var expr="sql_user_login_submit.csrf_field(REQUEST)">',
        source, flags=re.I,
    )
    if count:
        template.manage_edit(data=patched, title=template.title)
    else:
        raise ValueError("Customized login template has no recognizable POST form; review before upgrade")


def _restore_saved_defaults(folder, data):
    from .wizard import SQLUserWizard
    mapping = dict(connection_id=data["connection_id"], dialect=data["sql_dialect"], mode="managed")
    mapping.update({key + "_table": value for key, value in data["tables"].items()})
    for obj in folder.objectValues():
        if isinstance(obj, SQLUserWizard):
            for name, value in mapping.items():
                if name not in aq_base(obj).__dict__:
                    setattr(obj, name, value)


def upgrade_database(event):
    """Run after Zope product initialization, before requests are served."""
    connection = event.database.open()
    previous = getSecurityManager()
    newSecurityManager(None, system)
    try:
        root = connection.root().get("Application")
        if root is None:
            return
        upgrade_tree(root)
        transaction.commit()
    except Exception:
        transaction.abort()
        logger.exception("SQLUserWizard upgrade transaction failed; SQL data was not modified")
    finally:
        setSecurityManager(previous)
        transaction.abort()
        connection.close()


def upgrade_tree(root):
    """Isolate each installation so one broken folder cannot stop Zope."""
    configured = os.environ.get("SQLUSERWIZARD_UPGRADE_PATHS")
    selected = None if configured is None else {p.strip().rstrip("/") or "/" for p in configured.split(",") if p.strip()}
    stack, seen = [root], set()
    while stack:
        folder = stack.pop()
        base = aq_base(folder)
        oid = getattr(base, "_p_oid", None)
        identity = (id(getattr(base, "_p_jar", None)), oid) if oid else id(base)
        if identity in seen:
            continue
        seen.add(identity)
        if not hasattr(base, "objectValues"):
            continue
        path = "/" + "/".join(folder.getPhysicalPath()).strip("/")
        if selected is None or path in selected:
            checkpoint = transaction.savepoint(optimistic=True)
            try:
                upgrade_folder(folder)
            except Exception:
                checkpoint.rollback()
                logger.exception("SQLUserWizard upgrade needs attention at %s", folder.absolute_url_path())
                _block_failed_sql_auth(folder)
        try:
            stack.extend(child for child in folder.objectValues()
                         if hasattr(aq_base(child), "objectValues"))
        except Exception:
            logger.exception("Could not inspect children at %s", folder.absolute_url_path())


def _block_failed_sql_auth(folder):
    folder._sqluw_upgrade_error = (
        "SQLUserWizard upgrade needs attention. SQL login is disabled in this folder. "
        "Use a ZODB fallback administrator and review the server log before repair."
    )
    reader = SQLUserWizardInstaller(folder, "unused")
    pas = reader._local_object(folder, DEFAULT_PAS_ID)
    if pas is not None:
        for plugin_id in list(pas.plugins.listPluginIds(IAuthenticationPlugin)):
            plugin = reader._local_object(pas, plugin_id)
            if plugin is not None and "zsql_pas_fetch_user" in getattr(plugin, "objectIds", lambda: [])():
                pas.plugins.deactivatePlugin(IAuthenticationPlugin, plugin_id)
