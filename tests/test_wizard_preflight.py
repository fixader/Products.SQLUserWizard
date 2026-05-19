from Products.SQLUserWizard.config import MODE_AUTH_ONLY
from Products.SQLUserWizard.wizard import SQLUserWizard


def test_wizard_preflight_warns_about_application_named_managed_tables():
    wizard = SQLUserWizard()
    wizard.users_table = "valisy_users"
    wizard.roles_table = "valisy_roles"

    html = wizard._render_preflight()

    assert "Existing names" in html
    assert "security fields" in html
    assert "profile fields" in html
    assert "application-only data" in html


def test_wizard_preflight_documents_auth_only_as_read_only():
    wizard = SQLUserWizard()
    wizard.mode = MODE_AUTH_ONLY
    wizard.dialect = "existing_postgresql"

    html = wizard._render_preflight()

    assert "Auth-only" in html
    assert "No writes" in html
    assert "must not create" in html


def test_wizard_preflight_catches_duplicate_table_names():
    wizard = SQLUserWizard()
    wizard.users_table = "pas_users"
    wizard.profiles_table = "pas_users"

    html = wizard._render_preflight()

    assert "Stop First" in html
    assert "Use distinct tables" in html
