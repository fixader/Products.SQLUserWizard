from Products.SQLUserWizard.config import (
    DEFAULT_MANIFEST_ID,
    DEFAULT_PROFILE_GET_ID,
    DEFAULT_PROFILE_FORM_ID,
    DEFAULT_PROFILE_PREVIEW_ID,
    DEFAULT_PROFILE_SAVE_ID,
    DEFAULT_LOGOUT_ID,
    DEFAULT_SECURE_TEST_ID,
    DEFAULT_TABLES,
)


def test_manifest_id_is_stable_for_idempotent_reruns():
    assert DEFAULT_MANIFEST_ID == "sql_user_wizard_manifest"


def test_profile_form_id_is_stable_for_manager_edits():
    assert DEFAULT_PROFILE_FORM_ID == "sql_user_profile_form"
    assert DEFAULT_PROFILE_PREVIEW_ID == "sql_user_profile_preview"


def test_profile_zsql_ids_are_stable_for_manager_edits():
    assert DEFAULT_PROFILE_GET_ID == "sql_user_profile_get"
    assert DEFAULT_PROFILE_SAVE_ID == "sql_user_profile_save"


def test_test_shell_ids_are_stable_for_manual_testing():
    assert DEFAULT_LOGOUT_ID == "sql_user_logout"
    assert DEFAULT_SECURE_TEST_ID == "secure_test_page"


def test_default_tables_are_explicit():
    assert DEFAULT_TABLES == {
        "users": "pas_users",
        "profiles": "pas_user_profiles",
        "roles": "pas_roles_catalog",
        "user_roles": "pas_user_roles",
    }
