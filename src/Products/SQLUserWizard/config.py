DEFAULT_WIZARD_ID = "sql_user_wizard"
DEFAULT_PAS_ID = "acl_users"
DEFAULT_PLUGIN_ID = "sql_auth"
DEFAULT_ADMIN_ID = "sql_user_admin"
DEFAULT_FALLBACK_USER_PLUGIN_ID = "zodb_fallback_users"
DEFAULT_FALLBACK_ROLE_PLUGIN_ID = "zodb_fallback_roles"
DEFAULT_FALLBACK_LOGIN = "pas_fallback_manager"
DEFAULT_MANIFEST_ID = "sql_user_wizard_manifest"
DEFAULT_INFO_ID = "sql_user_wizard_info"
DEFAULT_PROFILE_FORM_ID = "sql_user_profile_form"
DEFAULT_PROFILE_PREVIEW_ID = "sql_user_profile_preview"
DEFAULT_PROFILE_GET_ID = "sql_user_profile_get"
DEFAULT_PROFILE_SAVE_ID = "sql_user_profile_save"
DEFAULT_LOGIN_FORM_ID = "sql_user_login_form"
DEFAULT_LOGIN_SUBMIT_ID = "sql_user_login_submit"
DEFAULT_LOGOUT_ID = "sql_user_logout"
DEFAULT_SECURE_TEST_ID = "secure_test_page"
DEFAULT_COOKIE_AUTH_ID = "sql_cookie_auth"
DEFAULT_PASSWORD_HASH_ID = "authencoding"
DEFAULT_TOTP_ISSUER = "Zope SQL Users"
MODE_MANAGED = "managed"
MODE_AUTH_ONLY = "auth_only"

DEFAULT_TABLES = {
    "users": "pas_users",
    "profiles": "pas_user_profiles",
    "roles": "pas_roles_catalog",
    "user_roles": "pas_user_roles",
}


