from Products.SQLUserWizard.config import DEFAULT_MIGRATION_SQL_ID
from Products.SQLUserWizard.config import MODE_AUTH_ONLY
from Products.SQLUserWizard.installer import SQLUserWizardInstaller


class FakeUser:
    def __init__(self, password):
        self.password = password

    def _getPassword(self):
        return self.password


def test_stored_password_decodes_classic_user_folder_byte_hashes():
    installer = SQLUserWizardInstaller(folder=None, connection_id="db")

    value = installer._stored_password(
        source=object(),
        user=FakeUser(b"{SSHA}abcdef"),
        user_id="admin",
    )

    assert value == "{SSHA}abcdef"
    assert not value.startswith("b'")


def test_stored_password_decodes_zodb_user_manager_byte_hashes():
    class Source:
        _user_passwords = {"admin": b"{SHA}abcdef"}

    installer = SQLUserWizardInstaller(folder=None, connection_id="db")

    value = installer._stored_password(
        source=Source(),
        user=object(),
        user_id="admin",
    )

    assert value == "{SHA}abcdef"
    assert not value.startswith("b'")


def test_auth_only_installer_creates_migration_zsql_method():
    installer = SQLUserWizardInstaller(
        folder=None,
        connection_id="db",
        dialect="existing_oracle",
        mode=MODE_AUTH_ONLY,
    )
    specs = []
    installer._upsert_zsql_method = lambda container, spec: specs.append(spec)

    installer._ensure_zsql_methods(plugin=object())

    ids = [spec["id"] for spec in specs]
    assert DEFAULT_MIGRATION_SQL_ID in ids
