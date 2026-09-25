"""Validate new schemas and refuse implicit takeover of existing SQL tables."""

import json
import re

from .config import DEFAULT_MANIFEST_ID, DEFAULT_TABLES, MODE_MANAGED
from .dialects import normalize_managed_dialect


def validate_tables(tables):
    if set(tables) != set(DEFAULT_TABLES):
        raise ValueError("Provide names for users, profiles, roles and user_roles")
    for name in tables.values():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,29}", name):
            raise ValueError("Table names must be simple SQL identifiers of 1–30 characters")
    if len({name.lower() for name in tables.values()}) != len(tables):
        raise ValueError("Use distinct tables")


def catalog_sql(dialect):
    queries = {
        "postgresql": "select relname as table_name from pg_class where pg_table_is_visible(oid)",
        "sqlite": "select name as table_name from sqlite_master union select name as table_name from sqlite_temp_master",
        "mysql": "select table_name from information_schema.tables where table_schema = database()",
        "mssql": "select name as table_name from sys.objects where schema_id = schema_id()",
        "oracle11g": "select object_name as table_name from user_objects union select synonym_name as table_name from all_synonyms where owner = 'PUBLIC'",
        "oracle12c": "select object_name as table_name from user_objects union select synonym_name as table_name from all_synonyms where owner = 'PUBLIC'",
    }
    normalized = normalize_managed_dialect(dialect)
    if normalized not in queries:
        raise ValueError("Unsupported database dialect; existing-schema modes have been removed")
    return queries[normalized]


def _existing_names(installer):
    from Products.ZSQLMethods.SQL import SQL
    query = SQL("sqluw_preflight", "Check table names", installer.connection_id, "", catalog_sql(installer.dialect))
    rows = query.__of__(installer.folder)()
    return {str(row[0]).lower() for row in rows}


def check_installation(installer):
    validate_tables(installer.tables)
    catalog_sql(installer.dialect)
    pas = installer._local_object(installer.folder, installer.pas_id)
    manifest = installer._local_object(pas, DEFAULT_MANIFEST_ID) if pas is not None else None
    owned = False
    if manifest is not None:
        data = json.loads(installer._object_source(manifest))
        if data.get("mode") != MODE_MANAGED:
            raise ValueError("This is a retired existing-database setup. Use a new folder and unused table names.")
        owned = (data.get("product") == "Products.SQLUserWizard"
                 and data.get("tables") == installer.tables
                 and data.get("connection_id") == installer.connection_id
                 and normalize_managed_dialect(data.get("sql_dialect")) == normalize_managed_dialect(installer.dialect))
        if not owned:
            raise ValueError("Repair must keep the recorded database connection, dialect and table names")
        _check_repair_sql(installer, pas)
    if not owned:
        collisions = set(name.lower() for name in installer.tables.values()) & _existing_names(installer)
        if collisions:
            raise ValueError("Tables already exist and are not owned by this installation: " + ", ".join(sorted(collisions)))


def _check_repair_sql(installer, pas):
    """Refuse template replacement when the persisted SQL contract differs."""
    from .dialects import managed_templates
    plugin = installer._local_object(pas, installer.plugin_id)
    if plugin is None:
        raise ValueError("Recorded SQL plugin is missing; review before schema repair")
    changed = []
    for spec in managed_templates(installer.dialect, installer.tables).values():
        method = installer._local_object(plugin, spec["id"])
        if method is None:
            continue
        if (getattr(method, "src", None) != spec["template"]
                or getattr(method, "arguments_src", None) != spec["arguments"]
                or getattr(method, "connection_id", None) != installer.connection_id):
            changed.append(spec["id"])
    if changed:
        raise ValueError("Repair would overwrite older or customized SQL; review manually before repair: "
                         + ", ".join(changed))
