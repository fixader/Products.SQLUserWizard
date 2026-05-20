from Products.SQLUserWizard.config import (
    DEFAULT_COOKIE_AUTH_ID,
    DEFAULT_MIGRATION_SQL_ID,
    DEFAULT_TABLES,
    auth_only_templates,
    classic_acl_users_migration_template,
    profile_postgresql_templates,
    postgresql_templates,
)
from Products.SQLUserWizard.dialects import (
    managed_templates,
    normalize_managed_dialect,
    profile_templates,
)


def test_postgresql_templates_use_configured_table_names():
    templates = postgresql_templates(
        {
            "users": "custom_users",
            "profiles": "custom_profiles",
            "roles": "custom_roles",
            "user_roles": "custom_user_roles",
        }
    )

    assert "create table if not exists custom_users" in templates["setup_users"]["template"]
    assert "create table if not exists custom_profiles" in templates["setup_profiles"]["template"]
    assert "create table if not exists custom_roles" in templates["setup_roles"]["template"]
    assert "create table if not exists custom_user_roles" in templates["setup_user_roles"]["template"]
    assert "from custom_users" in templates["fetch_user"]["template"]
    assert "from custom_user_roles" in templates["fetch_roles"]["template"]
    assert "join custom_roles" in templates["fetch_roles"]["template"]
    assert "update custom_users" in templates["update_user"]["template"]
    assert "case" in templates["update_user"]["template"]
    assert "delete from custom_user_roles" in templates["clear_roles"]["template"]
    assert "delete from custom_profiles" in templates["delete_profile"]["template"]
    assert "delete from custom_users" in templates["delete_user"]["template"]


def test_managed_user_table_uses_zope_friendly_username_column():
    templates = postgresql_templates(DEFAULT_TABLES)

    assert "username varchar(80)" in templates["setup_users"]["template"]
    assert "username as login_name" in templates["fetch_user"]["template"]
    assert "where username =" in templates["fetch_user"]["template"]
    assert "login_name varchar" not in templates["setup_users"]["template"]


def test_postgresql_templates_use_zsql_parameter_binding():
    templates = postgresql_templates(DEFAULT_TABLES)

    assert "<dtml-sqlvar login type=string>" in templates["fetch_user"]["template"]
    assert "<dtml-sqlvar user_id type=string>" in templates["fetch_roles"]["template"]
    assert "<dtml-sqlvar password type=string>" in templates["upsert_user"]["template"]
    assert "<dtml-sqlvar password type=string>" in templates["update_password"]["template"]
    assert "<dtml-sqlvar role_id type=string>" in templates["upsert_role"]["template"]
    assert "<dtml-sqlvar totp_secret type=string>" in templates["update_2fa"]["template"]


def test_authenticate_script_supports_hashed_and_plain_passwords():
    from Products.SQLUserWizard.config import AUTHENTICATE_SCRIPT

    assert "password_hash_id == 'plain'" in AUTHENTICATE_SCRIPT
    assert "from AuthEncoding import pw_validate" in AUTHENTICATE_SCRIPT
    assert "verify_totp_code" in AUTHENTICATE_SCRIPT
    assert "otp_code" in AUTHENTICATE_SCRIPT


def test_cookie_auth_helper_id_is_product_specific():
    assert DEFAULT_COOKIE_AUTH_ID == "sql_cookie_auth"


def test_postgresql_templates_keep_adapter_out_of_sql():
    templates = postgresql_templates(DEFAULT_TABLES)

    for spec in templates.values():
        assert "connection_id" not in spec["template"]
        assert "pg_odbc" not in spec["template"]


def test_profile_templates_are_separate_editable_layer():
    templates = profile_postgresql_templates(
        {
            "users": "custom_users",
            "profiles": "custom_profiles",
            "roles": "custom_roles",
            "user_roles": "custom_user_roles",
        }
    )

    assert templates["get_profile"]["id"] == "sql_user_profile_get"
    assert templates["save_profile"]["id"] == "sql_user_profile_save"
    assert "from custom_profiles" in templates["get_profile"]["template"]
    assert "insert into custom_profiles" in templates["save_profile"]["template"]
    assert "custom_users" not in templates["save_profile"]["template"]