def postgresql_templates(tables=None):
    tables = tables or DEFAULT_TABLES
    users = tables["users"]
    profiles = tables["profiles"]
    roles = tables["roles"]
    user_roles = tables["user_roles"]
    return {
        "setup_users": {
            "id": "zsql_pas_setup_users",
            "title": "Create PAS SQL users table",
            "arguments": "",
            "template": f"""create table if not exists {users} (
    user_id varchar(80) primary key,
    username varchar(80) unique not null,
    password varchar(255) not null,
    password_hash_id varchar(40) not null default 'plain',
    enabled boolean not null default true,
    totp_required boolean not null default false,
    totp_enabled boolean not null default false,
    totp_secret varchar(64),
    recovery_email varchar(255),
    created_at timestamp not null default current_timestamp,
    updated_at timestamp not null default current_timestamp,
    last_login_at timestamp
)""",
        },
        "setup_user_security_columns": {
            "id": "zsql_pas_setup_user_security_columns",
            "title": "Repair PAS SQL users security columns",
            "arguments": "",
            "template": f"""alter table {users}
    add column if not exists password_hash_id varchar(40) not null default 'plain',
    add column if not exists totp_required boolean not null default false,
    add column if not exists totp_enabled boolean not null default false,
    add column if not exists totp_secret varchar(64),
    add column if not exists recovery_email varchar(255),
    add column if not exists created_at timestamp not null default current_timestamp,
    add column if not exists updated_at timestamp not null default current_timestamp,
    add column if not exists last_login_at timestamp""",
        },
        "setup_profiles": {
            "id": "zsql_pas_setup_profiles",
            "title": "Create PAS SQL user profiles table",
            "arguments": "",
            "template": f"""create table if not exists {profiles} (
    user_id varchar(80) primary key,
    first_name varchar(80),
    last_name varchar(80),
    display_name varchar(160),
    email varchar(255),
    mobile varchar(40),
    created_at timestamp not null default current_timestamp,
    updated_at timestamp not null default current_timestamp
)""",
        },
        "setup_roles": {
            "id": "zsql_pas_setup_roles",
            "title": "Create PAS SQL role catalog table",
            "arguments": "",
            "template": f"""create table if not exists {roles} (
    role_id varchar(80) primary key,
    title varchar(160),
    enabled boolean not null default true,
    created_at timestamp not null default current_timestamp,
    updated_at timestamp not null default current_timestamp
)""",
        },
        "setup_user_roles": {
            "id": "zsql_pas_setup_user_roles",
            "title": "Create PAS SQL user role assignment table",
            "arguments": "",
            "template": f"""create table if not exists {user_roles} (
    user_id varchar(80) not null,
    role_id varchar(80) not null,
    primary key (user_id, role_id)
)""",
        },
        "fetch_user": {
            "id": "zsql_pas_fetch_user",
            "title": "Fetch PAS SQL user by login",
            "arguments": "login",
            "template": f"""select user_id, username as login_name, password, password_hash_id, enabled, totp_required, totp_enabled, totp_secret, recovery_email
from {users}
where username = <dtml-sqlvar login type=string>
  and enabled = true
limit 1""",
        },
        "fetch_roles": {
            "id": "zsql_pas_fetch_roles",
            "title": "Fetch active PAS SQL roles by user_id",
            "arguments": "user_id",
            "template": f"""select ur.role_id as role
from {user_roles} ur
join {roles} r on r.role_id = ur.role_id
where ur.user_id = <dtml-sqlvar user_id type=string>
  and r.enabled = true
order by ur.role_id""",
        },
        "get_user": {
            "id": "zsql_pas_get_user",
            "title": "Fetch PAS SQL user and profile by user_id",
            "arguments": "user_id",
            "template": f"""select
    u.user_id,
    u.username as login_name,
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
where u.user_id = <dtml-sqlvar user_id type=string>
limit 1""",
        },
        "upsert_user": {
            "id": "zsql_pas_upsert_user",
            "title": "Wizard upsert PAS SQL security user",
            "arguments": "user_id login_name password password_hash_id recovery_email enabled",
            "template": f"""insert into {users}
    (user_id, username, password, password_hash_id, enabled, recovery_email)
values
    (
      <dtml-sqlvar user_id type=string>,
      <dtml-sqlvar login_name type=string>,
      <dtml-sqlvar password type=string>,
      <dtml-sqlvar password_hash_id type=string>,
      case when <dtml-sqlvar enabled type=string> = '1' then true else false end,
      <dtml-sqlvar recovery_email type=string>
    )
on conflict (user_id) do update set
    username = excluded.username,
    password = excluded.password,
    password_hash_id = excluded.password_hash_id,
    enabled = excluded.enabled,
    recovery_email = excluded.recovery_email,
    updated_at = current_timestamp""",
        },
        "update_user": {
            "id": "zsql_pas_update_user",
            "title": "Wizard update PAS SQL security user",
            "arguments": "user_id login_name recovery_email enabled",
            "template": f"""update {users}
set
    username = <dtml-sqlvar login_name type=string>,
    recovery_email = <dtml-sqlvar recovery_email type=string>,
    enabled = case
        when <dtml-sqlvar enabled type=string> = '1' then true
        else false
    end,
    updated_at = current_timestamp
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
    updated_at = current_timestamp
where user_id = <dtml-sqlvar user_id type=string>""",
        },
        "update_2fa": {
            "id": "zsql_pas_update_2fa",
            "title": "Wizard update PAS SQL user TOTP settings",
            "arguments": "user_id totp_required totp_enabled totp_secret",
            "template": f"""update {users}
set
    totp_required = case
        when <dtml-sqlvar totp_required type=string> = '1' then true
        else false
    end,
    totp_enabled = case
        when <dtml-sqlvar totp_enabled type=string> = '1' then true
        else false
    end,
    totp_secret = <dtml-sqlvar totp_secret type=string>,
    updated_at = current_timestamp
where user_id = <dtml-sqlvar user_id type=string>""",
        },
        "upsert_profile": {
            "id": "zsql_pas_upsert_profile",
            "title": "Wizard upsert PAS SQL user profile",
            "arguments": "user_id first_name last_name display_name email mobile",
            "template": f"""insert into {profiles}
    (user_id, first_name, last_name, display_name, email, mobile)
values
    (
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
    updated_at = current_timestamp""",
        },
        "upsert_role": {
            "id": "zsql_pas_upsert_role",
            "title": "Wizard upsert PAS SQL role",
            "arguments": "role_id title enabled",
            "template": f"""insert into {roles} (role_id, title, enabled)
values (
    <dtml-sqlvar role_id type=string>,
    <dtml-sqlvar title type=string>,
    case when <dtml-sqlvar enabled type=string> = '1' then true else false end
)
on conflict (role_id) do update set
    title = excluded.title,
    enabled = excluded.enabled,
    updated_at = current_timestamp""",
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
            "template": f"""insert into {user_roles} (user_id, role_id)
values (<dtml-sqlvar user_id type=string>, <dtml-sqlvar role type=string>)
on conflict do nothing""",
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
            "template": f"""select
    u.user_id,
    u.username as login_name,
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
    coalesce(string_agg(ur.role_id, ', ' order by ur.role_id), '') as roles
from {users} u
left join {profiles} p on p.user_id = u.user_id
left join {user_roles} ur on ur.user_id = u.user_id
group by u.user_id, u.username, u.recovery_email, u.totp_required, u.totp_enabled, u.totp_secret, p.first_name, p.last_name, p.display_name, p.email, p.mobile, u.enabled
order by u.username""",
        },
    }



