"""Managed SQL dialect templates for Products.SQLUserWizard."""

from .config import DEFAULT_PROFILE_GET_ID
from .config import DEFAULT_PROFILE_SAVE_ID
from .config import DEFAULT_TABLES
from .config import postgresql_templates
from .config import profile_postgresql_templates

MANAGED_DIALECT_ALIASES = {
    "postgresql": "postgresql",
    "postgres": "postgresql",
    "sqlite": "sqlite",
    "mysql": "mysql",
    "mariadb": "mysql",
    "sqlserver": "mssql",
    "mssql": "mssql",
    "oracle": "oracle11g",
    "oracle11g": "oracle11g",
    "oracle12c": "oracle12c",
}

SUPPORTED_MANAGED_DIALECTS = (
    "postgresql",
    "sqlite",
    "mysql",
    "mariadb",
    "mssql",
    "sqlserver",
    "oracle",
    "oracle11g",
    "oracle12c",
)


def normalize_managed_dialect(dialect):
    return MANAGED_DIALECT_ALIASES.get((dialect or "postgresql").lower())


def managed_templates(dialect="postgresql", tables=None):
    """Return product-owned SQL templates for the supported mainstream dialects."""

    normalized = normalize_managed_dialect(dialect)
    if normalized is None:
        raise NotImplementedError(f"Unsupported managed SQL dialect: {dialect}")
    if normalized == "postgresql":
        return postgresql_templates(tables)

    tables = tables or DEFAULT_TABLES
    users = tables["users"]
    profiles = tables["profiles"]
    roles = tables["roles"]
    user_roles = tables["user_roles"]

    true_value = _sql_true(normalized)
    false_value = _sql_false(normalized)
    enabled_expr = _enabled_from_param(normalized)
    required_expr = _required_from_param(normalized)
    user_table = _create_table_if_missing(
        normalized,
        users,
        f"""    user_id varchar(80) primary key,
    login_name varchar(80) unique not null,
    password varchar(255) not null,
    password_hash_id varchar(40) not null default 'plain',
    enabled {_bool_type(normalized)} not null default {true_value},
    totp_required {_bool_type(normalized)} not null default {false_value},
    totp_enabled {_bool_type(normalized)} not null default {false_value},
    totp_secret varchar(64),
    recovery_email varchar(255),
    created_at {_timestamp_type(normalized)} not null default {_current_timestamp(normalized)},
    updated_at {_timestamp_type(normalized)} not null default {_current_timestamp(normalized)},
    last_login_at {_timestamp_type(normalized)}""",
    )
    profiles_table = _create_table_if_missing(
        normalized,
        profiles,
        f"""    user_id varchar(80) primary key,
    first_name varchar(80),
    last_name varchar(80),
    display_name varchar(160),
    email varchar(255),
    mobile varchar(40),
    created_at {_timestamp_type(normalized)} not null default {_current_timestamp(normalized)},
    updated_at {_timestamp_type(normalized)} not null default {_current_timestamp(normalized)}""",
    )
    roles_table = _create_table_if_missing(
        normalized,
        roles,
        f"""    role_id varchar(80) primary key,
    title varchar(160),
    enabled {_bool_type(normalized)} not null default {true_value},
    created_at {_timestamp_type(normalized)} not null default {_current_timestamp(normalized)},
    updated_at {_timestamp_type(normalized)} not null default {_current_timestamp(normalized)}""",
    )
    user_roles_table = _create_table_if_missing(
        normalized,
        user_roles,
        """    user_id varchar(80) not null,
    role_id varchar(80) not null,
    primary key (user_id, role_id)""",
    )

    return {
        "setup_users": {
            "id": "zsql_pas_setup_users",
            "title": "Create PAS SQL users table",
            "arguments": "",
            "template": user_table,
        },
        "setup_user_security_columns": {
            "id": "zsql_pas_setup_user_security_columns",
            "title": "Repair PAS SQL users security columns",
            "arguments": "",
            "template": _schema_repair_noop(normalized),
        },
        "setup_profiles": {
            "id": "zsql_pas_setup_profiles",
            "title": "Create PAS SQL user profiles table",
            "arguments": "",
            "template": profiles_table,
        },
        "setup_roles": {
            "id": "zsql_pas_setup_roles",
            "title": "Create PAS SQL role catalog table",
            "arguments": "",
            "template": roles_table,
        },
        "setup_user_roles": {
            "id": "zsql_pas_setup_user_roles",
            "title": "Create PAS SQL user role assignment table",
            "arguments": "",
            "template": user_roles_table,
        },
        "fetch_user": {
            "id": "zsql_pas_fetch_user",
            "title": "Fetch PAS SQL user by login",
            "arguments": "login",
            "template": _limit_one(
                normalized,
                f"""select {_top_one(normalized)}user_id, login_name, password, password_hash_id, enabled, totp_required, totp_enabled, totp_secret, recovery_email
from {users}
where login_name = <dtml-sqlvar login type=string>
  and enabled = {true_value}""",
            ),
        },
        "fetch_roles": {
            "id": "zsql_pas_fetch_roles",
            "title": "Fetch active PAS SQL roles by user_id",
            "arguments": "user_id",
            "template": f"""select ur.role_id as role
from {user_roles} ur
join {roles} r on r.role_id = ur.role_id
where ur.user_id = <dtml-sqlvar user_id type=string>
  and r.enabled = {true_value}
order by ur.role_id""",
        },
        "get_user": {
            "id": "zsql_pas_get_user",
            "title": "Fetch PAS SQL user and profile by user_id",
            "arguments": "user_id",
            "template": _limit_one(
                normalized,
                f"""select {_top_one(normalized)}
    u.user_id,
    u.login_name,
    u.password_hash_id,
    u.enabled,
    u.totp_required,
    u.totp_enabled,
    u.totp_secret,
    u.recovery_email,
    p.first_name,
    p.last_name,
    p.display_name,
    p.email,
    p.mobile
from {users} u
left join {profiles} p on p.user_id = u.user_id
where u.user_id = <dtml-sqlvar user_id type=string>""",
            ),
        },
        "upsert_user": {
            "id": "zsql_pas_upsert_user",
            "title": "Wizard upsert PAS SQL security user",
            "arguments": "user_id login_name password password_hash_id recovery_email enabled",
            "template": _upsert_user_sql(normalized, users, enabled_expr),
        },
        "update_user": {
            "id": "zsql_pas_update_user",
            "title": "Wizard update PAS SQL security user",
            "arguments": "user_id login_name recovery_email enabled",
            "template": f"""update {users}
set
    login_name = <dtml-sqlvar login_name type=string>,
    recovery_email = <dtml-sqlvar recovery_email type=string>,
    enabled = {enabled_expr},
    updated_at = {_current_timestamp(normalized)}
where user_id = <dtml-sqlvar user_id type=string>""",
        },
        "update_password": {
            "id": "zsql_pas_update_password",
            "title": "Wizard update PAS SQL user password",
            "arguments": "user_id password password_hash_id",
            "template": f"""update {users}
set
    password = <dtml-sqlvar password type=string>,
    password_hash_id = <dtml-sqlvar password_hash_id type=string>,
    updated_at = {_current_timestamp(normalized)}
where user_id = <dtml-sqlvar user_id type=string>""",
        },
        "update_2fa": {
            "id": "zsql_pas_update_2fa",
            "title": "Wizard update PAS SQL user TOTP settings",
            "arguments": "user_id totp_required totp_enabled totp_secret",
            "template": f"""update {users}
set
    totp_required = {required_expr},
    totp_enabled = {enabled_expr},
    totp_secret = <dtml-sqlvar totp_secret type=string>,
    updated_at = {_current_timestamp(normalized)}
where user_id = <dtml-sqlvar user_id type=string>""",
        },
        "upsert_profile": {
            "id": "zsql_pas_upsert_profile",
            "title": "Wizard upsert PAS SQL user profile",
            "arguments": "user_id first_name last_name display_name email mobile",
            "template": _upsert_profile_sql(normalized, profiles),
        },
        "upsert_role": {
            "id": "zsql_pas_upsert_role",
            "title": "Wizard upsert PAS SQL role",
            "arguments": "role_id title enabled",
            "template": _upsert_role_sql(normalized, roles, enabled_expr),
        },
        "list_roles": {
            "id": "zsql_pas_list_roles",
            "title": "Wizard list PAS SQL roles",
            "arguments": "",
            "template": f"""select role_id, title, enabled
from {roles}
order by role_id""",
        },
        "assign_role": {
            "id": "zsql_pas_assign_role",
            "title": "Wizard assign PAS SQL role",
            "arguments": "user_id role",
            "template": _assign_role_sql(normalized, user_roles),
        },
        "clear_roles": {
            "id": "zsql_pas_clear_roles",
            "title": "Wizard clear PAS SQL roles for user",
            "arguments": "user_id",
            "template": f"""delete from {user_roles}
where user_id = <dtml-sqlvar user_id type=string>""",
        },
        "delete_profile": {
            "id": "zsql_pas_delete_profile",
            "title": "Wizard delete PAS SQL user profile",
            "arguments": "user_id",
            "template": f"""delete from {profiles}
where user_id = <dtml-sqlvar user_id type=string>""",
        },
        "delete_user": {
            "id": "zsql_pas_delete_user",
            "title": "Wizard delete PAS SQL user",
            "arguments": "user_id",
            "template": f"""delete from {users}
where user_id = <dtml-sqlvar user_id type=string>""",
        },
        "list_users": {
            "id": "zsql_pas_list_users",
            "title": "Wizard list PAS SQL users",
            "arguments": "",
            "template": _list_users_sql(normalized, users, profiles, user_roles),
        },
    }


