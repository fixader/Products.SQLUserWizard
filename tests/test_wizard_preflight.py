from Products.SQLUserWizard.config import MODE_AUTH_ONLY
from Products.SQLUserWizard.wizard import SQLUserWizard


def test_wizard_preflight_warns_about_application_named_managed_tables():
    wizard = SQLUserWizard()
    wizard.users_table = "valisy_users"
    wizard.roles_table = "valisy_roles"

    html = wizard._render_preflight()

    assert "Existing names" in html
    assert "username" in html
    assert "password_hash_id" in html
    assert "role_id" in html
    assert "security fields" in html
    assert "profile fields" in html
    assert "application-only data" in html


def test_wizard_preflight_documents_auth_only_as_read_only():
    wizard = SQLUserWizard()
    wizard.mode = MODE_AUTH_ONLY
    wizard.dialect = "existing_postgresql"

    html = wizard._render_preflight()

    assert "Auth-only" in html
    assert "Managed later" in html
    assert "No writes" in html
    assert "must not create" in html


def test_wizard_auth_only_summarizes_classic_acl_users_migration():
    wizard = SQLUserWizard()
    wizard.mode = MODE_AUTH_ONLY
    wizard.dialect = "existing_oracle"
    wizard.users_table = "users"
    wizard.user_roles_table = "roles"

    html = wizard._render_preflight()

    assert "Classic acl_users Migration" in html
    assert "users.username" in html
    assert "roles.role" in html
    assert "username</code> to its internal" in html
    assert "pas_users_migrated" in html
    assert "pas_user_roles_migrated" in html
    assert "substr(password, 1, 1)" in html
    assert "Prepare wizard for managed takeover" in html
    assert "dialect" in html
    assert "oracle11g" in html


def test_wizard_prepare_managed_migration_updates_fields_without_installing():
    wizard = SQLUserWizard()
    wizard.mode = MODE_AUTH_ONLY
    wizard.dialect = "existing_oracle"
    wizard.users_table = "users"
    wizard.user_roles_table = "roles"

    wizard._prepare_managed_migration()

    assert wizard.mode == "managed"
    assert wizard.dialect == "oracle11g"
    assert wizard.users_table == "pas_users_migrated"
    assert wizard.user_roles_table == "pas_user_roles_migrated"


def test_wizard_preflight_catches_duplicate_table_names():
    wizard = SQLUserWizard()
    wizard.users_table = "pas_users"
    wizard.profiles_table = "pas_users"

    html = wizard._render_preflight()

    assert "Stop First" in html
    assert "Use distinct tables" in html


def test_wizard_screen_links_back_to_zmi_context():
    wizard = SQLUserWizard()

    html = wizard._render_form("")

    assert "Back to containing folder" in html
    assert 'href="../manage_workspace"' in html
    assert 'href="/manage_workspace"' in html