def test_existing_auth_only_templates_are_read_only():
    templates = auth_only_templates(
        "existing_postgresql",
        {
            "users": "users",
            "profiles": "ignored_profiles",
            "roles": "ignored_role_catalog",
            "user_roles": "roles",
        },
    )

    assert set(templates) == {"fetch_user", "fetch_roles", "get_profile"}
    combined = "\n".join(spec["template"].lower() for spec in templates.values())
    assert "from users" in combined
    assert "from roles" in combined
    assert "ignored_role_catalog" not in combined
    assert "insert " not in combined
    assert "update " not in combined
    assert "delete " not in combined
    assert "create " not in combined
    assert "alter " not in combined


def test_existing_oracle_auth_only_uses_oracle_string_functions():
    templates = auth_only_templates("existing_oracle", DEFAULT_TABLES)

    assert "substr(password, 1, 1)" in templates["fetch_user"]["template"]
    assert "||" in templates["get_profile"]["template"]
    assert "rownum = 1" in templates["fetch_user"]["template"].lower()


def test_managed_dialect_aliases_match_lab_databases():
    assert normalize_managed_dialect("postgresql") == "postgresql"
    assert normalize_managed_dialect("mariadb") == "mysql"
    assert normalize_managed_dialect("sqlserver") == "mssql"
    assert normalize_managed_dialect("oracle") == "oracle11g"


def test_managed_templates_support_mainstream_lab_dialects():
    for dialect in ("sqlite", "mysql", "mssql", "oracle11g", "oracle12c"):
        templates = managed_templates(dialect, DEFAULT_TABLES)
        assert "fetch_user" in templates
        assert "upsert_user" in templates
        assert "update_2fa" in templates
        assert "assign_role" in templates
        assert "zsql_pas_setup_users" == templates["setup_users"]["id"]
        assert "username" in templates["setup_users"]["template"].lower()
        assert "username as login_name" in templates["fetch_user"]["template"].lower()


def test_oracle11g_managed_templates_use_rownum_for_single_row_fetches():
    templates = managed_templates("oracle11g", DEFAULT_TABLES)

    assert "rownum = 1" in templates["fetch_user"]["template"].lower()
    assert "fetch first" not in templates["fetch_user"]["template"].lower()
    assert "merge into pas_users" in templates["upsert_user"]["template"].lower()
    assert "varchar2(80)" in templates["setup_users"]["template"].lower()
    assert "date default sysdate not null" in templates["setup_users"]["template"].lower()
    assert "number(1) default 1 not null" in templates["setup_users"]["template"].lower()


def test_oracle12c_managed_templates_can_use_fetch_first():
    templates = managed_templates("oracle12c", DEFAULT_TABLES)

    assert "fetch first 1 rows only" in templates["fetch_user"]["template"].lower()


def test_profile_templates_are_dialect_wrapped():
    templates = profile_templates("mssql", DEFAULT_TABLES)

    assert "top 1" in templates["get_profile"]["template"].lower()
    assert "merge pas_user_profiles" in templates["save_profile"]["template"].lower()


def test_default_role_catalog_name_is_explicit():
    assert DEFAULT_TABLES["roles"] == "pas_roles_catalog"


def test_classic_acl_users_migration_template_is_runnable_zsql():
    spec = classic_acl_users_migration_template(
        "existing_oracle",
        {
            "users": "users",
            "profiles": "pas_user_profiles",
            "roles": "pas_roles_catalog",
            "user_roles": "roles",
        },
    )

    assert spec["id"] == DEFAULT_MIGRATION_SQL_ID
    assert spec["arguments"] == ""
    assert "begin" in spec["template"].lower()
    assert "execute immediate" in spec["template"].lower()
    assert "create table pas_users_migrated" in spec["template"].lower()
    assert "from users" in spec["template"].lower()
    assert "from roles" in spec["template"].lower()