def profile_templates(dialect="postgresql", tables=None):
    normalized = normalize_managed_dialect(dialect)
    if normalized is None:
        raise NotImplementedError(f"Unsupported managed SQL dialect: {dialect}")
    if normalized == "postgresql":
        return profile_postgresql_templates(tables)

    tables = tables or DEFAULT_TABLES
    profiles = tables["profiles"]
    return {
        "get_profile": {
            "id": DEFAULT_PROFILE_GET_ID,
            "title": "Editable SQL user profile fetch",
            "arguments": "user_id",
            "template": _limit_one(
                normalized,
                f"""select {_top_one(normalized)}
    user_id,
    first_name,
    last_name,
    display_name,
    email,
    mobile
from {profiles}
where user_id = <dtml-sqlvar user_id type=string>""",
            ),
        },
        "save_profile": {
            "id": DEFAULT_PROFILE_SAVE_ID,
            "title": "Editable SQL user profile save",
            "arguments": "user_id first_name last_name display_name email mobile",
            "template": _upsert_profile_sql(normalized, profiles),
        },
    }


def _bool_type(dialect):
    if dialect in ("mysql", "mssql", "oracle11g", "oracle12c", "sqlite"):
        return "number(1)" if dialect.startswith("oracle") else "bit" if dialect == "mssql" else "integer" if dialect == "sqlite" else "tinyint(1)"
    return "boolean"