def auth_only_templates(dialect="existing_postgresql", tables=None):
    tables = tables or DEFAULT_TABLES
    users = tables["users"]
    user_roles = tables["user_roles"]

    if dialect == "existing_oracle":
        fetch_user_template = f"""select
    username as user_id,
    username as login_name,
    password,
    case when substr(password, 1, 1) = '{{' then 'authencoding' else 'plain' end as password_hash_id,
    1 as enabled,
    0 as totp_required,
    0 as totp_enabled,
    null as totp_secret,
    null as recovery_email
from {users}
where lower(username) = lower(<dtml-sqlvar login type=string>)
  and rownum = 1"""
        fetch_roles_template = f"""select role
from {user_roles}
where lower(username) = lower(<dtml-sqlvar user_id type=string>)
order by role"""
        get_profile_template = f"""select
    username as user_id,
    firstname as first_name,
    lastname as last_name,
    firstname || ' ' || lastname as display_name,
    null as email,
    null as mobile
from {users}
where lower(username) = lower(<dtml-sqlvar user_id type=string>)
  and rownum = 1"""
    else:
        fetch_user_template = f"""select
    username as user_id,
    username as login_name,
    password,
    case when left(password, 1) = '{{' then 'authencoding' else 'plain' end as password_hash_id,
    true as enabled,
    false as totp_required,
    false as totp_enabled,
    null as totp_secret,
    null as recovery_email
from {users}
where lower(username) = lower(<dtml-sqlvar login type=string>)
limit 1"""
        fetch_roles_template = f"""select role
from {user_roles}
where lower(username) = lower(<dtml-sqlvar user_id type=string>)
order by role"""
        get_profile_template = f"""select
    username as user_id,
    firstname as first_name,
    lastname as last_name,
    concat(firstname, ' ', lastname) as display_name,
    null as email,
    null as mobile
from {users}
where lower(username) = lower(<dtml-sqlvar user_id type=string>)
limit 1"""

    return {
        "fetch_user": {
            "id": "zsql_pas_fetch_user",
            "title": "Auth-only fetch existing SQL user by login",
            "arguments": "login",
            "template": fetch_user_template,
        },
        "fetch_roles": {
            "id": "zsql_pas_fetch_roles",
            "title": "Auth-only fetch existing SQL roles by user_id",
            "arguments": "user_id",
            "template": fetch_roles_template,
        },
        "get_profile": {
            "id": DEFAULT_PROFILE_GET_ID,
            "title": "Auth-only fetch existing SQL user profile",
            "arguments": "user_id",
            "template": get_profile_template,
        },
    }


def profile_postgresql_templates(tables=None):
    tables = tables or DEFAULT_TABLES
    profiles = tables["profiles"]
    return {
        "get_profile": {
            "id": DEFAULT_PROFILE_GET_ID,
            "title": "Editable SQL user profile fetch",
            "arguments": "user_id",
            "template": f"""select
    user_id,
    first_name,
    last_name,
    display_name,
    email,
    mobile
from {profiles}
where user_id = <dtml-sqlvar user_id type=string>
limit 1""",
        },
        "save_profile": {
            "id": DEFAULT_PROFILE_SAVE_ID,
            "title": "Editable SQL user profile save",
            "arguments": "user_id first_name last_name display_name email mobile",
            "template": f"""insert into {profiles}
    (user_id, first_name, last_name, display_name, email, mobile)
values
    (
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
    updated_at = current_timestamp""",
        },
    }


AUTHENTICATE_SCRIPT = """login = credentials.get('login')
password = credentials.get('password')
if not login or not password:
    return None

try:
    users = context.zsql_pas_fetch_user(login=login)
except Exception:
    return None

for user in users:
    if user.login_name != login:
        continue
    password_hash_id = getattr(user, 'password_hash_id', '') or 'plain'
    if password_hash_id == 'plain':
        if user.password != password:
            return None
    else:
        try:
            from AuthEncoding import pw_validate
            if not pw_validate(user.password, password):
                return None
        except Exception:
            return None
    totp_enabled = getattr(user, 'totp_enabled', False)
    if str(totp_enabled).lower() not in ('', '0', 'false', 'none'):
        try:
            request = getattr(container, 'REQUEST', None)
            if request is None:
                request = getattr(context, 'REQUEST', None)
            otp_code = ''
            if request is not None:
                otp_code = request.get('otp_code', '')
            is_form_login = (
                request is not None
                and getattr(request, 'form', {}).get('__ac_name', '')
            )
            if is_form_login or otp_code:
                from Products.SQLUserWizard.totp import verify_totp_code
                if not verify_totp_code(getattr(user, 'totp_secret', ''), otp_code):
                    return None
        except Exception:
            return None
    return (user.user_id, user.login_name)

return None
"""

ROLES_SCRIPT = """roles = []
user_id = principal.getId()

try:
    rows = context.zsql_pas_fetch_roles(user_id=user_id)
except Exception:
    return ()

for row in rows:
    roles.append(row.role)

return tuple(roles)
"""
