from Products.SQLUserWizard.compat import PAS_PLUGIN_INTERFACES
from Products.SQLUserWizard.config import ENUMERATE_USERS_SCRIPT
from Products.SQLUserWizard.installer import SQLUserWizardInstaller


def test_sql_plugin_declares_user_enumeration_interface():
    interface_names = [name for name, _interface in PAS_PLUGIN_INTERFACES]

    assert interface_names == [
        "IAuthenticationPlugin",
        "IUserEnumerationPlugin",
        "IRolesPlugin",
    ]


def test_installer_creates_enumerate_users_script():
    class FakePlugin:
        def __init__(self):
            self.scripts = {}

        def manage_updateInterfaces(self, interfaces):
            self.interfaces = interfaces

    plugin = FakePlugin()
    installer = SQLUserWizardInstaller(object(), "db")

    def capture_script(container, script_id, title, params, body):
        container.scripts[script_id] = {
            "title": title,
            "params": params,
            "body": body,
        }

    installer._upsert_python_script = capture_script

    installer._ensure_plugin_scripts(plugin)
    installer._activate_plugin_interfaces(plugin)

    assert plugin.scripts["enumerateUsers"] == {
        "title": "Enumerate SQL users for PAS",
        "params": (
            "id=None, login=None, exact_match=0, sort_by=None, "
            "max_results=None, **kw"
        ),
        "body": ENUMERATE_USERS_SCRIPT,
    }
    assert "IUserEnumerationPlugin" in plugin.interfaces