def _timestamp_type(dialect):
    return "datetime2" if dialect == "mssql" else "date" if dialect.startswith("oracle") else "datetime" if dialect == "mysql" else "timestamp"


def _current_timestamp(dialect):
    if dialect == "mssql":
        return "sysdatetime()"
    if dialect.startswith("oracle"):
        return "sysdate"
    return "current_timestamp"


def _sql_true(dialect):
    return "true" if dialect == "postgresql" else "1"


def _sql_false(dialect):
    return "false" if dialect == "postgresql" else "0"


def _enabled_from_param(dialect):
    true_value = _sql_true(dialect)
    false_value = _sql_false(dialect)
    return (
        "case when <dtml-sqlvar enabled type=string> = '1' "
        f"then {true_value} else {false_value} end"
    )


def _required_from_param(dialect):
    true_value = _sql_true(dialect)
    false_value = _sql_false(dialect)
    return (
        "case when <dtml-sqlvar totp_required type=string> = '1' "
        f"then {true_value} else {false_value} end"
    )


def _top_one(dialect):
    return "top 1 " if dialect == "mssql" else ""


def _limit_one(dialect, sql):
    if dialect == "mssql":
        return sql
    if dialect == "oracle11g":
        return f"{sql}\n  and rownum = 1"
    if dialect == "oracle12c":
        return f"{sql}\nfetch first 1 rows only"
    return f"{sql}\nlimit 1"


