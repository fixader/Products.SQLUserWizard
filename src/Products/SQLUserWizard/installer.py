import json
from datetime import datetime, timezone

from AccessControl.Permissions import view
from Acquisition import aq_base
from Acquisition import aq_parent

from .config import (
    AUTHENTICATE_SCRIPT,
    DEFAULT_ADMIN_ID,
    DEFAULT_COOKIE_AUTH_ID,
    DEFAULT_FALLBACK_LOGIN,
    DEFAULT_FALLBACK_ROLE_PLUGIN_ID,
    DEFAULT_FALLBACK_USER_PLUGIN_ID,
    DEFAULT_INFO_ID,
    DEFAULT_MANIFEST_ID,
    DEFAULT_PAS_ID,
    DEFAULT_LOGIN_FORM_ID,
    DEFAULT_LOGIN_SUBMIT_ID,
    DEFAULT_LOGOUT_ID,
    DEFAULT_PLUGIN_ID,
    DEFAULT_PROFILE_GET_ID,
    DEFAULT_PROFILE_FORM_ID,
    DEFAULT_PROFILE_PREVIEW_ID,
    DEFAULT_PROFILE_SAVE_ID,
    DEFAULT_SECURE_TEST_ID,
    DEFAULT_TABLES,
    DEFAULT_TOTP_ISSUER,
    MODE_AUTH_ONLY,
    MODE_MANAGED,
    ROLES_SCRIPT,
    auth_only_templates,
)
from .dialects import (
    managed_templates,
    profile_templates,
)
from .compat import PAS_FALLBACK_ROLE_INTERFACES
from .compat import PAS_FALLBACK_USER_INTERFACES
from .compat import PAS_COOKIE_AUTH_INTERFACES
from .compat import PAS_PLUGIN_INTERFACES
from .sqladmin import save_sql_user
from .sqladmin import seed_standard_roles


class InstallResult:
    def __init__(self):
        self.actions = []
        self.warnings = []

    def action(self, text):
        self.actions.append(text)

    def warning(self, text):
        self.warnings.append(text)