def _create_table_if_missing(dialect, table, columns):
    if dialect in ("sqlite", "mysql"):
        return f"""create table if not exists {table} (
{columns}
)"""
    if dialect == "mssql":
        return f"""if object_id(N'{table}', N'U') is null
create table {table} (
{columns}
)"""
    if dialect.startswith("oracle"):
        oracle_columns = _oracle_column_syntax(columns)
        escaped = (
            f"create table {table} ({oracle_columns})"
            .replace("'", "''")
            .replace("\n", " ")
        )
        return f"""declare
    table_count number;
begin
    select count(*) into table_count from user_tables where table_name = upper('{table}');
    if table_count = 0 then
        execute immediate '{escaped}';
    end if;
end;"""
    raise NotImplementedError(f"Unsupported create table dialect: {dialect}")


def _oracle_column_syntax(columns):
    return (
        columns.replace("varchar(", "varchar2(")
        .replace(" unique not null", " not null unique")
        .replace(" varchar2(40) not null default 'plain'", " varchar2(40) default 'plain' not null")
        .replace(" number(1) not null default 1", " number(1) default 1 not null")
        .replace(" date not null default sysdate", " date default sysdate not null")
    )


def _schema_repair_noop(dialect):
    if dialect.startswith("oracle"):
        return "select 1 from dual"
    return "select 1"


def _upsert_user_sql(dialect, users, enabled_expr):
    if dialect in ("sqlite",):
        return f"""insert into {users}
    (user_id, login_name, password, password_hash_id, enabled, recovery_email)
values (
    <dtml-sqlvar user_id type=string>,
    <dtml-sqlvar login_name type=string>,
    <dtml-sqlvar password type=string>,
    <dtml-sqlvar password_hash_id type=string>,
    {enabled_expr},
    <dtml-sqlvar recovery_email type=string>
)
on conflict (user_id) do update set
    login_name = excluded.login_name,
    password = excluded.password,
    password_hash_id = excluded.password_hash_id,
    enabled = excluded.enabled,
    recovery_email = excluded.recovery_email,
    updated_at = {_current_timestamp(dialect)}"""
    if dialect == "mysql":
        return f"""insert into {users}
    (user_id, login_name, password, password_hash_id, enabled, recovery_email)
values (
    <dtml-sqlvar user_id type=string>,
    <dtml-sqlvar login_name type=string>,
    <dtml-sqlvar password type=string>,
    <dtml-sqlvar password_hash_id type=string>,
    {enabled_expr},
    <dtml-sqlvar recovery_email type=string>
)
on duplicate key update
    login_name = values(login_name),
    password = values(password),
    password_hash_id = values(password_hash_id),
    enabled = values(enabled),
    recovery_email = values(recovery_email),
    updated_at = {_current_timestamp(dialect)}"""
    if dialect == "mssql":
        return f"""merge {users} as target
using (select
    <dtml-sqlvar user_id type=string> as user_id,
    <dtml-sqlvar login_name type=string> as login_name,
    <dtml-sqlvar password type=string> as password,
    <dtml-sqlvar password_hash_id type=string> as password_hash_id,
    {enabled_expr} as enabled,
    <dtml-sqlvar recovery_email type=string> as recovery_email
) as source
on target.user_id = source.user_id
when matched then update set
    login_name = source.login_name,
    password = source.password,
    password_hash_id = source.password_hash_id,
    enabled = source.enabled,
    recovery_email = source.recovery_email,
    updated_at = {_current_timestamp(dialect)}
when not matched then insert
    (user_id, login_name, password, password_hash_id, enabled, recovery_email)
values
    (source.user_id, source.login_name, source.password, source.password_hash_id, source.enabled, source.recovery_email);"""
    if dialect.startswith("oracle"):
        return f"""merge into {users} target
using (select
    <dtml-sqlvar user_id type=string> as user_id,
    <dtml-sqlvar login_name type=string> as login_name,
    <dtml-sqlvar password type=string> as password,
    <dtml-sqlvar password_hash_id type=string> as password_hash_id,
    {enabled_expr} as enabled,
    <dtml-sqlvar recovery_email type=string> as recovery_email
from dual) source
on (target.user_id = source.user_id)
when matched then update set
    target.login_name = source.login_name,
    target.password = source.password,
    target.password_hash_id = source.password_hash_id,
    target.enabled = source.enabled,
    target.recovery_email = source.recovery_email,
    target.updated_at = {_current_timestamp(dialect)}
when not matched then insert
    (user_id, login_name, password, password_hash_id, enabled, recovery_email)
values
    (source.user_id, source.login_name, source.password, source.password_hash_id, source.enabled, source.recovery_email)"""
    raise NotImplementedError(f"Unsupported upsert dialect: {dialect}")


def _upsert_profile_sql(dialect, profiles):
    if dialect == "mysql":
        return f"""insert into {profiles}
    (user_id, first_name, last_name, display_name, email, mobile)
values (
    <dtml-sqlvar user_id type=string>,
    <dtml-sqlvar first_name type=string>,
    <dtml-sqlvar last_name type=string>,
    <dtml-sqlvar display_name type=string>,
    <dtml-sqlvar email type=string>,
    <dtml-sqlvar mobile type=string>
)
on duplicate key update
    first_name = values(first_name),
    last_name = values(last_name),
    display_name = values(display_name),
    email = values(email),
    mobile = values(mobile),
    updated_at = {_current_timestamp(dialect)}"""
    if dialect in ("sqlite",):
        return f"""insert into {profiles}
    (user_id, first_name, last_name, display_name, email, mobile)
values (
    <dtml-sqlvar user_id type=string>,
    <dtml-sqlvar first_name type=string>,
    <dtml-sqlvar last_name type=string>,
    <dtml-sqlvar display_name type=string>,
    <dtml-sqlvar email type=string>,
    <dtml-sqlvar mobile type=string>
)
on conflict (user_id) do update set
    first_name = excluded.first_name,
    last_name = excluded.last_name,
    display_name = excluded.display_name,
    email = excluded.email,
    mobile = excluded.mobile,
    updated_at = {_current_timestamp(dialect)}"""
    if dialect == "mssql":
        return f"""merge {profiles} as target
using (select
    <dtml-sqlvar user_id type=string> as user_id,
    <dtml-sqlvar first_name type=string> as first_name,
    <dtml-sqlvar last_name type=string> as last_name,
    <dtml-sqlvar display_name type=string> as display_name,
    <dtml-sqlvar email type=string> as email,
    <dtml-sqlvar mobile type=string> as mobile
) as source
on target.user_id = source.user_id
when matched then update set
    first_name = source.first_name,
    last_name = source.last_name,
    display_name = source.display_name,
    email = source.email,
    mobile = source.mobile,
    updated_at = {_current_timestamp(dialect)}
when not matched then insert
    (user_id, first_name, last_name, display_name, email, mobile)
values
    (source.user_id, source.first_name, source.last_name, source.display_name, source.email, source.mobile);"""
    if dialect.startswith("oracle"):
        return f"""merge into {profiles} target
using (select
    <dtml-sqlvar user_id type=string> as user_id,
    <dtml-sqlvar first_name type=string> as first_name,
    <dtml-sqlvar last_name type=string> as last_name,
    <dtml-sqlvar display_name type=string> as display_name,
    <dtml-sqlvar email type=string> as email,
    <dtml-sqlvar mobile type=string> as mobile
from dual) source
on (target.user_id = source.user_id)
when matched then update set
    target.first_name = source.first_name,
    target.last_name = source.last_name,
    target.display_name = source.display_name,
    target.email = source.email,
    target.mobile = source.mobile,
    target.updated_at = {_current_timestamp(dialect)}
when not matched then insert
    (user_id, first_name, last_name, display_name, email, mobile)
values
    (source.user_id, source.first_name, source.last_name, source.display_name, source.email, source.mobile)"""
    raise NotImplementedError(f"Unsupported profile upsert dialect: {dialect}")