class SQLUserWizardInstaller:
    """Idempotent PAS + ZSQL installer.

    The installer only depends on Zope-visible Z SQL Methods at runtime. The
    concrete database adapter behind ``connection_id`` may be OpenODBCDA,
    SQLAlchemyDA, or any other adapter accepted by Products.ZSQLMethods.
    """

    def __init__(
        self,
        folder,
        connection_id,
        dialect="postgresql",
        pas_id=DEFAULT_PAS_ID,
        plugin_id=DEFAULT_PLUGIN_ID,
        fallback_login=DEFAULT_FALLBACK_LOGIN,
        fallback_password="",
        fallback_user_plugin_id=DEFAULT_FALLBACK_USER_PLUGIN_ID,
        fallback_role_plugin_id=DEFAULT_FALLBACK_ROLE_PLUGIN_ID,
        admin_id=DEFAULT_ADMIN_ID,
        initial_user=None,
        seed_roles=True,
        mode=MODE_MANAGED,
        tables=None,
        totp_issuer=DEFAULT_TOTP_ISSUER,
    ):
        self.folder = folder
        self.connection_id = connection_id
        self.dialect = dialect
        self.pas_id = pas_id
        self.plugin_id = plugin_id
        self.fallback_login = fallback_login
        self.fallback_password = fallback_password
        self.fallback_user_plugin_id = fallback_user_plugin_id
        self.fallback_role_plugin_id = fallback_role_plugin_id
        self.admin_id = admin_id
        self.initial_user = initial_user or {}
        self.seed_roles = seed_roles
        self.mode = mode or MODE_MANAGED
        self.tables = tables or dict(DEFAULT_TABLES)
        self.totp_issuer = totp_issuer or DEFAULT_TOTP_ISSUER
        self.result = InstallResult()

    def install(self):
        pas = self._ensure_pas()
        plugin = self._ensure_sql_plugin(pas)
        self._ensure_zsql_methods(plugin)
        if self.mode == MODE_AUTH_ONLY:
            self.result.action("Auth-only mode: skipped database schema changes")
        else:
            self._ensure_database_schema(plugin)
        self._ensure_plugin_scripts(plugin)
        self._activate_plugin_interfaces(plugin)
        try:
            self._ensure_cookie_auth_helper(pas)
        except Exception as exc:
            self.result.warning(
                f"Could not install Cookie Auth Helper {DEFAULT_COOKIE_AUTH_ID}: {exc}"
            )
        self._ensure_fallback_manager(pas)
        self._ensure_upstream_fallback_users(pas)
        self._activate_pas_registry(pas)
        if self.mode == MODE_AUTH_ONLY:
            self.result.action("Auth-only mode: skipped SQL user creation")
        else:
            if self.seed_roles:
                self._seed_standard_roles(plugin)
            else:
                self.result.action("Skipped standard Zope role seed")
            self._ensure_initial_sql_user(plugin)
            self._ensure_admin_tool()
        self._ensure_profile_zsql_methods()
        self._ensure_profile_template()
        self._ensure_profile_preview_template()
        self._ensure_login_submit()
        self._ensure_login_template()
        self._ensure_logout_template()
        self._ensure_secure_test_page()
        self._ensure_manifest(pas)
        self._ensure_info_page(pas)
        return self.result

    def _ensure_pas(self):
        local_ids = set(self.folder.objectIds())
        if self.pas_id in local_ids:
            existing = getattr(self.folder, self.pas_id, None)
        else:
            existing = None

        if existing is not None:
            if existing.meta_type == "User Folder":
                backup_id = self._backup_existing_user_folder()
                self.result.warning(
                    f"Renamed existing User Folder {self.pas_id} to {backup_id}"
                )
                existing = None
            elif existing.meta_type != "Pluggable Auth Service":
                raise ValueError(
                    f"{self.folder.absolute_url_path()}/{self.pas_id} exists "
                    f"but is {existing.meta_type!r}, not Pluggable Auth Service"
                )
            else:
                self.result.action(f"Using existing PAS {self.pas_id}")
                return existing

        product = self.folder.manage_addProduct["PluggableAuthService"]
        product.addPluggableAuthService(self.pas_id)
        self.result.action(f"Created PAS {self.pas_id}")
        return getattr(self.folder, self.pas_id)

    def _backup_existing_user_folder(self):
        base_id = f"{self.pas_id}_zodb_backup"
        backup_id = base_id
        suffix = 2
        while getattr(self.folder, backup_id, None) is not None:
            backup_id = f"{base_id}_{suffix}"
            suffix += 1

        self.folder.manage_renameObjects(ids=[self.pas_id], new_ids=[backup_id])
        return backup_id

    def _ensure_sql_plugin(self, pas):
        existing = getattr(pas, self.plugin_id, None)
        if existing is None:
            product = pas.manage_addProduct["PluggableAuthService"]
            product.addScriptablePlugin(
                self.plugin_id,
                "SQL Auth Plugin",
            )
            self.result.action(f"Created Scriptable Plugin {self.plugin_id}")
            return getattr(pas, self.plugin_id)

        self.result.action(f"Using existing Scriptable Plugin {self.plugin_id}")
        return existing

    def _ensure_zsql_methods(self, plugin):
        if self.mode == MODE_AUTH_ONLY:
            for spec in auth_only_templates(self.dialect, self.tables).values():
                if spec["id"] == DEFAULT_PROFILE_GET_ID:
                    continue
                self._upsert_zsql_method(plugin, spec)
            return

        for spec in managed_templates(self.dialect, self.tables).values():
            self._upsert_zsql_method(plugin, spec)

    def _upsert_zsql_method(self, container, spec):
        method = getattr(container, spec["id"], None)
        if method is None:
            product = container.manage_addProduct["ZSQLMethods"]
            product.manage_addZSQLMethod(
                id=spec["id"],
                title=spec["title"],
                connection_id=self.connection_id,
                arguments=spec["arguments"],
                template=spec["template"],
            )
            self.result.action(f"Created Z SQL Method {spec['id']}")
            return

        method.manage_edit(
            title=spec["title"],
            connection_id=self.connection_id,
            arguments=spec["arguments"],
            template=spec["template"],
        )
        self.result.action(f"Updated Z SQL Method {spec['id']}")

    def _ensure_database_schema(self, plugin):
        for method_id in (
            "zsql_pas_setup_users",
            "zsql_pas_setup_user_security_columns",
            "zsql_pas_setup_profiles",
            "zsql_pas_setup_roles",
            "zsql_pas_setup_user_roles",
        ):
            try:
                getattr(plugin, method_id)()
            except Exception as exc:
                if method_id == "zsql_pas_setup_user_security_columns":
                    self.result.warning(
                        f"Could not repair security columns automatically: {exc}"
                    )
                    continue
                raise
            else:
                self.result.action(f"Ran {method_id}")

    def _ensure_plugin_scripts(self, plugin):
        self._upsert_python_script(
            plugin,
            "authenticateCredentials",
            "Authenticate SQL credentials",
            "credentials",
            AUTHENTICATE_SCRIPT,
        )
        self._upsert_python_script(
            plugin,
            "getRolesForPrincipal",
            "Fetch SQL roles for principal",
            "principal, request=None",
            ROLES_SCRIPT,
        )

    def _upsert_python_script(self, container, script_id, title, params, body):
        script = getattr(container, script_id, None)
        if script is None:
            product = container.manage_addProduct["PythonScripts"]
            product.manage_addPythonScript(id=script_id)
            script = getattr(container, script_id)
            self.result.action(f"Created Python Script {script_id}")
        else:
            self.result.action(f"Updated Python Script {script_id}")

        script.ZPythonScript_edit(params=params, body=body)
        script.title = title

    def _activate_plugin_interfaces(self, plugin):
        plugin.manage_updateInterfaces(
            interfaces=[name for name, _interface in PAS_PLUGIN_INTERFACES]
        )
        self.result.action("Activated sql plugin interfaces")

    def _ensure_fallback_manager(self, pas):
        if not self.fallback_login:
            self.result.warning("No fallback manager login configured")
            return

        users = self._ensure_zodb_user_manager(pas)
        roles = self._ensure_zodb_role_manager(pas)

        if self.fallback_password:
            try:
                users.getLoginForUserId(self.fallback_login)
            except KeyError:
                users.addUser(
                    self.fallback_login,
                    self.fallback_login,
                    self.fallback_password,
                )
                self.result.action(f"Created fallback manager {self.fallback_login}")
            else:
                users.updateUserPassword(self.fallback_login, self.fallback_password)
                self.result.action(f"Updated fallback manager {self.fallback_login}")
        else:
            self.result.action(
                "No extra fallback manager password supplied; relying on synced "
                "parent-folder fallback users unless this user already exists"
            )

        try:
            roles.addRole("Manager")
        except KeyError:
            pass

        try:
            roles.assignRoleToPrincipal("Manager", self.fallback_login)
        except KeyError:
            self.result.warning("Could not assign Manager role to fallback manager")
        else:
            self.result.action(
                f"Ensured fallback manager {self.fallback_login} has Manager role"
            )

    def _ensure_upstream_fallback_users(self, pas):
        users = self._ensure_zodb_user_manager(pas)
        roles = self._ensure_zodb_role_manager(pas)
        imported = 0
        skipped = 0

        for source in self._iter_upstream_user_folders():
            for upstream_user in self._iter_source_users(source):
                user_id = upstream_user.get("user_id")
                login = upstream_user.get("login") or user_id
                password = upstream_user.get("password")
                if not user_id or not login:
                    continue
                if not password:
                    skipped += 1
                    self.result.warning(
                        f"Could not import upstream user {user_id}: stored password "
                        "hash is not readable"
                    )
                    continue

                try:
                    self._upsert_fallback_user_with_hash(
                        users,
                        user_id,
                        login,
                        password,
                    )
                    self._assign_fallback_roles(roles, user_id, upstream_user["roles"])
                except Exception as exc:
                    skipped += 1
                    self.result.warning(
                        f"Could not import upstream user {user_id}: {exc}"
                    )
                else:
                    imported += 1

        if imported:
            self.result.action(
                f"Synced {imported} upstream user(s) into local fallback users"
            )
        elif skipped:
            self.result.warning(
                "No upstream users were imported because their password hashes were "
                "not readable"
            )
        else:
            self.result.action("No upstream users found for fallback import")

    def _iter_upstream_user_folders(self):
        seen = set()
        parent = aq_parent(self.folder)
        while parent is not None:
            source = self._local_object(parent, self.pas_id)
            if source is not None and id(aq_base(source)) not in seen:
                seen.add(id(aq_base(source)))
                yield source
            parent = aq_parent(parent)

        for object_id in getattr(self.folder, "objectIds", lambda: [])():
            if not object_id.startswith(f"{self.pas_id}_zodb_backup"):
                continue
            source = self._local_object(self.folder, object_id)
            if source is not None and id(aq_base(source)) not in seen:
                seen.add(id(aq_base(source)))
                yield source

    def _local_object(self, container, object_id):
        if object_id not in getattr(container, "objectIds", lambda: [])():
            return None
        getter = getattr(container, "_getOb", None)
        if getter is not None:
            return getter(object_id)
        return getattr(container, object_id, None)

    def _iter_source_users(self, source):
        by_id = {}

        for user in self._classic_source_users(source):
            user_id = self._user_id(user)
            if user_id:
                by_id[user_id] = user

        for user_id in self._source_user_ids(source):
            if user_id not in by_id:
                user = self._source_user_by_id(source, user_id)
                if user is not None:
                    by_id[user_id] = user

        for user_id, user in by_id.items():
            roles = self._user_roles(user)
            yield {
                "user_id": user_id,
                "login": self._user_login(user, user_id),
                "password": self._stored_password(source, user, user_id),
                "roles": roles,
            }

    def _classic_source_users(self, source):
        get_users = getattr(source, "getUsers", None)
        if get_users is None:
            return []
        try:
            return list(get_users())
        except Exception:
            return []

    def _source_user_ids(self, source):
        get_user_names = getattr(source, "getUserNames", None)
        if get_user_names is not None:
            try:
                return list(get_user_names())
            except Exception:
                pass

        enumerate_users = getattr(source, "enumerateUsers", None)
        if enumerate_users is not None:
            try:
                return [
                    row["id"]
                    for row in enumerate_users()
                    if isinstance(row, dict) and row.get("id")
                ]
            except Exception:
                pass

        passwords = getattr(source, "_user_passwords", None)
        if self._is_mapping_like(passwords):
            return list(passwords.keys())

        return []

    def _source_user_by_id(self, source, user_id):
        for method_name in ("getUserById", "getUser"):
            method = getattr(source, method_name, None)
            if method is None:
                continue
            try:
                user = method(user_id)
            except Exception:
                continue
            if user is not None:
                return user
        return None

    def _user_id(self, user):
        for method_name in ("getId", "getUserId"):
            method = getattr(user, method_name, None)
            if method is None:
                continue
            try:
                value = method()
            except Exception:
                continue
            if value:
                return str(value)
        for attr_name in ("id", "name"):
            value = getattr(user, attr_name, "")
            if value:
                return str(value)
        return ""

    def _user_login(self, user, user_id):
        for method_name in ("getUserName", "getLogin"):
            method = getattr(user, method_name, None)
            if method is None:
                continue
            try:
                value = method()
            except Exception:
                continue
            if value:
                return str(value)
        return user_id

    def _user_roles(self, user):
        method = getattr(user, "getRoles", None)
        if method is None:
            return []
        try:
            values = method()
        except Exception:
            return []
        ignored = {"Anonymous", "Authenticated"}
        return [str(role) for role in values if role and role not in ignored]

    def _stored_password(self, source, user, user_id):
        for method_name in ("_getPassword", "getPassword"):
            method = getattr(user, method_name, None)
            if method is None:
                continue
            try:
                value = method()
            except Exception:
                continue
            if value:
                return self._password_text(value)

        for attr_name in ("__", "_password", "password"):
            value = getattr(user, attr_name, "")
            if value:
                return self._password_text(value)

        passwords = getattr(source, "_user_passwords", None)
        if self._is_mapping_like(passwords):
            value = passwords.get(user_id)
            if value:
                return self._password_text(value)

        data = getattr(source, "data", None)
        if self._is_mapping_like(data):
            stored_user = data.get(user_id)
            if stored_user is not None and stored_user is not user:
                return self._stored_password(source, stored_user, user_id)

        return ""

    def _password_text(self, value):
        if isinstance(value, bytes):
            return value.decode("ascii")
        return str(value)

    def _upsert_fallback_user_with_hash(self, users, user_id, login, password_hash):
        try:
            users.getLoginForUserId(user_id)
        except KeyError:
            users.addUser(user_id, login, "temporary-password-replaced-by-import")
        else:
            update_login = getattr(users, "updateUser", None)
            if update_login is not None:
                try:
                    update_login(user_id, login)
                except Exception:
                    pass

        passwords = getattr(aq_base(users), "_user_passwords", None)
        if self._is_mapping_like(passwords):
            passwords[user_id] = password_hash
            return

        raise ValueError(
            f"Fallback user manager {self.fallback_user_plugin_id} does not expose "
            "stored password hashes"
        )

    def _is_mapping_like(self, value):
        return (
            value is not None
            and hasattr(value, "get")
            and hasattr(value, "keys")
            and hasattr(value, "__setitem__")
        )

    def _assign_fallback_roles(self, roles, user_id, role_ids):
        for role_id in role_ids:
            try:
                roles.addRole(role_id)
            except KeyError:
                pass
            try:
                roles.assignRoleToPrincipal(role_id, user_id)
            except KeyError:
                self.result.warning(
                    f"Could not assign imported role {role_id} to {user_id}"
                )

    def _ensure_cookie_auth_helper(self, pas):
        existing = None
        if DEFAULT_COOKIE_AUTH_ID in pas.objectIds():
            existing = pas._getOb(DEFAULT_COOKIE_AUTH_ID)
        if existing is not None:
            self.result.action(f"Using existing Cookie Auth Helper {DEFAULT_COOKIE_AUTH_ID}")
            self._configure_cookie_auth_helper(existing)
            self._activate_cookie_auth_interfaces(existing)
            return existing

        from Products.PluggableAuthService.plugins.CookieAuthHelper import (
            addCookieAuthHelper,
        )

        addCookieAuthHelper(
            pas,
            DEFAULT_COOKIE_AUTH_ID,
            "SQL User Cookie Auth",
            cookie_name="sql_user_auth",
        )
        self.result.action(f"Created Cookie Auth Helper {DEFAULT_COOKIE_AUTH_ID}")
        helper = pas._getOb(DEFAULT_COOKIE_AUTH_ID)
        self._configure_cookie_auth_helper(helper)
        self._activate_cookie_auth_interfaces(helper)
        return helper

    def _configure_cookie_auth_helper(self, helper):
        helper.login_path = f"{self.folder.absolute_url_path()}/{DEFAULT_LOGIN_FORM_ID}"
        self.result.action(
            f"Configured {DEFAULT_COOKIE_AUTH_ID} login path to {DEFAULT_LOGIN_FORM_ID}"
        )

    def _activate_cookie_auth_interfaces(self, helper):
        if hasattr(helper, "manage_updateInterfaces"):
            helper.manage_updateInterfaces(
                interfaces=[interface.__name__ for interface in PAS_COOKIE_AUTH_INTERFACES]
            )
        elif hasattr(helper, "manage_activateInterfaces"):
            helper.manage_activateInterfaces(
                interfaces=self._registry_interface_ids(
                    helper._getPAS().plugins,
                    PAS_COOKIE_AUTH_INTERFACES,
                )
            )
        else:
            raise ValueError(
                f"{DEFAULT_COOKIE_AUTH_ID} exists but is {helper.__class__.__name__}"
            )
        self.result.action("Activated cookie auth helper interfaces")

    def _registry_interface_ids(self, registry, plugin_types):
        ids = []
        for plugin_type in plugin_types:
            info = registry._plugin_type_info.get(plugin_type)
            if info is not None:
                ids.append(info["id"])
        return ids

    def _ensure_zodb_user_manager(self, pas):
        existing = getattr(pas, self.fallback_user_plugin_id, None)
        if existing is None:
            product = pas.manage_addProduct["PluggableAuthService"]
            product.addZODBUserManager(
                self.fallback_user_plugin_id,
                "Fallback ZODB Users",
            )
            self.result.action(
                f"Created ZODB User Manager {self.fallback_user_plugin_id}"
            )
            return getattr(pas, self.fallback_user_plugin_id)

        self.result.action(
            f"Using existing ZODB User Manager {self.fallback_user_plugin_id}"
        )
        return existing

    def _ensure_zodb_role_manager(self, pas):
        existing = getattr(pas, self.fallback_role_plugin_id, None)
        if existing is None:
            product = pas.manage_addProduct["PluggableAuthService"]
            product.addZODBRoleManager(
                self.fallback_role_plugin_id,
                "Fallback ZODB Roles",
            )
            self.result.action(
                f"Created ZODB Role Manager {self.fallback_role_plugin_id}"
            )
            return getattr(pas, self.fallback_role_plugin_id)

        self.result.action(
            f"Using existing ZODB Role Manager {self.fallback_role_plugin_id}"
        )
        return existing

    def _activate_pas_registry(self, pas):
        registry = pas.plugins
        for _name, plugin_type in PAS_PLUGIN_INTERFACES:
            active = list(registry.listPluginIds(plugin_type))
            if self.plugin_id not in active:
                registry.activatePlugin(plugin_type, self.plugin_id)
                self.result.action(f"Activated {self.plugin_id} for {plugin_type}")
            self._move_plugin_first(registry, plugin_type, self.plugin_id)

        for plugin_type in PAS_FALLBACK_USER_INTERFACES:
            self._activate_if_missing(
                registry,
                plugin_type,
                self.fallback_user_plugin_id,
            )

        for plugin_type in PAS_FALLBACK_ROLE_INTERFACES:
            self._activate_if_missing(
                registry,
                plugin_type,
                self.fallback_role_plugin_id,
            )

        if DEFAULT_COOKIE_AUTH_ID in pas.objectIds():
            for plugin_type in PAS_COOKIE_AUTH_INTERFACES:
                self._activate_if_missing(registry, plugin_type, DEFAULT_COOKIE_AUTH_ID)
        else:
            self.result.warning(
                f"Cookie Auth Helper {DEFAULT_COOKIE_AUTH_ID} is not installed; "
                "form login skeleton was left editable but inactive"
            )

        for _name, plugin_type in PAS_PLUGIN_INTERFACES:
            self._move_plugin_first(registry, plugin_type, self.plugin_id)

    def _activate_if_missing(self, registry, plugin_type, plugin_id):
        try:
            active = list(registry.listPluginIds(plugin_type))
        except KeyError:
            self.result.warning(
                f"Plugin registry does not know interface {plugin_type}; "
                f"could not activate {plugin_id}"
            )
            return
        if plugin_id not in active:
            registry.activatePlugin(plugin_type, plugin_id)
            self.result.action(f"Activated {plugin_id} for {plugin_type}")

    def _ensure_initial_sql_user(self, plugin):
        user_id = self.initial_user.get("user_id", "").strip()
        if not user_id:
            return

        save_sql_user(plugin, **self.initial_user)
        self.result.action(f"Ensured initial SQL user {user_id}")

    def _seed_standard_roles(self, plugin):
        seed_standard_roles(plugin)
        self.result.action("Ensured standard Zope roles in SQL role catalog")

    def _ensure_admin_tool(self):
        existing = getattr(self.folder, self.admin_id, None)
        if existing is not None:
            self.result.action(f"Using existing SQL User Admin {self.admin_id}")
            if hasattr(existing, "totp_issuer"):
                existing.totp_issuer = self.totp_issuer
                self.result.action(f"Configured TOTP issuer {self.totp_issuer}")
            return existing

        from .admin import SQLUserAdmin

        admin = SQLUserAdmin(self.admin_id)
        admin.title = "SQL User Admin"
        admin.totp_issuer = self.totp_issuer
        self.folder._setObject(self.admin_id, admin)
        self.result.action(f"Created SQL User Admin {self.admin_id}")
        self.result.action(f"Configured TOTP issuer {self.totp_issuer}")
        return getattr(self.folder, self.admin_id)

    def _ensure_profile_template(self):
        return self._ensure_managed_dtml_method(
            object_id=DEFAULT_PROFILE_FORM_ID,
            title="SQL User Profile Form",
            text=self._default_profile_template(),
            marker="SQLUSERWIZARD-MANAGED-PROFILE-FORM",
            legacy_markers=[
                "Editable profile field template used by sql_user_admin",
            ],
            action_name="editable profile template",
        )

    def _ensure_profile_preview_template(self):
        return self._ensure_managed_dtml_method(
            object_id=DEFAULT_PROFILE_PREVIEW_ID,
            title="SQL User Profile Form Preview",
            text=self._default_profile_preview_template(),
            marker="SQLUSERWIZARD-MANAGED-PROFILE-PREVIEW",
            legacy_markers=[
                "SQL User Profile Form Preview",
                "Profile Form Preview",
            ],
            action_name="editable profile preview",
        )

    def _ensure_login_template(self):
        return self._ensure_managed_dtml_method(
            object_id=DEFAULT_LOGIN_FORM_ID,
            title="SQL User Login Form",
            text=self._default_login_template(),
            marker="SQLUSERWIZARD-MANAGED-LOGIN",
            legacy_markers=[
                "Editable form-login skeleton",
                "Editable form-login page",
            ],
            action_name="editable login template",
        )

    def _ensure_logout_template(self):
        return self._ensure_managed_dtml_method(
            object_id=DEFAULT_LOGOUT_ID,
            title="SQL User Logout",
            text=self._default_logout_template(),
            marker="SQLUSERWIZARD-MANAGED-LOGOUT",
            legacy_markers=[
                "Editable logout wrapper",
            ],
            action_name="editable logout page",
            view_roles=["Anonymous"],
            view_acquire=1,
        )

    def _ensure_secure_test_page(self):
        return self._ensure_managed_dtml_method(
            object_id=DEFAULT_SECURE_TEST_ID,
            title="SQL User Secure Test Page",
            text=self._default_secure_test_template(),
            marker="SQLUSERWIZARD-MANAGED-SECURE-TEST",
            legacy_markers=[
                "SQL User Secure Test Page",
                "Secure Test Page",
            ],
            action_name="secure test page",
            view_roles=["Authenticated"],
            view_acquire=0,
        )

    def _ensure_login_submit(self):
        existing = getattr(self.folder, DEFAULT_LOGIN_SUBMIT_ID, None)
        if existing is None:
            from .login import SQLUserLoginSubmit

            submit = SQLUserLoginSubmit(DEFAULT_LOGIN_SUBMIT_ID)
            submit.title = "SQL User Login Submit"
            self.folder._setObject(DEFAULT_LOGIN_SUBMIT_ID, submit)
            existing = getattr(self.folder, DEFAULT_LOGIN_SUBMIT_ID)
            self.result.action(f"Created login submit controller {DEFAULT_LOGIN_SUBMIT_ID}")
        else:
            self.result.action(f"Using existing login submit controller {DEFAULT_LOGIN_SUBMIT_ID}")

        if hasattr(existing, "pas_id"):
            existing.pas_id = self.pas_id
        if hasattr(existing, "plugin_id"):
            existing.plugin_id = self.plugin_id
        self._configure_view_permission(existing, ["Anonymous"], 1)
        return existing

    def _ensure_managed_dtml_method(
        self,
        object_id,
        title,
        text,
        marker,
        legacy_markers=(),
        action_name="editable object",
        view_roles=None,
        view_acquire=None,
    ):
        existing = getattr(self.folder, object_id, None)
        if existing is None:
            self.folder.manage_addProduct["OFSP"].manage_addDTMLMethod(
                id=object_id,
                title=title,
                file=text,
            )
            obj = getattr(self.folder, object_id)
            self._configure_view_permission(obj, view_roles, view_acquire)
            self.result.action(f"Created {action_name} {object_id}")
            return obj

        source = self._object_source(existing)
        if marker in source or any(legacy in source for legacy in legacy_markers):
            existing.manage_edit(data=text, title=title)
            self._configure_view_permission(existing, view_roles, view_acquire)
            self.result.action(f"Updated managed {action_name} {object_id}")
            return existing

        self.result.action(f"Using existing {action_name} {object_id}")
        self.result.warning(f"{object_id} looks customized; not overwritten")
        return existing

    def _configure_view_permission(self, obj, roles, acquire):
        if roles is not None and acquire is not None:
            obj.manage_permission(view, roles=roles, acquire=acquire)

    def _ensure_profile_zsql_methods(self):
        if self.mode == MODE_AUTH_ONLY:
            spec = auth_only_templates(self.dialect, self.tables)["get_profile"]
            existing = getattr(self.folder, spec["id"], None)
            if existing is not None:
                self.result.action(f"Using existing auth-only Z SQL Method {spec['id']}")
                return
            self._upsert_zsql_method(self.folder, spec)
            self.result.action(f"Created auth-only profile Z SQL Method {spec['id']}")
            return

        for spec in profile_templates(self.dialect, self.tables).values():
            existing = getattr(self.folder, spec["id"], None)
            if existing is not None:
                self.result.action(f"Using existing editable Z SQL Method {spec['id']}")
                continue
            self._upsert_zsql_method(self.folder, spec)
            self.result.action(f"Created editable profile Z SQL Method {spec['id']}")

    def _default_profile_template(self):
        return """<dtml-comment>
SQLUSERWIZARD-MANAGED-PROFILE-FORM
Editable profile field template used by sql_user_admin and sql_user_admin/my_profile.

This template deliberately renders fields only, not the surrounding form tag.
The product currently saves these field names:
first_name, last_name, display_name, email, mobile.

Managers can change labels, layout, help text, and remove fields here. Adding
new saved fields such as avatar requires adding storage and save handling too.
</dtml-comment>
<fieldset>
  <legend>Profile</legend>
  <div class="split">
    <label>First name
      <input name="first_name" value="<dtml-var first_name html_quote>">
    </label>
    <label>Last name
      <input name="last_name" value="<dtml-var last_name html_quote>">
    </label>
  </div>
  <label>Display name
    <input name="display_name" value="<dtml-var display_name html_quote>">
  </label>
  <label>Email
    <input name="email" value="<dtml-var email html_quote>">
  </label>
  <label>Mobile
    <input name="mobile" value="<dtml-var mobile html_quote>">
  </label>
</fieldset>
"""

    def _default_profile_preview_template(self):
        return f"""<html>
<head>
  <dtml-comment>SQLUSERWIZARD-MANAGED-PROFILE-PREVIEW</dtml-comment>
  <title>SQL User Profile Form Preview</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1.5rem; max-width: 760px; }}
    .note {{ color: #555; background: #f6f7f9; border-left: 4px solid #9aa6b2; padding: .75rem 1rem; }}
    label {{ display: block; margin: .65rem 0; font-weight: 600; }}
    input {{ box-sizing: border-box; width: min(36rem, 100%); padding: .4rem; }}
    fieldset {{ border: 1px solid #c8ced8; margin: 1rem 0; padding: 1rem; }}
  </style>
</head>
<body>
  <h1>Profile Form Preview</h1>
  <p class="note"><code>{DEFAULT_PROFILE_FORM_ID}</code> is a partial profile
  form, not a complete page. Keep it as fields only, so it can be embedded by
  both manager tools such as <code>{self.admin_id}</code> and user-facing pages
  such as <code>{self.admin_id}/my_profile</code>.</p>
  <dtml-let user_id="'preview_user'"
            first_name="REQUEST.get('first_name', '')"
            last_name="REQUEST.get('last_name', '')"
            display_name="REQUEST.get('display_name', '')"
            email="REQUEST.get('email', '')"
            mobile="REQUEST.get('mobile', '')">
    <dtml-var {DEFAULT_PROFILE_FORM_ID}>
  </dtml-let>
</body>
</html>
"""

    def _default_login_template(self):
        profile_link = ""
        if self.mode != MODE_AUTH_ONLY:
            profile_link = f'<a href="{self.admin_id}/my_profile">My profile</a>'
        return f"""<dtml-comment>
SQLUSERWIZARD-MANAGED-LOGIN
Editable form-login page. It posts to the SQL User Wizard login controller,
which validates password and optional TOTP before PAS receives credentials.
</dtml-comment>
<dtml-let came_from="REQUEST.get('came_from', '{self.folder.absolute_url_path()}/{DEFAULT_SECURE_TEST_ID}')">
<!doctype html>
<html>
<head>
  <title>SQL User Login</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{ font-family: system-ui, sans-serif; margin: 0; color: #172033; background: #eef2f6; }}
    main {{ min-height: 100vh; display: grid; grid-template-columns: minmax(0, 1fr); place-items: center; padding: 2rem; box-sizing: border-box; }}
    .login-shell {{ width: min(58rem, 100%); display: grid; grid-template-columns: minmax(0, .95fr) minmax(22rem, .8fr); background: #fff; border: 1px solid #d5dbe3; box-shadow: 0 18px 46px rgba(20, 34, 52, .12); }}
    .intro {{ background: #203447; color: #fff; padding: 2rem; display: flex; flex-direction: column; justify-content: space-between; gap: 2rem; }}
    .intro h1 {{ margin: 0 0 .75rem; font-size: 1.75rem; font-weight: 750; }}
    .intro p {{ margin: 0; color: #dbe5ee; line-height: 1.55; }}
    .status-list {{ display: grid; gap: .55rem; margin: 0; padding: 0; list-style: none; }}
    .status-list li {{ display: flex; align-items: center; gap: .5rem; color: #edf4fa; }}
    .dot {{ width: .55rem; height: .55rem; border-radius: 50%; background: #7ec5a6; flex: 0 0 auto; }}
    .login-panel {{ padding: 2rem; }}
    h2 {{ margin: 0 0 .35rem; font-size: 1.35rem; }}
    p {{ color: #596579; line-height: 1.45; }}
    label {{ display: block; margin: .95rem 0 .35rem; font-weight: 650; }}
    input {{ box-sizing: border-box; width: 100%; padding: .65rem .7rem; border: 1px solid #b8c2cf; font: inherit; background: #fff; }}
    input:focus {{ outline: 2px solid #6797c6; outline-offset: 1px; }}
    button {{ margin-top: 1rem; width: 100%; padding: .75rem .8rem; border: 0; background: #20663f; color: #fff; font: inherit; font-weight: 750; cursor: pointer; }}
    button:hover {{ background: #185532; }}
    nav {{ margin-top: 1rem; display: flex; gap: .8rem; flex-wrap: wrap; font-size: .95rem; }}
    a {{ color: #1f5f8b; }}
    .notice {{ border-left: 4px solid #d29528; background: #fff7e8; padding: .7rem .8rem; color: #513a12; }}
    .muted {{ color: #6b7585; font-size: .92rem; }}
    @media (max-width: 760px) {{
      main {{ padding: 1rem; place-items: stretch; }}
      .login-shell {{ grid-template-columns: 1fr; }}
      .intro, .login-panel {{ padding: 1.35rem; }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="login-shell">
      <div class="intro">
        <div>
          <h1>SQL User Access</h1>
          <p>This folder uses local PAS authentication backed by SQL users,
          with synced parent-folder users available as fallback access.</p>
        </div>
        <ul class="status-list">
          <li><span class="dot"></span>SQL users first</li>
          <li><span class="dot"></span>Parent-folder fallback active</li>
          <li><span class="dot"></span>Profile editing available after login</li>
        </ul>
      </div>
      <div class="login-panel">
        <h2>Log in</h2>
        <p>Use your username, password, and authenticator code when two-factor
        login is enabled for your user.</p>
        <dtml-if expr="REQUEST.get('login_error') == 'credentials'">
          <p class="notice">Login was not accepted. Check the username and password, then try again.</p>
        </dtml-if>
        <dtml-if expr="REQUEST.get('login_error') == 'otp_required'">
          <p class="notice">Authenticator code is required for this user.</p>
        </dtml-if>
        <dtml-if expr="REQUEST.get('login_error') == 'otp'">
          <p class="notice">Authenticator code was not accepted. Check the current code and try again.</p>
        </dtml-if>
        <form method="post" action="{DEFAULT_LOGIN_SUBMIT_ID}">
          <label for="__ac_name">Login</label>
          <input id="__ac_name" name="__ac_name" value="<dtml-var "REQUEST.get('__ac_name', '')" html_quote>" autocomplete="username" autofocus>

          <label for="__ac_password">Password</label>
          <input id="__ac_password" name="__ac_password" type="password" autocomplete="current-password">

          <label for="otp_code">Authenticator code</label>
          <input id="otp_code" name="otp_code" inputmode="numeric" autocomplete="one-time-code" value="">

          <input type="hidden" name="came_from" value="<dtml-var came_from html_quote>">
          <button type="submit">Log in</button>
        </form>
        <nav>
          {profile_link}
          <a href="{DEFAULT_LOGOUT_ID}">Log out</a>
        </nav>
        <p class="muted">ZMI recovery can also use Basic Auth.</p>
      </div>
    </section>
  </main>
</body>
</html>
</dtml-let>
"""

    def _default_logout_template(self):
        return f"""<dtml-comment>
SQLUSERWIZARD-MANAGED-LOGOUT
Editable logout wrapper. It clears PAS credentials and returns to the login form.
</dtml-comment>
<dtml-call "acl_users.resetCredentials(REQUEST, RESPONSE)">
<dtml-call "RESPONSE.redirect('{DEFAULT_LOGIN_FORM_ID}')">
"""

    def _default_secure_test_template(self):
        profile_link = ""
        separator = ""
        if self.mode != MODE_AUTH_ONLY:
            profile_link = (
                f'<a href="{self.admin_id}/my_profile?came_from='
                '<dtml-var "REQUEST.URL0" url_quote>">Edit my profile</a>'
            )
            separator = " | "
        return f"""<html>
<head>
  <dtml-comment>SQLUSERWIZARD-MANAGED-SECURE-TEST</dtml-comment>
  <title>SQL User Secure Test Page</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1.5rem; max-width: 820px; }}
    table {{ border-collapse: collapse; margin: 1rem 0; width: 100%; }}
    th, td {{ border: 1px solid #c8ced8; padding: .45rem .6rem; text-align: left; }}
    th {{ width: 14rem; background: #f6f7f9; }}
    code {{ background: #f6f7f9; padding: .1rem .25rem; }}
  </style>
</head>
<body>
  <h1>Secure Test Page</h1>
  <p>This page requires an authenticated user. Use it to test SQL/PAS login,
  cookie auth, roles, and the profile lookup without opening the ZMI user admin.</p>
  <table>
    <tr><th>User id</th><td><dtml-var "AUTHENTICATED_USER.getId()" html_quote></td></tr>
    <tr><th>User name</th><td><dtml-var "AUTHENTICATED_USER.getUserName()" html_quote></td></tr>
    <tr><th>Roles</th><td><dtml-var "AUTHENTICATED_USER.getRoles()" html_quote></td></tr>
  </table>
  <h2>Profile Row</h2>
  <dtml-in "sql_user_profile_get(user_id=AUTHENTICATED_USER.getId())" size="1">
    <table>
      <tr><th>Display name</th><td><dtml-var display_name html_quote></td></tr>
      <tr><th>First name</th><td><dtml-var first_name html_quote></td></tr>
      <tr><th>Last name</th><td><dtml-var last_name html_quote></td></tr>
      <tr><th>Email</th><td><dtml-var email html_quote></td></tr>
      <tr><th>Mobile</th><td><dtml-var mobile html_quote></td></tr>
    </table>
  <dtml-else>
    <p>No profile row was found for this user.</p>
  </dtml-in>
  <p>
    {profile_link}{separator}
    <a href="{DEFAULT_LOGOUT_ID}">Log out</a>
  </p>
</body>
</html>
"""

    def _move_plugin_first(self, registry, plugin_type, plugin_id):
        active = list(registry.listPluginIds(plugin_type))
        while active and active[0] != plugin_id:
            registry.movePluginsUp(plugin_type, [plugin_id])
            new_active = list(registry.listPluginIds(plugin_type))
            if new_active == active:
                break
            active = new_active
        self.result.action(f"Prioritized {plugin_id} for {plugin_type}")

    def _ensure_manifest(self, pas):
        if self.mode == MODE_AUTH_ONLY:
            profile_methods = [DEFAULT_PROFILE_GET_ID]
            zsql_methods = [
                spec["id"]
                for key, spec in auth_only_templates(self.dialect, self.tables).items()
                if key != "get_profile"
            ]
            admin_path = None
        else:
            profile_methods = [
                spec["id"] for spec in profile_templates(self.dialect, self.tables).values()
            ]
            zsql_methods = [
                spec["id"] for spec in managed_templates(self.dialect, self.tables).values()
            ]
            admin_path = f"{self.folder.absolute_url_path()}/{self.admin_id}"

        manifest = {
            "product": "Products.SQLUserWizard",
            "version": "0.1.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "mode": self.mode,
            "folder_path": self.folder.absolute_url_path(),
            "pas_path": pas.absolute_url_path(),
            "connection_id": self.connection_id,
            "sql_dialect": self.dialect,
            "totp_issuer": self.totp_issuer,
            "plugin_id": self.plugin_id,
            "admin_path": admin_path,
            "profile_template_path": (
                f"{self.folder.absolute_url_path()}/{DEFAULT_PROFILE_FORM_ID}"
            ),
            "profile_preview_path": (
                f"{self.folder.absolute_url_path()}/{DEFAULT_PROFILE_PREVIEW_ID}"
            ),
            "login_template_path": (
                f"{self.folder.absolute_url_path()}/{DEFAULT_LOGIN_FORM_ID}"
            ),
            "login_submit_path": (
                f"{self.folder.absolute_url_path()}/{DEFAULT_LOGIN_SUBMIT_ID}"
            ),
            "logout_path": f"{self.folder.absolute_url_path()}/{DEFAULT_LOGOUT_ID}",
            "secure_test_path": (
                f"{self.folder.absolute_url_path()}/{DEFAULT_SECURE_TEST_ID}"
            ),
            "profile_zsql_methods": profile_methods,
            "fallback": {
                "login": self.fallback_login,
                "user_plugin_id": self.fallback_user_plugin_id,
                "role_plugin_id": self.fallback_role_plugin_id,
                "role": "Manager",
                "imports_readable_upstream_users": True,
            },
            "tables": self.tables,
            "zsql_methods": zsql_methods,
            "runtime_note": (
                "Authentication works without the wizard object after setup. "
                "This manifest is for repair, diagnosis, and humans."
            ),
        }
        self._upsert_text_object(
            pas,
            DEFAULT_MANIFEST_ID,
            "SQL User Wizard Manifest",
            json.dumps(manifest, indent=2, sort_keys=True),
            content_type="application/json",
        )
        self.result.action("Updated manifest")

    def _ensure_info_page(self, pas):
        if self.mode == MODE_AUTH_ONLY:
            admin_row = "<tr><th>User admin</th><td>Disabled in auth-only mode</td></tr>"
            profile_save_row = (
                "<tr><th>Editable profile save SQL</th>"
                "<td>Disabled in auth-only mode</td></tr>"
            )
            profile_check = ""
            data_model_note = (
                f"<p>Auth-only mode reads existing <code>{self.tables['users']}</code> "
                f"and <code>{self.tables['roles']}</code> tables. It does not create, "
                "alter, delete, or update database rows.</p>"
            )
            maintenance_note = (
                "<p>User maintenance is disabled in auth-only mode. Manage users in "
                "the source application/database, not from this folder.</p>"
            )
            profile_form_section = f"""
<h2>Profile Display</h2>
<p><code>{DEFAULT_PROFILE_FORM_ID}</code> remains a manager-editable DTML Method
so the secure test page can display non-security profile values from the
existing database. In auth-only mode it is display-oriented: the wizard does
not install profile save SQL or a local user self-service editor.</p>
<p><code>{DEFAULT_PROFILE_PREVIEW_ID}</code> is a wrapper page for viewing the
profile partial in ZMI with empty/demo values.</p>
<p><code>{DEFAULT_PROFILE_GET_ID}</code> is the read-only Z SQL Method used for
profile lookup. Keep application-specific profile maintenance in the source
application/database until this folder is deliberately switched to a managed
mode.</p>
"""
        else:
            admin_row = (
                f"<tr><th>User admin</th><td>{self.folder.absolute_url_path()}/"
                f"{self.admin_id}</td></tr>"
            )
            profile_save_row = (
                f"<tr><th>Editable profile save SQL</th><td>"
                f"{self.folder.absolute_url_path()}/{DEFAULT_PROFILE_SAVE_ID}</td></tr>"
            )
            profile_check = (
                f'  <li>Open <a href="{self.folder.absolute_url_path()}/'
                f'{self.admin_id}/my_profile"><code>{self.admin_id}/my_profile'
                "</code></a> and edit the current user's profile.</li>"
            )
            data_model_note = (
                f"<p><code>{self.tables['users']}</code> stores security-critical "
                f"identity fields. <code>{self.tables['profiles']}</code> stores "
                f"editable profile fields. <code>{self.tables['roles']}</code> stores "
                f"the role catalog, and <code>{self.tables['user_roles']}</code> stores "
                "user-role assignments.</p>"
            )
            maintenance_note = (
                f'<p>Use <a href="{self.folder.absolute_url_path()}/{self.admin_id}">'
                f"<code>{self.admin_id}</code></a> to add users, change passwords, "
                "assign roles, disable users, and edit profile fields. SQL developers "
                "may also use the generated Z SQL Methods directly.</p>"
            )
            profile_form_section = f"""
<h2>Editable Profile Form</h2>
<p>Generated editable DTML objects with <code>SQLUSERWIZARD-MANAGED-*</code>
markers may be refreshed by wizard repair. Remove the marker, or make a clear
custom change outside the managed template, when the application should take
ownership of that object. Customized objects are preserved and reported as
warnings during repair.</p>
<p><code>{DEFAULT_PROFILE_FORM_ID}</code> is a manager-editable DTML Method in
the application folder. It is used both inside the manager user admin screen
and by <code>{self.admin_id}/my_profile</code>. It renders profile fields only,
not the surrounding form tag. The product currently saves
<code>first_name</code>, <code>last_name</code>, <code>display_name</code>,
<code>email</code>, and <code>mobile</code>.</p>
<p><code>{DEFAULT_PROFILE_PREVIEW_ID}</code> is a wrapper page for viewing the
profile partial in ZMI with empty/demo values. Edit the partial for reusable
fields; edit or replace the wrapper only when you want a different preview or
example page.</p>
<p><code>{DEFAULT_PROFILE_GET_ID}</code> and
<code>{DEFAULT_PROFILE_SAVE_ID}</code> are editable Z SQL Methods for the
profile layer. Extend those methods and <code>{DEFAULT_PROFILE_FORM_ID}</code>
when the application needs more profile fields. Do not change the security
tables unless you are changing authentication behavior deliberately.</p>
"""

        html = f"""<!doctype html>
<html>
<head>
  <title>SQL User Wizard Status</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1.5rem; color: #172033; max-width: 980px; }}
    h1 {{ margin-bottom: .25rem; }}
    h2 {{ margin-top: 1.6rem; border-bottom: 1px solid #d8dee8; padding-bottom: .25rem; }}
    table {{ border-collapse: collapse; width: 100%; margin: .8rem 0; }}
    th, td {{ border: 1px solid #d8dee8; padding: .45rem .6rem; text-align: left; vertical-align: top; }}
    th {{ width: 15rem; background: #f6f7f9; }}
    code {{ background: #f6f7f9; padding: .1rem .25rem; }}
    .note {{ background: #f6f7f9; border-left: 4px solid #7f8fa3; padding: .75rem 1rem; }}
    li {{ margin: .3rem 0; }}
  </style>
</head>
<body>
<h1>SQL User Wizard Status</h1>
<p class="note">This folder is configured with a local Pluggable Auth Service.
Re-running the wizard repairs generated security objects and does not delete
user data.</p>
<h2>Manual Test Checklist</h2>
<ol>
  <li>Open <a href="{self.folder.absolute_url_path()}/{DEFAULT_LOGIN_FORM_ID}"><code>{DEFAULT_LOGIN_FORM_ID}</code></a> and log in with a SQL user.</li>
  <li>Open <a href="{self.folder.absolute_url_path()}/{DEFAULT_SECURE_TEST_ID}"><code>{DEFAULT_SECURE_TEST_ID}</code></a> and verify user id, roles, and profile values.</li>
{profile_check}
  <li>Use <a href="{self.folder.absolute_url_path()}/{DEFAULT_LOGOUT_ID}"><code>{DEFAULT_LOGOUT_ID}</code></a>, then confirm the secure test page redirects to login.</li>
  <li>Verify a synced parent-folder user can still reach ZMI if SQL auth is broken.</li>
</ol>
<h2>Runtime Objects</h2>
<table>
<tr><th>PAS</th><td>{pas.absolute_url_path()}</td></tr>
<tr><th>Mode</th><td>{self.mode}</td></tr>
<tr><th>SQL plugin</th><td>{self.plugin_id}</td></tr>
{admin_row}
<tr><th>Login template</th><td>{self.folder.absolute_url_path()}/{DEFAULT_LOGIN_FORM_ID}</td></tr>
<tr><th>Login submit controller</th><td>{self.folder.absolute_url_path()}/{DEFAULT_LOGIN_SUBMIT_ID}</td></tr>
<tr><th>Logout page</th><td>{self.folder.absolute_url_path()}/{DEFAULT_LOGOUT_ID}</td></tr>
<tr><th>Secure test page</th><td>{self.folder.absolute_url_path()}/{DEFAULT_SECURE_TEST_ID}</td></tr>
<tr><th>Editable profile template</th><td>{self.folder.absolute_url_path()}/{DEFAULT_PROFILE_FORM_ID}</td></tr>
<tr><th>Editable profile preview</th><td>{self.folder.absolute_url_path()}/{DEFAULT_PROFILE_PREVIEW_ID}</td></tr>
<tr><th>Editable profile fetch SQL</th><td>{self.folder.absolute_url_path()}/{DEFAULT_PROFILE_GET_ID}</td></tr>
{profile_save_row}
<tr><th>Connection id</th><td>{self.connection_id}</td></tr>
<tr><th>Dialect</th><td>{self.dialect}</td></tr>
<tr><th>Users table</th><td>{self.tables["users"]}</td></tr>
<tr><th>Profiles table</th><td>{self.tables["profiles"]}</td></tr>
<tr><th>Roles catalog table</th><td>{self.tables["roles"]}</td></tr>
<tr><th>User roles table</th><td>{self.tables["user_roles"]}</td></tr>
<tr><th>Fallback manager</th><td>{self.fallback_login}</td></tr>
</table>
<h2>Authentication Flow</h2>
<p>Credentials are checked by <code>{self.plugin_id}/authenticateCredentials</code>.
Roles are loaded by <code>{self.plugin_id}/getRolesForPrincipal</code>.</p>
<p><code>{DEFAULT_COOKIE_AUTH_ID}</code> is installed as a Cookie Auth Helper,
and points PAS challenges to <code>{DEFAULT_LOGIN_FORM_ID}</code>.
<code>{DEFAULT_LOGOUT_ID}</code> clears PAS credentials and returns to the
login form. Basic Auth remains available while the form flow is matured for
2FA.</p>
<p><code>{DEFAULT_SECURE_TEST_ID}</code> is an authenticated diagnostic page
for checking the current user, roles, profile lookup, cookie login, and logout.</p>
<h2>Data Model</h2>
{data_model_note}
<h2>Fallback Access</h2>
<p><code>{self.fallback_user_plugin_id}</code> and
<code>{self.fallback_role_plugin_id}</code> are local ZODB fallback plugins.
They are activated after the SQL plugin, so SQL authentication wins when a
matching SQL user exists, while synced parent-folder users still work in the
same folder.</p>
<p>During install/repair the wizard also scans parent folders for local
<code>{self.pas_id}</code> objects. Users whose stored password hash can be
read are copied into <code>{self.fallback_user_plugin_id}</code> with their
local roles in <code>{self.fallback_role_plugin_id}</code>. If a parent user
folder cannot expose password hashes, the wizard leaves a warning instead of
creating a broken user.</p>
<p>The fallback manager field is optional. Use it only when this installation
wants one extra local recovery account in addition to synced parent-folder
users.</p>
<h2>User Maintenance</h2>
{maintenance_note}
{profile_form_section}
<h2>Important</h2>
<p>Do not delete <code>{self.pas_id}</code> unless you mean to remove local
authentication for this folder. Re-running the wizard repairs missing pieces
and updates generated methods, but it does not delete user data.</p>
</body>
</html>
"""
        self._upsert_text_object(
            pas,
            DEFAULT_INFO_ID,
            "SQL User Wizard Info",
            html,
            content_type="text/html",
        )
        self.result.action("Updated manager info page")

    def _upsert_text_object(self, container, object_id, title, text, content_type):
        obj = getattr(container, object_id, None)
        if obj is None:
            container.manage_addProduct["OFSP"].manage_addDTMLMethod(
                id=object_id,
                title=title,
                file=text,
            )
            obj = getattr(container, object_id)
        else:
            obj.manage_edit(data=text, title=title)

        if hasattr(obj, "content_type"):
            obj.content_type = content_type

    def _object_source(self, obj):
        for name in ("raw", "_text"):
            value = getattr(obj, name, None)
            if isinstance(value, str):
                return value
            if callable(value):
                try:
                    result = value()
                except TypeError:
                    continue
                if isinstance(result, str):
                    return result

        for name in ("document_src", "manage_FTPget"):
            method = getattr(obj, name, None)
            if callable(method):
                try:
                    result = method()
                except TypeError:
                    continue
                if isinstance(result, str):
                    return result
        return ""