def _upsert_role_sql(dialect, roles, enabled_expr):
    if dialect == "mysql":
        return f"""insert into {roles} (role_id, title, enabled)
values (
    <dtml-sqlvar role_id type=string>,
    <dtml-sqlvar title type=string>,
    {enabled_expr}
)
on duplicate key update
    title = values(title),
    enabled = values(enabled),
    updated_at = {_current_timestamp(dialect)}"""
    if dialect == "sqlite":
        return f"""insert into {roles} (role_id, title, enabled)
values (
    <dtml-sqlvar role_id type=string>,
    <dtml-sqlvar title type=string>,
    {enabled_expr}
)
on conflict (role_id) do update set
    title = excluded.title,
    enabled = excluded.enabled,
    updated_at = {_current_timestamp(dialect)}"""
    if dialect == "mssql":
        return f"""merge {roles} as target
using (select
    <dtml-sqlvar role_id type=string> as role_id,
    <dtml-sqlvar title type=string> as title,
    {enabled_expr} as enabled
) as source
on target.role_id = source.role_id
when matched then update set
    title = source.title,
    enabled = source.enabled,
    updated_at = {_current_timestamp(dialect)}
when not matched then insert (role_id, title, enabled)
values (source.role_id, source.title, source.enabled);"""
    if dialect.startswith("oracle"):
        return f"""merge into {roles} target
using (select
    <dtml-sqlvar role_id type=string> as role_id,
    <dtml-sqlvar title type=string> as title,
    {enabled_expr} as enabled
from dual) source
on (target.role_id = source.role_id)
when matched then update set
    target.title = source.title,
    target.enabled = source.enabled,
    target.updated_at = {_current_timestamp(dialect)}
when not matched then insert (role_id, title, enabled)
values (source.role_id, source.title, source.enabled)"""
    raise NotImplementedError(f"Unsupported role upsert dialect: {dialect}")


def _assign_role_sql(dialect, user_roles):
    if dialect == "mysql":
        return f"""insert ignore into {user_roles} (user_id, role_id)
values (<dtml-sqlvar user_id type=string>, <dtml-sqlvar role type=string>)"""
    if dialect == "sqlite":
        return f"""insert or ignore into {user_roles} (user_id, role_id)
values (<dtml-sqlvar user_id type=string>, <dtml-sqlvar role type=string>)"""
    if dialect == "mssql":
        return f"""if not exists (
    select 1 from {user_roles}
    where user_id = <dtml-sqlvar user_id type=string>
      and role_id = <dtml-sqlvar role type=string>
)
insert into {user_roles} (user_id, role_id)
values (<dtml-sqlvar user_id type=string>, <dtml-sqlvar role type=string>)"""
    if dialect.startswith("oracle"):
        return f"""insert into {user_roles} (user_id, role_id)
select <dtml-sqlvar user_id type=string>, <dtml-sqlvar role type=string>
from dual
where not exists (
    select 1 from {user_roles}
    where user_id = <dtml-sqlvar user_id type=string>
      and role_id = <dtml-sqlvar role type=string>
)"""
    raise NotImplementedError(f"Unsupported assign role dialect: {dialect}")


def _list_users_sql(dialect, users, profiles, user_roles):
    if dialect == "mysql":
        roles_expr = "coalesce(group_concat(ur.role_id order by ur.role_id separator ', '), '')"
    elif dialect == "mssql":
        roles_expr = (
            "coalesce((select string_agg(ur2.role_id, ', ') "
            f"from {user_roles} ur2 where ur2.user_id = u.user_id), '')"
        )
    elif dialect.startswith("oracle"):
        roles_expr = (
            "coalesce((select listagg(ur2.role_id, ', ') within group (order by ur2.role_id) "
            f"from {user_roles} ur2 where ur2.user_id = u.user_id), '')"
        )
    elif dialect == "sqlite":
        roles_expr = (
            "coalesce((select group_concat(ur2.role_id, ', ') "
            f"from {user_roles} ur2 where ur2.user_id = u.user_id), '')"
        )
    else:
        roles_expr = "''"
    if dialect in ("mssql", "oracle11g", "oracle12c", "sqlite"):
        return f"""select
    u.user_id,
    u.login_name,
    u.recovery_email,
    u.totp_required,
    u.totp_enabled,
    u.totp_secret,
    p.first_name,
    p.last_name,
    p.display_name,
    p.email,
    p.mobile,
    u.enabled,
    {roles_expr} as roles
from {users} u
left join {profiles} p on p.user_id = u.user_id
order by u.login_name"""
    return f"""select
    u.user_id,
    u.login_name,
    u.recovery_email,
    u.totp_required,
    u.totp_enabled,
    u.totp_secret,
    p.first_name,
    p.last_name,
    p.display_name,
    p.email,
    p.mobile,
    u.enabled,
    {roles_expr} as roles
from {users} u
left join {profiles} p on p.user_id = u.user_id
left join {user_roles} ur on ur.user_id = u.user_id
group by u.user_id, u.login_name, u.recovery_email, u.totp_required, u.totp_enabled, u.totp_secret, p.first_name, p.last_name, p.display_name, p.email, p.mobile, u.enabled
order by u.login_name"""


